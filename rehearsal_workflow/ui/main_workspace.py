"""
main_workspace.py - メインワークスペース

単一画面構成のメインUI。
- ソース情報表示
- 波形表示（除外区間ハッチング表示対応）
- チャプターテーブル（YouTube形式コピー対応）
- 動画プレビュー
- 書出設定・実行（エンコーダ選択、チャプター埋込対応）
- ログパネル
"""

from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QSplitter, QComboBox, QLineEdit, QGroupBox,
    QSizePolicy, QAbstractItemView, QSlider, QFileDialog, QDialog,
    QCheckBox, QSpinBox, QApplication
)
from PySide6.QtCore import Qt, Signal, QUrl, QThread, QObject, QTimer, QEvent, QMimeData
from PySide6.QtGui import QFont, QFontDatabase, QPainter, QColor, QPen, QBrush
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

import platform
import re
import subprocess
import tempfile
import os

from .log_panel import LogPanel, LogLevel
from .dialogs import SourceSelectionDialog, CoverImageDialog
from .models import (
    ChapterInfo,
    ColorspaceInfo,
    SourceFile,
    ProjectState,
    detect_video_colorspace,
    detect_video_duration,
    detect_video_bitrate,
    detect_available_encoders,
)
from .workers import WaveformWorker, SpectrogramWorker, ExportWorker
from .widgets import WaveformWidget, CenteredFileDialog
from .ffmpeg_utils import get_ffmpeg_path, get_ffprobe_path, extract_chapters_with_ffmpeg, get_subprocess_kwargs


# ファイル拡張子定義
AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.wav', '.aac', '.flac'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}


class DropVideoFrame(QFrame):
    """
    ドラッグ＆ドロップ対応の動画プレビューフレーム

    対応:
    - 動画/音声ファイル: ドロップで読み込み
    - フォルダ: 作業ディレクトリとして設定
    """

    files_dropped = Signal(list)  # ファイルパスのリスト
    folder_dropped = Signal(str)  # フォルダパス

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drag_active = False

    def dragEnterEvent(self, event):
        """ドラッグ進入時: 有効なファイル/フォルダか確認"""
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            urls = mime_data.urls()
            if urls:
                # 少なくとも1つの有効なファイル/フォルダがあるか確認
                for url in urls:
                    if url.isLocalFile():
                        path = Path(url.toLocalFile())
                        if path.is_dir():
                            event.acceptProposedAction()
                            self._drag_active = True
                            self._update_drag_style(True)
                            return
                        ext = path.suffix.lower()
                        if ext in VIDEO_EXTENSIONS or ext in AUDIO_EXTENSIONS:
                            event.acceptProposedAction()
                            self._drag_active = True
                            self._update_drag_style(True)
                            return
        event.ignore()

    def dragLeaveEvent(self, event):
        """ドラッグ離脱時: スタイルを戻す"""
        self._drag_active = False
        self._update_drag_style(False)
        event.accept()

    def dropEvent(self, event):
        """ドロップ時: ファイル/フォルダを処理"""
        self._drag_active = False
        self._update_drag_style(False)

        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            event.ignore()
            return

        urls = mime_data.urls()
        files = []
        folder = None

        for url in urls:
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_dir():
                    # 最初のフォルダを作業ディレクトリとして使用
                    if folder is None:
                        folder = str(path)
                else:
                    ext = path.suffix.lower()
                    if ext in VIDEO_EXTENSIONS or ext in AUDIO_EXTENSIONS:
                        files.append(str(path))

        # フォルダが優先（フォルダがあればファイルは無視）
        if folder:
            self.folder_dropped.emit(folder)
        elif files:
            self.files_dropped.emit(files)

        event.acceptProposedAction()

    def _update_drag_style(self, active: bool):
        """ドラッグ中のスタイル更新"""
        if active:
            self.setStyleSheet("""
                QFrame {
                    background: #1a1a1a;
                    border: 2px solid #3b82f6;
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background: #1a1a1a;
                    border: 1px solid #3a3a3a;
                    border-radius: 8px;
                }
            """)


