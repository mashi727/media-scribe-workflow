"""
Report Generator

SRTファイルと設定から LaTeX レポートを生成する。
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import ConfigLoader
from .srt_parser import SRTParser, Subtitle, format_subtitles_as_text


@dataclass
class ReportMetadata:
    """レポートメタデータ"""

    date: str = ""
    instructor: str = ""
    instructor_title: str = ""
    instrument: str = ""
    lesson_topic: str = ""
    student_level: str = ""
    repertoire: str = ""
    author_name: str = ""
    author_affiliation: str = ""

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ReportMetadata":
        """設定からメタデータを生成"""
        metadata = config.get("metadata", {})
        author = config.get("author", {})
        return cls(
            date=metadata.get("date", ""),
            instructor=metadata.get("instructor", ""),
            instructor_title=metadata.get("instructor_title", ""),
            instrument=metadata.get("instrument", ""),
            lesson_topic=metadata.get("lesson_topic", ""),
            student_level=metadata.get("student_level", ""),
            repertoire=metadata.get("repertoire", ""),
            author_name=author.get("name", ""),
            author_affiliation=author.get("affiliation", ""),
        )


@dataclass
class ReportGenerator:
    """LaTeX レポートジェネレーター"""

    config_loader: ConfigLoader = field(default_factory=ConfigLoader)
    srt_parser: SRTParser = field(default_factory=SRTParser)

    def generate(
        self,
        project_path: Path | str,
        srt_path: Path | str | None = None,
        output_path: Path | str | None = None,
    ) -> str:
        """
        レポートを生成

        Args:
            project_path: .vce.json プロジェクトファイルのパス
            srt_path: SRT ファイルのパス（指定しない場合は字幕なし）
            output_path: 出力ファイルのパス（指定しない場合は文字列を返す）

        Returns:
            生成された LaTeX 文字列
        """
        project_path = Path(project_path)

        # 設定を読み込み
        config = self.config_loader.get_merged_config(project_path)
        metadata = ReportMetadata.from_config(config)

        # 字幕を読み込み
        subtitles = []
        if srt_path:
            subtitles = self.srt_parser.parse(srt_path)

        # LaTeX を生成
        latex = self._generate_latex(config, metadata, subtitles)

        # 出力
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(latex)

        return latex

    def _generate_latex(
        self,
        config: dict[str, Any],
        metadata: ReportMetadata,
        subtitles: list[Subtitle],
    ) -> str:
        """LaTeX ドキュメントを生成"""
        parts = []

        # プリアンブル
        parts.append(self._generate_preamble(config, metadata))

        # ドキュメント開始
        parts.append("\\begin{document}")
        parts.append("\\thispagestyle{firstpage}")
        parts.append("")

        # タイトル
        parts.append(self._generate_title(config, metadata))

        # 目次（設定に応じて）
        if config.get("misc", {}).get("include_toc", True):
            parts.append("\\tableofcontents")
            parts.append("\\newpage")
            parts.append("")

        # セクション
        parts.append(self._generate_sections(config, metadata, subtitles))

        # 謝辞
        parts.append(self._generate_acknowledgments(config, metadata))

        # ドキュメント終了
        parts.append("\\end{document}")

        return "\n".join(parts)

    def _generate_preamble(
        self, config: dict[str, Any], metadata: ReportMetadata
    ) -> str:
        """プリアンブルを生成"""
        # luatex-settings.yaml から preamble テンプレートを取得
        latex_settings_path = config.get("latex", {}).get(
            "settings_file", "~/.config/msw/luatex-settings.yaml"
        )
        latex_settings_path = Path(latex_settings_path).expanduser()

        if latex_settings_path.exists():
            import yaml

            with open(latex_settings_path, "r", encoding="utf-8") as f:
                latex_settings = yaml.safe_load(f) or {}
            preamble = latex_settings.get("preamble", "")
        else:
            # フォールバック: 最小限のプリアンブル
            preamble = self._minimal_preamble()

        # 日時を置換
        now = datetime.now()
        preamble = preamble.replace(
            "\\newcommand{\\generatedDate}{YYYY-MM-DD}",
            f"\\newcommand{{\\generatedDate}}{{{now.strftime('%Y-%m-%d')}}}",
        )
        preamble = preamble.replace(
            "\\newcommand{\\generatedTime}{HH:MM}",
            f"\\newcommand{{\\generatedTime}}{{{now.strftime('%H:%M')}}}",
        )

        return preamble

    def _minimal_preamble(self) -> str:
        """最小限のプリアンブル"""
        return r"""\documentclass[a4paper,10pt,twocolumn]{ltjsarticle}
