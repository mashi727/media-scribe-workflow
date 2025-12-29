"""
main_workspace.py - メインワークスペース

単一画面構成のメインUI。
- ソース情報表示
- 波形表示
- チャプターテーブル
- 書出設定・実行
- ログパネル
"""

from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QSplitter, QProgressBar, QComboBox, QLineEdit, QGroupBox,
    QSizePolicy, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal

from .log_panel import LogPanel, LogLevel
from .dialogs import SourceSelectionDialog, CoverImageDialog, SourceFile


@dataclass
class Chapter:
    """チャプター情報"""
    time_ms: int
    title: str
    is_excluded: bool = False  # --プレフィックスで除外

    @property
    def time_str(self) -> str:
        """HH:MM:SS.mmm形式"""
        total_sec = self.time_ms // 1000
        ms = self.time_ms % 1000
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}.{ms:03d}"


@dataclass
class ProjectState:
    """プロジェクト状態"""
    sources: List[SourceFile] = field(default_factory=list)
    cover_image_path: Optional[Path] = None
    chapters: List[Chapter] = field(default_factory=list)
    output_path: Optional[Path] = None


class MainWorkspace(QWidget):
    """
    メインワークスペース

    構成:
    ┌─────────────────────────────────────────────┐
    │ [ソース選択] [カバー画像]    ← ボタン行     │
    │ ソース: audio.mp3 (14:20)   ← 情報表示     │
    ├─────────────────────────────────────────────┤
    │ [波形表示]                  ← WaveformWidget │
    ├─────────────────────────────────────────────┤
    │ [チャプターテーブル]                        │
    ├─────────────────────────────────────────────┤
    │ [書出設定] [書出ボタン]                     │
    ├─────────────────────────────────────────────┤
    │ [ログパネル]                                │
    └─────────────────────────────────────────────┘
    """

    # シグナル
    export_requested = Signal()
    source_changed = Signal(list)  # List[SourceFile]
    chapter_changed = Signal(list)  # List[Chapter]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = ProjectState()
        self._log_panel: Optional[LogPanel] = None
        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # === ヘッダー部（ソース・カバー選択）===
        header = self._create_header()
        layout.addWidget(header)

        # === メインコンテンツ（波形 + テーブル）===
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 波形プレースホルダー
        self._waveform_placeholder = self._create_waveform_placeholder()
        splitter.addWidget(self._waveform_placeholder)

        # チャプターテーブル
        self._chapter_table = self._create_chapter_table()
        splitter.addWidget(self._chapter_table)

        splitter.setSizes([200, 300])
        layout.addWidget(splitter, stretch=1)

        # === 書出設定 ===
        export_section = self._create_export_section()
        layout.addWidget(export_section)

        # === ログパネル ===
        self._log_panel = LogPanel()
        layout.addWidget(self._log_panel)

        # 初期ログ
        self._log_panel.info("Workspace initialized", source="UI")

    def _create_header(self) -> QWidget:
        """ヘッダー部（ソース・カバー選択）"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)

        # ソース選択ボタン
        self._source_btn = QPushButton("Select Source")
        self._source_btn.setStyleSheet(self._button_style())
        self._source_btn.clicked.connect(self._open_source_dialog)
        layout.addWidget(self._source_btn)

        # カバー画像ボタン
        self._cover_btn = QPushButton("Cover Image")
        self._cover_btn.setStyleSheet(self._button_style())
        self._cover_btn.clicked.connect(self._open_cover_dialog)
        layout.addWidget(self._cover_btn)

        layout.addSpacing(20)

        # ソース情報表示
        self._source_info = QLabel("No source selected")
        self._source_info.setStyleSheet("color: #a0a0a0;")
        layout.addWidget(self._source_info)

        layout.addStretch()

        # カバー情報表示
        self._cover_info = QLabel("")
        self._cover_info.setStyleSheet("color: #666666;")
        layout.addWidget(self._cover_info)

        return frame

    def _create_waveform_placeholder(self) -> QWidget:
        """波形表示プレースホルダー"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #0f0f0f;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)
        frame.setMinimumHeight(150)

        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel("Waveform Display")
        label.setStyleSheet("color: #666666; font-size: 14px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        hint = QLabel("(Select source to show waveform)")
        hint.setStyleSheet("color: #444444;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        return frame

    def _create_chapter_table(self) -> QWidget:
        """チャプターテーブル"""
        group = QGroupBox("Chapters")
        group.setStyleSheet("""
            QGroupBox {
                color: #f0f0f0;
                font-weight: bold;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
        """)

        layout = QVBoxLayout(group)

        # テーブル
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Time", "Title", ""])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 100)
        self._table.setColumnWidth(2, 60)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setStyleSheet("""
            QTableWidget {
                background: #0f0f0f;
                color: #f0f0f0;
                border: none;
                gridline-color: #2d2d2d;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background: #3b82f6;
            }
            QHeaderView::section {
                background: #1a1a1a;
                color: #a0a0a0;
                border: none;
                padding: 8px;
            }
        """)
        layout.addWidget(self._table)

        # ボタン行
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("Add")
        add_btn.setStyleSheet(self._button_style())
        add_btn.clicked.connect(self._add_chapter)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setStyleSheet(self._button_style())
        remove_btn.clicked.connect(self._remove_chapter)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        copy_btn = QPushButton("Copy YouTube")
        copy_btn.setStyleSheet(self._button_style())
        copy_btn.clicked.connect(self._copy_youtube_chapters)
        btn_layout.addWidget(copy_btn)

        layout.addLayout(btn_layout)

        return group

    def _create_export_section(self) -> QWidget:
        """書出設定セクション"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)

        # 出力先
        layout.addWidget(QLabel("Output:"))
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("output.mp4")
        self._output_edit.setStyleSheet("""
            QLineEdit {
                background: #0f0f0f;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        layout.addWidget(self._output_edit, stretch=1)

        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(40)
        browse_btn.setStyleSheet(self._button_style())
        layout.addWidget(browse_btn)

        layout.addSpacing(20)

        # 品質設定
        layout.addWidget(QLabel("Quality:"))
        self._quality_combo = QComboBox()
        self._quality_combo.addItems(["High (CRF 18)", "Medium (CRF 23)", "Low (CRF 28)"])
        self._quality_combo.setCurrentIndex(1)
        self._quality_combo.setStyleSheet("""
            QComboBox {
                background: #2d2d2d;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 6px;
                min-width: 120px;
            }
        """)
        layout.addWidget(self._quality_combo)

        layout.addSpacing(20)

        # プログレスバー
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar {
                background: #0f0f0f;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #3b82f6;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self._progress, stretch=1)

        # 書出ボタン
        self._export_btn = QPushButton("Export")
        self._export_btn.setStyleSheet(self._button_style(primary=True))
        self._export_btn.clicked.connect(self._start_export)
        layout.addWidget(self._export_btn)

        return frame

    def _button_style(self, primary: bool = False) -> str:
        """ボタンスタイル"""
        if primary:
            return """
                QPushButton {
                    background: #3b82f6;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #2563eb;
                }
                QPushButton:disabled {
                    background: #1e3a5f;
                    color: #666666;
                }
            """
        return """
            QPushButton {
                background: #2d2d2d;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #363636;
            }
        """

    # === ダイアログ操作 ===

    def _open_source_dialog(self):
        """ソース選択ダイアログを開く"""
        dialog = SourceSelectionDialog(self, self._state.sources)
        if dialog.exec():
            self._state.sources = dialog.get_sources()
            self._update_source_info()
            self._log_panel.info(
                f"Sources updated: {len(self._state.sources)} files",
                source="UI"
            )
            self.source_changed.emit(self._state.sources)

    def _open_cover_dialog(self):
        """カバー画像ダイアログを開く"""
        dialog = CoverImageDialog(self)
        if dialog.exec():
            image = dialog.get_image()
            if image:
                self._cover_info.setText("Cover: 1920x1080")
                self._log_panel.info("Cover image set", source="UI")

    def _update_source_info(self):
        """ソース情報表示を更新"""
        if not self._state.sources:
            self._source_info.setText("No source selected")
            return

        if len(self._state.sources) == 1:
            src = self._state.sources[0]
            self._source_info.setText(f"{src.path.name}")
        else:
            self._source_info.setText(f"{len(self._state.sources)} files")

    # === チャプター操作 ===

    def _add_chapter(self):
        """チャプター追加"""
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem("0:00:00.000"))
        self._table.setItem(row, 1, QTableWidgetItem("New Chapter"))

        del_btn = QPushButton("Del")
        del_btn.setStyleSheet("""
            QPushButton {
                background: #ef4444;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
            }
        """)
        del_btn.clicked.connect(lambda: self._remove_row(row))
        self._table.setCellWidget(row, 2, del_btn)

        self._log_panel.debug(f"Chapter added at row {row}", source="UI")

    def _remove_chapter(self):
        """選択チャプター削除"""
        rows = set(item.row() for item in self._table.selectedItems())
        for row in sorted(rows, reverse=True):
            self._table.removeRow(row)
        self._log_panel.debug(f"Removed {len(rows)} chapters", source="UI")

    def _remove_row(self, row: int):
        """指定行削除"""
        self._table.removeRow(row)

    def _copy_youtube_chapters(self):
        """YouTubeチャプター形式でコピー"""
        # TODO: 実装
        self._log_panel.info("Copied chapters to clipboard", source="UI")

    # === エクスポート ===

    def _start_export(self):
        """エクスポート開始"""
        self._log_panel.info("Export started", source="ffmpeg")
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._export_btn.setEnabled(False)

        # TODO: 実際のエクスポート処理
        self.export_requested.emit()

    # === 公開API ===

    def get_log_panel(self) -> LogPanel:
        """ログパネルを取得"""
        return self._log_panel

    def get_state(self) -> ProjectState:
        """プロジェクト状態を取得"""
        return self._state
