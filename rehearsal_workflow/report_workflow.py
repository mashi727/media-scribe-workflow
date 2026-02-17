#!/usr/bin/env python3
"""
workflow_gui.py - 汎用ワークフローGUI

音声/動画コンテンツからの記録作成ワークフロー。
リハーサル記録、会議議事録、講義ノートに対応。

設計思想:
  - ゴールベースUI（やりたいことから選択）
  - セミオート対応（Web AI利用フロー）
  - 2画面構成（実行ログ + 出力）
  - プロンプトテンプレート表示

使用方法:
  python3 workflow_gui.py

作成日: 2024-12-25
バージョン: 2.0.0
"""

import sys
import os
import subprocess
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List
from datetime import datetime
from enum import Enum

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox, QFileDialog,
    QComboBox, QCheckBox, QProgressBar, QTabWidget, QScrollArea,
    QMessageBox, QSplitter, QFrame, QPlainTextEdit, QButtonGroup,
    QRadioButton, QStackedWidget
)
from PySide6.QtCore import Qt, QProcess, QTimer, Signal, Slot, QDir, QSortFilterProxyModel
import re
from PySide6.QtGui import QFont, QColor, QPalette, QClipboard


# ==============================================================================
# ファイルフィルタ用プロキシモデル
# ==============================================================================

class FileFilterProxyModel(QSortFilterProxyModel):
    """ファイル拡張子でフィルタリングするプロキシモデル"""

    def __init__(self, extensions=None, parent=None):
        super().__init__(parent)
        self.extensions = extensions or []

    def set_extensions(self, extensions):
        self.extensions = extensions
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        file_path = model.filePath(index)

        # ディレクトリは常に表示
        if model.isDir(index):
            return True

        # 拡張子がない場合は全て表示
        if not self.extensions:
            return True

        # 拡張子チェック
        suffix = Path(file_path).suffix.lower()
        return suffix in self.extensions


def parse_filter_extensions(filter_str: str) -> list:
    """フィルタ文字列から拡張子リストを抽出"""
    match = re.search(r'\(([^)]+)\)', filter_str)
    if match:
        patterns = match.group(1).split()
        return [p.replace('*', '') for p in patterns]
    return []


# ==============================================================================
# 定数・設定
# ==============================================================================

CONFIG_DIR = Path.home() / ".config" / "rehearsal-workflow"
PROMPTS_DIR = Path(__file__).parent.parent / "examples" / "prompts"

# ゴール定義（ラベルマッピング）
GOAL_CONFIGS = {
    "rehearsal": {
        "name": "リハーサル記録",
        "icon": "🎼",
        "labels": {
            "title": "曲目",
            "title_with_chapters": "合奏の目的",
            "datetime": "練習日",
            "key_person": "指揮者",
            "organization": "団体名",
            "consumer": "利用者",
        },
        "defaults": {
            "organization": "",
            "consumer": "団員",
        },
        "prompt_file": "rehearsal.md",
    },
    "meeting": {
        "name": "会議議事録",
        "icon": "📋",
        "labels": {
            "title": "議題",
            "datetime": "開催日時",
            "key_person": "議長/進行",
            "organization": "会議体",
            "consumer": "利用者",
        },
        "defaults": {
            "organization": "",
            "consumer": "参加者",
        },
        "prompt_file": "meeting.md",
    },
    "lecture": {
        "name": "講義ノート",
        "icon": "📚",
        "labels": {
            "title": "講義名",
            "datetime": "開催日",
            "key_person": "講師",
            "organization": "主催/場所",
            "consumer": "利用者",
        },
        "defaults": {
            "organization": "",
            "consumer": "受講者",
        },
        "prompt_file": "lecture.md",
    },
    "other": {
        "name": "その他",
        "icon": "🎬",
        "labels": {
            "title": "内容",
            "title_with_chapters": "目的",
            "datetime": "日付",
            "key_person": "キーパーソン",
            "organization": "制作元/場所",
            "consumer": "利用者",
        },
        "defaults": {
            "organization": "",
            "consumer": "",
        },
        "prompt_file": "other.md",
    },
}


# ==============================================================================
# データモデル
# ==============================================================================

@dataclass
class WorkflowMetadata:
    """ワークフローメタデータ（共通構造）"""
    # ゴール種別
    goal_type: str = "rehearsal"

    # 共通メタデータ（動的ラベル）
    title: str = ""           # 曲目/議題/講義名
    datetime_str: str = ""    # 日時
    key_person: str = ""      # 指揮者/議長/講師
    organization: str = ""    # 団体/会議体/主催
    consumer: str = ""        # 利用者

    # 入力ソース
    source_type: str = "youtube"  # youtube, local, audio
    source_path: str = ""         # URL or ファイルパス

    # 生成ファイル
    transcript_text: str = ""     # 文字起こし結果
    chapters_text: str = ""       # チャプター情報

    def get_label(self, field: str) -> str:
        """フィールドのラベルを取得"""
        config = GOAL_CONFIGS.get(self.goal_type, GOAL_CONFIGS["rehearsal"])
        return config["labels"].get(field, field)


