"""段階: normalize → transcribe → analyze → render

各段は出力ファイルがあれば飛ばす（冪等）。WSL が途中で落ちても、
ワーカーがジョブを取り直したときに終わった段からやり直さずに済む。

ジョブディレクトリ:
    input.bin          アップロードされた原本（完了後に削除、MSW_DELETE_INPUT=0 で残す）
    chapters.txt       章立て（任意）
    audio.flac         片ch・16kHz・可逆
    transcript.srt / transcript.words.json / transcript.meta.json   一次資料（audio-transcribe）
    report.json        構造化（Claude）
    report.tex / report.pdf
"""
from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import analysis, tex
from .config import Settings

Progress = Callable[[str], None]


class StageError(RuntimeError):
    pass


def _run(cmd: list[str], cwd: Path, timeout: float | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       check=False)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-15:]
        raise StageError(f"{Path(cmd[0]).name} が失敗しました:\n" + "\n".join(tail))


def normalize(d: Path, cfg: Settings) -> None:
    if (d / "audio.flac").exists():
        return
    # ステレオを足し合わせない: L/R の同期残差でコムフィルタが出るので先頭chだけを使う
    _run(["ffmpeg", "-nostdin", "-v", "error", "-i", "input.bin", "-vn",
          "-af", "pan=mono|c0=c0", "-ar", "16000", "-c:a", "flac", "audio.flac.part.flac"], d)
    (d / "audio.flac.part.flac").rename(d / "audio.flac")


def transcribe(d: Path, cfg: Settings) -> None:
    if (d / "transcript.srt").exists():
        return
    cmd = [str(cfg.repo_root / "bin" / "advanced" / "audio-transcribe"),
           "audio.flac", "-o", "transcript", "--force", *cfg.transcribe_args]
    if cfg.terms_file and Path(cfg.terms_file).is_file():
        cmd += ["--terms", cfg.terms_file]
    _run(cmd, d)


def analyze(d: Path, cfg: Settings, meta: dict[str, Any], progress: Progress,
            analyzer: analysis.Analyzer | None = None) -> None:
    if (d / "report.json").exists():
        return
    analyzer = analyzer or analysis.Analyzer(cfg.model, cfg.effort)
    report = analysis.analyze(d / "transcript.srt", d / "chapters.txt", meta, analyzer,
                              cfg.window_minutes, progress)
    tmp = d / "report.json.part"
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(d / "report.json")


def render(d: Path, cfg: Settings) -> None:
    report = json.loads((d / "report.json").read_text(encoding="utf-8"))
    (d / "report.tex").write_text(tex.render(report, cfg.tex_jfont), encoding="utf-8")
    build = d / "texbuild"
    shutil.rmtree(build, ignore_errors=True)
    build.mkdir()
    shutil.copy(d / "report.tex", build / "report.tex")
    # shell-escape を禁止し、作業ディレクトリの外へは書かせない
    _run([cfg.lualatex, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
          "report.tex"], build, timeout=cfg.tex_timeout)
    shutil.move(str(build / "report.pdf"), d / "report.pdf")
    shutil.rmtree(build, ignore_errors=True)


def run_all(d: Path, cfg: Settings, meta: dict[str, Any], progress: Progress) -> None:
    progress("音声を整えています")
    normalize(d, cfg)
    progress("文字起こし中（長い音声は時間がかかります）")
    transcribe(d, cfg)
    progress("記録を構成しています")
    analyze(d, cfg, meta, progress)
    progress("PDF を組版しています")
    render(d, cfg)
    if cfg.delete_input_after_done:
        for name in ("input.bin", "audio.flac"):
            (d / name).unlink(missing_ok=True)
