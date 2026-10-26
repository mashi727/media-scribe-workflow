"""文字起こし → 記録 JSON

構成段は差し替えられる（MSW_ANALYZER）。既定の "transcript" は AI を使わず、
区間（章）ごとに時刻付きの発言録を作る。外部へは何も送らず、費用もかからない。
内容は ASR の生結果そのままなので、要約による取りこぼしや捏造が起きない。

区間割りは章立て（chaptr の .txt）があれば章＝曲ごと、無ければ固定幅。
'--' 始まりの章は chaptr でカットとした区間（休憩・準備）なので出さない。

words.json（audio-transcribe の機械忠実層）があれば語ごとの確信度を読み、
低い語を印付きで出す（PDF 上で「どこが怪しいか」が分かる）。無ければ SRT を使う。

後でローカル LLM（Ollama 等）を足すときは Analyzer を実装して ANALYZERS に登録する。
REPORT_SCHEMA / SYSTEM_PROMPT / ground() はそのための界面として残してある
（LLM の出力は ground() で出典時刻を検証してから使う）。
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from media_scribe_workflow.pipeline.srt_parser import SRTParser

# bin/advanced/video-cut-chapters と同じ書式（'H:MM:SS.mmm タイトル'、'#' はコメント）
CHAPTER_LINE = re.compile(r"^\s*(\d+):(\d\d):(\d\d)[.,](\d{1,3})\s+(.*\S)\s*$")
TS = re.compile(r"^(\d{1,2}):([0-5]\d):([0-5]\d)$")
CUT_PREFIX = "--"
# 出典時刻の許容（その時刻の前後にこの秒数以内で発話があれば実在とみなす）
GROUND_TOLERANCE_S = 20


@dataclass
class Word:
    text: str
    probability: float


@dataclass
class Utterance:
    start_s: float
    end_s: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Segment:
    title: str
    start_s: float
    end_s: float


def hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_hms(text: str) -> float | None:
    m = TS.match(text.strip())
    if not m:
        return None
    h, mi, s = (int(x) for x in m.groups())
    return h * 3600 + mi * 60 + s


# --- 入力 ---------------------------------------------------------------

def load_utterances(srt_path: Path, words_path: Path | None = None) -> list[Utterance]:
    """words.json（stable-ts 形式）を優先し、無ければ SRT から読む"""
    if words_path and words_path.is_file():
        data = json.loads(words_path.read_text(encoding="utf-8"))
        out = []
        for s in data.get("segments", []):
            words = [Word(w.get("word", ""), float(w.get("probability", 1.0)))
                     for w in s.get("words") or []]
            out.append(Utterance(float(s["start"]), float(s["end"]),
                                 str(s.get("text", "")).strip(), words))
        return out
    return [Utterance(c.start_ms / 1000, c.end_ms / 1000, c.text.replace("\n", " ").strip())
            for c in SRTParser().parse(srt_path)]


def load_chapters(path: Path) -> list[tuple[float, str]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = CHAPTER_LINE.match(line)
        if not m:
            continue
        g = m.groups()
        t = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3].ljust(3, "0")) / 1000
        out.append((t, g[4]))
    return sorted(out)


def plan_segments(utts: list[Utterance], chapters: list[tuple[float, str]],
                  window_minutes: int) -> list[Segment]:
    end = max((u.end_s for u in utts), default=0)
    if chapters:
        segs = []
        for i, (t, title) in enumerate(chapters):
            nxt = chapters[i + 1][0] if i + 1 < len(chapters) else end
            if not title.startswith(CUT_PREFIX) and nxt > t:
                segs.append(Segment(title, t, nxt))
        return segs
    w = window_minutes * 60
    starts = [t for t in range(0, int(end) + 1, w) if t < end]
    return [Segment(f"区間 {i}", t, min(t + w, end)) for i, t in enumerate(starts, 1)]


def utterances_in(utts: list[Utterance], seg: Segment) -> list[Utterance]:
    return [u for u in utts if seg.start_s <= u.start_s < seg.end_s]


# --- 構成段 -------------------------------------------------------------

class Analyzer(Protocol):
    name: str

    def analyze_segment(self, meta: dict[str, Any], seg: Segment,
                        utts: list[Utterance]) -> dict[str, Any]: ...


class TranscriptAnalyzer:
    """AI を使わない発言録

    近い発話（間が gap_s 未満）を段落にまとめ、段落が max_s を超えたら切る。
    段落の頭に時刻を付ける（\\ts{} になり、tex-link-timestamps で動画へ飛べる）。
    """

    name = "transcript"

    def __init__(self, gap_s: float = 4.0, max_s: float = 60.0, low_conf: float = 0.4):
        self.gap_s = gap_s
        self.max_s = max_s
        self.low_conf = low_conf

    def runs(self, u: Utterance) -> list[dict[str, Any]]:
        """確信度の低い語を印付きの run に分ける（連続する同種はまとめる）"""
        if not u.words:
            return [{"text": u.text, "low": False}]
        out: list[dict[str, Any]] = []
        for w in u.words:
            low = w.probability < self.low_conf
            if out and out[-1]["low"] == low:
                out[-1]["text"] += w.text
            else:
                out.append({"text": w.text, "low": low})
        return out

    def analyze_segment(self, meta: dict[str, Any], seg: Segment,
                        utts: list[Utterance]) -> dict[str, Any]:
        paragraphs: list[dict[str, Any]] = []
        para_start = para_end = None
        for u in utts:
            if (para_start is None or u.start_s - para_end > self.gap_s
                    or u.end_s - para_start > self.max_s):
                paragraphs.append({"time": hms(u.start_s), "runs": []})
                para_start = u.start_s
            elif paragraphs[-1]["runs"]:
                paragraphs[-1]["runs"].append({"text": " ", "low": False})
            paragraphs[-1]["runs"].extend(self.runs(u))
            para_end = u.end_s
        low = sum(1 for p in paragraphs for r in p["runs"] if r["low"])
        return {"summary": "", "topics": [], "part_notes": [],
                "transcript": paragraphs, "low_confidence_runs": low}


ANALYZERS: dict[str, type] = {"transcript": TranscriptAnalyzer}


def make_analyzer(name: str) -> Analyzer:
    try:
        return ANALYZERS[name]()
    except KeyError:
        raise ValueError(f"未知の構成方式です: {name}（選べるもの: {', '.join(ANALYZERS)}）") from None


def analyze(srt_path: Path, chapters_path: Path | None, meta: dict[str, Any],
            analyzer: Analyzer, window_minutes: int, progress: Any = None,
            words_path: Path | None = None) -> dict[str, Any]:
    utts = load_utterances(srt_path, words_path)
    chapters = load_chapters(chapters_path) if chapters_path and chapters_path.exists() else []
    segments = plan_segments(utts, chapters, window_minutes)
    out = []
    for i, seg in enumerate(segments, 1):
        if progress:
            progress(f"構成 {i}/{len(segments)}: {seg.title}")
        su = utterances_in(utts, seg)
        if not su:
            continue
        result = analyzer.analyze_segment(meta, seg, su)
        if result.get("topics"):
            result = ground(result, seg, su)
        out.append({"title": seg.title, "start": hms(seg.start_s), "end": hms(seg.end_s),
                    **result})
    return {
        "meta": meta,
        "analyzer": analyzer.name,
        "chaptered": bool(chapters),
        "segments": out,
    }


# --- LLM 用の界面（ローカル LLM を足すとき用。今は未使用） ----------------------

SYSTEM_PROMPT = """\
あなたはオーケストラ・吹奏楽のリハーサル記録の書き手です。
入力は、リハーサル1区間ぶんの文字起こし（各行が [HH:MM:SS] で始まる）です。
この区間に参加できなかった団員が、何を直されたか・次に何を意識すべきかを
読んで分かる記録を、指定の JSON スキーマで返してください。