# ==============================================================================
# プロンプトテンプレート
# ==============================================================================

DEFAULT_PROMPTS = {
    "rehearsal": """# リハーサル記録作成プロンプト

以下はオーケストラのリハーサル録音の文字起こしです。

## 基本情報
- {{title_label}}: {{title}}
- {{datetime_label}}: {{datetime}}
- {{key_person_label}}: {{key_person}}
- {{organization_label}}: {{organization}}

## 依頼内容
指揮者の指示を中心に、以下の観点で要約してください：

1. **テンポ・ダイナミクス**に関する指示
2. **アーティキュレーション**（音の切り方、つなげ方）
3. **バランス**（パート間の音量調整）
4. **音楽的解釈**（表現、フレージング）
5. **技術的注意点**（運指、運弓等）

各指示について、該当する小節番号や練習番号があれば記載してください。

---
## 文字起こし

{{transcript}}
""",

    "meeting": """# 会議議事録作成プロンプト

以下は会議の録音文字起こしです。

## 基本情報
- {{title_label}}: {{title}}
- {{datetime_label}}: {{datetime}}
- {{key_person_label}}: {{key_person}}
- {{organization_label}}: {{organization}}

## 依頼内容
以下の形式で議事録を作成してください：

1. **決定事項**: 会議で決まったこと
2. **継続検討事項**: 結論が出ず、次回以降に持ち越す事項
3. **アクションアイテム**: 誰が・何を・いつまでに
4. **次回予定**: 次回の日程、議題

発言者が特定できる場合は、発言者名を記載してください。

---
## 文字起こし

{{transcript}}
""",

    "lecture": """# 講義ノート作成プロンプト

以下は講義の録音文字起こしです。

## 基本情報
- {{title_label}}: {{title}}
- {{datetime_label}}: {{datetime}}
- {{key_person_label}}: {{key_person}}
- {{organization_label}}: {{organization}}

## 依頼内容
以下の観点で講義内容を整理してください：

1. **主要トピック**: 講義で扱われた主題
2. **重要概念**: キーワードとその説明
3. **具体例・事例**: 講師が挙げた例
4. **質疑応答**: あれば要約
5. **参考文献・資料**: 言及されたもの

学習者が復習しやすい形式で記述してください。

---
## 文字起こし

{{transcript}}
""",

    "other": """# 動画/音声コンテンツ要約プロンプト

以下は動画/音声コンテンツの文字起こしです。

## 基本情報
- {{title_label}}: {{title}}
- {{datetime_label}}: {{datetime}}
- {{key_person_label}}: {{key_person}}
- {{organization_label}}: {{organization}}

## 依頼内容
以下の観点でコンテンツを要約してください：

1. **主題**: このコンテンツの主な内容
2. **重要ポイント**: 特に重要な情報や発言
3. **時系列**: 主な出来事の流れ
4. **結論・まとめ**: 最終的な結論や要点

---
## 文字起こし

{{transcript}}
""",
}


def load_prompt_template(goal_type: str) -> str:
    """プロンプトテンプレートを読み込み"""
    config = GOAL_CONFIGS.get(goal_type, GOAL_CONFIGS["rehearsal"])
    prompt_file = PROMPTS_DIR / config["prompt_file"]

    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    else:
        return DEFAULT_PROMPTS.get(goal_type, DEFAULT_PROMPTS["rehearsal"])


def render_prompt(template: str, metadata: WorkflowMetadata, transcript: str,
                  has_chapters: bool = False) -> str:
    """プロンプトテンプレートを変数展開"""
    config = GOAL_CONFIGS.get(metadata.goal_type, GOAL_CONFIGS["rehearsal"])
    labels = config["labels"]

    # タイトルラベルはチャプター有無で切り替え
    if has_chapters and "title_with_chapters" in labels:
        title_label = labels["title_with_chapters"]
    else:
        title_label = labels["title"]

    result = template
    # ラベルも動的に置換
    result = result.replace("{{title_label}}", title_label)
    result = result.replace("{{datetime_label}}", labels.get("datetime", "日時"))
    result = result.replace("{{key_person_label}}", labels.get("key_person", "キーパーソン"))
    result = result.replace("{{organization_label}}", labels.get("organization", "組織"))
    result = result.replace("{{consumer_label}}", labels.get("consumer", "利用者"))
    # 値を置換
    result = result.replace("{{title}}", metadata.title)
    result = result.replace("{{datetime}}", metadata.datetime_str)
    result = result.replace("{{key_person}}", metadata.key_person)
    result = result.replace("{{organization}}", metadata.organization)
    result = result.replace("{{consumer}}", metadata.consumer)
    result = result.replace("{{transcript}}", transcript)
    return result


# ==============================================================================
# UI コンポーネント
# ==============================================================================