class MainWorkspace(QWidget):
    """
    メインワークスペース

    左側: 操作系（操作順に配置）
    右側: 表示系 + 再生コントロール

    構成:
    ┌─────────────────────────────┬───────────────────────────────┐
    │ 1. [ソース選択]             │                               │
    ├─────────────────────────────┤     動画プレビュー（最大化）  │
    │ 2. [チャプターテーブル]     │                               │
    │    [Add] [Remove] [Copy YT] ├───────────────────────────────┤
    ├─────────────────────────────┤     [波形表示]                │
    │ 3. [Cover] [Output] [Export]├───────────────────────────────┤
    ├─────────────────────────────┤ [Load][Play][Stop] [Vol]      │
    │ 4. [ログパネル]             │ [シークバー] 00:00/00:00      │
    └─────────────────────────────┴───────────────────────────────┘
    """

    # シグナル
    export_requested = Signal()
    export_progress = Signal(int, str)  # (percent, status) エクスポート進捗
    export_finished = Signal(bool, str)  # (success, message) エクスポート完了
    source_changed = Signal(list)  # List[SourceFile]
    chapter_changed = Signal(list)  # List[Chapter]

    # プラットフォーム別等幅フォント
    MONO_FONTS = {
        "Darwin": ["SF Mono", "Menlo"],
        "Windows": ["Cascadia Code", "Consolas"],
        "Linux": ["Ubuntu Mono", "DejaVu Sans Mono"],
    }

    @staticmethod
    def _get_monospace_font(size: int = 11) -> QFont:
        """クロスプラットフォーム対応の等幅フォントを取得"""
        system = platform.system()
        font_names = MainWorkspace.MONO_FONTS.get(system, ["monospace"])

        for font_name in font_names:
            if QFontDatabase.hasFamily(font_name) and QFontDatabase.isFixedPitch(font_name):
                return QFont(font_name, size)

        # フォールバック: システムの等幅フォント
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(size)
        return font

    def __init__(self, work_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._state = ProjectState(work_dir=work_dir or Path.cwd())
        self._log_panel: Optional[LogPanel] = None
        self._media_player: Optional[QMediaPlayer] = None
        self._audio_output: Optional[QAudioOutput] = None

        # 波形生成スレッド
        self._waveform_thread: Optional[QThread] = None
        self._waveform_worker: Optional[WaveformWorker] = None
        self._waveform_widget: Optional[WaveformWidget] = None

        # スペクトログラム生成スレッド
        self._spectrogram_thread: Optional[QThread] = None
        self._spectrogram_worker: Optional[SpectrogramWorker] = None
        self._spectrogram_generated = False  # スペクトログラム生成済みフラグ

        # カバー画像
        self._cover_image = None  # QImage

        # 埋め込みチャプターフラグ（MP4から読み込んだチャプターがあるか）
        self._has_embedded_chapters = False

        # 音声のみモード（MP3等からのエクスポート時は静止画用固定）
        self._is_audio_only = False

        # 現在再生中のチャプター行（ハイライト用）
        self._current_chapter_row = -1

        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # === メイン水平スプリッター（左: 編集, 右: プレビュー）===
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左側パネル（固定幅: 1.5:3比率 → 480px）
        left_panel = self._create_left_panel()
        left_panel.setFixedWidth(480)
        main_splitter.addWidget(left_panel)

        # 右側パネル（動画プレビュー）- 残りのスペースを使用
        right_panel = self._create_video_panel()
        main_splitter.addWidget(right_panel)

        layout.addWidget(main_splitter, stretch=1)

    def _create_left_panel(self) -> QWidget:
        """左側パネル（操作系を操作順に配置）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # === 1. ソース選択 ===
        source_section = self._create_source_section()
        layout.addWidget(source_section)

        # === 2. チャプターテーブル ===
        self._chapter_table = self._create_chapter_table()
        layout.addWidget(self._chapter_table, stretch=1)

        # === 3. 書出設定 ===
        export_section = self._create_export_section()
        layout.addWidget(export_section)

        # === 4. ログパネル ===
        self._log_panel = LogPanel()
        layout.addWidget(self._log_panel)

        # 初期ログ
        self._log_panel.info("Workspace initialized", source="UI")

        return widget

    def _create_source_section(self) -> QWidget:
        """1. ソース選択セクション"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)

        main_layout = QVBoxLayout(frame)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(8)

        # 上段: ソース選択
        source_row = QHBoxLayout()

        self._source_btn = QPushButton("Select Source")
        self._source_btn.setStyleSheet("""
            QPushButton {
                background: #3b82f6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 15px;
            }
            QPushButton:hover {
                background: #2563eb;
            }
        """)
        self._source_btn.setToolTip("音声/動画ファイルを選択")
        self._source_btn.clicked.connect(self._open_source_dialog)
        source_row.addWidget(self._source_btn)

        # カバー画像ボタン
        self._cover_btn = QPushButton("Cover Image")
        self._cover_btn.setStyleSheet(self._button_style())
        self._cover_btn.setToolTip("カバー画像を設定")
        self._cover_btn.clicked.connect(self._open_cover_dialog)
        source_row.addWidget(self._cover_btn)

        # カバー情報表示
        self._cover_info = QLabel("")
        self._cover_info.setStyleSheet("color: #666666;")
        self._cover_set = False  # カバー画像設定済みフラグ
        source_row.addWidget(self._cover_info)

        source_row.addStretch()

        main_layout.addLayout(source_row)

        # 下段: 出力ファイル名
        output_row = QHBoxLayout()

        output_label = QLabel("Output:")
        output_label.setStyleSheet("color: #a0a0a0;")
        output_row.addWidget(output_label)

        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("output.mp4")
        self._output_edit.setToolTip("出力ファイル名")
        self._output_edit.setStyleSheet("""
            QLineEdit {
                background: #0f0f0f;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        output_row.addWidget(self._output_edit, stretch=1)

        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(40)
        browse_btn.setStyleSheet(self._button_style())
        browse_btn.setToolTip("出力先を変更")
        browse_btn.clicked.connect(self._browse_output)
        output_row.addWidget(browse_btn)

        main_layout.addLayout(output_row)

        return frame

    def _create_playback_section(self) -> QWidget:
        """再生コントロールセクション（movie-viewerスタイル、波形中央揃え）"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # メディアプレイヤー設定
        self._media_player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._media_player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(0.8)

        # シグナル接続
        self._media_player.positionChanged.connect(self._on_position_changed)
        self._media_player.durationChanged.connect(self._on_duration_changed)
        self._media_player.errorOccurred.connect(self._on_media_error)
        self._media_player.mediaStatusChanged.connect(self._on_media_status_changed)

        # === 中央揃えのコントロール行（movie-viewerスタイル）===
        ctrl_row = QHBoxLayout()
        ctrl_row.addStretch()  # 左側スペーサー

        # 時間移動ボタンのスタイル
        time_btn_style = """
            QPushButton {
                background: #2d2d2d;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 12px;
                font-size: 18px;
                font-weight: bold;
                padding: 4px 2px;
            }
            QPushButton:hover {
                background: #3d3d3d;
            }
            QPushButton:pressed {
                background: #4d4d4d;
            }
            QPushButton:disabled {
                background: #1a1a1a;
                color: #666666;
            }
        """

        # -10s
        btn_m10s = QPushButton("-10s")
        btn_m10s.setStyleSheet(time_btn_style)
        btn_m10s.setFixedSize(55, 45)
        btn_m10s.setToolTip("10秒戻る")
        btn_m10s.clicked.connect(lambda: self._seek_relative(-10000))
        ctrl_row.addWidget(btn_m10s)

        # -1s
        btn_m1s = QPushButton("-1s")
        btn_m1s.setStyleSheet(time_btn_style)
        btn_m1s.setFixedSize(55, 45)
        btn_m1s.setToolTip("1秒戻る")
        btn_m1s.clicked.connect(lambda: self._seek_relative(-1000))
        ctrl_row.addWidget(btn_m1s)

        # -.3s
        btn_m03s = QPushButton("-.3s")
        btn_m03s.setStyleSheet(time_btn_style)
        btn_m03s.setFixedSize(55, 45)
        btn_m03s.setToolTip("0.3秒戻る")
        btn_m03s.clicked.connect(lambda: self._seek_relative(-300))
        ctrl_row.addWidget(btn_m03s)

        # -1f (約33ms @ 30fps)
        btn_m1f = QPushButton("-1f")
        btn_m1f.setStyleSheet(time_btn_style)
        btn_m1f.setFixedSize(55, 45)
        btn_m1f.setToolTip("1フレーム戻る")
        btn_m1f.clicked.connect(lambda: self._seek_relative(-33))
        ctrl_row.addWidget(btn_m1f)

        # Play/Pause（大きめボタン）
        self._play_btn = QPushButton("▶")
        self._play_btn.setStyleSheet("""
            QPushButton {
                background: #3b82f6;
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 28px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2563eb;
            }
            QPushButton:pressed {
                background: #1d4ed8;
            }
            QPushButton:disabled {
                background: #1e3a5f;
                color: #666666;
            }
        """)
        self._play_btn.setFixedSize(80, 55)
        self._play_btn.setToolTip("再生/一時停止 (Space)")
        self._play_btn.clicked.connect(self._toggle_playback)
        self._play_btn.setEnabled(False)
        ctrl_row.addWidget(self._play_btn)

        # +1f
        btn_p1f = QPushButton("+1f")
        btn_p1f.setStyleSheet(time_btn_style)
        btn_p1f.setFixedSize(55, 45)
        btn_p1f.setToolTip("1フレーム進む")
        btn_p1f.clicked.connect(lambda: self._seek_relative(33))
        ctrl_row.addWidget(btn_p1f)

        # +.3s
        btn_p03s = QPushButton("+.3s")
        btn_p03s.setStyleSheet(time_btn_style)
        btn_p03s.setFixedSize(55, 45)
        btn_p03s.setToolTip("0.3秒進む")
        btn_p03s.clicked.connect(lambda: self._seek_relative(300))
        ctrl_row.addWidget(btn_p03s)

        # +1s
        btn_p1s = QPushButton("+1s")
        btn_p1s.setStyleSheet(time_btn_style)
        btn_p1s.setFixedSize(55, 45)
        btn_p1s.setToolTip("1秒進む")
        btn_p1s.clicked.connect(lambda: self._seek_relative(1000))
        ctrl_row.addWidget(btn_p1s)

        # +10s
        btn_p10s = QPushButton("+10s")
        btn_p10s.setStyleSheet(time_btn_style)
        btn_p10s.setFixedSize(55, 45)
        btn_p10s.setToolTip("10秒進む")
        btn_p10s.clicked.connect(lambda: self._seek_relative(10000))
        ctrl_row.addWidget(btn_p10s)

        ctrl_row.addStretch()  # 右側スペーサー
        layout.addLayout(ctrl_row)

        # === 下部行（表示モード、音量、時間） ===
        bottom_row = QHBoxLayout()

        # 表示モード選択（Waveform/Mel Spectrogram）
        self._display_mode_combo = QComboBox()
        self._display_mode_combo.addItem("Waveform", WaveformWidget.MODE_WAVEFORM)
        self._display_mode_combo.addItem("Mel Spectrogram", WaveformWidget.MODE_SPECTROGRAM)
        self._display_mode_combo.setFixedWidth(160)
        self._display_mode_combo.setStyleSheet("""
            QComboBox {
                background: #2d2d2d;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox:disabled {
                background: #1a1a1a;
                color: #666666;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #a0a0a0;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background: #2d2d2d;
                color: #f0f0f0;
                selection-background-color: #3b82f6;
            }
        """)
        self._display_mode_combo.setToolTip("波形表示モード")
        self._display_mode_combo.currentIndexChanged.connect(self._on_display_mode_changed)
        self._display_mode_combo.setEnabled(False)
        bottom_row.addWidget(self._display_mode_combo)

        bottom_row.addSpacing(12)

        # 音量
        volume_label = QLabel("Vol:")
        volume_label.setStyleSheet("color: #a0a0a0;")
        bottom_row.addWidget(volume_label)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setMaximum(100)
        self._volume_slider.setValue(80)
        self._volume_slider.setFixedWidth(80)
        self._volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #2d2d2d;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #a0a0a0;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
        """)
        self._volume_slider.setToolTip("音量調整")
        self._volume_slider.valueChanged.connect(self._set_volume)
        bottom_row.addWidget(self._volume_slider)

        bottom_row.addStretch()

        # 時間表示
        self._time_label = QLabel("0:00:00.000 / 0:00:00.000")
        self._time_label.setStyleSheet("color: #22c55e;")
        self._time_label.setFont(self._get_monospace_font(18))
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom_row.addWidget(self._time_label)

        layout.addLayout(bottom_row)

        return frame

    def _seek_relative(self, delta_ms: int):
        """現在位置から相対的にシーク"""
        if not self._media_player:
            return
        current = self._media_player.position()
        duration = self._media_player.duration()
        new_pos = max(0, min(duration, current + delta_ms))
        self._media_player.setPosition(new_pos)

    def _create_video_panel(self) -> QWidget:
        """右側パネル（Video + Waveform + 再生コントロール）"""
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # === 動画プレビュー（最大化）===
        video_frame = DropVideoFrame()
        video_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # ドロップシグナル接続
        video_frame.files_dropped.connect(self._on_files_dropped)
        video_frame.folder_dropped.connect(self._on_folder_dropped)

        video_layout = QVBoxLayout(video_frame)
        video_layout.setContentsMargins(4, 4, 4, 4)
        video_layout.setSpacing(0)

        # 動画表示エリア - 最大化
        self._video_widget = QVideoWidget()
        self._video_widget.setStyleSheet("background: #0f0f0f; border-radius: 4px;")
        self._video_widget.setMinimumSize(400, 300)
        self._video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        video_layout.addWidget(self._video_widget, stretch=1)

        video_frame.setLayout(video_layout)
        main_layout.addWidget(video_frame, stretch=4)  # 動画に多くのスペース

        # === 波形表示 ===
        waveform_section = self._create_waveform_section()
        main_layout.addWidget(waveform_section, stretch=1)

        # === 再生コントロール ===
        playback_section = self._create_playback_section()
        main_layout.addWidget(playback_section)

        # メディアプレイヤーの出力先を設定
        self._media_player.setVideoOutput(self._video_widget)

        return container

    def _create_waveform_section(self) -> QWidget:
        """波形表示セクション"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #0f0f0f;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)
        frame.setMinimumHeight(120)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        # 波形ウィジェット
        self._waveform_widget = WaveformWidget()
        self._waveform_widget.setToolTip("クリックで再生位置を移動\n赤いハッチング: 除外区間（--チャプター）")
        self._waveform_widget.position_clicked.connect(self._on_waveform_clicked)
        layout.addWidget(self._waveform_widget)

        return frame

    def _create_chapter_table(self) -> QWidget:
        """チャプターテーブル"""
        self._chapter_group = QGroupBox()
        self._chapter_group.setStyleSheet("""
            QGroupBox {
                color: #f0f0f0;
                font-weight: bold;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                margin-top: 4px;
                padding-top: 4px;
            }
        """)

        layout = QVBoxLayout(self._chapter_group)

        # カスタムタイトルラベル（リッチテキスト対応）
        self._chapter_title_label = QLabel("Chapters")
        self._chapter_title_label.setStyleSheet("font-weight: bold; color: #f0f0f0;")
        layout.addWidget(self._chapter_title_label)

        # テーブル
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Time", "Title"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)  # セル単位選択
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)  # 単一選択
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # Enterキーのみで編集
        self._table.installEventFilter(self)  # Enterキー処理用
        self._table.viewport().installEventFilter(self)  # ダブルクリック処理用
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
        # チャプター編集後に波形を更新（ダブルクリックシークはeventFilterで処理）
        self._table.cellChanged.connect(self._on_chapter_edited)
        # 選択変更時に文字色を復元
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

        # ボタン行
        btn_layout = QHBoxLayout()

        load_btn = QPushButton("Load")
        load_btn.setStyleSheet(self._button_style())
        load_btn.clicked.connect(self._load_chapters)
        load_btn.setToolTip("チャプターファイルを読み込み")
        btn_layout.addWidget(load_btn)

        add_btn = QPushButton("Add")
        add_btn.setStyleSheet(self._button_style())
        add_btn.setToolTip("現在位置にチャプター追加")
        add_btn.clicked.connect(self._add_chapter)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setStyleSheet(self._button_style())
        remove_btn.setToolTip("選択チャプターを削除")
        remove_btn.clicked.connect(self._remove_chapter)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        copy_btn = QPushButton("Copy YouTube")
        copy_btn.setStyleSheet(self._button_style())
        copy_btn.setToolTip("YouTube用チャプターをクリップボードにコピー")
        copy_btn.clicked.connect(self._copy_youtube_chapters)
        btn_layout.addWidget(copy_btn)

        layout.addLayout(btn_layout)

        return self._chapter_group

    def _create_export_section(self) -> QWidget:
        """4. 書出設定セクション（カバー画像 + エンコーダ選択 + オプション + Export）"""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        # === 上段: エンコーダ選択 ===
        middle_frame = QFrame()
        middle_frame.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)
        middle_layout = QHBoxLayout(middle_frame)
        middle_layout.setContentsMargins(12, 8, 12, 8)

        combo_style = """
            QComboBox {
                background: #2d2d2d;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                min-width: 150px;
                font-size: 14px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0;
            }
        """

        # エンコーダ選択
        encoder_label = QLabel("Encoder:")
        encoder_label.setStyleSheet("color: #a0a0a0; font-size: 14px;")
        middle_layout.addWidget(encoder_label)

        self._encoder_combo = QComboBox()
        self._encoder_combo.setStyleSheet(combo_style)
        self._encoder_combo.setToolTip("エンコーダを選択\nGPU: 高速、CPU: 高画質")
        self._available_encoders = detect_available_encoders()
        for encoder_id, display_name, description in self._available_encoders:
            self._encoder_combo.addItem(display_name, encoder_id)
            # ツールチップとして説明を追加
            idx = self._encoder_combo.count() - 1
            self._encoder_combo.setItemData(idx, description, Qt.ItemDataRole.ToolTipRole)
        middle_layout.addWidget(self._encoder_combo)

        middle_layout.addStretch()

        container_layout.addWidget(middle_frame)

        # === エンコード設定段: ビットレート + CRF ===
        encode_frame = QFrame()
        encode_frame.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)
        encode_layout = QHBoxLayout(encode_frame)
        encode_layout.setContentsMargins(12, 8, 12, 8)

        # 品質設定（プリセット）
        quality_label = QLabel("Quality:")
        quality_label.setStyleSheet("color: #a0a0a0; font-size: 14px;")
        encode_layout.addWidget(quality_label)

        self._quality_combo = QComboBox()
        # 動画用品質オプション: (display_name, bitrate_kbps, crf)
        # bitrate_kbps=0 は「元と同じ」を意味する
        self._video_quality_options = [
            ("元と同じ (自動)", 0, 23),  # 検出ビットレートを使用
            ("高画質 (6Mbps)", 6000, 20),
            ("標準 (4Mbps)", 4000, 23),
            ("軽量 (2Mbps)", 2000, 28),
            ("最小 (1Mbps)", 1000, 32),
        ]
        # 音声用（静止画）品質オプション
        self._audio_quality_options = [
            ("静止画用 (CRF 32)", 500, 32),  # 静止画は低品質で十分
        ]
        # 初期状態は動画用
        for display_name, bitrate, crf in self._video_quality_options:
            self._quality_combo.addItem(display_name, (bitrate, crf))
        self._quality_combo.setCurrentIndex(0)  # デフォルト: 元と同じ
        self._quality_combo.setToolTip("ビットレート設定\n「元と同じ」で元動画のビットレートを維持")
        self._quality_combo.setStyleSheet("""
            QComboBox {
                background: #0f0f0f;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px 12px;
                min-width: 180px;
                font-size: 14px;
            }
            QComboBox:hover {
                border-color: #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #a0a0a0;
            }
            QComboBox QAbstractItemView {
                background: #1a1a1a;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                selection-background-color: #3b82f6;
            }
        """)
        encode_layout.addWidget(self._quality_combo)

        encode_layout.addStretch()

        container_layout.addWidget(encode_frame)

        # === 下段: オプション + プログレス + Export ===
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(12, 8, 12, 8)

        # チェックボックス群
        checkbox_style = """
            QCheckBox {
                color: #a0a0a0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #3a3a3a;
                background: #0f0f0f;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #3b82f6;
                background: #3b82f6;
                border-radius: 3px;
            }
        """

        # チャプター埋込
        self._embed_chapters_cb = QCheckBox("Embed Chapters")
        self._embed_chapters_cb.setChecked(True)
        self._embed_chapters_cb.setStyleSheet(checkbox_style)
        self._embed_chapters_cb.setToolTip("MP4ファイルにチャプターメタデータを埋め込み")
        bottom_layout.addWidget(self._embed_chapters_cb)

        bottom_layout.addSpacing(20)

        # 除外区間カット
        self._cut_excluded_cb = QCheckBox("Cut Excluded")
        self._cut_excluded_cb.setChecked(True)
        self._cut_excluded_cb.setStyleSheet(checkbox_style)
        self._cut_excluded_cb.setToolTip("--で始まるチャプターの区間を切り取り")
        bottom_layout.addWidget(self._cut_excluded_cb)

        bottom_layout.addStretch()

        # 書出ボタン（エクスポート中はキャンセルボタンに変化）
        self._export_btn = QPushButton("Export")
        self._export_btn.setStyleSheet(self._button_style(primary=True))
        self._export_btn.setToolTip("編集した動画を書き出す")
        self._export_btn.clicked.connect(self._on_export_btn_clicked)
        self._is_exporting = False  # エクスポート状態フラグ
        bottom_layout.addWidget(self._export_btn)

        container_layout.addWidget(bottom_frame)

        return container

    def _browse_output(self):
        """出力先ファイル選択"""
        file_path, _ = CenteredFileDialog.getSaveFileName(
            self,
            "Save Output Video",
            str(self._state.work_dir / "output.mp4"),
            "MP4 Files (*.mp4);;All Files (*)"
        )
        if file_path:
            self._output_edit.setText(file_path)
            self._state.output_path = Path(file_path)

    def _button_style(self, primary: bool = False, danger: bool = False) -> str:
        """ボタンスタイル"""
        if danger:
            return """
                QPushButton {
                    background: #dc2626;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #ef4444;
                }
                QPushButton:pressed {
                    background: #b91c1c;
                }
                QPushButton:disabled {
                    background: #7f1d1d;
                    color: #666666;
                }
            """
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

    # === 動画操作 ===

    def _load_source_media(self):
        """ソースからメディアを読み込み"""
        if not self._state.sources:
            return

        # ファイル拡張子で判定
        VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}
        AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.wav', '.aac', '.flac'}

        first_source = self._state.sources[0]
        file_path = first_source.path
        ext = file_path.suffix.lower()

        if ext in VIDEO_EXTENSIONS:
            # 動画ファイル: そのまま読み込み
            self._state.video_path = file_path
            self._media_player.setSource(QUrl.fromLocalFile(str(file_path)))
            self._play_btn.setEnabled(True)
            self._log_panel.info(f"Video loaded: {file_path.name}", source="Media")
            self._start_waveform_generation(file_path)
            # 埋め込みチャプターがあれば読み込み
            self._load_embedded_chapters(file_path)
            # 動画モード: 品質選択を有効化
            self._update_quality_combo_for_mode(is_audio=False)

        elif ext in AUDIO_EXTENSIONS:
            # 音声モード: 品質選択を静止画用に固定
            self._update_quality_combo_for_mode(is_audio=True)

            if len(self._state.sources) == 1:
                # 単一音声: そのまま読み込み（チャプター編集用）
                self._state.video_path = file_path
                self._media_player.setSource(QUrl.fromLocalFile(str(file_path)))
                self._play_btn.setEnabled(True)
                self._log_panel.info(f"Audio loaded: {file_path.name}", source="Media")
                self._start_waveform_generation(file_path)
            else:
                # 複数音声: 再生せず、チャプター設定のみ
                # Export時にffmpegで結合する
                self._state.video_path = None
                self._play_btn.setEnabled(False)
                self._log_panel.info(
                    f"{len(self._state.sources)} audio files selected (preview after Export)",
                    source="Media"
                )
        else:
            self._log_panel.warning(f"Unknown file type: {ext}", source="Media")

    def _update_quality_combo_for_mode(self, is_audio: bool):
        """品質コンボボックスを動画/音声モードに応じて更新"""
        self._is_audio_only = is_audio
        self._quality_combo.clear()

        if is_audio:
            # 音声モード: 静止画用のみ、変更不可
            for display_name, bitrate, crf in self._audio_quality_options:
                self._quality_combo.addItem(display_name, (bitrate, crf))
            self._quality_combo.setEnabled(False)
            self._quality_combo.setToolTip("音声ファイルは静止画用固定です")
        else:
            # 動画モード: 複数選択可能
            for display_name, bitrate, crf in self._video_quality_options:
                self._quality_combo.addItem(display_name, (bitrate, crf))
            self._quality_combo.setEnabled(True)
            self._quality_combo.setToolTip("ビットレート設定\n「元と同じ」で元動画のビットレートを維持")

        self._quality_combo.setCurrentIndex(0)

    def _merge_audio_files(self) -> Optional[Path]:
        """複数の音声ファイルをffmpegで結合

        ffmpegのconcat demuxerを使用して結合。
        シングルクォートを含むファイル名も適切にエスケープ。

        Returns:
            結合されたファイルのパス、失敗時はNone
        """
        if len(self._state.sources) < 2:
            return None

        try:
            # 一時ディレクトリに出力
            output_path = Path(tempfile.gettempdir()) / "merged_audio.mp3"

            # concat demuxer用のファイルリストを作成
            list_file = Path(tempfile.gettempdir()) / "concat_list.txt"
            with open(list_file, 'w', encoding='utf-8') as f:
                for src in self._state.sources:
                    # concat demuxerではシングルクォートをエスケープする必要がある
                    # file 'path' 形式で、パス内のシングルクォートは '\'' でエスケープ
                    escaped_path = str(src.path).replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            self._log_panel.debug(f"Concat list: {list_file}", source="Media")

            # ffmpegで結合
            cmd = [
                get_ffmpeg_path(), '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(list_file),
                '-c', 'copy',
                str(output_path)
            ]

            self._log_panel.debug(f"Running: {' '.join(cmd[:8])}...", source="Media")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分タイムアウト
            )

            if result.returncode != 0:
                self._log_panel.error(f"ffmpeg error: {result.stderr[:200]}", source="Media")
                return None

            # 一時ファイルを削除
            if list_file.exists():
                list_file.unlink()

            self._log_panel.info(
                f"Merged {len(self._state.sources)} files → {output_path.name}",
                source="Media"
            )
            return output_path

        except subprocess.TimeoutExpired:
            self._log_panel.error("Merge timeout (5 min)", source="Media")
            return None
        except Exception as e:
            self._log_panel.error(f"Merge failed: {e}", source="Media")
            return None

    def _toggle_playback(self):
        """再生/一時停止切替"""
        if self._media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._media_player.pause()
            self._play_btn.setText("▶")
        else:
            self._media_player.play()
            self._play_btn.setText("⏸")

    def _stop_video(self):
        """停止"""
        self._media_player.stop()
        self._play_btn.setText("▶")

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus):
        """メディアステータス変更時の処理"""
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            # 読み込み完了後、自動再生開始
            self._media_player.play()
            self._play_btn.setText("⏸")

    def _seek_video(self, position: int):
        """シーク"""
        self._media_player.setPosition(position)

    def _set_volume(self, value: int):
        """音量設定"""
        self._audio_output.setVolume(value / 100.0)

    def _on_position_changed(self, position: int):
        """再生位置変更"""
        # 時間表示更新
        duration = self._media_player.duration()
        self._time_label.setText(
            f"{self._format_time(position)} / {self._format_time(duration)}"
        )

        # 波形位置更新
        if duration > 0 and self._waveform_widget:
            self._waveform_widget.set_position(position / duration)

        # 現在のチャプターをハイライト
        self._highlight_current_chapter(position)

    def _on_duration_changed(self, duration: int):
        """動画長さ変更"""
        self._log_panel.debug(f"Duration: {self._format_time(duration)}", source="Video")

    def _highlight_current_chapter(self, position: int):
        """現在再生中のチャプターをハイライト"""
        if self._table.rowCount() == 0:
            self._current_chapter_row = -1
            return

        # 現在位置より前で最も近いチャプターを見つける
        current_row = -1
        for row in range(self._table.rowCount()):
            time_item = self._table.item(row, 0)
            if time_item:
                chapter = ChapterInfo.from_time_str(time_item.text(), "")
                if chapter.time_ms <= position:
                    current_row = row
                else:
                    break

        # チャプターが変わっていなければ何もしない
        if current_row == self._current_chapter_row:
            return

        # ハイライト用の色（選択色の青とは異なるティール系）
        highlight_bg = QBrush(QColor("#14b8a6"))  # ティール背景
        transparent_bg = QBrush(Qt.GlobalColor.transparent)  # 透明（デフォルトに戻す）

        # 全行の背景をクリア（文字色は維持）
        for row in range(self._table.rowCount()):
            for col in range(2):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(transparent_bg)

        # 現在のチャプターをハイライト（背景色のみ変更、文字色は維持）
        if current_row >= 0:
            for col in range(2):
                item = self._table.item(current_row, col)
                if item:
                    item.setBackground(highlight_bg)

        self._current_chapter_row = current_row

    def _on_media_error(self, error):
        """メディアエラー"""
        self._log_panel.error(f"Media error: {error}", source="Video")

    def _format_time(self, ms: int) -> str:
        """ミリ秒を h:mm:ss.sss 形式に変換"""
        total_sec = ms // 1000
        millis = ms % 1000
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}.{millis:03d}"

    def _skip_to_prev_chapter(self):
        """前のチャプターへスキップ"""
        if not self._media_player:
            return

        current_pos = self._media_player.position()
        chapters = self._get_table_chapters()

        if not chapters:
            # チャプターがない場合は先頭へ
            self._media_player.setPosition(0)
            return

        # 時間順にソート
        sorted_chapters = sorted(chapters, key=lambda c: c.time_ms)

        # 現在位置より前のチャプターを探す（2秒以上前なら同じチャプターの先頭へ）
        margin_ms = 2000
        prev_chapter = None
        for ch in sorted_chapters:
            if ch.time_ms < current_pos - margin_ms:
                prev_chapter = ch
            else:
                break

        if prev_chapter:
            self._media_player.setPosition(prev_chapter.time_ms)
            self._log_panel.debug(f"Skip to: {prev_chapter.title}", source="Playback")
        else:
            # 最初のチャプターより前なら先頭へ
            self._media_player.setPosition(0)

    def _skip_to_next_chapter(self):
        """次のチャプターへスキップ"""
        if not self._media_player:
            return

        current_pos = self._media_player.position()
        chapters = self._get_table_chapters()

        if not chapters:
            return

        # 時間順にソート
        sorted_chapters = sorted(chapters, key=lambda c: c.time_ms)

        # 現在位置より後のチャプターを探す
        for ch in sorted_chapters:
            if ch.time_ms > current_pos + 500:  # 500ms マージン
                self._media_player.setPosition(ch.time_ms)
                self._log_panel.debug(f"Skip to: {ch.title}", source="Playback")
                return

        # 最後のチャプター以降なら何もしない（または末尾へ）
        self._log_panel.debug("Already at last chapter", source="Playback")

    # === 波形操作（別スレッド） ===

    def _start_waveform_generation(self, file_path: Path):
        """波形生成を開始（別スレッド）"""
        # 既存のスレッドをクリーンアップ
        self._cleanup_waveform_thread()

        # 波形ウィジェットをローディング状態に
        if self._waveform_widget:
            self._waveform_widget.set_loading(0)

        self._log_panel.debug(f"Starting waveform generation: {file_path.name}", source="Waveform")

        # ワーカーとスレッドを作成
        # サンプル数を多めに取得（min-max法で間引くため）
        self._waveform_thread = QThread()
        self._waveform_worker = WaveformWorker(file_path, num_samples=4000)

        # ワーカーをスレッドに移動
        self._waveform_worker.moveToThread(self._waveform_thread)

        # シグナル接続
        self._waveform_thread.started.connect(self._waveform_worker.run)
        self._waveform_worker.progress.connect(self._on_waveform_progress)
        self._waveform_worker.finished.connect(self._on_waveform_finished)
        self._waveform_worker.error.connect(self._on_waveform_error)
        self._waveform_worker.finished.connect(self._waveform_thread.quit)
        self._waveform_worker.error.connect(self._waveform_thread.quit)

        # スレッド開始
        self._waveform_thread.start()

    def _cleanup_waveform_thread(self):
        """波形スレッドをクリーンアップ"""
        if self._waveform_worker:
            self._waveform_worker.cancel()
            self._waveform_worker = None

        if self._waveform_thread and self._waveform_thread.isRunning():
            self._waveform_thread.quit()
            self._waveform_thread.wait(1000)  # 最大1秒待機
            self._waveform_thread = None

    def _on_waveform_progress(self, progress: int):
        """波形生成進捗"""
        if self._waveform_widget:
            self._waveform_widget.set_loading(progress)
            # UIを即時更新（高速処理時にも進捗を表示）
            QApplication.processEvents()

    def _on_waveform_finished(self, data: list):
        """波形生成完了"""
        if self._waveform_widget:
            self._waveform_widget.set_waveform(data)
        self._log_panel.info(f"Waveform generated: {len(data)} samples", source="Waveform")

        # テーブルにチャプターがあれば波形に反映
        if self._table.rowCount() > 0:
            self._update_waveform_chapters()

        # UIを更新して波形を表示
        QApplication.processEvents()

        # 波形表示後にスペクトログラム生成を開始（100ms遅延）
        if self._state.video_path and not self._spectrogram_generated:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._start_spectrogram_after_waveform)

    def _start_spectrogram_after_waveform(self):
        """波形表示後にスペクトログラム生成を開始"""
        if self._state.video_path and not self._spectrogram_generated:
            self._start_spectrogram_generation(self._state.video_path)

    def _on_waveform_error(self, message: str):
        """波形生成エラー"""
        if self._waveform_widget:
            self._waveform_widget.set_error(message)
        self._log_panel.warning(f"Waveform error: {message}", source="Waveform")

    def _on_waveform_clicked(self, position: float):
        """波形クリックでシーク"""
        if self._media_player:
            duration = self._media_player.duration()
            if duration > 0:
                new_position = int(position * duration)
                self._media_player.setPosition(new_position)
                self._log_panel.debug(f"Seek to {self._format_time(new_position)}", source="Waveform")

    # === 表示モード切替 ===

    def _on_display_mode_changed(self, index: int):
        """表示モード変更"""
        mode = self._display_mode_combo.currentData()

        if mode == WaveformWidget.MODE_SPECTROGRAM:
            # スペクトログラムモード
            if not self._spectrogram_generated and self._state.video_path:
                # スペクトログラム未生成の場合、生成を開始
                self._start_spectrogram_generation(self._state.video_path)
            else:
                # 既に生成済みの場合、表示を切り替え
                if self._waveform_widget:
                    self._waveform_widget.set_display_mode(mode)
                    self._update_waveform_chapters()
        else:
            # 波形モード
            if self._waveform_widget:
                self._waveform_widget.set_display_mode(mode)
                self._update_waveform_chapters()

    def _start_spectrogram_generation(self, file_path: Path):
        """スペクトログラム生成を開始（バックグラウンド）"""
        # 既存のスレッドがあれば停止
        if self._spectrogram_thread and self._spectrogram_thread.isRunning():
            if self._spectrogram_worker:
                self._spectrogram_worker.cancel()
            self._spectrogram_thread.quit()
            self._spectrogram_thread.wait()

        # コンボボックスを無効化
        self._display_mode_combo.setEnabled(False)

        # ワーカーとスレッドを作成
        self._spectrogram_thread = QThread()
        target_width = self._waveform_widget.width() if self._waveform_widget else 1000
        target_height = self._waveform_widget.height() if self._waveform_widget else 100
        self._spectrogram_worker = SpectrogramWorker(
            str(file_path),
            target_width=target_width,
            target_height=target_height
        )
        self._spectrogram_worker.moveToThread(self._spectrogram_thread)

        # シグナル接続
        self._spectrogram_thread.started.connect(self._spectrogram_worker.run)
        self._spectrogram_worker.progress.connect(self._on_spectrogram_progress)
        self._spectrogram_worker.finished.connect(self._on_spectrogram_finished)
        self._spectrogram_worker.error.connect(self._on_spectrogram_error)
        self._spectrogram_worker.finished.connect(self._spectrogram_thread.quit)
        self._spectrogram_worker.error.connect(self._spectrogram_thread.quit)

        # 開始
        self._spectrogram_thread.start()
        self._log_panel.info("Generating spectrogram...", source="Spectrogram")

        if self._waveform_widget:
            self._waveform_widget.set_loading(0, "spectrogram")

    def _on_spectrogram_progress(self, progress: int):
        """スペクトログラム生成進捗"""
        if self._waveform_widget:
            self._waveform_widget.set_loading(progress, "spectrogram")

    def _on_spectrogram_finished(self, data):
        """スペクトログラム生成完了"""
        self._spectrogram_generated = True

        if self._waveform_widget:
            duration_ms = self._media_player.duration() if self._media_player else 0
            self._waveform_widget.set_spectrogram(data, duration_ms)
            # 表示モードは切り替えない（デフォルトは波形のまま）

        # コンボボックスを有効化（ユーザーが切り替え可能に）
        self._display_mode_combo.setEnabled(True)

        self._log_panel.info("Spectrogram generated", source="Spectrogram")

    def _on_spectrogram_error(self, message: str):
        """スペクトログラム生成エラー"""
        if self._waveform_widget:
            self._waveform_widget.set_error(message)

        # コンボボックスを有効化して波形モードに戻す
        self._display_mode_combo.setEnabled(True)
        self._display_mode_combo.setCurrentIndex(0)  # 波形モードに戻す

        self._log_panel.warning(f"Spectrogram error: {message}", source="Spectrogram")

    # === ダイアログ操作 ===

    def _open_source_dialog(self):
        """ソース選択ダイアログを開く"""
        dialog = SourceSelectionDialog(self, self._state.sources, work_dir=self._state.work_dir)
        if dialog.exec():
            self._state.sources = dialog.get_sources()
            self._update_source_info()
            self._log_panel.info(
                f"Sources updated: {len(self._state.sources)} files",
                source="UI"
            )
            self.source_changed.emit(self._state.sources)

            # 埋め込みチャプターフラグをリセット（新しいソースを読み込むので）
            self._has_embedded_chapters = False
            self._chapter_title_label.setText("Chapters")
            self._chapter_title_label.setTextFormat(Qt.TextFormat.PlainText)
            self._table.setRowCount(0)  # チャプターリストをクリア
            self._current_chapter_row = -1  # ハイライトもリセット

            # スペクトログラム関連をリセット
            self._spectrogram_generated = False
            self._waveform_widget.set_spectrogram(None)  # スペクトログラムデータをクリア
            self._waveform_widget.set_display_mode(WaveformWidget.MODE_WAVEFORM)  # 振幅モードに戻す
            self._display_mode_combo.setCurrentIndex(0)  # コンボボックスも振幅に
            self._display_mode_combo.setEnabled(False)  # 波形生成完了まで無効化

            # 複数MP3の場合、チャプターを自動生成
            if len(self._state.sources) > 1:
                self._generate_chapters_from_sources()

            # ソースがあれば自動的にメディアプレーヤーに読み込み
            if self._state.sources:
                self._load_source_media()

    def _open_cover_dialog(self):
        """カバー画像ダイアログを開く"""
        dialog = CoverImageDialog(self, work_dir=self._state.work_dir)
        if dialog.exec():
            image = dialog.get_image()
            if image:
                self._cover_image = image  # QImageを保存
                self._cover_set = True
                self._cover_info.setText("Set")
                self._cover_info.setStyleSheet("color: #22c55e;")  # 緑
                self._log_panel.info("Cover image set", source="UI")

    def _update_source_info(self):
        """ソース情報表示を更新"""
        if not self._state.sources:
            # ソースがない場合はカバー情報を非表示
            self._cover_info.setText("")
            return

        # ソースがロードされたらカバー情報を表示
        if not self._cover_set:
            self._cover_info.setText("Not Set")
            self._cover_info.setStyleSheet("color: #ef4444;")  # 赤

    # === チャプター操作 ===

    def _generate_chapters_from_sources(self):
        """ソースファイルからチャプターを自動生成

        各ソースファイルの長さに基づいて、累積時間でチャプターを作成。
        ファイル名（拡張子なし）をチャプターのタイトルとして使用。
        """
        if not self._state.sources:
            return

        # テーブルをクリア（シグナルをブロックして不要なイベントを防ぐ）
        self._table.blockSignals(True)
        self._table.setRowCount(0)

        cumulative_ms = 0
        chapters = []

        for src in self._state.sources:
            # ChapterInfoを作成
            chapter = ChapterInfo(time_ms=cumulative_ms, title=src.path.stem)
            chapters.append(chapter)

            # テーブルに追加
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(chapter.time_str))
            self._table.setItem(row, 1, QTableWidgetItem(chapter.title))

            # 累積時間を更新
            cumulative_ms += src.duration_ms

        self._table.blockSignals(False)

        self._log_panel.info(
            f"Generated {len(chapters)} chapters from source files",
            source="Chapter"
        )

        # 波形にチャプターを反映（メディアロード後に更新されるので、ここでは状態を保持）
        self._state.chapters = chapters

    def _add_chapter(self):
        """チャプター追加（時間順にソートされた位置に挿入）"""
        # 現在の再生位置をチャプター時間として使用
        current_pos = self._media_player.position() if self._media_player else 0
        time_str = self._format_time(current_pos)

        # 挿入位置を時間順で決定
        insert_row = self._table.rowCount()  # デフォルトは最後
        for row in range(self._table.rowCount()):
            time_item = self._table.item(row, 0)
            if time_item:
                chapter = ChapterInfo.from_time_str(time_item.text(), "")
                if current_pos < chapter.time_ms:
                    insert_row = row
                    break

        self._table.insertRow(insert_row)

        time_item = QTableWidgetItem(time_str)
        title_item = QTableWidgetItem("New Chapter")

        # 追加したチャプターは常に赤色で表示（元のチャプターと区別するため）
        added_color = QColor("#ef4444")  # 赤色
        time_item.setForeground(QBrush(added_color))
        title_item.setForeground(QBrush(added_color))
        # ハイライト解除時の復元用に元の色を保存
        time_item.setData(Qt.ItemDataRole.UserRole, added_color)
        title_item.setData(Qt.ItemDataRole.UserRole, added_color)

        self._table.setItem(insert_row, 0, time_item)
        self._table.setItem(insert_row, 1, title_item)

        # 挿入した行を選択
        self._table.selectRow(insert_row)

        self._log_panel.debug(f"Chapter added at {time_str}", source="UI")
        self._update_waveform_chapters()

    def _remove_chapter(self):
        """選択チャプター削除"""
        rows = set(item.row() for item in self._table.selectedItems())
        for row in sorted(rows, reverse=True):
            self._table.removeRow(row)
        self._log_panel.debug(f"Removed {len(rows)} chapters", source="UI")
        self._update_waveform_chapters()

    def _on_chapter_edited(self, row: int, column: int):
        """チャプター編集後に波形を更新"""
        self._update_waveform_chapters()

    def _on_selection_changed(self):
        """選択変更時に文字色を復元（Qtの選択スタイルで上書きされるのを防ぐ）"""
        # 全行の両列の文字色を復元
        for row in range(self._table.rowCount()):
            for col in range(2):
                item = self._table.item(row, col)
                if item:
                    original_color = item.data(Qt.ItemDataRole.UserRole)
                    if original_color and original_color.isValid():
                        item.setForeground(QBrush(original_color))

    def _update_waveform_chapters(self):
        """テーブルからチャプターを取得して波形ウィジェットに反映"""
        # ハイライトをリセット（行が変わった可能性があるため）
        self._current_chapter_row = -1

        if not self._waveform_widget:
            return

        chapters = self._get_table_chapters()
        duration = self._media_player.duration() if self._media_player else 0
        self._waveform_widget.set_chapters(chapters, duration)

    def _remove_row(self, row: int):
        """指定行削除"""
        self._table.removeRow(row)

    def _on_chapter_clicked(self, row: int, column: int):
        """チャプタークリックでその位置にシーク"""
        time_item = self._table.item(row, 0)
        if not time_item:
            return

        time_str = time_item.text()

        # ChapterInfoを使って時間をパース
        chapter = ChapterInfo.from_time_str(time_str, "")
        position_ms = chapter.time_ms

        # メディアプレイヤーをシーク
        if self._media_player:
            self._media_player.setPosition(position_ms)
            self._log_panel.debug(f"Seek to chapter: {time_str}", source="Chapter")

    def _load_chapters(self):
        """チャプターファイルを読み込み

        サポートする形式:
        - HH:MM:SS.mmm タイトル (例: 1:23:45.678 イントロ)
        - HH:MM:SS タイトル (例: 1:23:45 イントロ)
        - MM:SS タイトル (例: 23:45 イントロ)
        - YouTube形式: 時間とタイトルがスペースで区切られた形式
        """
        file_path, _ = CenteredFileDialog.getOpenFileName(
            self,
            "Open Chapter File",
            str(self._state.work_dir),
            "Chapter Files (*.chapters *.txt *.srt);;All Files (*)"
        )

        if not file_path:
            return

        try:
            chapters = self._parse_chapter_file(file_path)

            if not chapters:
                self._log_panel.warning(f"No chapters found in: {Path(file_path).name}", source="Chapter")
                return

            # テーブルをクリアして新しいチャプターを追加（シグナルをブロック）
            self._table.blockSignals(True)
            self._table.setRowCount(0)

            # 埋め込みチャプターフラグをリセット
            self._has_embedded_chapters = False
            self._chapter_title_label.setText("Chapters")
            self._chapter_title_label.setTextFormat(Qt.TextFormat.PlainText)

            # デフォルトの白色
            default_color = QColor("#f0f0f0")

            for ch in chapters:
                row = self._table.rowCount()
                self._table.insertRow(row)

                time_item = QTableWidgetItem(ch.time_str)
                title_item = QTableWidgetItem(ch.title)

                # ハイライト解除時の復元用に元の色を保存
                time_item.setData(Qt.ItemDataRole.UserRole, default_color)
                title_item.setData(Qt.ItemDataRole.UserRole, default_color)

                self._table.setItem(row, 0, time_item)
                self._table.setItem(row, 1, title_item)

            self._table.blockSignals(False)

            # 波形にチャプターを反映
            if self._waveform_widget and self._media_player:
                duration = self._media_player.duration()
                self._waveform_widget.set_chapters(chapters, duration)

            self._log_panel.info(f"Loaded {len(chapters)} chapters from: {Path(file_path).name}", source="Chapter")

        except Exception as e:
            self._log_panel.error(f"Failed to load chapters: {e}", source="Chapter")

    def _parse_chapter_file(self, file_path: str) -> List[ChapterInfo]:
        """チャプターファイルをパース

        サポートする形式:
        1. 標準形式: "HH:MM:SS.mmm タイトル" または "HH:MM:SS タイトル"
        2. YouTube形式: "H:MM:SS タイトル" または "MM:SS タイトル"
        3. SRT風形式: 番号付きのチャプター

        Args:
            file_path: チャプターファイルパス

        Returns:
            ChapterInfoのリスト
        """
        import re

        chapters = []

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 時間パターン: HH:MM:SS.mmm, HH:MM:SS, H:MM:SS, MM:SS.mmm, MM:SS, M:SS
        time_pattern = re.compile(
            r'^(\d{1,2}:\d{2}:\d{2}(?:\.\d{1,3})?|\d{1,2}:\d{2}(?:\.\d{1,3})?)\s+(.+)$'
        )

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            match = time_pattern.match(line)
            if match:
                time_str = match.group(1)
                title = match.group(2).strip()

                # ChapterInfo.from_time_strを使用してパース
                chapter = ChapterInfo.from_time_str(time_str, title)
                chapters.append(chapter)

        return chapters

    def _extract_chapters_from_media(self, file_path: Path) -> List[ChapterInfo]:
        """メディアファイルから埋め込みチャプターを抽出

        ffprobeを使用してMP4/MKVなどのコンテナに埋め込まれた
        チャプター情報を抽出する。

        Args:
            file_path: メディアファイルパス

        Returns:
            ChapterInfoのリスト（チャプターがない場合は空リスト）
        """
        import json

        # ffprobeを試行、なければffmpegフォールバック
        use_ffprobe = True
        try:
            ffprobe_path = get_ffprobe_path()
            self._log_panel.debug(f"Using ffprobe: {ffprobe_path}", source="Chapter")
        except RuntimeError:
            use_ffprobe = False
            self._log_panel.debug("ffprobe not available, using ffmpeg fallback", source="Chapter")

        if use_ffprobe:
            try:
                cmd = [
                    ffprobe_path,
                    '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_chapters',
                    str(file_path)
                ]

                kwargs = get_subprocess_kwargs(timeout=30)
                result = subprocess.run(cmd, **kwargs)

                if result.returncode != 0:
                    self._log_panel.debug(f"ffprobe failed (code {result.returncode}), trying ffmpeg", source="Chapter")
                    use_ffprobe = False
                elif not result.stdout or not result.stdout.strip():
                    self._log_panel.debug("ffprobe returned empty output, trying ffmpeg", source="Chapter")
                    use_ffprobe = False
                else:
                    data = json.loads(result.stdout)
                    chapters_data = data.get('chapters', [])

                    if chapters_data:
                        chapters = []
                        for ch in chapters_data:
                            start_time = float(ch.get('start_time', 0))
                            time_ms = int(start_time * 1000)
                            tags = ch.get('tags', {})
                            title = tags.get('title', f'Chapter {len(chapters) + 1}')
                            chapter = ChapterInfo(time_ms=time_ms, title=title)
                            chapters.append(chapter)

                        self._log_panel.info(f"Loaded {len(chapters)} chapters from media", source="Chapter")
                        return chapters
                    else:
                        self._log_panel.debug("No chapters found via ffprobe", source="Chapter")
                        return []

            except subprocess.TimeoutExpired:
                self._log_panel.warning("ffprobe timeout", source="Chapter")
                use_ffprobe = False
            except json.JSONDecodeError as e:
                self._log_panel.debug(f"ffprobe JSON parse error: {e}, trying ffmpeg", source="Chapter")
                use_ffprobe = False
            except Exception as e:
                self._log_panel.debug(f"ffprobe failed: {e}, trying ffmpeg", source="Chapter")
                use_ffprobe = False

        # ffmpegフォールバック（imageio-ffmpegにはffprobeが含まれない）
        if not use_ffprobe:
            try:
                chapters_data = extract_chapters_with_ffmpeg(str(file_path))
                if chapters_data:
                    chapters = []
                    for ch in chapters_data:
                        time_ms = int(ch['start_time'] * 1000)
                        title = ch['title']
                        chapter = ChapterInfo(time_ms=time_ms, title=title)
                        chapters.append(chapter)

                    self._log_panel.info(f"Loaded {len(chapters)} chapters from media (via ffmpeg)", source="Chapter")
                    return chapters
                else:
                    self._log_panel.debug("No chapters found in media file", source="Chapter")
                    return []
            except Exception as e:
                self._log_panel.warning(f"Chapter extraction failed: {e}", source="Chapter")
                return []

        return []

    def _load_embedded_chapters(self, file_path: Path):
        """埋め込みチャプターを読み込んでテーブルに追加

        Args:
            file_path: メディアファイルパス
        """
        chapters = self._extract_chapters_from_media(file_path)

        if not chapters:
            self._has_embedded_chapters = False
            self._log_panel.debug("No embedded chapters found", source="Chapter")
            return

        # テーブルをクリアして新しいチャプターを追加（シグナルをブロック）
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        self._has_embedded_chapters = True
        self._log_panel.debug(f"Set _has_embedded_chapters = True ({len(chapters)} chapters)", source="Chapter")

        # チャプターグループのタイトルを更新（埋め込みを緑色で表示）
        if hasattr(self, '_chapter_title_label'):
            self._chapter_title_label.setText('Chapters <span style="color: #22c55e;">(埋め込み)</span>')
            self._chapter_title_label.setTextFormat(Qt.TextFormat.RichText)

        # デフォルトの白色（埋め込みチャプター用）
        default_color = QColor("#f0f0f0")

        for ch in chapters:
            row = self._table.rowCount()
            self._table.insertRow(row)

            time_item = QTableWidgetItem(ch.time_str)
            title_item = QTableWidgetItem(ch.title)

            # ハイライト解除時の復元用に元の色を保存
            time_item.setData(Qt.ItemDataRole.UserRole, default_color)
            title_item.setData(Qt.ItemDataRole.UserRole, default_color)

            self._table.setItem(row, 0, time_item)
            self._table.setItem(row, 1, title_item)

        self._table.blockSignals(False)
        self._state.chapters = chapters

        self._log_panel.info(
            f"Loaded {len(chapters)} embedded chapters",
            source="Chapter"
        )

    def _copy_youtube_chapters(self):
        """YouTubeチャプター形式でコピー（HH:MM:SS タイトル）

        テーブルからチャプターを読み取り、YouTube形式に変換してクリップボードにコピー。
        除外チャプター（--プレフィックス）はスキップ。
        """
        chapters = []
        for row in range(self._table.rowCount()):
            time_item = self._table.item(row, 0)
            title_item = self._table.item(row, 1)
            if time_item and title_item:
                time_str = time_item.text()
                title = title_item.text()

                # 除外チャプターはスキップ
                if title.startswith("--"):
                    continue

                # ChapterInfoを使ってYouTube形式に変換
                chapter = ChapterInfo.from_time_str(time_str, title)
                chapters.append(chapter)

        if not chapters:
            self._log_panel.warning("No chapters to copy", source="UI")
            return

        # YouTube形式でテキスト生成
        lines = []
        for ch in chapters:
            lines.append(f"{ch.time_str_youtube} {ch.title}")

        youtube_text = "\n".join(lines)

        # クリップボードにコピー
        clipboard = QApplication.clipboard()
        clipboard.setText(youtube_text)

        self._log_panel.info(f"Copied {len(chapters)} chapters to clipboard (YouTube format)", source="UI")

    def paste_chapters(self):
        """クリップボードからチャプターをペースト

        サポートする形式:
        - YouTube形式: HH:MM:SS タイトル or MM:SS タイトル
        - 詳細形式: HH:MM:SS.mmm タイトル or MM:SS.mmm タイトル

        YouTube形式（ミリ秒なし）の場合は.000でパディング。
        """
        clipboard = QApplication.clipboard()
        text = clipboard.text()

        if not text or not text.strip():
            self._log_panel.warning("Clipboard is empty", source="Paste")
            return

        lines = text.strip().split('\n')
        chapters = []

        # 時間パターン: HH:MM:SS.mmm, HH:MM:SS, MM:SS.mmm, MM:SS
        time_pattern = re.compile(r'^(\d{1,2}:\d{2}:\d{2}(?:\.\d{1,3})?|\d{1,2}:\d{2}(?:\.\d{1,3})?)\s+(.+)$')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = time_pattern.match(line)
            if match:
                time_str = match.group(1)
                title = match.group(2).strip()

                # ChapterInfo.from_time_str は自動でミリ秒なしを0パディング
                try:
                    chapter = ChapterInfo.from_time_str(time_str, title)
                    chapters.append(chapter)
                except Exception as e:
                    self._log_panel.warning(f"Parse error: {line} ({e})", source="Paste")
            else:
                # マッチしない行はスキップ（空行やコメント行）
                if line and not line.startswith('#'):
                    self._log_panel.debug(f"Skipped: {line}", source="Paste")

        if not chapters:
            self._log_panel.warning("No valid chapters found in clipboard", source="Paste")
            return

        # 既存のチャプターをクリア
        self._table.setRowCount(0)

        # 新しいチャプターを追加
        default_color = QColor("#f0f0f0")
        for ch in chapters:
            row = self._table.rowCount()
            self._table.insertRow(row)

            time_item = QTableWidgetItem(ch.time_str)
            title_item = QTableWidgetItem(ch.title)

            time_item.setData(Qt.ItemDataRole.UserRole, default_color)
            title_item.setData(Qt.ItemDataRole.UserRole, default_color)

            self._table.setItem(row, 0, time_item)
            self._table.setItem(row, 1, title_item)

        self._state.chapters = chapters
        self._update_waveform_chapters()
        self._log_panel.info(f"Pasted {len(chapters)} chapters from clipboard", source="Paste")

    # === エクスポート ===

    def _get_table_chapters(self) -> List[ChapterInfo]:
        """テーブルからチャプター情報を取得"""
        chapters = []
        for row in range(self._table.rowCount()):
            time_item = self._table.item(row, 0)
            title_item = self._table.item(row, 1)
            if time_item and title_item:
                time_str = time_item.text()
                title = title_item.text()
                chapter = ChapterInfo.from_time_str(time_str, title)
                chapters.append(chapter)
        return chapters

    def _start_export(self):
        """エクスポート開始"""
        # 複数音声ファイルの場合は先に結合
        input_path = self._state.video_path
        is_multi_audio = False

        if not input_path and len(self._state.sources) > 1:
            # 複数音声: 結合する
            is_multi_audio = True
            self._log_panel.info(
                f"Merging {len(self._state.sources)} audio files...",
                source="Export"
            )
            merged_path = self._merge_audio_files()
            if merged_path:
                input_path = merged_path
                self._log_panel.info(f"Merged: {merged_path.name}", source="Export")
            else:
                self._log_panel.error("Failed to merge audio files", source="Export")
                return

        # 入力検証
        if not input_path or not input_path.exists():
            self._log_panel.error("No video/audio loaded", source="Export")
            return

        # 出力ファイル名を決定（ベース名_chaptered.mp4）
        output_base = self._output_edit.text().strip()
        if not output_base:
            output_base = "output"
        # 拡張子を除去してベース名を取得
        output_base_path = Path(output_base)
        if output_base_path.suffix.lower() in {'.mp4', '.mov', '.avi', '.mkv', '.mp3', '.m4a'}:
            output_base = str(output_base_path.with_suffix(''))
        # _chaptered.mp4を付けて出力パスを作成
        output_path = self._state.work_dir / f"{Path(output_base).name}_chaptered.mp4"

        # 入力と出力が同じ場合は連番を付ける
        if input_path.resolve() == output_path.resolve():
            counter = 2
            while True:
                output_path = self._state.work_dir / f"{Path(output_base).name}_chaptered_{counter}.mp4"
                if not output_path.exists():
                    break
                counter += 1
            self._log_panel.info(f"Output renamed to avoid overwriting input: {output_path.name}", source="Export")

        output_path = str(output_path)

        # 設定を取得
        encoder_id = self._encoder_combo.currentData()
        bitrate, crf = self._quality_combo.currentData()
        embed_chapters = self._embed_chapters_cb.isChecked()
        cut_excluded = self._cut_excluded_cb.isChecked()

        # 「元と同じ」が選択されている場合の処理
        if bitrate == 0:
            base_bitrate = 4000  # デフォルト値
            if encoder_id == "libx264":
                # CPU: CRFモードで高画質（ビットレートは参考値）
                bitrate = base_bitrate
                crf = 18  # 高画質CRF
                self._log_panel.debug(f"Auto quality: CRF {crf}", source="Export")
            else:
                # GPU: ビットレート×1.5で再エンコード劣化を補償
                bitrate = int(base_bitrate * 1.5)
                self._log_panel.debug(f"Auto quality: {bitrate} kbps", source="Export")

        # テーブルからチャプターを取得
        chapters = self._get_table_chapters()

        # 色空間情報を取得（音声のみの場合はNone）
        colorspace = detect_video_colorspace(str(input_path)) if input_path.suffix.lower() in VIDEO_EXTENSIONS else None

        self._log_panel.info(f"Export started: {Path(output_path).name}", source="Export")
        self._log_panel.debug(f"Encoder: {encoder_id}, Bitrate: {bitrate}kbps, CRF: {crf}", source="Export")
        self._log_panel.debug(f"Chapters: {len(chapters)}, Embed: {embed_chapters}, Cut excluded: {cut_excluded}", source="Export")

        # ボタンをキャンセルモードに変更
        self._is_exporting = True
        self._export_btn.setText("Cancel")
        self._export_btn.setStyleSheet(self._button_style(danger=True))
        self._export_btn.setToolTip("エクスポートを中止")

        # 動画の長さを取得
        if is_multi_audio:
            # 複数音声の場合はチャプターから計算
            duration_ms = sum(src.duration_ms for src in self._state.sources)
        else:
            duration_ms = self._media_player.duration() if self._media_player else 0

        # カバー画像を取得
        cover_image_path = None
        if hasattr(self, '_cover_image') and self._cover_image is not None:
            # 一時ファイルに保存
            cover_image_path = Path(tempfile.gettempdir()) / "cover_image.jpg"
            self._cover_image.save(str(cover_image_path), "JPEG", 85)
            self._log_panel.debug(f"Cover image: {cover_image_path}", source="Export")

        # ExportWorkerを作成して開始
        self._export_worker = ExportWorker(
            input_file=str(input_path),
            output_file=output_path,
            chapters=chapters,
            embed_chapters=embed_chapters,
            embed_title=True,
            overlay_chapter_titles=True,  # チャプター名焼き込み有効
            total_duration_ms=duration_ms,
            encoder_id=encoder_id,
            bitrate_kbps=bitrate,
            crf=crf,
            colorspace=colorspace,
            cut_excluded=cut_excluded,
            cover_image=str(cover_image_path) if cover_image_path else None,
            is_audio_only=input_path.suffix.lower() in AUDIO_EXTENSIONS
        )

        # シグナル接続
        self._export_worker.progress_update.connect(self._on_export_progress)
        self._export_worker.progress_percent.connect(self._on_export_percent)
        self._export_worker.export_completed.connect(self._on_export_completed)
        self._export_worker.error_occurred.connect(self._on_export_error)

        self._export_worker.start()
        self.export_requested.emit()

    def _on_export_progress(self, message: str):
        """エクスポート進捗メッセージ"""
        self._log_panel.info(message, source="Export")

    def _on_export_percent(self, percent: int, status: str):
        """エクスポート進捗パーセント"""
        # ステータスバー用シグナル
        self.export_progress.emit(percent, f"{status} {percent}%")

    def _on_export_completed(self, output_path: str):
        """エクスポート完了"""
        self._log_panel.info(f"Export completed: {Path(output_path).name}", source="Export")
        # ボタンをExportモードに戻す
        self._reset_export_btn()
        # ステータスバー用シグナル
        self.export_finished.emit(True, Path(output_path).name)

        # エクスポート完了後、出力動画をメイン画面に読み込み（確認用）
        # 注: 再エクスポート時は焼き込みテキストが二重になる可能性あり
        self._load_exported_video(output_path)

    def _load_exported_video(self, video_path: str):
        """エクスポート完了後に出力動画を読み込む"""
        output_file = Path(video_path)
        if not output_file.exists():
            self._log_panel.warning(f"Output file not found: {video_path}", source="Export")
            return

        self._log_panel.info(f"Loading exported video: {output_file.name}", source="Export")

        # 状態更新
        self._state.video_path = output_file

        # メディアプレーヤーに読み込み
        self._media_player.setSource(QUrl.fromLocalFile(str(output_file)))
        self._play_btn.setEnabled(True)

        # 動画モードに切り替え（品質選択を有効化）
        self._update_quality_combo_for_mode(is_audio=False)

        # 波形生成をリセットして再生成
        self._spectrogram_generated = False
        self._start_waveform_generation(output_file)

        # 注: 埋め込みチャプターは読み込まない
        # 再エクスポート時にチャプター名が二重焼き込みになるのを防ぐため
        # チャプターリストは編集前の状態を維持
        self._log_panel.debug("Chapters preserved (not reloaded from exported video)", source="Export")

    def _on_export_error(self, error: str):
        """エクスポートエラー"""
        self._log_panel.error(f"Export failed: {error}", source="Export")
        # ボタンをExportモードに戻す
        self._reset_export_btn()
        # ステータスバー用シグナル
        self.export_finished.emit(False, error[:50])

    def _on_export_btn_clicked(self):
        """Export/Cancelボタンクリック"""
        if self._is_exporting:
            self._cancel_export()
        else:
            self._start_export()

    def _cancel_export(self):
        """エクスポートを中止"""
        if hasattr(self, '_export_worker') and self._export_worker is not None:
            self._log_panel.warning("Export cancellation requested...", source="Export")
            self._export_worker.cancel()
            # ボタンを無効化してキャンセル中表示
            self._export_btn.setEnabled(False)
            self._export_btn.setText("Cancelling...")

    def _reset_export_btn(self):
        """Exportボタンを初期状態に戻す"""
        self._is_exporting = False
        self._export_btn.setText("Export")
        self._export_btn.setStyleSheet(self._button_style(primary=True))
        self._export_btn.setToolTip("編集した動画を書き出す")
        self._export_btn.setEnabled(True)

    # === 公開API ===

    def get_log_panel(self) -> LogPanel:
        """ログパネルを取得"""
        return self._log_panel

    def get_state(self) -> ProjectState:
        """プロジェクト状態を取得"""
        return self._state

    def load_video_file(self, path: Path):
        """動画ファイルを読み込み（外部API）"""
        self._state.video_path = path
        self._media_player.setSource(QUrl.fromLocalFile(str(path)))
        self._play_btn.setEnabled(True)
        self._log_panel.info(f"Loaded: {path.name}", source="Video")

        # 波形生成を開始（別スレッド）
        self._start_waveform_generation(path)

    # === ドラッグ＆ドロップハンドラ ===

    def _on_files_dropped(self, file_paths: list):
        """ファイルドロップ時の処理

        - 動画: 最初の1つのみ読み込み
        - 音声: 複数の場合は結合リストとして処理
        """
        if not file_paths:
            return

        videos = []
        audios = []

        for path_str in file_paths:
            path = Path(path_str)
            ext = path.suffix.lower()
            if ext in VIDEO_EXTENSIONS:
                videos.append(path)
            elif ext in AUDIO_EXTENSIONS:
                audios.append(path)

        # 動画を優先（最初の1つのみ）
        if videos:
            video_path = videos[0]
            # ソースをクリアして新しい動画を設定
            self._state.sources = [SourceFile(path=video_path)]
            self._on_source_changed()
            self._log_panel.info(f"Dropped video: {video_path.name}", source="Drop")
        elif audios:
            # 音声ファイル: ソースとして設定
            self._state.sources = [SourceFile(path=p) for p in audios]
            self._on_source_changed()
            if len(audios) == 1:
                self._log_panel.info(f"Dropped audio: {audios[0].name}", source="Drop")
            else:
                self._log_panel.info(f"Dropped {len(audios)} audio files", source="Drop")

    def _on_folder_dropped(self, folder_path: str):
        """フォルダドロップ時の処理: 作業ディレクトリとして設定"""
        path = Path(folder_path)
        if not path.is_dir():
            return

        self._state.work_dir = path
        self._log_panel.info(f"Working directory changed: {path}", source="Drop")

        # フォルダ内のメディアファイルをスキャン
        media_files = []
        for ext in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
            media_files.extend(path.glob(f"*{ext}"))
            media_files.extend(path.glob(f"*{ext.upper()}"))

        # 重複を除去してソート
        media_files = sorted(set(media_files), key=lambda p: p.name.lower())

        if media_files:
            # 最初の動画、または音声ファイルをソースとして設定
            videos = [f for f in media_files if f.suffix.lower() in VIDEO_EXTENSIONS]
            if videos:
                self._state.sources = [SourceFile(path=videos[0])]
                self._on_source_changed()
                self._log_panel.info(f"Found {len(videos)} video(s), loaded: {videos[0].name}", source="Drop")
            else:
                # 音声のみの場合は全て読み込み
                audios = [f for f in media_files if f.suffix.lower() in AUDIO_EXTENSIONS]
                self._state.sources = [SourceFile(path=p) for p in audios]
                self._on_source_changed()
                self._log_panel.info(f"Found {len(audios)} audio file(s)", source="Drop")
        else:
            self._log_panel.info("No media files found in folder", source="Drop")

    def cleanup(self):
        """リソースクリーンアップ"""
        self._cleanup_waveform_thread()

        if self._media_player:
            self._media_player.stop()

    def closeEvent(self, event):
        """ウィジェット終了時"""
        self.cleanup()
        super().closeEvent(event)

    def eventFilter(self, obj, event):
        """イベントフィルター: テーブルのEnter/ダブルクリック処理"""
        # テーブル本体: Enterキーで編集開始、編集中の上下矢印処理
        if obj == self._table:
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()

                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    # 編集中の場合はデフォルト処理（編集確定）に任せる
                    if self._table.state() == QAbstractItemView.State.EditingState:
                        return False  # デフォルト処理に委譲
                    # 編集中でなければ編集開始
                    index = self._table.currentIndex()
                    if index.isValid():
                        # 一時的にトリガーを有効にして編集開始
                        self._table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
                        self._table.edit(index)
                        # 編集開始後すぐにトリガーを無効に戻す（編集中の状態は維持される）
                        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                        return True

                # 編集中の上下矢印: カーソル移動（セル移動ではなく）
                if self._table.state() == QAbstractItemView.State.EditingState:
                    if key == Qt.Key.Key_Up:
                        # 上矢印: カーソルを先頭へ
                        editor = self._table.findChild(QLineEdit)
                        if editor:
                            editor.setCursorPosition(0)
                            return True
                    elif key == Qt.Key.Key_Down:
                        # 下矢印: カーソルを末尾へ
                        editor = self._table.findChild(QLineEdit)
                        if editor:
                            editor.setCursorPosition(len(editor.text()))
                            return True

        # ビューポート: ダブルクリックでシーク
        elif obj == self._table.viewport():
            if event.type() == QEvent.Type.MouseButtonDblClick:
                # ビューポート座標でセルを検出
                pos = event.position().toPoint()
                index = self._table.indexAt(pos)
                if index.isValid():
                    self._on_chapter_clicked(index.row(), index.column())
                return True  # 編集をブロック
        return super().eventFilter(obj, event)