守ること:
- 文字起こしに書かれていることだけを記録する。推測で補った指示を作らない
- 各指示の time には、その発話が始まる行の時刻を HH:MM:SS でそのまま写す
- 指揮者の指示は意味を変えずに簡潔にまとめる。小節番号・練習記号・楽器名は原文どおり
- 演奏中で発話の無い時間帯は topics に含めない
- parts には対象パート（例: ホルン、木管、全員）を入れる。不明なら空配列
"""

REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string"},
                    "instructions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "time": {"type": "string"},
                                "text": {"type": "string"},
                                "parts": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["time", "text", "parts"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "start", "instructions"],
                "additionalProperties": False,
            },
        },
        "part_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "topics", "part_notes"],
    "additionalProperties": False,
}


def transcript_text(utts: list[Utterance]) -> str:
    """LLM に渡す形（[HH:MM:SS] 本文）"""
    return "\n".join(f"[{hms(u.start_s)}] {u.text}" for u in utts)


def ground(result: dict[str, Any], seg: Segment, utts: list[Utterance]) -> dict[str, Any]:
    """LLM が返した時刻が、その区間の実在する発話に対応するか確かめる"""
    starts = [u.start_s for u in utts]

    def ok(ts: str) -> bool:
        t = parse_hms(ts)
        if t is None or not (seg.start_s - 1 <= t <= seg.end_s + 1):
            return False
        return any(abs(t - s) <= GROUND_TOLERANCE_S for s in starts)

    for topic in result.get("topics", []):
        topic["verified"] = ok(topic.get("start", ""))
        for ins in topic.get("instructions", []):
            ins["verified"] = ok(ins.get("time", ""))
    return result