class GoalSelector(QWidget):
    """ゴール選択ウィジェット"""
    goal_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_goal = "rehearsal"
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.button_group = QButtonGroup(self)
        self.buttons = {}

        for goal_id, config in GOAL_CONFIGS.items():
            btn = QPushButton(f"{config['icon']} {config['name']}")
            btn.setCheckable(True)
            btn.setFont(QFont("", 18))
            btn.setMinimumHeight(60)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 12px 24px;
                    border: 2px solid #555;
                    border-radius: 8px;
                    background-color: #2d2d2d;
                    font-size: 18pt;
                }
                QPushButton:checked {
                    background-color: #0d47a1;
                    border-color: #2196F3;
                }
                QPushButton:hover {
                    background-color: #3d3d3d;
                }
            """)

            if goal_id == "rehearsal":
                btn.setChecked(True)

            btn.clicked.connect(lambda checked, g=goal_id: self.on_goal_selected(g))
            self.button_group.addButton(btn)
            self.buttons[goal_id] = btn
            layout.addWidget(btn)

    def on_goal_selected(self, goal_id: str):
        self.current_goal = goal_id
        self.goal_changed.emit(goal_id)


class MetadataForm(QWidget):
    """動的ラベル付きメタデータフォーム"""
    metadata_changed = Signal()  # メタデータ変更時に発火

    def __init__(self, metadata: WorkflowMetadata, parent=None):
        super().__init__(parent)
        self.metadata = metadata
        self.labels = {}
        self.inputs = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        font = QFont("", 18)

        # 各フィールド
        fields = ["title", "datetime", "key_person", "organization", "consumer"]

        for field in fields:
            row = QHBoxLayout()

            label = QLabel()
            label.setFont(font)
            label.setMinimumWidth(120)
            self.labels[field] = label
            row.addWidget(label)

            input_field = QLineEdit()
            input_field.setFont(font)
            input_field.textChanged.connect(
                lambda text, f=field: self._on_field_changed(f, text)
            )
            self.inputs[field] = input_field
            row.addWidget(input_field)

            layout.addLayout(row)

        self.update_labels()

    def update_labels(self, has_chapters: bool = False):
        """ゴールに応じてラベルを更新"""
        config = GOAL_CONFIGS.get(self.metadata.goal_type, GOAL_CONFIGS["rehearsal"])
        labels = config["labels"]

        for field, label_widget in self.labels.items():
            # titleフィールドはチャプター有無で切り替え
            if field == "title" and has_chapters and "title_with_chapters" in labels:
                label_widget.setText(labels["title_with_chapters"] + ":")
            else:
                label_widget.setText(labels.get(field, field) + ":")

        # デフォルト値を設定
        defaults = config.get("defaults", {})
        for field, value in defaults.items():
            if field in self.inputs and not self.inputs[field].text():
                self.inputs[field].setText(value)

    def set_goal(self, goal_type: str):
        """ゴール変更時"""
        self.metadata.goal_type = goal_type
        self.update_labels()

    def set_has_chapters(self, has_chapters: bool):
        """チャプター有無でラベル切替"""
        self.update_labels(has_chapters)

    def _on_field_changed(self, field: str, text: str):
        """フィールド変更時"""
        attr_name = "datetime_str" if field == "datetime" else field
        setattr(self.metadata, attr_name, text)
        self.metadata_changed.emit()


class SourceInput(QWidget):
    """入力ソース指定ウィジェット"""
    source_selected = Signal(str, str)  # (type, path)
    chapters_changed = Signal(bool)  # チャプター有無が変わった
    directory_changed = Signal(str)  # カレントディレクトリ変更

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chapter_file_path = ""
        self.last_directory = str(Path.home())  # 最後に開いたディレクトリ
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        font = QFont("", 18)

        # URL入力
        url_layout = QHBoxLayout()
        url_label = QLabel("YouTube URL:")
        url_label.setFont(font)
        url_label.setMinimumWidth(140)
        url_layout.addWidget(url_label)

        self.url_input = QLineEdit()
        self.url_input.setFont(font)
        self.url_input.setPlaceholderText("https://youtu.be/VIDEO_ID")
        url_layout.addWidget(self.url_input)

        layout.addLayout(url_layout)

        # ファイル名入力
        filename_layout = QHBoxLayout()
        filename_label = QLabel("ファイル名:")
        filename_label.setFont(font)
        filename_label.setMinimumWidth(140)
        filename_layout.addWidget(filename_label)

        self.filename_input = QLineEdit()
        self.filename_input.setFont(font)
        self.filename_input.setPlaceholderText("保存ファイル名（拡張子なし）")
        filename_layout.addWidget(self.filename_input)

        layout.addLayout(filename_layout)

        # または区切り
        or_label = QLabel("── または ──")
        or_label.setFont(QFont("", 16))
        or_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        or_label.setStyleSheet("color: #888;")
        layout.addWidget(or_label)

        # 動画ファイル選択
        file_layout = QHBoxLayout()
        self.file_label = QLabel("動画ファイル未選択")
        self.file_label.setFont(font)
        file_layout.addWidget(self.file_label)

        file_btn = QPushButton("📂 選択")
        file_btn.setFont(font)
        file_btn.clicked.connect(self.select_file)
        file_layout.addWidget(file_btn)

        file_clear_btn = QPushButton("✕")
        file_clear_btn.setFont(font)
        file_clear_btn.setMaximumWidth(40)
        file_clear_btn.clicked.connect(self.clear_file)
        file_layout.addWidget(file_clear_btn)

        layout.addLayout(file_layout)

        # チャプターファイル選択（オプション）
        layout.addSpacing(10)
        chapter_header = QLabel("チャプター（任意）")
        chapter_header.setFont(QFont("", 16))
        chapter_header.setStyleSheet("color: #aaa;")
        layout.addWidget(chapter_header)

        chapter_layout = QHBoxLayout()
        self.chapter_label = QLabel("チャプター未選択")
        self.chapter_label.setFont(font)
        chapter_layout.addWidget(self.chapter_label)

        chapter_btn = QPushButton("📂 選択")
        chapter_btn.setFont(font)
        chapter_btn.clicked.connect(self.select_chapter)
        chapter_layout.addWidget(chapter_btn)

        clear_btn = QPushButton("✕")
        clear_btn.setFont(font)
        clear_btn.setMaximumWidth(40)
        clear_btn.clicked.connect(self.clear_chapter)
        chapter_layout.addWidget(clear_btn)

        layout.addLayout(chapter_layout)

        # 文字起こしオプション
        layout.addSpacing(10)
        options_header = QLabel("文字起こしオプション")
        options_header.setFont(QFont("", 16))
        options_header.setStyleSheet("color: #aaa;")
        layout.addWidget(options_header)

        # 文字起こし方法
        method_layout = QHBoxLayout()
        method_label = QLabel("文字起こし:")
        method_label.setFont(font)
        method_label.setMinimumWidth(140)
        method_layout.addWidget(method_label)

        self.method_combo = QComboBox()
        self.method_combo.setFont(font)
        self.method_combo.addItems(["YouTube字幕", "Whisper", "両方"])
        method_layout.addWidget(self.method_combo)

        layout.addLayout(method_layout)

        # 最終出力形式
        format_layout = QHBoxLayout()
        format_label = QLabel("最終出力:")
        format_label.setFont(font)
        format_label.setMinimumWidth(140)
        format_layout.addWidget(format_label)

        self.format_combo = QComboBox()
        self.format_combo.setFont(font)
        self.format_combo.addItems(["Markdown (.md)", "LaTeX (.tex)", "Word (.docx)"])
        format_layout.addWidget(self.format_combo)

        layout.addLayout(format_layout)

    def _open_file_dialog(self, title: str, filters: str) -> str:
        """ファイルダイアログを開く（ディレクトリ記憶、カレント変更）"""
        dialog = QFileDialog(self, title, self.last_directory)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        # フィルタ設定
        filter_list = [f.strip() for f in filters.split(";;")]
        dialog.setNameFilters(filter_list)

        # カスタムプロキシモデルでファイルフィルタリング
        proxy = FileFilterProxyModel()
        initial_exts = parse_filter_extensions(filter_list[0])
        proxy.set_extensions(initial_exts)
        dialog.setProxyModel(proxy)

        # フィルタ変更時に拡張子を更新
        def on_filter_changed(new_filter):
            exts = parse_filter_extensions(new_filter)
            proxy.set_extensions(exts)

        dialog.filterSelected.connect(on_filter_changed)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            files = dialog.selectedFiles()
            if files:
                file_path = files[0]
                new_dir = str(Path(file_path).parent)
                self.last_directory = new_dir
                # カレントディレクトリを変更
                os.chdir(new_dir)
                self.directory_changed.emit(new_dir)
                return file_path
        return ""

    def select_file(self):
        file_path = self._open_file_dialog(
            "動画/音声ファイルを選択",
            "メディア (*.mp4 *.mov *.avi *.mkv *.webm *.m4v *.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma);;"
            "動画 (*.mp4 *.mov *.avi *.mkv *.webm *.m4v);;"
            "音声 (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma)"
        )
        if file_path:
            self.file_label.setText(Path(file_path).name)
            self.url_input.clear()
            self.source_selected.emit("local", file_path)

    def clear_file(self):
        self.file_label.setText("動画ファイル未選択")
        self.source_selected.emit("", "")

    def select_chapter(self):
        file_path = self._open_file_dialog(
            "チャプターファイルを選択",
            "チャプター (*.txt *.chapters *.json)"
        )
        if file_path:
            self.chapter_file_path = file_path
            self.chapter_label.setText(Path(file_path).name)
            self.chapters_changed.emit(True)

    def clear_chapter(self):
        self.chapter_file_path = ""
        self.chapter_label.setText("チャプター未選択")
        self.chapters_changed.emit(False)

    def get_source(self) -> tuple:
        """(type, path) を返す"""
        if self.url_input.text():
            return ("youtube", self.url_input.text())
        elif self.file_label.text() != "動画ファイル未選択":
            return ("local", self.file_label.text())
        return ("", "")

    def get_chapter_file(self) -> str:
        """チャプターファイルパスを返す"""
        return self.chapter_file_path

    def has_chapters(self) -> bool:
        """チャプターが設定されているか"""
        return bool(self.chapter_file_path)

    def get_filename(self) -> str:
        """保存ファイル名を取得（拡張子なし）"""
        return self.filename_input.text().strip()

    def get_transcription_method(self) -> str:
        """文字起こし方法を取得（youtube / whisper / both）"""
        methods = ["youtube", "whisper", "both"]
        return methods[self.method_combo.currentIndex()]

    def get_output_format(self) -> str:
        """最終出力形式を取得（md / tex / docx）"""
        formats = ["md", "tex", "docx"]
        return formats[self.format_combo.currentIndex()]


class LogPanel(QTextEdit):
    """実行ログパネル"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Monaco", 16))
        self.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
                padding: 8px;
                font-size: 16pt;
            }
        """)

    def log(self, message: str, level: str = "info"):
        colors = {
            "info": "#4ec9b0",
            "warn": "#dcdcaa",
            "error": "#f48771",
            "step": "#569cd6",
            "success": "#6a9955",
        }
        color = colors.get(level, "#d4d4d4")
        prefix = f"[{level.upper()}]" if level != "info" else ""
        self.append(f'<span style="color: {color};">{prefix}</span> {message}')


class OutputPanel(QWidget):
    """出力パネル（コピー機能付き）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ヘッダー（タイトル + ボタン）
        header = QHBoxLayout()
        title = QLabel("出力")
        title.setFont(QFont("", 18, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()

        copy_btn = QPushButton("📋 コピー")
        copy_btn.setFont(QFont("", 16))
        copy_btn.clicked.connect(self.copy_to_clipboard)
        header.addWidget(copy_btn)

        save_btn = QPushButton("💾 保存")
        save_btn.setFont(QFont("", 16))
        save_btn.clicked.connect(self.save_to_file)
        header.addWidget(save_btn)

        layout.addLayout(header)

        # テキストエリア
        self.text_area = QPlainTextEdit()
        self.text_area.setFont(QFont("Monaco", 16))
        self.text_area.setStyleSheet("""
            QPlainTextEdit {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
                padding: 8px;
                font-size: 16pt;
            }
        """)
        layout.addWidget(self.text_area)

    def set_text(self, text: str):
        self.text_area.setPlainText(text)

    def get_text(self) -> str:
        return self.text_area.toPlainText()

    def copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_area.toPlainText())

    def save_to_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存先を選択",
            str(Path.cwd() / "output.txt"),
            "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            Path(file_path).write_text(self.text_area.toPlainText(), encoding="utf-8")


class PromptPanel(QWidget):
    """プロンプトテンプレート表示パネル"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ヘッダー
        header = QHBoxLayout()
        title = QLabel("プロンプト")
        title.setFont(QFont("", 18, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()

        copy_btn = QPushButton("📋 コピー")
        copy_btn.setFont(QFont("", 16))
        copy_btn.clicked.connect(self.copy_to_clipboard)
        header.addWidget(copy_btn)

        layout.addLayout(header)

        # テキストエリア
        self.text_area = QPlainTextEdit()
        self.text_area.setFont(QFont("Monaco", 16))
        self.text_area.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1a1a2e;
                color: #eee;
                border: 1px solid #3e3e3e;
                padding: 8px;
                font-size: 16pt;
            }
        """)
        self.text_area.setMinimumHeight(150)
        layout.addWidget(self.text_area)

    def set_prompt(self, text: str):
        self.text_area.setPlainText(text)

    def get_prompt(self) -> str:
        return self.text_area.toPlainText()

    def copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_area.toPlainText())


