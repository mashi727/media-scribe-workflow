"""構造化 JSON → LuaLaTeX

LLM には TeX を書かせない。文字列はすべてここでエスケープしてから埋め込むので、
文字起こしやフォーム由来の \\input / \\write18 などは文字として出るだけになる。

下流との界面（変えないこと）:
    \\section{区間＝曲名}     … ダッシュボードの build_<slug>.py が曲別まとめを機械生成する単位
    \\ts{HH:MM:SS}            … tex-link-timestamps が定義だけ差し替えて YouTube リンクにする
    \\newcommand{\\ts}[1]{...} … 1行で書く（tex-link-timestamps の TS_DEF が行単位で探す）
"""
from __future__ import annotations

from typing import Any

from .analysis import parse_hms

_ESCAPES = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&",
    "#": r"\#", "%": r"\%", "_": r"\_", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}",
}


def esc(text: Any) -> str:
    s = "".join(_ESCAPES.get(ch, ch) for ch in str(text or ""))
    # 制御文字は落とす（改行は空白に）
    return "".join(max(ch, " ") for ch in s)


def ts(value: str) -> str:
    """検証済みの HH:MM:SS だけを \\ts{} にする（それ以外は文字として出す）"""
    return rf"\ts{{{value}}}" if parse_hms(value) is not None else esc(value)


PREAMBLE = r"""\documentclass[a4paper,10pt,twocolumn]{ltjsarticle}
\usepackage{luatexja-fontspec}
\setmainjfont{__JFONT__}
\usepackage[margin=18mm]{geometry}
\usepackage{xcolor}
\usepackage[hidelinks]{hyperref}
\definecolor{navy}{RGB}{20,40,80}
\newcommand{\ts}[1]{\texttt{\small [#1]}}
\newcommand{\unverified}{\textsuperscript{\textcolor{red!70!black}{\scriptsize 要確認}}}
\newcommand{\parts}[1]{\textcolor{navy}{\small〔#1〕}}
"""


def render(report: dict[str, Any], jfont: str = "Noto Serif CJK JP") -> str:
    meta = report.get("meta", {})
    title = meta.get("title") or "リハーサル記録"
    lines = [PREAMBLE.replace("__JFONT__", esc(jfont))]
    lines.append(rf"\title{{\textcolor{{navy}}{{{esc(title)}}}}}")
    lines.append(rf"\author{{{esc(meta.get('author') or '')}}}")
    lines.append(rf"\date{{{esc(meta.get('date') or '')}}}")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")

    lines.append(r"\section*{概要}")
    rows = [rf"\item[{label}] {esc(meta[key])}"
            for label, key in (("団体", "ensemble"), ("指揮者", "conductor"),
                               ("本番", "concert"), ("視点", "viewpoint")) if meta.get(key)]
    if meta.get("pieces"):
        rows.append(rf"\item[曲目] {esc('、'.join(meta['pieces']))}")
    if rows:  # 空の description は LaTeX のエラーになる
        lines += [r"\begin{description}", *rows, r"\end{description}"]
    lines.append(
        r"{\small 本記録は文字起こしから自動生成した下書きです。"
        r"\unverified\ の付いた時刻・指示は文字起こしと照合できなかったものです。"
        r"一次資料は音声・映像です。}")

    for seg in report.get("segments", []):
        lines.append(rf"\section{{{esc(seg['title'])} {ts(seg['start'])}〜{ts(seg['end'])}}}")
        if seg.get("summary"):
            lines.append(esc(seg["summary"]))
        for topic in seg.get("topics", []):
            mark = "" if topic.get("verified") else r"\unverified"
            lines.append(rf"\subsection{{{esc(topic['title'])} {ts(topic['start'])}{mark}}}")
            items = topic.get("instructions", [])
            if items:
                lines.append(r"\begin{itemize}")
                for ins in items:
                    parts = "・".join(ins.get("parts") or [])
                    mark = "" if ins.get("verified") else r"\unverified"
                    tail = rf" \parts{{{esc(parts)}}}" if parts else ""
                    lines.append(rf"\item {ts(ins['time'])}{mark} {esc(ins['text'])}{tail}")
                lines.append(r"\end{itemize}")
        if seg.get("part_notes"):
            lines.append(r"\subsection*{パート向けの要点}")
            lines.append(r"\begin{itemize}")
            lines.extend(rf"\item {esc(n)}" for n in seg["part_notes"])
            lines.append(r"\end{itemize}")

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"
