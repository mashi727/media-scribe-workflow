"""SRT → 構造化 JSON（Claude）

/rehearsal skill（claude/commands/rehearsal.md）の Web 版。対話で前提を尋ねる代わりに
フォームの値を受け取り、TeX ではなく JSON を返させる（TeX は tex.py が組む）。

区間ごとに1回呼ぶ。章立て（chaptr の .txt）があれば章＝曲ごと、無ければ固定幅。
1回の呼び出しが1区間の発話しか見ないので、曲をまたいだ帰属の取り違えが起きにくい
（ダッシュボード SOP の「\\section 構造から機械生成」と同じ理由）。

出力された時刻は SRT に照らして検証し、区間外・発話の無い時刻は verified=False にする。
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from media_scribe_workflow.pipeline.srt_parser import SRTParser, Subtitle

# bin/advanced/video-cut-chapters と同じ書式（'H:MM:SS.mmm タイトル'、'#' はコメント）
CHAPTER_LINE = re.compile(r"^\s*(\d+):(\d\d):(\d\d)[.,](\d{1,3})\s+(.*\S)\s*$")
TS = re.compile(r"^(\d{1,2}):([0-5]\d):([0-5]\d)$")
CUT_PREFIX = "--"
# 出典時刻の許容（その時刻の前後にこの秒数以内で発話の cue があれば実在とみなす）
GROUND_TOLERANCE_S = 20

SYSTEM_PROMPT = """\
あなたはオーケストラ・吹奏楽のリハーサル記録の書き手です。
入力は、リハーサル1区間ぶんの文字起こし（各行が [HH:MM:SS] で始まる）です。
この区間に参加できなかった団員が、何を直されたか・次に何を意識すべきかを
読んで分かる記録を、指定の JSON スキーマで返してください。

守ること:
- 文字起こしに書かれていることだけを記録する。推測で補った指示を作らない
- 各指示の time には、その発話が始まる行の時刻を HH:MM:SS でそのまま写す
- 指揮者の指示は意味を変えずに簡潔にまとめる。小節番号・練習記号・楽器名は原文どおり
- 誤認識と思われる語は、文脈から明らかな場合のみ直し、確信がなければ原文を残す
- 演奏中で発話の無い時間帯は topics に含めない
- parts には対象パート（例: ホルン、木管、全員）を入れる。不明なら空配列
- 依頼者の視点（パート）が指定されていれば、そのパートに関わる指示を漏らさない
"""

REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "この区間の要点（2〜4文）"},
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "練習箇所（例: 練習番号C〜D）"},
                    "start": {"type": "string", "description": "HH:MM:SS"},
                    "instructions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "time": {"type": "string", "description": "HH:MM:SS"},
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
        "part_notes": {
            "type": "array",
            "description": "依頼者の視点のパート向けの要点（指定が無ければ空）",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "topics", "part_notes"],
    "additionalProperties": False,
}


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


def plan_segments(cues: list[Subtitle], chapters: list[tuple[float, str]],
                  window_minutes: int) -> list[Segment]:
    end = max((c.end_ms for c in cues), default=0) / 1000
    if chapters:
        segs = []
        for i, (t, title) in enumerate(chapters):
            nxt = chapters[i + 1][0] if i + 1 < len(chapters) else end
            # '--' 始まりは chaptr でカットとした区間（休憩・準備）
            if not title.startswith(CUT_PREFIX) and nxt > t:
                segs.append(Segment(title, t, nxt))
        return segs
    w = window_minutes * 60
    starts = [t for t in range(0, int(end) + 1, w) if t < end]
    return [Segment(f"区間 {i}", t, min(t + w, end)) for i, t in enumerate(starts, 1)]


def cues_in(cues: list[Subtitle], seg: Segment) -> list[Subtitle]:
    return [c for c in cues if seg.start_s <= c.start_ms / 1000 < seg.end_s]


def transcript_text(cues: list[Subtitle]) -> str:
    return "\n".join(f"[{hms(c.start_ms / 1000)}] {c.text.replace(chr(10), ' ')}" for c in cues)


def ground(result: dict[str, Any], seg: Segment, cues: list[Subtitle]) -> dict[str, Any]:
    """モデルが返した時刻が、その区間の実在する発話に対応するか確かめる"""
    starts = [c.start_ms / 1000 for c in cues]

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


def job_context(meta: dict[str, Any]) -> str:
    rows = [
        ("日付", meta.get("date")), ("団体", meta.get("ensemble")),
        ("指揮者", meta.get("conductor")), ("曲目", "、".join(meta.get("pieces") or [])),
        ("本番", meta.get("concert")), ("記録者", meta.get("author")),
        ("視点（パート）", meta.get("viewpoint")),
    ]
    return "\n".join(f"{k}: {v}" for k, v in rows if v)


class Analyzer:
    def __init__(self, model: str, effort: str, client: Any = None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.effort = effort

    def analyze_segment(self, meta: dict[str, Any], seg: Segment,
                        cues: list[Subtitle]) -> dict[str, Any]:
        user = (
            f"## 前提情報\n{job_context(meta) or '（指定なし）'}\n\n"
            f"## 区間\n{seg.title}（{hms(seg.start_s)}〜{hms(seg.end_s)}）\n\n"
            f"## 文字起こし\n{transcript_text(cues)}"
        )
        # 長い入力なのでストリーミングで受ける。system は全区間で同一なのでキャッシュに載せる。
        # fallbacks="default": 安全分類器が断ったときにサーバ側で別モデルへ回す
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=32000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort,
                           "format": {"type": "json_schema", "schema": REPORT_SCHEMA}},
        ) as stream:
            message = stream.get_final_message()
        if message.stop_reason == "refusal":
            raise RuntimeError(f"区間「{seg.title}」の解析が拒否されました")
        if message.stop_reason == "max_tokens":
            raise RuntimeError(f"区間「{seg.title}」の出力が上限で切れました（区間を短くしてください）")
        text = next(b.text for b in message.content if b.type == "text")
        return json.loads(text)


def analyze(srt_path: Path, chapters_path: Path | None, meta: dict[str, Any],
            analyzer: Analyzer, window_minutes: int,
            progress: Any = None) -> dict[str, Any]:
    cues = SRTParser().parse(srt_path)
    chapters = load_chapters(chapters_path) if chapters_path and chapters_path.exists() else []
    segments = plan_segments(cues, chapters, window_minutes)
    out = []
    for i, seg in enumerate(segments, 1):
        if progress:
            progress(f"解析 {i}/{len(segments)}: {seg.title}")
        sc = cues_in(cues, seg)
        if not sc:
            continue
        result = ground(analyzer.analyze_segment(meta, seg, sc), seg, sc)
        out.append({"title": seg.title, "start": hms(seg.start_s), "end": hms(seg.end_s),
                    **result})
    return {
        "meta": meta,
        "model": analyzer.model,
        "chaptered": bool(chapters),
        "segments": out,
    }