# ==============================================================================
# メインウィンドウ
# ==============================================================================

class WorkflowGUI(QMainWindow):
    """ワークフローGUIメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.metadata = WorkflowMetadata()
        self.process: Optional[QProcess] = None
        self.has_chapters = False  # チャプター有無の状態
        self.expected_srt_filename = ""  # 期待されるSRTファイル名
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Workflow GUI - 音声/動画コンテンツ記録作成")
        self.setGeometry(100, 100, 1600, 1000)

        # メインウィジェット
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # ゴール選択
        goal_group = QGroupBox("記録の種類を選択")
        goal_group.setFont(QFont("", 18))
        goal_layout = QVBoxLayout(goal_group)
        self.goal_selector = GoalSelector()
        self.goal_selector.goal_changed.connect(self.on_goal_changed)
        goal_layout.addWidget(self.goal_selector)
        main_layout.addWidget(goal_group)

        # 中央部分（左右分割）- ストレッチ2
        center_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左側：入力フォーム（固定幅）
        left_widget = QWidget()
        left_widget.setFixedWidth(450)
        left_layout = QVBoxLayout(left_widget)

        # メタデータフォーム
        form_group = QGroupBox("基本情報")
        form_group.setFont(QFont("", 18))
        form_layout = QVBoxLayout(form_group)
        self.metadata_form = MetadataForm(self.metadata)
        self.metadata_form.metadata_changed.connect(self.update_prompt_template)
        form_layout.addWidget(self.metadata_form)
        left_layout.addWidget(form_group)

        # 入力ソース
        source_group = QGroupBox("音声/動画ソース")
        source_group.setFont(QFont("", 18))
        source_layout = QVBoxLayout(source_group)
        self.source_input = SourceInput()
        self.source_input.chapters_changed.connect(self.on_chapters_changed)
        self.source_input.directory_changed.connect(self.on_directory_changed)
        source_layout.addWidget(self.source_input)
        left_layout.addWidget(source_group)

        # 実行ボタン
        btn_layout = QHBoxLayout()

        self.run_btn = QPushButton("▶️ 文字起こし開始")
        self.run_btn.setFont(QFont("", 18))
        self.run_btn.setMinimumHeight(60)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #388E3C;
                color: white;
                border-radius: 8px;
                padding: 12px 30px;
                font-size: 18pt;
            }
            QPushButton:hover {
                background-color: #4CAF50;
            }
            QPushButton:disabled {
                background-color: #555;
            }
        """)
        self.run_btn.clicked.connect(self.run_transcription)
        btn_layout.addWidget(self.run_btn)

        left_layout.addLayout(btn_layout)

        # 保存/読み込みボタン
        io_layout = QHBoxLayout()

        save_btn = QPushButton("💾 設定保存")
        save_btn.setFont(QFont("", 16))
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self.save_settings)
        io_layout.addWidget(save_btn)

        load_btn = QPushButton("📂 設定読込")
        load_btn.setFont(QFont("", 16))
        load_btn.setMinimumHeight(40)
        load_btn.clicked.connect(self.load_settings)
        io_layout.addWidget(load_btn)

        left_layout.addLayout(io_layout)
        left_layout.addStretch()

        center_splitter.addWidget(left_widget)

        # 右側：ログ + 出力（上下分割）
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # ログパネル
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_title = QLabel("実行ログ")
        log_title.setFont(QFont("", 18, QFont.Weight.Bold))
        log_layout.addWidget(log_title)
        self.log_panel = LogPanel()
        log_layout.addWidget(self.log_panel)
        right_splitter.addWidget(log_widget)

        # 出力パネル
        self.output_panel = OutputPanel()
        right_splitter.addWidget(self.output_panel)

        right_splitter.setSizes([250, 450])
        right_splitter.setStretchFactor(0, 1)  # ログ: 1
        right_splitter.setStretchFactor(1, 2)  # 出力: 2
        center_splitter.addWidget(right_splitter)

        # 左は固定幅なので、右側のみ伸縮
        center_splitter.setStretchFactor(0, 0)  # 左: 固定
        center_splitter.setStretchFactor(1, 1)  # 右: 伸縮
        main_layout.addWidget(center_splitter, stretch=2)

        # プロンプトパネル（下部）- ストレッチ1
        self.prompt_panel = PromptPanel()
        main_layout.addWidget(self.prompt_panel, stretch=1)

        # 初期プロンプト表示
        self.update_prompt_template()

        # 初期メッセージ
        self.log_panel.log("Workflow GUI 起動", "info")
        self.log_panel.log(f"カレントディレクトリ: {Path.cwd()}", "info")

    def on_goal_changed(self, goal_type: str):
        """ゴール変更時"""
        self.metadata.goal_type = goal_type
        self.metadata_form.set_goal(goal_type)
        # チャプター状態を維持してラベルを再適用
        self.metadata_form.set_has_chapters(self.has_chapters)
        self.update_prompt_template()

        config = GOAL_CONFIGS[goal_type]
        self.log_panel.log(f"ゴール変更: {config['icon']} {config['name']}", "step")

    def on_chapters_changed(self, has_chapters: bool):
        """チャプター有無変更時"""
        self.has_chapters = has_chapters
        self.metadata_form.set_has_chapters(has_chapters)
        self.update_prompt_template()  # プロンプトのラベルも更新
        if has_chapters:
            chapter_file = self.source_input.get_chapter_file()
            self.log_panel.log(f"チャプター設定: {Path(chapter_file).name}", "info")
        else:
            self.log_panel.log("チャプター解除", "info")

    def on_directory_changed(self, new_dir: str):
        """カレントディレクトリ変更時"""
        self.log_panel.log(f"作業ディレクトリ: {new_dir}", "step")

    def update_prompt_template(self):
        """プロンプトテンプレートを更新（メタデータを反映）"""
        template = load_prompt_template(self.metadata.goal_type)
        # 現在の出力パネルの内容を文字起こしとして使用
        transcript = self.output_panel.get_text() if hasattr(self, 'output_panel') else ""
        if not transcript:
            transcript = "（文字起こし結果がここに入ります）"
        # has_chaptersを取得（初期化前は属性がないためgetattr使用）
        has_chapters = getattr(self, 'has_chapters', False)
        rendered = render_prompt(template, self.metadata, transcript, has_chapters)
        self.prompt_panel.set_prompt(rendered)

    def run_transcription(self):
        """文字起こし実行"""
        source_type, source_path = self.source_input.get_source()
        method = self.source_input.get_transcription_method()
        output_format = self.source_input.get_output_format()

        if not source_path:
            QMessageBox.warning(self, "入力エラー", "YouTube URLまたはファイルを指定してください")
            return

        method_names = {"youtube": "YouTube字幕", "whisper": "Whisper", "both": "両方"}
        format_names = {"md": "Markdown", "tex": "LaTeX", "docx": "Word"}
        self.log_panel.log(f"文字起こし開始: {source_path}", "step")
        self.log_panel.log(f"方法: {method_names.get(method, method)}, 最終出力: {format_names.get(output_format, output_format)}", "info")
        self.run_btn.setEnabled(False)

        # 文字起こし方法に応じて処理
        if method == "youtube":
            if source_type == "youtube":
                self.run_youtube_transcription(source_path)
            else:
                self.log_panel.log("ローカルファイルはWhisperを選択してください", "warn")
                self.run_btn.setEnabled(True)
        elif method == "whisper":
            self.run_whisper_transcription(source_type, source_path)
        elif method == "both":
            self.run_both_transcription(source_type, source_path)

    def run_youtube_transcription(self, url: str):
        """YouTube文字起こし"""
        filename = self.source_input.get_filename()

        if not filename:
            QMessageBox.warning(self, "入力エラー", "ファイル名を入力してください")
            self.run_btn.setEnabled(True)
            return

        self.log_panel.log(f"YouTube字幕を取得中（ファイル名: {filename}）...", "info")
        self.expected_srt_filename = f"{filename}_yt.srt"

        # ytdl コマンド実行
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.handle_output)
        self.process.finished.connect(self.on_transcription_finished)

        script_dir = Path(__file__).parent.parent / "bin"
        cmd = f"{script_dir}/ytdl '{url}' -o '{filename}'"
        self.process.start("bash", ["-c", cmd])

    def run_whisper_transcription(self, source_type: str, source_path: str):
        """Whisper文字起こし"""
        filename = self.source_input.get_filename()

        if not filename:
            QMessageBox.warning(self, "入力エラー", "ファイル名を入力してください")
            self.run_btn.setEnabled(True)
            return

        self.expected_srt_filename = f"{filename}.srt"
        self.log_panel.log(f"Whisper文字起こし中（出力: {self.expected_srt_filename}）...", "info")

        # whisper-remote コマンド実行
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.handle_output)
        self.process.finished.connect(self.on_transcription_finished)

        # YouTubeの場合は先に動画をダウンロード
        if source_type == "youtube":
            script_dir = Path(__file__).parent.parent / "bin"
            cmd = f"{script_dir}/ytdl '{source_path}' -o '{filename}' --no-subs && whisper-remote '{filename}.mp4' -o srt -n '{filename}'"
        else:
            # ローカルファイルの場合
            cmd = f"whisper-remote '{source_path}' -o srt -n '{filename}'"

        self.process.start("bash", ["-c", cmd])

    def run_both_transcription(self, source_type: str, source_path: str):
        """YouTube字幕とWhisper両方で文字起こし"""
        filename = self.source_input.get_filename()

        if not filename:
            QMessageBox.warning(self, "入力エラー", "ファイル名を入力してください")
            self.run_btn.setEnabled(True)
            return

        if source_type != "youtube":
            self.log_panel.log("「両方」はYouTube URLのみ対応", "warn")
            self.run_btn.setEnabled(True)
            return

        self.expected_srt_filename = f"{filename}.srt"  # Whisperの出力を優先
        self.log_panel.log(f"YouTube字幕 + Whisper両方で文字起こし中...", "info")

        # YouTube字幕とWhisper両方実行
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.handle_output)
        self.process.finished.connect(self.on_transcription_finished)

        script_dir = Path(__file__).parent.parent / "bin"
        # YouTube字幕 → Whisper の順で実行
        cmd = f"{script_dir}/ytdl '{source_path}' -o '{filename}' && whisper-remote '{filename}.mp4' -o srt -n '{filename}'"
        self.process.start("bash", ["-c", cmd])

    def handle_output(self):
        """プロセス出力処理"""
        if self.process:
            output = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
            for line in output.strip().split('\n'):
                if line:
                    self.log_panel.log(line, "info")

    def on_transcription_finished(self, exit_code: int, exit_status):
        """文字起こし完了"""
        self.run_btn.setEnabled(True)

        if exit_code == 0:
            self.log_panel.log("文字起こし完了", "success")

            # 期待されるSRTファイルを探して読み込み
            srt_path = Path.cwd() / self.expected_srt_filename
            if srt_path.exists():
                transcript = srt_path.read_text(encoding="utf-8")
                self.output_panel.set_text(transcript)
                self.log_panel.log(f"字幕ファイル読み込み: {srt_path.name}", "info")

                # プロンプトを更新（文字起こし結果を埋め込み）
                self.update_prompt_template()

                self.log_panel.log("", "info")
                self.log_panel.log("📋 出力とプロンプトをコピーしてWeb AIに貼り付けてください", "step")
            else:
                # フォールバック: 最新のSRTファイルを探す
                srt_files = sorted(Path.cwd().glob("*.srt"), key=lambda p: p.stat().st_mtime, reverse=True)
                if srt_files:
                    transcript = srt_files[0].read_text(encoding="utf-8")
                    self.output_panel.set_text(transcript)
                    self.log_panel.log(f"字幕ファイル読み込み: {srt_files[0].name}", "info")
                    self.update_prompt_template()
                    self.log_panel.log("📋 出力とプロンプトをコピーしてWeb AIに貼り付けてください", "step")
                else:
                    self.log_panel.log("字幕ファイルが見つかりませんでした", "warn")
        else:
            self.log_panel.log(f"文字起こし失敗（終了コード: {exit_code}）", "error")

    def closeEvent(self, event):
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.terminate()
            self.process.waitForFinished(3000)
        event.accept()

    def get_current_settings(self) -> dict:
        """現在の設定を辞書として取得"""
        return {
            "goal_type": self.metadata.goal_type,
            "title": self.metadata.title,
            "datetime_str": self.metadata.datetime_str,
            "key_person": self.metadata.key_person,
            "organization": self.metadata.organization,
            "consumer": self.metadata.consumer,
            "source_path": self.source_input.file_label.text(),
            "chapter_file": self.source_input.get_chapter_file(),
            "has_chapters": self.has_chapters,
            "youtube_url": self.source_input.url_input.text(),
            "filename": self.source_input.get_filename(),
            "transcription_method": self.source_input.get_transcription_method(),
            "output_format": self.source_input.get_output_format(),
            "working_directory": str(Path.cwd()),
        }

    def apply_settings(self, settings: dict):
        """設定を適用"""
        # 作業ディレクトリ復元
        if settings.get("working_directory"):
            work_dir = Path(settings["working_directory"])
            if work_dir.exists():
                os.chdir(work_dir)
                self.source_input.last_directory = str(work_dir)
                self.log_panel.log(f"作業ディレクトリ: {work_dir}", "step")

        # ゴール設定
        goal_type = settings.get("goal_type", "rehearsal")
        if goal_type in self.goal_selector.buttons:
            self.goal_selector.buttons[goal_type].setChecked(True)
            self.goal_selector.on_goal_selected(goal_type)

        # メタデータ設定
        if "title" in settings:
            self.metadata_form.inputs["title"].setText(settings["title"])
        if "datetime_str" in settings:
            self.metadata_form.inputs["datetime"].setText(settings["datetime_str"])
        if "key_person" in settings:
            self.metadata_form.inputs["key_person"].setText(settings["key_person"])
        if "organization" in settings:
            self.metadata_form.inputs["organization"].setText(settings["organization"])
        if "consumer" in settings:
            self.metadata_form.inputs["consumer"].setText(settings["consumer"])

        # ソース設定
        if settings.get("youtube_url"):
            self.source_input.url_input.setText(settings["youtube_url"])
        if settings.get("filename"):
            self.source_input.filename_input.setText(settings["filename"])
        if settings.get("source_path") and settings["source_path"] != "動画ファイル未選択":
            self.source_input.file_label.setText(settings["source_path"])

        # 文字起こしオプション
        method = settings.get("transcription_method", "youtube")
        method_index = {"youtube": 0, "whisper": 1, "both": 2}.get(method, 0)
        self.source_input.method_combo.setCurrentIndex(method_index)
        output_format = settings.get("output_format", "md")
        format_index = {"md": 0, "tex": 1, "docx": 2}.get(output_format, 0)
        self.source_input.format_combo.setCurrentIndex(format_index)

        # チャプター設定
        if settings.get("chapter_file"):
            self.source_input.chapter_file_path = settings["chapter_file"]
            self.source_input.chapter_label.setText(Path(settings["chapter_file"]).name)
            self.has_chapters = True
            self.metadata_form.set_has_chapters(True)
        else:
            self.has_chapters = settings.get("has_chapters", False)
            self.metadata_form.set_has_chapters(self.has_chapters)

        self.update_prompt_template()

    def save_settings(self):
        """設定をJSONファイルに保存"""
        dialog = QFileDialog(self, "設定を保存", str(Path.cwd()))
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setNameFilter("JSON Files (*.json)")
        dialog.selectFile("workflow_settings.json")

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            files = dialog.selectedFiles()
            if files:
                file_path = files[0]
                # 拡張子がなければ追加
                if not file_path.endswith('.json'):
                    file_path += '.json'
                settings = self.get_current_settings()
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(settings, f, ensure_ascii=False, indent=2)
                    self.log_panel.log(f"設定を保存: {Path(file_path).name}", "success")
                except Exception as e:
                    self.log_panel.log(f"保存失敗: {e}", "error")

    def load_settings(self):
        """JSONファイルから設定を読み込み"""
        dialog = QFileDialog(self, "設定を読み込み", str(Path.cwd()))
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setNameFilters(["JSON Files (*.json)"])

        # カスタムプロキシモデルでJSONファイルのみ表示
        proxy = FileFilterProxyModel()
        proxy.set_extensions([".json"])
        dialog.setProxyModel(proxy)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            files = dialog.selectedFiles()
            if files:
                file_path = files[0]
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                    self.apply_settings(settings)
                    self.log_panel.log(f"設定を読み込み: {Path(file_path).name}", "success")
                except Exception as e:
                    self.log_panel.log(f"読み込み失敗: {e}", "error")


# ==============================================================================
# エントリーポイント
# ==============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # ダークテーマ
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(palette)

    window = WorkflowGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