\usepackage{luatexja-fontspec}
\usepackage[margin=20mm]{geometry}
\usepackage{hyperref}
"""

    def _generate_title(
        self, config: dict[str, Any], metadata: ReportMetadata
    ) -> str:
        """タイトルブロックを生成"""
        lines = []

        # タイトル
        title = self._build_title(metadata)
        lines.append(f"\\title{{{title}}}")

        # 著者
        author = metadata.author_name
        if metadata.author_affiliation:
            author = f"{author}\\\\{metadata.author_affiliation}"
        lines.append(f"\\author{{{author}}}")

        # 日付（非表示設定の場合は空）
        if config.get("misc", {}).get("hide_title_date", True):
            lines.append("\\date{}")
        else:
            lines.append(f"\\date{{{metadata.date}}}")

        lines.append("")
        lines.append("\\maketitle")
        lines.append("")

        return "\n".join(lines)

    def _build_title(self, metadata: ReportMetadata) -> str:
        """タイトル文字列を構築"""
        parts = []

        if metadata.lesson_topic:
            parts.append(metadata.lesson_topic)
        if metadata.instrument:
            if parts:
                parts[0] = f"{metadata.instrument}レッスン: {parts[0]}"
            else:
                parts.append(f"{metadata.instrument}レッスン")

        if metadata.instructor:
            instructor_str = metadata.instructor
            if metadata.instructor_title:
                instructor_str = f"{instructor_str}（{metadata.instructor_title}）"
            parts.append(f"講師: {instructor_str}")

        if metadata.date:
            parts.append(metadata.date)

        return " --- ".join(parts) if parts else "レポート"

    def _generate_sections(
        self,
        config: dict[str, Any],
        metadata: ReportMetadata,
        subtitles: list[Subtitle],
    ) -> str:
        """セクションを生成"""
        lines = []
        report_config = config.get("report", {})
        sections = report_config.get("sections", report_config.get("common_sections", []))
        timestamp_config = config.get("timestamp", {})
        timestamp_format = timestamp_config.get("format", "[HH:MM:SS]")

        for section in sections:
            section_id = section.get("id", "")
            section_title = section.get("title", section_id.capitalize())

            # 謝辞セクションは後で別途生成するのでスキップ
            if section_id == "acknowledgments":
                continue

            lines.append(f"\\section{{{section_title}}}")
            lines.append("")

            # セクションIDに応じた内容生成
            if section_id == "overview":
                lines.append(self._generate_overview_content(metadata))
            elif section_id == "content":
                lines.append(self._generate_content_section(subtitles, timestamp_format))
            elif section_id == "summary":
                lines.append(self._generate_summary_placeholder())
            elif section_id == "terminology":
                lines.append(self._generate_terminology_placeholder())
            else:
                lines.append(f"% {section_id} セクション - 内容を追加してください")
                lines.append("")

            lines.append("")

        return "\n".join(lines)

    def _generate_overview_content(self, metadata: ReportMetadata) -> str:
        """概要セクションの内容"""
        lines = []
        lines.append("\\begin{itemize}")

        if metadata.date:
            lines.append(f"  \\item 日付: {metadata.date}")
        if metadata.instructor:
            instructor = metadata.instructor
            if metadata.instructor_title:
                instructor = f"{instructor}（{metadata.instructor_title}）"
            lines.append(f"  \\item 講師: {instructor}")
        if metadata.instrument:
            lines.append(f"  \\item 楽器: {metadata.instrument}")
        if metadata.lesson_topic:
            lines.append(f"  \\item テーマ: {metadata.lesson_topic}")
        if metadata.repertoire:
            lines.append(f"  \\item 曲目: {metadata.repertoire}")

        lines.append("\\end{itemize}")
        return "\n".join(lines)

    def _generate_content_section(
        self, subtitles: list[Subtitle], timestamp_format: str
    ) -> str:
        """本文セクション（字幕内容）"""
        if not subtitles:
            return "% 字幕データがありません\n\\textit{（字幕データを追加してください）}"

        lines = []
        for sub in subtitles:
            timestamp = sub.format_timestamp(timestamp_format)
            # LaTeX特殊文字をエスケープ
            text = self._escape_latex(sub.text)
            lines.append(f"\\texttt{{{timestamp}}} {text}")
            lines.append("")

        return "\n".join(lines)

    def _generate_summary_placeholder(self) -> str:
        """Summaryセクションのプレースホルダー"""
        return "% AI分析によるサマリーをここに追加\n\\textit{（サマリーを追加してください）}"

    def _generate_terminology_placeholder(self) -> str:
        """用語集セクションのプレースホルダー"""
        return "% 専門用語の解説をここに追加\n\\textit{（用語集を追加してください）}"

    def _generate_acknowledgments(
        self, config: dict[str, Any], metadata: ReportMetadata
    ) -> str:
        """謝辞セクション"""
        ack_config = config.get("report", {}).get("acknowledgments", {})
        if not ack_config.get("include_claude_code", True):
            return ""

        lines = []
        lines.append("\\section*{謝辞}")
        lines.append("")
        lines.append("本レポートは Claude Code を使用して生成されました。")
        lines.append("")

        return "\n".join(lines)

    def _escape_latex(self, text: str) -> str:
        """LaTeX特殊文字をエスケープ"""
        replacements = [
            ("\\", "\\textbackslash{}"),
            ("&", "\\&"),
            ("%", "\\%"),
            ("$", "\\$"),
            ("#", "\\#"),
            ("_", "\\_"),
            ("{", "\\{"),
            ("}", "\\}"),
            ("~", "\\textasciitilde{}"),
            ("^", "\\textasciicircum{}"),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        return text
