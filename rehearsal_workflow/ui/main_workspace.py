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
    QSplitter, QComboBox, QLineEdit, QGroupBox, QProgressBar,
    QSizePolicy, QAbstractItemView, QSlider, QFileDialog, QDialog,
    QCheckBox, QSpinBox, QApplication, QStackedLayout, QAbstractButton
)
from PySide6.QtCore import Qt, Signal, QUrl, QThread, QObject, QTimer, QEvent, QMimeData, QPoint
from PySide6.QtGui import QFont, QFontDatabase, QPainter, QColor, QPen, QBrush, QPixmap, QIcon, QPolygon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget

import platform
import re
import subprocess
import tempfile
import os

from .log_panel import LogPanel, LogLevel
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
from .workers import (
    WaveformWorker, SpectrogramWorker, ExportWorker, SplitExportWorker,
    YouTubeDownloadWorker, PlaylistInfoWorker, PlaylistDownloadWorker
)
from .widgets import WaveformWidget, CenteredFileDialog
from .ffmpeg_utils import get_ffmpeg_path, get_ffprobe_path, extract_chapters_with_ffmpeg, get_subprocess_kwargs
from .dialogs import ExportSettingsDialog, PlaylistVideoSelectionDialog, ReorderSourcesDialog


# ファイル拡張子定義
AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.wav', '.aac', '.flac'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}


def get_icon_path(icon_name: str) -> Path:
    """アイコンファイルのパスを取得（開発/バンドル両対応）"""
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstallerバンドル
        base = Path(sys._MEIPASS) / 'rehearsal_workflow' / 'ui' / 'icons'
    else:
        # 開発環境
        base = Path(__file__).parent / 'icons'
    return base / icon_name


class DropOverlay(QWidget):
    """
    動画ウィジェットの上に配置する透明なドロップオーバーレイ

    QVideoWidgetは内部に複雑なウィジェット構造を持つため、
    親フレームでのドロップイベント受信が困難。
    このオーバーレイを動画の上に配置してドロップを受け取る。
    """

    files_dropped = Signal(list)
    folder_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drag_active = False
        # 透明にしてマウスイベントはドロップのみ受け取る
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event):
        # マウスクリックは下のウィジェットに透過（ドラッグ以外）
        event.ignore()

    def mouseReleaseEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        event.ignore()

    def dragEnterEvent(self, event):
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.is_dir():
                        event.acceptProposedAction()
                        self._drag_active = True
                        self._update_style(True)
                        return
                    ext = path.suffix.lower()
                    if ext in VIDEO_EXTENSIONS or ext in AUDIO_EXTENSIONS:
                        event.acceptProposedAction()
                        self._drag_active = True
                        self._update_style(True)
                        return
        event.ignore()

    def dragMoveEvent(self, event):
        # ドラッグ中も受け入れ続ける
        if self._drag_active:
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._drag_active = False
        self._update_style(False)
        event.accept()

    def dropEvent(self, event):
        self._drag_active = False
        self._update_style(False)

        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            event.ignore()
            return

        files = []
        folder = None

        for url in mime_data.urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_dir():
                    if folder is None:
                        folder = str(path)
                else:
                    ext = path.suffix.lower()
                    if ext in VIDEO_EXTENSIONS or ext in AUDIO_EXTENSIONS:
                        files.append(str(path))

        if folder:
            self.folder_dropped.emit(folder)
        elif files:
            self.files_dropped.emit(files)

        event.acceptProposedAction()

    def _update_style(self, active: bool):
        if active:
            self.setStyleSheet("""
                background: rgba(59, 130, 246, 0.2);
                border: 2px solid #3b82f6;
                border-radius: 4px;
            """)
        else:
            self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event):
        # マウスクリックは下のウィジェットに透過
        event.ignore()

    def mouseReleaseEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        event.ignore()


class AudioDeviceComboBox(QComboBox):
    """
    ポップアップ表示時にデバイスリストを更新するコンボボックス

    アプリ起動後にオーディオデバイスを接続しても選択可能にする。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._refresh_callback = None

    def set_refresh_callback(self, callback):
        """デバイスリスト更新用のコールバックを設定"""
        self._refresh_callback = callback

    def showPopup(self):
        """ポップアップ表示時にデバイスリストを更新"""
        if self._refresh_callback:
            self._refresh_callback()
        super().showPopup()


class DragDropTableWidget(QTableWidget):
    """
    挿入位置を線で表示するドラッグ＆ドロップ対応テーブル

    デフォルトの行ハイライト表示ではなく、
    挿入位置を示す水平線を描画する。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drop_indicator_row = -1  # 挿入位置（-1: 非表示）
        self._drop_indicator_above = True  # True: 行の上、False: 行の下
        # デフォルトのドロップインジケーターを非表示
        self.setDropIndicatorShown(False)

    def dragMoveEvent(self, event):
        """ドラッグ中の挿入位置を計算"""
        pos = event.position().toPoint()
        index = self.indexAt(pos)

        if index.isValid():
            # 行の中央より上か下かで挿入位置を決定
            row_rect = self.visualRect(index)
            row_center = row_rect.top() + row_rect.height() // 2

            if pos.y() < row_center:
                self._drop_indicator_row = index.row()
                self._drop_indicator_above = True
            else:
                self._drop_indicator_row = index.row()
                self._drop_indicator_above = False
        else:
            # 有効な行がない場合は最後に挿入
            self._drop_indicator_row = self.rowCount() - 1
            self._drop_indicator_above = False

        self.viewport().update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        """ドラッグ終了時にインジケーターを非表示"""
        self._drop_indicator_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        """ドロップ時にインジケーターを非表示"""
        self._drop_indicator_row = -1
        self.viewport().update()
        super().dropEvent(event)

    def paintEvent(self, event):
        """挿入位置インジケーターを描画"""
        super().paintEvent(event)

        if self._drop_indicator_row < 0:
            return

        # インジケーターの位置を計算
        if self._drop_indicator_row < self.rowCount():
            index = self.model().index(self._drop_indicator_row, 0)
            row_rect = self.visualRect(index)

            if self._drop_indicator_above:
                y = row_rect.top()
            else:
                y = row_rect.bottom()
        else:
            # 最後の行の下
            if self.rowCount() > 0:
                index = self.model().index(self.rowCount() - 1, 0)
                row_rect = self.visualRect(index)
                y = row_rect.bottom()
            else:
                return

        # 水平線を描画
        painter = QPainter(self.viewport())
        pen = QPen(QColor("#ef4444"))  # 赤色
        pen.setWidth(3)
        painter.setPen(pen)

        # 左端から右端まで線を引く
        width = self.viewport().width()
        painter.drawLine(0, y, width, y)

        # 両端に小さな三角形を描画（挿入位置を強調）
        triangle_size = 6
        painter.setBrush(QBrush(QColor("#ef4444")))
        painter.setPen(Qt.PenStyle.NoPen)

        # 左側の三角形
        left_triangle = [
            QPoint(0, y - triangle_size),
            QPoint(triangle_size, y),
            QPoint(0, y + triangle_size),
        ]
        painter.drawPolygon(QPolygon(left_triangle))

        # 右側の三角形
        right_triangle = [
            QPoint(width, y - triangle_size),
            QPoint(width - triangle_size, y),
            QPoint(width, y + triangle_size),
        ]
        painter.drawPolygon(QPolygon(right_triangle))

        painter.end()


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


class SourceListWidget(QWidget):
    """
    ソースリストウィジェット

    常時表示。単一ファイル時は1行、複数ファイル時は3行表示。
    """

    source_clicked = Signal(int)  # ソースインデックスがクリックされた
    open_clicked = Signal()  # Openボタンがクリックされた

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sources: List[SourceFile] = []
        self._current_index: int = 0
        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # 左側: ソース情報
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # タイトル（ファイル数に応じてSource/Sourcesを切り替え）
        self._title_label = QLabel("Source")
        self._title_label.setStyleSheet("font-weight: bold; color: #f0f0f0; padding-bottom: 4px;")
        left_layout.addWidget(self._title_label)

        # 3行のラベル（prev / current / next）- 必要に応じて表示/非表示
        self._rows: List[QLabel] = []
        for i in range(3):
            row = QLabel()
            row.setStyleSheet(self._get_row_style(i == 1))  # 中央行がカレント
            row.setFixedHeight(24)
            row.mousePressEvent = lambda e, idx=i: self._on_row_clicked(idx)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            left_layout.addWidget(row)
            self._rows.append(row)

        main_layout.addWidget(left_widget, stretch=1)

        # 右側: Openボタン
        self._open_btn = QPushButton("Open")
        self._open_btn.setFixedHeight(28)
        self._open_btn.setFixedWidth(80)
        self._open_btn.setStyleSheet("""
            QPushButton {
                background: #3b82f6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #2563eb;
            }
        """)
        self._open_btn.setToolTip("音声/動画ファイルを選択")
        self._open_btn.clicked.connect(self.open_clicked.emit)
        main_layout.addWidget(self._open_btn, alignment=Qt.AlignmentFlag.AlignTop)

        # 初期表示を更新
        self._update_display()

    def _get_row_style(self, is_current: bool) -> str:
        """行のスタイルを取得"""
        if is_current:
            return """
                QLabel {
                    background: #14b8a6;
                    color: #000000;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QLabel:hover {
                    background: #0d9488;
                }
            """
        else:
            return """
                QLabel {
                    background: transparent;
                    color: #808080;
                    padding: 4px 8px;
                }
                QLabel:hover {
                    background: #2a2a2a;
                    border-radius: 4px;
                }
            """

    def _on_row_clicked(self, row_index: int):
        """行クリック時の処理"""
        # row_index: 0=prev, 1=current, 2=next
        source_index = self._current_index + (row_index - 1)
        if 0 <= source_index < len(self._sources):
            self.source_clicked.emit(source_index)

    def set_sources(self, sources: List[SourceFile]):
        """ソースリストを設定"""
        self._sources = sources
        self._current_index = 0
        self._update_display()
        # 常時表示（非表示にしない）

    def set_current_index(self, index: int):
        """現在のソースインデックスを設定"""
        if 0 <= index < len(self._sources):
            self._current_index = index
            self._update_display()

    def get_current_index(self) -> int:
        """現在のソースインデックスを取得"""
        return self._current_index

    def _update_display(self):
        """表示を更新"""
        num_sources = len(self._sources)

        # タイトル更新（0-1: Source, 2+: Sources）
        self._title_label.setText("Sources" if num_sources >= 2 else "Source")

        if num_sources == 0:
            # ソースなし: 1行目に「No source」表示
            self._rows[0].setText("No source selected")
            self._rows[0].setStyleSheet(self._get_row_style(False))
            self._rows[0].setVisible(True)
            self._rows[0].setCursor(Qt.CursorShape.ArrowCursor)
            self._rows[1].setVisible(False)
            self._rows[2].setVisible(False)
        elif num_sources == 1:
            # 単一ファイル: 1行のみ表示
            source = self._sources[0]
            name = source.path.name
            duration = self._format_duration(source.duration_ms)
            self._rows[0].setText(f"▶ {name}  ({duration})")
            self._rows[0].setStyleSheet(self._get_row_style(True))
            self._rows[0].setVisible(True)
            self._rows[0].setCursor(Qt.CursorShape.ArrowCursor)
            self._rows[1].setVisible(False)
            self._rows[2].setVisible(False)
        else:
            # 複数ファイル: 3行表示（prev / current / next）
            for i, row in enumerate(self._rows):
                source_idx = self._current_index + (i - 1)  # -1, 0, +1
                if 0 <= source_idx < num_sources:
                    source = self._sources[source_idx]
                    name = source.path.name
                    duration = self._format_duration(source.duration_ms)
                    if i == 1:  # 現在のファイル
                        row.setText(f"▶ {name}  ({duration})")
                    else:
                        row.setText(f"   {name}  ({duration})")
                    row.setVisible(True)
                    row.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    row.setText("")
                    row.setVisible(False)
                row.setStyleSheet(self._get_row_style(i == 1))

    def _format_duration(self, ms: int) -> str:
        """ミリ秒を mm:ss 形式に変換"""
        if ms <= 0:
            return "--:--"
        total_sec = ms // 1000
        m, s = divmod(total_sec, 60)
        return f"{m}:{s:02d}"


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
    work_dir_changed = Signal(object)  # Path - 作業ディレクトリ変更

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

        # YouTube URL（ダウンロード用）
        self._youtube_url = ""

        # YouTubeダウンロードワーカー
        self._youtube_worker: Optional[YouTubeDownloadWorker] = None

        # プレイリストダウンロードワーカー
        self._playlist_info_worker: Optional[PlaylistInfoWorker] = None
        self._playlist_worker: Optional[PlaylistDownloadWorker] = None

        # 埋め込みチャプターフラグ（MP4から読み込んだチャプターがあるか）
        self._has_embedded_chapters = False

        # 音声のみモード（MP3等からのエクスポート時は静止画用固定）
        self._is_audio_only = False

        # 現在再生中のチャプター行（ハイライト用）
        self._current_chapter_row = -1

        # チャプターが編集されたかどうか（スキップボタン有効化用）
        self._chapters_edited = False

        # 仮想タイムライン: ファイル切替後のシーク位置
        self._pending_seek_position: Optional[int] = None
        self._target_source_url: Optional[QUrl] = None  # 切替先のソースURL

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

        # === 上段: YouTube URL入力 ===
        youtube_row = QHBoxLayout()
        youtube_row.setSpacing(8)

        youtube_label = QLabel("YouTube")
        youtube_label.setStyleSheet("font-weight: bold; color: #f0f0f0;")
        youtube_row.addWidget(youtube_label)

        self._youtube_url_edit = QLineEdit()
        self._youtube_url_edit.setPlaceholderText("https://youtube.com/watch?v=... or https://youtu.be/...")
        self._youtube_url_edit.setStyleSheet("""
            QLineEdit {
                background: #0f0f0f;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #ef4444;
            }
        """)
        self._youtube_url_edit.returnPressed.connect(self._start_youtube_download)
        youtube_row.addWidget(self._youtube_url_edit, stretch=1)

        self._youtube_download_btn = QPushButton("DL")
        self._youtube_download_btn.setFixedWidth(80)
        self._youtube_download_btn.setFixedHeight(28)
        self._youtube_download_btn.setStyleSheet(self._youtube_btn_style_normal())
        self._youtube_download_btn.clicked.connect(self._start_youtube_download)
        youtube_row.addWidget(self._youtube_download_btn)

        main_layout.addLayout(youtube_row)

        # YouTubeダウンロード進捗バー（通常は非表示）
        self._youtube_progress = QProgressBar()
        self._youtube_progress.setFixedHeight(4)
        self._youtube_progress.setTextVisible(False)
        self._youtube_progress.setStyleSheet("""
            QProgressBar {
                background: #2d2d2d;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: #84cc16;
                border-radius: 2px;
            }
        """)
        self._youtube_progress.setVisible(False)
        main_layout.addWidget(self._youtube_progress)

        # === 下段: ソースリスト + Openボタン ===
        self._source_list = SourceListWidget()
        self._source_list.source_clicked.connect(self._on_source_clicked)
        self._source_list.open_clicked.connect(self._open_source_dialog)
        main_layout.addWidget(self._source_list)

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
        self._audio_output.setVolume(1.0)  # OSボリュームに任せる

        # シグナル接続
        self._media_player.positionChanged.connect(self._on_position_changed)
        self._media_player.durationChanged.connect(self._on_duration_changed)
        self._media_player.errorOccurred.connect(self._on_media_error)
        self._media_player.mediaStatusChanged.connect(self._on_media_status_changed)

        # === 中央揃えのコントロール行（movie-viewerスタイル）===
        ctrl_row = QHBoxLayout()
        ctrl_row.addStretch()  # 左側スペーサー

        # 時間移動ボタンのスタイル（戻る系: パステルブルー）
        back_btn_style = """
            QPushButton {
                background: #2a3a4d;
                color: #a8c8e8;
                border: 1px solid #3a5068;
                border-radius: 12px;
                font-size: 18px;
                font-weight: bold;
                padding: 4px 2px;
            }
            QPushButton:hover {
                background: #354a5f;
            }
            QPushButton:pressed {
                background: #405a70;
            }
            QPushButton:disabled {
                background: #1a2530;
                color: #4a5a6a;
            }
        """

        # 時間移動ボタンのスタイル（進む系: パステルブルーに統一）
        forward_btn_style = back_btn_style

        # -10s
        self._btn_m10s = QPushButton("-10s")
        self._btn_m10s.setStyleSheet(back_btn_style)
        self._btn_m10s.setFixedSize(55, 45)
        self._btn_m10s.setToolTip("10秒戻る")
        self._btn_m10s.clicked.connect(lambda: self._seek_relative(-10000))
        self._btn_m10s.setEnabled(False)
        ctrl_row.addWidget(self._btn_m10s)

        # -1s
        self._btn_m1s = QPushButton("-1s")
        self._btn_m1s.setStyleSheet(back_btn_style)
        self._btn_m1s.setFixedSize(55, 45)
        self._btn_m1s.setToolTip("1秒戻る")
        self._btn_m1s.clicked.connect(lambda: self._seek_relative(-1000))
        self._btn_m1s.setEnabled(False)
        ctrl_row.addWidget(self._btn_m1s)

        # -.3s
        self._btn_m03s = QPushButton("-.3s")
        self._btn_m03s.setStyleSheet(back_btn_style)
        self._btn_m03s.setFixedSize(55, 45)
        self._btn_m03s.setToolTip("0.3秒戻る")
        self._btn_m03s.clicked.connect(lambda: self._seek_relative(-300))
        self._btn_m03s.setEnabled(False)
        ctrl_row.addWidget(self._btn_m03s)

        # -1f (約33ms @ 30fps)
        self._btn_m1f = QPushButton("-1f")
        self._btn_m1f.setStyleSheet(back_btn_style)
        self._btn_m1f.setFixedSize(55, 45)
        self._btn_m1f.setToolTip("1フレーム戻る")
        self._btn_m1f.clicked.connect(lambda: self._seek_relative(-33))
        self._btn_m1f.setEnabled(False)
        ctrl_row.addWidget(self._btn_m1f)

        # チャプタースキップボタンのスタイル
        # Windows: Segoe UI Symbolを使用して絵文字ではなくシンボルとして描画
        is_windows = platform.system() == "Windows"
        symbol_font_css = "font-family: 'Segoe UI Symbol';" if is_windows else ""

        # 前のチャプター（パステルブルー - 戻る系と統一）
        prev_chapter_style = f"""
            QPushButton {{
                background: #2a3a4d;
                color: #a8c8e8;
                border: 1px solid #3a5068;
                border-radius: 14px;
                font-size: 20px;
                font-weight: bold;
                {symbol_font_css}
            }}
            QPushButton:hover {{
                background: #354a5f;
            }}
            QPushButton:pressed {{
                background: #405a70;
            }}
            QPushButton:disabled {{
                background: #1a2530;
                color: #4a5a6a;
            }}
        """

        # 次のチャプター（パステルブルーに統一）
        next_chapter_style = prev_chapter_style

        # 前のチャプター
        self._prev_chapter_btn = QPushButton("|◀")
        self._prev_chapter_btn.setStyleSheet(prev_chapter_style)
        self._prev_chapter_btn.setFixedSize(50, 50)
        self._prev_chapter_btn.setToolTip("前のチャプター")
        self._prev_chapter_btn.clicked.connect(self._goto_prev_chapter)
        self._prev_chapter_btn.setEnabled(False)
        ctrl_row.addWidget(self._prev_chapter_btn)

        # Play/Pause - アイコンボタン（アイコン自体がボタン）
        self._play_icon = QIcon(str(get_icon_path('play.png')))
        self._pause_icon = QIcon(str(get_icon_path('pause.png')))
        self._play_btn = QPushButton()
        self._play_btn.setIcon(self._play_icon)
        self._play_btn.setFlat(True)
        self._play_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.2);
            }
            QPushButton:disabled {
                opacity: 0.3;
            }
        """)
        self._play_btn.setFixedSize(55, 55)
        from PySide6.QtCore import QSize
        self._play_btn.setIconSize(QSize(55, 55))
        self._play_btn.setToolTip("再生/一時停止 (Space)")
        self._play_btn.clicked.connect(self._toggle_playback)
        self._play_btn.setEnabled(False)
        ctrl_row.addWidget(self._play_btn)

        # 次のチャプター
        self._next_chapter_btn = QPushButton("▶|")
        self._next_chapter_btn.setStyleSheet(next_chapter_style)
        self._next_chapter_btn.setFixedSize(50, 50)
        self._next_chapter_btn.setToolTip("次のチャプター")
        self._next_chapter_btn.clicked.connect(self._goto_next_chapter)
        self._next_chapter_btn.setEnabled(False)
        ctrl_row.addWidget(self._next_chapter_btn)

        # +1f
        self._btn_p1f = QPushButton("+1f")
        self._btn_p1f.setStyleSheet(forward_btn_style)
        self._btn_p1f.setFixedSize(55, 45)
        self._btn_p1f.setToolTip("1フレーム進む")
        self._btn_p1f.clicked.connect(lambda: self._seek_relative(33))
        self._btn_p1f.setEnabled(False)
        ctrl_row.addWidget(self._btn_p1f)

        # +.3s
        self._btn_p03s = QPushButton("+.3s")
        self._btn_p03s.setStyleSheet(forward_btn_style)
        self._btn_p03s.setFixedSize(55, 45)
        self._btn_p03s.setToolTip("0.3秒進む")
        self._btn_p03s.clicked.connect(lambda: self._seek_relative(300))
        self._btn_p03s.setEnabled(False)
        ctrl_row.addWidget(self._btn_p03s)

        # +1s
        self._btn_p1s = QPushButton("+1s")
        self._btn_p1s.setStyleSheet(forward_btn_style)
        self._btn_p1s.setFixedSize(55, 45)
        self._btn_p1s.setToolTip("1秒進む")
        self._btn_p1s.clicked.connect(lambda: self._seek_relative(1000))
        self._btn_p1s.setEnabled(False)
        ctrl_row.addWidget(self._btn_p1s)

        # +10s
        self._btn_p10s = QPushButton("+10s")
        self._btn_p10s.setStyleSheet(forward_btn_style)
        self._btn_p10s.setFixedSize(55, 45)
        self._btn_p10s.setToolTip("10秒進む")
        self._btn_p10s.clicked.connect(lambda: self._seek_relative(10000))
        self._btn_p10s.setEnabled(False)
        ctrl_row.addWidget(self._btn_p10s)

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

        # 出力デバイス選択（ボリュームはOSに任せる）
        output_label = QLabel("Out:")
        output_label.setStyleSheet("color: #a0a0a0;")
        bottom_row.addWidget(output_label)

        self._audio_device_combo = AudioDeviceComboBox()
        self._audio_device_combo.setStyleSheet("""
            QComboBox {
                background: #1a1a1a;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 120px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1a1a1a;
                color: #f0f0f0;
                selection-background-color: #3b82f6;
            }
        """)
        self._audio_device_combo.setToolTip("音声出力デバイス")
        self._audio_device_combo.set_refresh_callback(self._populate_audio_devices)
        self._populate_audio_devices()
        self._audio_device_combo.currentIndexChanged.connect(self._on_audio_device_changed)
        bottom_row.addWidget(self._audio_device_combo)

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

        # === 出力ファイル名（編集可能）===
        output_row = QHBoxLayout()
        output_row.setSpacing(8)

        output_label = QLabel("Output:")
        output_label.setStyleSheet("""
            QLabel {
                color: #60a5fa;
                font-size: 15px;
                font-weight: bold;
            }
        """)
        output_row.addWidget(output_label)

        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("output filename")
        self._output_edit.setToolTip("出力ファイル名（拡張子は自動付与）")
        self._output_edit.setStyleSheet("""
            QLineEdit {
                background: #1a1a1a;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 10px 16px;
                font-size: 16px;
                font-weight: bold;
            }
            QLineEdit:focus {
                border: 1px solid #60a5fa;
            }
        """)
        output_row.addWidget(self._output_edit, stretch=1)

        browse_btn = QPushButton("...")
        browse_btn.setFixedSize(40, 40)
        browse_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a2a;
                color: #a0a0a0;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #3a3a3a;
                color: #f0f0f0;
            }
        """)
        browse_btn.setToolTip("出力先を変更")
        browse_btn.clicked.connect(self._browse_output)
        output_row.addWidget(browse_btn)

        main_layout.addLayout(output_row)

        # === 動画プレビュー（最大化）===
        # 外枠フレーム
        video_frame = QFrame()
        video_frame.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)
        video_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        video_outer_layout = QVBoxLayout(video_frame)
        video_outer_layout.setContentsMargins(4, 4, 4, 4)
        video_outer_layout.setSpacing(0)

        # 動画とオーバーレイを重ねるコンテナ（レイアウトなしで手動配置）
        self._video_container = QWidget()
        self._video_container.setObjectName("video_container")
        self._video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 動画ウィジェット（最下層）
        self._video_widget = QVideoWidget(self._video_container)
        self._video_widget.setObjectName("video_widget")
        self._video_widget.setStyleSheet("background: #0f0f0f; border-radius: 4px;")
        self._video_widget.setMinimumSize(400, 300)

        # Cover Image表示用（音声のみの場合）
        self._cover_image_label = QLabel(self._video_container)
        self._cover_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_image_label.setStyleSheet("background: #0f0f0f;")
        self._cover_image_label.hide()  # 初期状態は非表示

        # チャプター名オーバーレイ（音声モードのみ）
        # 動画モードではQVideoWidgetがCore Animation/AVFoundationを使用するため
        # オーバーレイ表示不可。エンコード時のdrawtext焼き込みは別途実施。
        # 音声モード設定: 下部（85%）、小さめ（3.5%）
        self._chapter_overlay_label = QLabel(self._video_container)
        self._chapter_overlay_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chapter_overlay_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._chapter_overlay_label.hide()

        self._chapter_overlay_enabled = True  # オーバーレイ表示フラグ（デフォルトON）

        # ドロップオーバーレイ（最上層）
        self._drop_overlay = DropOverlay(self._video_container)
        self._drop_overlay.files_dropped.connect(self._on_files_dropped)
        self._drop_overlay.folder_dropped.connect(self._on_folder_dropped)

        # リサイズイベントで子ウィジェットのサイズを調整
        self._video_container.installEventFilter(self)

        video_outer_layout.addWidget(self._video_container, stretch=1)
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

        # テーブル（カスタムドラッグ＆ドロップ対応）
        self._table = DragDropTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Time", "Title"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # 行番号（垂直ヘッダー）を表示
        self._table.verticalHeader().setVisible(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # 行単位選択（ドラッグ用）
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)  # 単一選択
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # Enterキーのみで編集
        # テーブル行のドラッグ＆ドロップ（_update_chapter_drag_enabled() で動的制御）
        self._table.setDragEnabled(False)  # 初期状態は無効
        self._table.setAcceptDrops(True)
        self._table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._table.verticalHeader().setSectionsMovable(False)
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
            QHeaderView {
                background: #000000;
            }
            QHeaderView::section {
                background: #000000;
                color: #a0a0a0;
                border: none;
                padding: 8px;
            }
            QTableCornerButton::section {
                background: #000000;
                color: #a0a0a0;
                border: none;
            }
        """)
        # コーナーウィジェットに「No.」ラベルを設定
        corner_btn = self._table.findChild(QAbstractButton)
        if corner_btn:
            corner_label = QLabel("No.")
            corner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            corner_label.setStyleSheet("background: #000000; color: #a0a0a0; padding: 4px;")
            corner_btn.setLayout(QVBoxLayout())
            corner_btn.layout().setContentsMargins(0, 0, 0, 0)
            corner_btn.layout().addWidget(corner_label)
        # チャプター編集後に波形を更新（ダブルクリックシークはeventFilterで処理）
        self._table.cellChanged.connect(self._on_chapter_edited)
        # 選択変更時にスタイル更新（両方のシグナルを接続してキーボード操作を確実にキャッチ）
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.currentCellChanged.connect(self._on_current_cell_changed)
        # 行ドラッグ＆ドロップはeventFilterでDrop処理（_sync_after_row_drop）
        layout.addWidget(self._table)

        # ボタン行
        btn_layout = QHBoxLayout()

        load_btn = QPushButton("Load")
        load_btn.setFixedHeight(40)
        load_btn.setStyleSheet(self._button_style())
        load_btn.clicked.connect(self._load_chapters)
        load_btn.setToolTip("チャプターファイルを読み込み")
        btn_layout.addWidget(load_btn)

        add_btn = QPushButton("Add")
        add_btn.setFixedHeight(40)
        add_btn.setStyleSheet(self._button_style())
        add_btn.setToolTip("現在位置にチャプター追加")
        add_btn.clicked.connect(self._add_chapter)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setFixedHeight(40)
        remove_btn.setStyleSheet(self._button_style())
        remove_btn.setToolTip("選択チャプターを削除")
        remove_btn.clicked.connect(self._remove_chapter)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        copy_btn = QPushButton("Copy YouTube")
        copy_btn.setFixedHeight(40)
        copy_btn.setStyleSheet(self._button_style())
        copy_btn.setToolTip("YouTube用チャプターをクリップボードにコピー")
        copy_btn.clicked.connect(self._copy_youtube_chapters)
        btn_layout.addWidget(copy_btn)

        layout.addLayout(btn_layout)

        return self._chapter_group

    def _create_export_section(self) -> QWidget:
        """4. 書出設定セクション（Settings + Export）"""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        # エンコーダリストを保持（ダイアログに渡すため）
        self._available_encoders = detect_available_encoders()

        # 品質オプションを保持（export時に参照）
        self._video_quality_options = [
            ("元と同じ (自動)", 0, 23),
            ("高画質 (6Mbps)", 6000, 20),
            ("標準 (4Mbps)", 4000, 23),
            ("軽量 (2Mbps)", 2000, 28),
            ("最小 (1Mbps)", 1000, 32),
        ]
        self._audio_quality_options = [
            ("静止画用 (CRF 32)", 500, 32),
        ]

        # === ボタン行: Settings + Export ===
        btn_frame = QFrame()
        btn_frame.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(12, 8, 12, 8)

        # Settingsボタン
        self._settings_btn = QPushButton("Settings")
        self._settings_btn.setFixedHeight(40)
        self._settings_btn.setStyleSheet(self._button_style())
        self._settings_btn.setToolTip("エクスポート設定を開く")
        self._settings_btn.clicked.connect(self._open_export_settings)
        btn_layout.addWidget(self._settings_btn)

        btn_layout.addStretch()

        # 書出ボタン（エクスポート中はキャンセルボタンに変化）
        self._export_btn = QPushButton("Export")
        self._export_btn.setFixedHeight(40)
        self._export_btn.setStyleSheet(self._button_style(primary=True))
        self._export_btn.setToolTip("編集した動画を書き出す")
        self._export_btn.clicked.connect(self._on_export_btn_clicked)
        self._is_exporting = False  # エクスポート状態フラグ
        btn_layout.addWidget(self._export_btn)

        container_layout.addWidget(btn_frame)

        return container

    def _open_export_settings(self):
        """エクスポート設定ダイアログを開く"""
        dialog = ExportSettingsDialog(
            self,
            available_encoders=self._available_encoders,
            is_audio_only=self._is_audio_only,
            cover_image=self._cover_image
        )
        dialog.cover_image_changed.connect(self._on_cover_image_changed)
        dialog.exec()

    def _on_cover_image_changed(self, cover_image):
        """カバー画像変更時のハンドラ"""
        self._cover_image = cover_image
        self._log_panel.info(f"Cover image updated, is_audio_only={self._is_audio_only}", source="UI")
        # 音声のみの場合はCover Imageを表示
        if self._is_audio_only:
            self._update_cover_image_display()
        else:
            self._log_panel.debug("Skipping cover image display (not audio only)", source="UI")

    def _resize_video_overlays(self):
        """ビデオコンテナ内の全ウィジェットをリサイズ"""
        if not hasattr(self, '_video_container'):
            return

        size = self._video_container.size()
        rect = self._video_container.rect()

        # 全ウィジェットをコンテナサイズに合わせる
        self._video_widget.setGeometry(rect)
        self._cover_image_label.setGeometry(rect)
        self._drop_overlay.setGeometry(rect)

        # Cover Image が表示中なら再スケール（先に処理してz-orderを確保）
        if self._cover_image is not None and self._cover_image_label.isVisible():
            self._update_cover_image_display()

        # チャプターオーバーレイを更新（音声モードのみ）
        if self._is_audio_only and self._chapter_overlay_label.isVisible():
            container_height = rect.height()
            # 音声モード設定: 下部（85%）、小さめ（3.5%）
            font_size = max(10, int(container_height * 0.035))
            self._chapter_overlay_label.setStyleSheet(f"""
                QLabel {{
                    color: white;
                    font-size: {font_size}px;
                    font-weight: bold;
                    background-color: rgba(0, 0, 0, 0.6);
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    padding: 8px 12px;
                    border-radius: 4px;
                }}
            """)
            self._chapter_overlay_label.adjustSize()
            label_size = self._chapter_overlay_label.size()
            x = (rect.width() - label_size.width()) // 2
            y = int(container_height * 0.85 - label_size.height() / 2)
            self._chapter_overlay_label.move(x, y)
            self._chapter_overlay_label.raise_()

    def _update_cover_image_display(self):
        """Cover Image表示を更新"""
        if not hasattr(self, '_cover_image_label'):
            self._log_panel.debug("No _cover_image_label", source="UI")
            return

        # まずジオメトリを設定（レイアウトがないため手動で設定が必要）
        container_rect = self._video_container.rect()
        self._cover_image_label.setGeometry(container_rect)
        self._log_panel.debug(f"Cover image label geometry: {container_rect.x()},{container_rect.y()} {container_rect.width()}x{container_rect.height()}", source="UI")

        if self._cover_image is not None:
            # QImageをQLabelのサイズに合わせてスケール
            pixmap = QPixmap.fromImage(self._cover_image)
            label_size = self._cover_image_label.size()
            self._log_panel.debug(f"Cover image label size: {label_size.width()}x{label_size.height()}", source="UI")
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    label_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._cover_image_label.setPixmap(scaled)
                self._cover_image_label.show()
                self._cover_image_label.raise_()  # 前面に持ってくる
                self._video_widget.lower()  # 動画ウィジェットを最下層に
                # チャプターオーバーレイは常に最前面
                if hasattr(self, '_chapter_overlay_label'):
                    self._chapter_overlay_label.raise_()
                self._log_panel.info(f"Cover image displayed: {scaled.width()}x{scaled.height()}", source="UI")
            else:
                self._cover_image_label.clear()
                self._cover_image_label.hide()
                self._log_panel.debug("Cover image pixmap is null", source="UI")
        else:
            self._cover_image_label.clear()
            self._cover_image_label.hide()
            self._log_panel.debug("No cover image set", source="UI")

    def _show_cover_image_for_audio(self):
        """音声ファイルの場合にCover Image（または黒背景）を表示"""
        if not self._is_audio_only:
            self._cover_image_label.hide()
            self._video_widget.show()  # 動画モードでは動画ウィジェットを表示
            # 動画モード: オーバーレイは使用しない
            if hasattr(self, '_chapter_overlay_label'):
                self._chapter_overlay_label.hide()
            return

        # 音声のみの場合は動画ウィジェットを非表示
        self._video_widget.hide()

        # ジオメトリを設定
        container_rect = self._video_container.rect()
        self._cover_image_label.setGeometry(container_rect)
        self._log_panel.debug(f"Cover image geometry set: {container_rect.width()}x{container_rect.height()}", source="UI")

        if self._cover_image is not None:
            self._update_cover_image_display()
        else:
            # Cover Imageがない場合は黒背景のまま表示
            self._cover_image_label.clear()
            self._cover_image_label.setStyleSheet("background: #0f0f0f;")
            self._cover_image_label.show()
            self._cover_image_label.raise_()
            # チャプターオーバーレイは常に最前面
            if hasattr(self, '_chapter_overlay_label'):
                self._chapter_overlay_label.raise_()

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

    def _youtube_btn_style_normal(self) -> str:
        """YouTubeダウンロードボタン: 通常時（青）"""
        return """
            QPushButton {
                background: #3b82f6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #2563eb;
            }
            QPushButton:disabled {
                background: #1e3a5f;
                color: #666666;
            }
        """

    def _youtube_btn_style_processing(self) -> str:
        """YouTubeダウンロードボタン: 処理中（赤）"""
        return """
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #dc2626;
            }
            QPushButton:disabled {
                background: #dc2626;
                color: white;
            }
        """

    # === 動画操作 ===

    def _load_source_media(self):
        """ソースからメディアを読み込み"""
        if not self._state.sources:
            return

        # ソースリストを更新
        self._source_list.set_sources(self._state.sources)

        # ファイル拡張子で判定
        VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}
        AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.wav', '.aac', '.flac'}

        first_source = self._state.sources[0]
        file_path = first_source.path
        ext = file_path.suffix.lower()

        if ext in VIDEO_EXTENSIONS:
            # 動画モード: 品質選択を有効化
            self._update_quality_combo_for_mode(is_audio=False)

            if len(self._state.sources) == 1:
                # 単一動画: そのまま読み込み
                self._state.video_path = file_path
                url = QUrl.fromLocalFile(str(file_path))
                self._log_panel.debug(f"Setting media source: {url.toString()}", source="Media")
                self._media_player.setSource(url)
                self._play_btn.setEnabled(True)
                self._update_seek_buttons(True)
                self._log_panel.info(f"Video loaded: {file_path.name}", source="Media")
                self._start_waveform_generation(file_path)
                # 埋め込みチャプターがあれば読み込み
                self._load_embedded_chapters(file_path)
            else:
                # 複数動画: 仮想タイムライン方式で再生
                self._state.video_path = file_path
                self._media_player.setSource(QUrl.fromLocalFile(str(file_path)))
                self._play_btn.setEnabled(True)
                self._update_seek_buttons(True)
                self._log_panel.info(
                    f"{len(self._state.sources)} video files loaded (Virtual Timeline)",
                    source="Media"
                )
                self._start_waveform_generation(file_path)
                # 全ファイルから埋め込みチャプターを読み込み
                self._load_all_embedded_chapters()

        elif ext in AUDIO_EXTENSIONS:
            # 音声モード: 品質選択を静止画用に固定
            self._update_quality_combo_for_mode(is_audio=True)

            if len(self._state.sources) == 1:
                # 単一音声: そのまま読み込み（チャプター編集用）
                self._state.video_path = file_path
                self._media_player.setSource(QUrl.fromLocalFile(str(file_path)))
                self._play_btn.setEnabled(True)
                self._update_seek_buttons(True)
                self._log_panel.info(f"Audio loaded: {file_path.name}", source="Media")
                self._start_waveform_generation(file_path)
            else:
                # 複数音声: 仮想タイムライン方式で再生
                # 最初のファイルを読み込んで再生開始
                self._state.video_path = file_path
                self._media_player.setSource(QUrl.fromLocalFile(str(file_path)))
                self._play_btn.setEnabled(True)
                self._update_seek_buttons(True)
                self._log_panel.info(
                    f"{len(self._state.sources)} audio files loaded (Virtual Timeline)",
                    source="Media"
                )
                self._start_waveform_generation(file_path)
                # 全ファイルから埋め込みチャプターを読み込み
                self._load_all_embedded_chapters()
        else:
            self._log_panel.warning(f"Unknown file type: {ext}", source="Media")

    def _update_quality_combo_for_mode(self, is_audio: bool):
        """音声/動画モードを記録（設定ダイアログ移行後は内部フラグのみ）"""
        self._is_audio_only = is_audio

    def _on_source_clicked(self, index: int):
        """ソースリストのクリック時: 指定ソースに切り替え"""
        if index < 0 or index >= len(self._state.sources):
            return

        source = self._state.sources[index]
        self._source_list.set_current_index(index)
        self._state.video_path = source.path
        self._media_player.setSource(QUrl.fromLocalFile(str(source.path)))
        self._log_panel.info(f"Switched to: {source.path.name}", source="Media")

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
            self._play_btn.setIcon(self._play_icon)
        else:
            self._media_player.play()
            self._play_btn.setIcon(self._pause_icon)

    def _stop_video(self):
        """停止"""
        self._media_player.stop()
        self._play_btn.setIcon(self._play_icon)

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus):
        """メディアステータス変更時の処理"""
        current_source = self._media_player.source() if self._media_player else None
        self._log_panel.debug(
            f"Media status changed: {status}, target={self._target_source_url}, "
            f"current={current_source}, pending={self._pending_seek_position}",
            source="Media"
        )

        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            # 読み込み完了後
            self._log_panel.debug("LoadedMedia - starting playback", source="Media")
            # ターゲットソースがロードされた場合のみシークを適用
            if (self._target_source_url is not None and
                current_source == self._target_source_url and
                self._pending_seek_position is not None):
                self._log_panel.debug(f"Applying pending seek: {self._pending_seek_position}", source="Media")
                self._media_player.setPosition(self._pending_seek_position)
                self._pending_seek_position = None
                self._target_source_url = None
            self._media_player.play()
            self._play_btn.setIcon(self._pause_icon)
            # 音声ファイルの場合はCover Imageを表示
            self._show_cover_image_for_audio()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            # 仮想タイムライン: 次のファイルへ自動切り替え
            self._switch_to_next_source()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._log_panel.error("Invalid media file", source="Media")

    def _switch_to_next_source(self):
        """次のソースファイルに切り替え（仮想タイムライン用）"""
        if len(self._state.sources) <= 1:
            # 単一ファイル: 通常の終了処理
            self._play_btn.setIcon(self._play_icon)
            return

        current_idx = self._source_list.get_current_index()
        next_idx = current_idx + 1

        if next_idx < len(self._state.sources):
            # 次のファイルへ切り替え
            source = self._state.sources[next_idx]
            self._source_list.set_current_index(next_idx)
            self._state.video_path = source.path
            self._media_player.setSource(QUrl.fromLocalFile(str(source.path)))
            self._log_panel.info(f"Auto-switch to: {source.path.name}", source="Media")
        else:
            # 最後のファイル終了: 再生停止
            self._play_btn.setIcon(self._play_icon)
            self._log_panel.info("Reached end of all sources", source="Media")

    def _get_source_offsets(self) -> List[int]:
        """各ソースの開始オフセット（累積デュレーション）を取得"""
        offsets = [0]
        cumulative = 0
        for source in self._state.sources[:-1]:  # 最後以外
            cumulative += source.duration_ms
            offsets.append(cumulative)
        return offsets

    def _get_total_duration(self) -> int:
        """仮想タイムライン全体のデュレーション（ミリ秒）"""
        return sum(s.duration_ms for s in self._state.sources)

    def _get_local_time_in_source(self, absolute_time_ms: int, source_idx: int) -> int:
        """絶対時間（仮想タイムライン）をソース内のローカル時間に変換

        Args:
            absolute_time_ms: 仮想タイムライン上の絶対時間（ミリ秒）
            source_idx: 対象ソースのインデックス

        Returns:
            ソース内でのローカル時間（ミリ秒）
        """
        if source_idx is None or source_idx < 0:
            return absolute_time_ms

        offsets = self._get_source_offsets()
        if source_idx < len(offsets):
            return max(0, absolute_time_ms - offsets[source_idx])
        return absolute_time_ms

    def _virtual_to_source(self, virtual_pos: int) -> tuple:
        """仮想位置を (ソースインデックス, ローカルオフセット) に変換"""
        if len(self._state.sources) <= 1:
            return (0, virtual_pos)

        cumulative = 0
        for idx, source in enumerate(self._state.sources):
            if cumulative + source.duration_ms > virtual_pos:
                return (idx, virtual_pos - cumulative)
            cumulative += source.duration_ms

        # 最後のファイルの末尾
        last_idx = len(self._state.sources) - 1
        return (last_idx, self._state.sources[last_idx].duration_ms)

    def _source_to_virtual(self, source_idx: int, local_pos: int) -> int:
        """ソース位置を仮想位置に変換"""
        if len(self._state.sources) <= 1:
            return local_pos

        offsets = self._get_source_offsets()
        if source_idx < len(offsets):
            return offsets[source_idx] + local_pos
        return local_pos

    def _get_virtual_position(self) -> int:
        """現在の仮想タイムライン位置を取得"""
        if len(self._state.sources) <= 1:
            return self._media_player.position() if self._media_player else 0

        current_idx = self._source_list.get_current_index()
        local_pos = self._media_player.position() if self._media_player else 0
        return self._source_to_virtual(current_idx, local_pos)

    def _seek_virtual(self, virtual_pos: int):
        """仮想タイムライン位置にシーク"""
        if len(self._state.sources) <= 1:
            # 単一ファイル: 直接シーク
            if self._media_player:
                self._media_player.setPosition(virtual_pos)
            return

        # 仮想位置からソースとオフセットを計算
        source_idx, local_pos = self._virtual_to_source(virtual_pos)
        current_idx = self._source_list.get_current_index()

        if source_idx != current_idx:
            # 別のファイルに切り替え
            source = self._state.sources[source_idx]
            self._source_list.set_current_index(source_idx)
            self._state.video_path = source.path
            # シーク位置とターゲットURLを保存しておき、ロード完了後にシーク
            self._pending_seek_position = local_pos
            self._target_source_url = QUrl.fromLocalFile(str(source.path))
            self._media_player.setSource(self._target_source_url)
        else:
            # 同じファイル内: 直接シーク
            if self._media_player:
                self._media_player.setPosition(local_pos)

    def _seek_video(self, position: int):
        """シーク"""
        self._media_player.setPosition(position)

    def _populate_audio_devices(self):
        """音声出力デバイス一覧を取得してコンボボックスに設定"""
        # 現在選択されているデバイスのIDを保存
        current_device = self._audio_device_combo.currentData()
        current_device_id = current_device.id() if current_device else None

        # シグナルをブロックして更新
        self._audio_device_combo.blockSignals(True)
        self._audio_device_combo.clear()

        devices = QMediaDevices.audioOutputs()
        default_device = QMediaDevices.defaultAudioOutput()

        selected_index = 0
        for i, device in enumerate(devices):
            self._audio_device_combo.addItem(device.description(), device)
            # 以前選択されていたデバイスがあればそれを選択
            if current_device_id and device.id() == current_device_id:
                selected_index = i
            # なければデフォルトデバイスを選択
            elif not current_device_id and device.id() == default_device.id():
                selected_index = i

        self._audio_device_combo.setCurrentIndex(selected_index)
        self._audio_device_combo.blockSignals(False)

    def _on_audio_device_changed(self, index: int):
        """音声出力デバイスが変更されたとき"""
        if index < 0:
            return
        device = self._audio_device_combo.currentData()
        if device and self._media_player:
            default_device = QMediaDevices.defaultAudioOutput()
            is_default = device.id() == default_device.id()

            self._log_panel.debug(
                f"Changing audio device to: {device.description()} (default={is_default})",
                source="Audio"
            )

            # 現在の再生状態と位置を保存
            was_playing = self._media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            current_pos = self._media_player.position()

            # 再生を一時停止
            if was_playing:
                self._media_player.pause()

            # 現在のオーディオ出力を切断
            self._media_player.setAudioOutput(None)

            # 新しいQAudioOutputを作成
            # デフォルトデバイスの場合はデバイスを指定しない（OSボリュームと連動）
            if is_default:
                new_audio_output = QAudioOutput()
            else:
                new_audio_output = QAudioOutput(device)

            new_audio_output.setVolume(1.0)  # OSボリュームに任せる

            # メディアプレイヤーに新しいオーディオ出力を設定
            self._media_player.setAudioOutput(new_audio_output)

            # 古いオーディオ出力を置き換え
            self._audio_output = new_audio_output

            self._log_panel.debug(f"New audio output device: {self._audio_output.device().description()}", source="Audio")

            # 再生状態を復元
            if was_playing:
                self._media_player.setPosition(current_pos)
                self._media_player.play()

            self._log_panel.info(
                f"Audio output: {device.description()}",
                source="Audio"
            )

    def _on_position_changed(self, position: int):
        """再生位置変更"""
        # 仮想タイムラインモードの場合
        if len(self._state.sources) > 1:
            current_idx = self._source_list.get_current_index()
            virtual_pos = self._source_to_virtual(current_idx, position)
            total_duration = self._get_total_duration()

            # 時間表示更新（仮想位置）
            self._time_label.setText(
                f"{self._format_time(virtual_pos)} / {self._format_time(total_duration)}"
            )

            # 波形位置更新（仮想位置）
            if total_duration > 0 and self._waveform_widget:
                self._waveform_widget.set_position(virtual_pos / total_duration)

            # 現在のチャプターをハイライト（仮想位置）
            self._highlight_current_chapter(virtual_pos)
        else:
            # 単一ファイルの場合は従来通り
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
        # チャプタースキップボタンの有効/無効を更新
        self._update_chapter_buttons()

    def _highlight_current_chapter(self, position: int):
        """現在再生中のチャプターをハイライト"""
        if self._table.rowCount() == 0:
            self._current_chapter_row = -1
            self._update_chapter_overlay("")
            return

        # 現在位置より前で最も近いチャプターを見つける
        current_row = -1
        current_chapter_title = ""
        for row in range(self._table.rowCount()):
            time_item = self._table.item(row, 0)
            title_item = self._table.item(row, 1)
            if time_item:
                try:
                    chapter = ChapterInfo.from_time_str(time_item.text(), "")
                    if chapter.time_ms <= position:
                        current_row = row
                        current_chapter_title = title_item.text() if title_item else ""
                    else:
                        break
                except ValueError:
                    # 時間形式でない値がある場合はスキップ
                    continue

        # チャプターが変わっていなければ何もしない
        if current_row == self._current_chapter_row:
            return

        # ハイライト用の色
        highlight_bg = QBrush(QColor("#14b8a6"))  # ティール背景
        transparent_bg = QBrush(Qt.GlobalColor.transparent)  # 透明

        # 選択行を取得
        selected_row = self._table.currentRow()

        # 全行の背景とフォントを更新
        for row in range(self._table.rowCount()):
            is_playing = (row == current_row)
            is_selected = (row == selected_row)
            should_bold = is_playing or is_selected
            for col in range(2):  # Time, Title
                item = self._table.item(row, col)
                if item:
                    # 背景色: 再生中の行のみティール
                    item.setBackground(highlight_bg if is_playing else transparent_bg)
                    # フォント: 再生中または選択中ならボールド
                    font = item.font()
                    font.setBold(should_bold)
                    item.setFont(font)

        # 再生中の行を中央付近にスクロール（選択行と一致する場合のみ）
        # ユーザーが別の行を選択している場合はスクロールしない
        if current_row >= 0 and (selected_row < 0 or selected_row == current_row):
            self._table.scrollToItem(
                self._table.item(current_row, 0),
                QAbstractItemView.ScrollHint.PositionAtCenter
            )

        self._current_chapter_row = current_row

        # チャプター名オーバーレイを更新
        self._update_chapter_overlay(current_chapter_title)

    def _update_chapter_overlay(self, title: str):
        """チャプター名オーバーレイを更新（音声モードのみ）

        動画モードではQVideoWidgetがCore Animation/AVFoundationを使用するため
        オーバーレイ表示は不可。チャプター名はテーブルで確認可能。
        エンコード時のdrawtext焼き込みは別途実施。
        """
        # 動画モードではオーバーレイ無効
        if not self._is_audio_only:
            self._chapter_overlay_label.hide()
            return

        if not self._chapter_overlay_enabled:
            self._chapter_overlay_label.hide()
            return

        # --で始まるチャプター（除外区間）は表示しない
        if title.startswith("--"):
            self._chapter_overlay_label.hide()
            return

        if title:
            # 音声モード: カバー画像上にオーバーレイ表示
            container_rect = self._video_container.rect()
            container_height = container_rect.height()

            # 音声モード用設定: 下部（85%）、小さめ（3.5%）
            font_size = max(10, int(container_height * 0.035))
            self._chapter_overlay_label.setStyleSheet(f"""
                QLabel {{
                    color: white;
                    font-size: {font_size}px;
                    font-weight: bold;
                    background-color: rgba(0, 0, 0, 0.6);
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    padding: 8px 12px;
                    border-radius: 4px;
                }}
            """)
            self._chapter_overlay_label.setText(title)
            self._chapter_overlay_label.adjustSize()

            label_size = self._chapter_overlay_label.size()
            x = (container_rect.width() - label_size.width()) // 2
            y = int(container_height * 0.85 - label_size.height() / 2)
            self._chapter_overlay_label.move(x, y)
            self._chapter_overlay_label.raise_()
            self._chapter_overlay_label.show()
        else:
            self._chapter_overlay_label.hide()

    def set_chapter_overlay_enabled(self, enabled: bool):
        """チャプター名オーバーレイの表示切り替え（音声モードのみ有効）"""
        self._chapter_overlay_enabled = enabled
        if enabled and self._is_audio_only:
            # 現在のチャプターでオーバーレイを更新
            if self._current_chapter_row >= 0:
                title_item = self._table.item(self._current_chapter_row, 1)
                if title_item:
                    self._update_chapter_overlay(title_item.text())
        else:
            self._chapter_overlay_label.hide()
        self._log_panel.info(f"Chapter overlay {'enabled' if enabled else 'disabled'}", source="UI")

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
        """波形生成を開始（別スレッド）

        単一ファイル: そのファイルの波形を生成
        複数ファイル: 仮想タイムライン全体の波形を生成
        """
        # 既存のスレッドをクリーンアップ
        self._cleanup_waveform_thread()

        # 波形ウィジェットをローディング状態に
        if self._waveform_widget:
            self._waveform_widget.set_loading(0)

        # 複数ファイル時は仮想タイムライン用波形生成
        if len(self._state.sources) > 1:
            self._start_virtual_timeline_waveform()
            return

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

    def _start_virtual_timeline_waveform(self):
        """仮想タイムライン用の波形生成（複数ファイル）

        ffmpegのconcat filterを使って仮想的に結合した音声から波形を生成。
        実際のファイルは結合しない（エンコード回避）。
        """
        self._log_panel.debug(
            f"Starting virtual timeline waveform: {len(self._state.sources)} files",
            source="Waveform"
        )

        # concat demuxer用のファイルリストを作成
        concat_file = Path(tempfile.gettempdir()) / "waveform_concat.txt"
        with open(concat_file, 'w', encoding='utf-8') as f:
            for src in self._state.sources:
                escaped_path = str(src.path).replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")

        # ファイル境界情報を波形ウィジェットに渡す
        if self._waveform_widget:
            offsets = self._get_source_offsets()
            total_duration = self._get_total_duration()
            # 境界位置を0-1の正規化座標で渡す
            if total_duration > 0:
                boundaries = [offset / total_duration for offset in offsets[1:]]  # 最初の0は除外
                self._waveform_widget.set_file_boundaries(boundaries)

        # ワーカーとスレッドを作成（concat fileを入力として使用）
        self._waveform_thread = QThread()
        # WaveformWorkerにconcatファイルを渡す（特別な処理が必要）
        self._waveform_worker = WaveformWorker(concat_file, num_samples=4000, is_concat=True)

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

        # 仮想タイムラインの場合、ファイル境界を再設定
        if len(self._state.sources) > 1 and self._waveform_widget:
            offsets = self._get_source_offsets()
            total_duration = self._get_total_duration()
            if total_duration > 0:
                boundaries = [offset / total_duration for offset in offsets[1:]]
                self._waveform_widget.set_file_boundaries(boundaries)

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
        if not self._media_player:
            return

        self._log_panel.debug(f"Waveform clicked: position={position:.4f}, sources={len(self._state.sources)}", source="Waveform")

        # 仮想タイムラインモードの場合
        if len(self._state.sources) > 1:
            total_duration = self._get_total_duration()
            self._log_panel.debug(f"Virtual mode: total_duration={total_duration}", source="Waveform")
            if total_duration > 0:
                virtual_pos = int(position * total_duration)
                source_idx, local_pos = self._virtual_to_source(virtual_pos)
                self._log_panel.debug(f"Virtual seek: virtual_pos={virtual_pos}, source_idx={source_idx}, local_pos={local_pos}", source="Waveform")
                self._seek_virtual(virtual_pos)
        else:
            # 単一ファイルの場合
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
            # 仮想タイムラインモードの場合は全体の長さを使用
            if len(self._state.sources) > 1:
                duration_ms = self._get_total_duration()
            else:
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

    def _prepare_for_new_source(self):
        """新しいソース読み込み前の準備処理

        チャプター、スペクトログラム、UI状態をリセット。
        再生中のメディアを停止し、再生画面をクリア。
        Select Source / ドロップ共通処理。
        """
        # 再生中のメディアを停止し、再生画面をクリア
        if self._media_player:
            self._media_player.stop()
            self._media_player.setSource(QUrl())  # ソースをクリアして画面をリセット

        self._update_source_info()
        self.source_changed.emit(self._state.sources)

        # 埋め込みチャプターフラグをリセット（新しいソースを読み込むので）
        self._has_embedded_chapters = False
        self._chapter_title_label.setText("Chapters")
        self._chapter_title_label.setTextFormat(Qt.TextFormat.PlainText)
        self._table.setRowCount(0)  # チャプターリストをクリア
        self._current_chapter_row = -1  # ハイライトもリセット
        self._chapters_edited = False  # 編集フラグもリセット

        # 波形・スペクトログラム関連をリセット
        self._waveform_widget.clear()  # 波形データをクリア
        self._spectrogram_generated = False
        self._waveform_widget.set_spectrogram(None)  # スペクトログラムデータをクリア
        self._waveform_widget.set_display_mode(WaveformWidget.MODE_WAVEFORM)  # 振幅モードに戻す
        self._display_mode_combo.setCurrentIndex(0)  # コンボボックスも振幅に
        self._display_mode_combo.setEnabled(False)  # 波形生成完了まで無効化

    def _open_source_dialog(self):
        """ソース選択ダイアログを開く（ローカルファイル / YouTube対応）"""
        from rehearsal_workflow.ui.dialogs import SourceSelectionDialog, detect_video_duration

        dialog = SourceSelectionDialog(
            parent=self,
            initial_sources=self._state.sources,
            work_dir=self._state.work_dir
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # ローカルファイル
        sources = dialog.get_sources()

        if not sources:
            return

        # 作業ディレクトリを更新
        new_work_dir = dialog.get_work_dir()
        if new_work_dir != self._state.work_dir:
            self._state.work_dir = new_work_dir
            self.work_dir_changed.emit(self._state.work_dir)
            self._log_panel.info(
                f"Working directory: {new_work_dir}",
                source="UI"
            )

        self._state.sources = sources

        # 最初のファイル名をOutputのベースファイル名に設定
        if sources:
            first_file = sources[0].path
            base_name = first_file.stem
            self._output_edit.setText(base_name)

        self._log_panel.info(
            f"Sources updated: {len(self._state.sources)} files",
            source="UI"
        )

        self._prepare_for_new_source()

        # 複数ファイルの場合、チャプターを自動生成
        if len(self._state.sources) > 1:
            self._generate_chapters_from_sources()

        # ソースがあれば自動的にメディアプレーヤーに読み込み
        if self._state.sources:
            self._load_source_media()

    def _update_source_info(self):
        """ソース情報表示を更新"""
        pass

    def _file_dialog_dark_style(self) -> str:
        """ファイルダイアログ用ダークテーマスタイル"""
        return """
            QFileDialog {
                background-color: #1a1a1a;
                color: #f0f0f0;
            }
            QFileDialog QLabel {
                color: #f0f0f0;
            }
            QFileDialog QLineEdit {
                background-color: #0f0f0f;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 6px;
            }
            QFileDialog QPushButton {
                background-color: #2d2d2d;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 6px 16px;
            }
            QFileDialog QPushButton:hover {
                background-color: #363636;
            }
            QFileDialog QTreeView, QFileDialog QListView {
                background-color: #0f0f0f;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                selection-background-color: #3b82f6;
            }
            QFileDialog QTreeView::item:hover, QFileDialog QListView::item:hover {
                background-color: #2d2d2d;
            }
            QFileDialog QComboBox {
                background-color: #2d2d2d;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 6px;
            }
            QFileDialog QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #f0f0f0;
                selection-background-color: #3b82f6;
            }
            QFileDialog QHeaderView::section {
                background-color: #1a1a1a;
                color: #a0a0a0;
                border: 1px solid #3a3a3a;
                padding: 6px;
            }
            QFileDialog QToolButton {
                background-color: #2d2d2d;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
            }
            QFileDialog QToolButton:hover {
                background-color: #363636;
            }
            QFileDialog QScrollBar:vertical {
                background-color: #1a1a1a;
                width: 12px;
            }
            QFileDialog QScrollBar::handle:vertical {
                background-color: #3a3a3a;
                border-radius: 4px;
                min-height: 20px;
            }
            QFileDialog QSplitter::handle {
                background-color: #3a3a3a;
            }
            QFileDialog #sidebar {
                background-color: #1a1a1a;
            }
        """

    # === YouTubeダウンロード ===

    def _clean_youtube_url(self, url: str) -> str:
        """URLから一時的なプレイリストパラメータを除去

        TLP, RD等の自動生成プレイリストIDを含む場合、
        list=パラメータを削除して単一動画URLにする。
        """
        import re
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        # プレイリストIDを確認
        match = re.search(r'list=([a-zA-Z0-9_-]+)', url)
        if match:
            list_id = match.group(1)
            # 一時的なプレイリストの場合、list=を削除
            if list_id.startswith(('TLP', 'RD', 'OL', 'UU', 'LL')):
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                # list パラメータを削除
                params.pop('list', None)
                # index パラメータも削除
                params.pop('index', None)
                new_query = urlencode(params, doseq=True)
                cleaned = urlunparse((
                    parsed.scheme, parsed.netloc, parsed.path,
                    parsed.params, new_query, parsed.fragment
                ))
                return cleaned
        return url

    def _start_youtube_download(self):
        """YouTubeダウンロードを開始"""
        url = self._youtube_url_edit.text().strip()
        if not url:
            self._log_panel.warning("Please enter a YouTube URL", source="YouTube")
            return

        # URL検証
        if not ('youtube.com' in url or 'youtu.be' in url):
            self._log_panel.warning("Invalid YouTube URL", source="YouTube")
            return

        # プレイリストURL検出
        if self._is_playlist_url(url):
            self._start_playlist_download(url)
            return

        # 一時的なプレイリストパラメータを除去
        original_url = url
        url = self._clean_youtube_url(url)
        if url != original_url:
            self._log_panel.info(f"Removed temp playlist param: {url}", source="YouTube")

        # 既存のダウンロードがあればキャンセル
        if self._youtube_worker and self._youtube_worker.isRunning():
            self._youtube_worker.cancel()
            self._youtube_worker.wait()

        # UI状態を更新（処理中は赤）
        self._youtube_download_btn.setStyleSheet(self._youtube_btn_style_processing())
        self._youtube_download_btn.setEnabled(False)
        self._youtube_download_btn.setText("DL...")
        self._youtube_url_edit.setEnabled(False)

        # プログレスバー表示
        self._youtube_progress.setValue(0)
        self._youtube_progress.setVisible(True)

        self._log_panel.info(f"Starting YouTube download: {url}", source="YouTube")

        # ワーカーを作成
        self._youtube_worker = YouTubeDownloadWorker(
            url=url,
            output_dir=str(self._state.work_dir),
            download_subs=True,
            sub_lang="ja"
        )

        # シグナル接続
        self._youtube_worker.log_message.connect(
            lambda msg: self._log_panel.info(msg, source="YouTube")
        )
        self._youtube_worker.progress_update.connect(self._on_youtube_progress)
        self._youtube_worker.download_completed.connect(self._on_youtube_completed)
        self._youtube_worker.error_occurred.connect(self._on_youtube_error)

        # ダウンロード開始
        self._youtube_worker.start()

    def _reset_youtube_ui(self):
        """YouTubeダウンロードUI状態をリセット"""
        self._youtube_download_btn.setStyleSheet(self._youtube_btn_style_normal())
        self._youtube_download_btn.setEnabled(True)
        self._youtube_download_btn.setText("DL")
        self._youtube_url_edit.setEnabled(True)
        self._youtube_progress.setVisible(False)

    def _on_youtube_progress(self, message: str):
        """YouTubeダウンロード進捗"""
        self._log_panel.debug(message, source="YouTube")

        # パーセンテージを抽出してプログレスバー更新（例: "15.0% at 2.5MB/s"）
        match = re.search(r'(\d+(?:\.\d+)?)\s*%', message)
        if match:
            percent = int(float(match.group(1)))
            self._youtube_progress.setValue(percent)

    def _on_youtube_completed(self, video_path: str, srt_path: str):
        """YouTubeダウンロード完了"""
        self._reset_youtube_ui()
        self._youtube_url_edit.clear()
        self._log_panel.info(f"Download completed: {Path(video_path).name}", source="YouTube")

        if srt_path:
            self._log_panel.info(f"Subtitle saved: {Path(srt_path).name}", source="YouTube")

        # ダウンロードした動画をソースとしてロード
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            self._log_panel.error(f"Video file not found: {video_path}", source="YouTube")
            return

        duration_ms = detect_video_duration(str(video_path_obj)) or 0
        source = SourceFile(
            path=video_path_obj,
            duration_ms=duration_ms,
            file_type="mp4"
        )
        self._state.sources = [source]
        self._prepare_for_new_source()

        # 少し遅延を入れてからロード（メディアプレーヤーのリセット完了を待つ）
        QTimer.singleShot(100, lambda: self._load_youtube_video(video_path_obj))

    def _load_youtube_video(self, video_path: Path):
        """YouTube動画をロード（遅延呼び出し用）"""
        self._log_panel.debug(f"Loading YouTube video: {video_path}", source="YouTube")
        self._log_panel.debug(f"File exists: {video_path.exists()}", source="YouTube")
        self._log_panel.debug(f"Sources count: {len(self._state.sources)}", source="YouTube")

        self._load_source_media()

        # 出力ファイル名を設定（動画名から）
        self._output_edit.setText(video_path.stem)

        self._log_panel.info("Video loaded as source", source="YouTube")

    def _on_youtube_error(self, error_message: str):
        """YouTubeダウンロードエラー"""
        self._reset_youtube_ui()
        self._log_panel.error(f"Download failed: {error_message}", source="YouTube")

    # === プレイリストダウンロード ===

    def _is_playlist_url(self, url: str) -> bool:
        """プレイリストURLかどうかを判定

        一時的なミックスプレイリスト（TLP, RD等）は除外し、
        単一動画としてダウンロードする。
        """
        if 'list=' not in url:
            return False

        # プレイリストIDを抽出
        import re
        match = re.search(r'list=([a-zA-Z0-9_-]+)', url)
        if match:
            list_id = match.group(1)
            # TLP, RD, OL, UU, LL などは一時的/自動生成プレイリスト
            # これらはAPIでアクセスできないので単一動画として扱う
            if list_id.startswith(('TLP', 'RD', 'OL', 'UU', 'LL')):
                return False

        return True

    def _start_playlist_download(self, url: str):
        """プレイリスト情報取得を開始"""
        # 既存のワーカーがあればキャンセル
        if self._playlist_info_worker and self._playlist_info_worker.isRunning():
            self._playlist_info_worker.terminate()
            self._playlist_info_worker.wait()

        # UI状態を更新
        self._youtube_download_btn.setStyleSheet(self._youtube_btn_style_processing())
        self._youtube_download_btn.setEnabled(False)
        self._youtube_download_btn.setText("DL List...")
        self._youtube_url_edit.setEnabled(False)

        self._log_panel.info(f"Fetching playlist info: {url}", source="YouTube")

        # ワーカーを作成
        self._playlist_info_worker = PlaylistInfoWorker(url)
        self._playlist_info_worker.playlist_info_ready.connect(self._on_playlist_info_ready)
        self._playlist_info_worker.error_occurred.connect(self._on_playlist_info_error)
        self._playlist_info_worker.start()

    def _on_playlist_info_ready(self, playlist_info: dict):
        """プレイリスト情報取得完了"""
        entries = playlist_info.get('entries', [])
        playlist_title = playlist_info.get('title', 'Playlist')

        if not entries:
            self._reset_youtube_ui()
            self._log_panel.warning("No videos found in playlist", source="YouTube")
            return

        self._log_panel.info(f"Found {len(entries)} videos in '{playlist_title}'", source="YouTube")

        # 選択ダイアログを表示
        dialog = PlaylistVideoSelectionDialog(playlist_info, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            selected = dialog.get_selected_videos()
            force_download = dialog.get_force_download()
            if selected:
                self._download_playlist_videos(selected, force_download)
            else:
                self._reset_youtube_ui()
                self._log_panel.info("No videos selected", source="YouTube")
        else:
            self._reset_youtube_ui()
            self._log_panel.info("Playlist download cancelled", source="YouTube")

    def _on_playlist_info_error(self, error_message: str):
        """プレイリスト情報取得エラー"""
        self._reset_youtube_ui()
        self._log_panel.error(f"Failed to fetch playlist info: {error_message}", source="YouTube")

    def _download_playlist_videos(self, videos: list, force_download: bool = False):
        """選択された動画をダウンロード"""
        if not videos:
            self._reset_youtube_ui()
            return

        # 既存のダウンロードがあればキャンセル
        if self._playlist_worker and self._playlist_worker.isRunning():
            self._playlist_worker.cancel()
            self._playlist_worker.wait()

        # UI状態を更新
        self._youtube_download_btn.setText(f"0/{len(videos)}")
        self._youtube_progress.setValue(0)
        self._youtube_progress.setVisible(True)

        if force_download:
            self._log_panel.info(f"Starting download of {len(videos)} videos (force re-download)", source="YouTube")
        else:
            self._log_panel.info(f"Starting download of {len(videos)} videos", source="YouTube")

        # ワーカーを作成
        self._playlist_worker = PlaylistDownloadWorker(
            videos=videos,
            output_dir=str(self._state.work_dir),
            download_subs=True,
            sub_lang="ja",
            force_overwrite=force_download
        )

        # シグナル接続
        self._playlist_worker.log_message.connect(
            lambda msg: self._log_panel.info(msg, source="YouTube")
        )
        self._playlist_worker.progress_update.connect(self._on_playlist_progress)
        self._playlist_worker.video_completed.connect(self._on_playlist_video_completed)
        self._playlist_worker.all_completed.connect(self._on_playlist_completed)
        self._playlist_worker.error_occurred.connect(self._on_playlist_error)

        # ダウンロード開始
        self._playlist_worker.start()

    def _on_playlist_progress(self, message: str):
        """プレイリストダウンロード進捗"""
        self._log_panel.debug(message, source="YouTube")

        # "1/10: Downloading..." 形式からボタンテキストを更新
        match = re.match(r'(\d+)/(\d+)', message)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            self._youtube_download_btn.setText(f"{current}/{total}")
            # 全体進捗をプログレスバーに反映
            if total > 0:
                self._youtube_progress.setValue(int((current - 1) / total * 100))

        # パーセンテージ抽出（個別動画の進捗）
        pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', message)
        if pct_match:
            pass  # 個別進捗は現在表示しない

    def _on_playlist_video_completed(self, video_path: str, srt_path: str, current: int, total: int):
        """プレイリスト個別動画ダウンロード完了"""
        self._log_panel.info(f"Downloaded ({current}/{total}): {Path(video_path).name}", source="YouTube")
        # プログレスバー更新
        if total > 0:
            self._youtube_progress.setValue(int(current / total * 100))
        self._youtube_download_btn.setText(f"{current}/{total}")

    def _on_playlist_completed(self, video_paths: list):
        """プレイリスト全ダウンロード完了"""
        self._reset_youtube_ui()
        self._youtube_url_edit.clear()

        if not video_paths:
            self._log_panel.warning("No videos were downloaded", source="YouTube")
            return

        self._log_panel.info(f"Playlist download completed: {len(video_paths)} videos", source="YouTube")

        # ダウンロードした動画を複数ソースとして追加
        sources = []
        for video_path in sorted(video_paths):  # ファイル名でソート
            video_path_obj = Path(video_path)
            if video_path_obj.exists():
                duration_ms = detect_video_duration(str(video_path_obj)) or 0
                source = SourceFile(
                    path=video_path_obj,
                    duration_ms=duration_ms,
                    file_type="mp4"
                )
                sources.append(source)

        if sources:
            self._state.sources = sources
            self._prepare_for_new_source()
            QTimer.singleShot(100, self._load_source_media)

            # チャプターを自動生成
            if len(sources) > 1:
                self._generate_chapters_from_sources()

            self._log_panel.info(f"Added {len(sources)} videos as sources", source="YouTube")

    def _on_playlist_error(self, error_message: str):
        """プレイリストダウンロードエラー"""
        self._reset_youtube_ui()
        self._log_panel.error(f"Playlist download failed: {error_message}", source="YouTube")

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
        default_color = QColor("#f0f0f0")

        for source_idx, src in enumerate(self._state.sources):
            # ChapterInfoを作成（source_indexを設定）
            chapter = ChapterInfo(time_ms=cumulative_ms, title=src.path.stem, source_index=source_idx)
            chapters.append(chapter)

            # テーブルに追加
            row = self._table.rowCount()
            self._table.insertRow(row)

            time_item = QTableWidgetItem(chapter.time_str)
            title_item = QTableWidgetItem(chapter.title)

            # source_indexを設定（ソースファイルとの紐付け）
            time_item.setData(Qt.ItemDataRole.UserRole, default_color)
            title_item.setData(Qt.ItemDataRole.UserRole, default_color)
            time_item.setData(Qt.ItemDataRole.UserRole + 1, source_idx)
            title_item.setData(Qt.ItemDataRole.UserRole + 1, source_idx)

            self._table.setItem(row, 0, time_item)
            self._table.setItem(row, 1, title_item)

            # 累積時間を更新
            cumulative_ms += src.duration_ms

        self._table.blockSignals(False)

        self._log_panel.info(
            f"Generated {len(chapters)} chapters from source files",
            source="Chapter"
        )

        # 波形にチャプターを反映（メディアロード後に更新されるので、ここでは状態を保持）
        self._state.chapters = chapters

        # ドラッグ可否を更新
        self._update_chapter_drag_enabled()

        # 最初のチャプターを選択・ハイライト（クリック時と同じ動作）
        if self._table.rowCount() > 0:
            self._table.selectRow(0)
            self._highlight_current_chapter(0)

    def _add_chapter(self):
        """チャプター追加（時間順にソートされた位置に挿入）"""
        # 現在の再生位置をチャプター時間として使用
        # 仮想タイムラインモードの場合は仮想位置を使用
        if len(self._state.sources) > 1:
            local_pos = self._media_player.position() if self._media_player else 0
            current_idx = self._source_list.get_current_index()
            current_pos = self._source_to_virtual(current_idx, local_pos)
            # 現在のソースインデックスを紐付け
            source_index = current_idx
        else:
            current_pos = self._media_player.position() if self._media_player else 0
            source_index = 0
        time_str = self._format_time(current_pos)

        # 挿入位置を時間順で決定
        insert_row = self._table.rowCount()  # デフォルトは最後
        for row in range(self._table.rowCount()):
            time_item = self._table.item(row, 0)
            if time_item:
                try:
                    chapter = ChapterInfo.from_time_str(time_item.text(), "")
                    if current_pos < chapter.time_ms:
                        insert_row = row
                        break
                except ValueError:
                    continue

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
        # source_indexを設定（ソースファイルとの紐付け）
        time_item.setData(Qt.ItemDataRole.UserRole + 1, source_index)
        title_item.setData(Qt.ItemDataRole.UserRole + 1, source_index)

        self._table.setItem(insert_row, 0, time_item)
        self._table.setItem(insert_row, 1, title_item)

        # 挿入した行を選択
        self._table.selectRow(insert_row)

        self._log_panel.debug(f"Chapter added at {time_str} (source_index={source_index})", source="UI")
        self._chapters_edited = True
        self._update_waveform_chapters()
        self._update_chapter_buttons()
        self._update_chapter_drag_enabled()

    def _remove_chapter(self):
        """選択チャプター削除（対応するソースも削除）"""
        rows = sorted(set(item.row() for item in self._table.selectedItems()), reverse=True)

        if not rows:
            return

        # チャプターとソースの1:1対応をチェック
        sources_match = len(self._state.sources) == self._table.rowCount()

        # source_indexが設定されているかチェック
        first_row = rows[-1]  # 最小行番号
        first_item = self._table.item(first_row, 0)
        has_source_index = first_item and first_item.data(Qt.ItemDataRole.UserRole + 1) is not None

        # source_indexモードか判定
        if has_source_index and not sources_match:
            # source_indexモード: source_indexでグループ削除
            self._remove_chapter_grouped(rows)
        else:
            # 1:1対応モード: 従来のロジック
            self._remove_chapter_one_to_one(rows, sources_match)

        self._update_waveform_chapters()
        self._update_chapter_buttons()
        self._update_chapter_drag_enabled()

    def _remove_chapter_one_to_one(self, rows: list, sources_match: bool):
        """1:1対応時のチャプター削除処理"""
        # 現在再生中のソースインデックスを取得
        current_playing_idx = self._source_list.get_current_index()
        need_reload_media = False

        # 行を削除（逆順で）
        for row in rows:
            self._table.removeRow(row)
            # ソースも削除（1:1対応の場合のみ）
            if sources_match and row < len(self._state.sources):
                removed_source = self._state.sources.pop(row)
                self._log_panel.info(
                    f"Removed source: {removed_source.path.name}",
                    source="UI"
                )
                # 削除されたソースが再生中だった場合はリロードが必要
                if row == current_playing_idx:
                    need_reload_media = True
                # 削除されたソースより後のインデックスの場合、現在のインデックスを調整
                elif row < current_playing_idx:
                    current_playing_idx -= 1

        self._log_panel.debug(f"Removed {len(rows)} chapters", source="UI")
        self._chapters_edited = True

        # ソースが残っている場合、チャプター時間を再計算
        if sources_match and self._state.sources:
            self._recalculate_chapter_times()
            # UI更新
            self._source_list.set_sources(self._state.sources)
            # 波形を再生成
            self._start_waveform_generation(self._state.sources[0].path)

            # 再生中のソースが削除された場合、先頭から再生を開始
            if need_reload_media:
                self._source_list.set_current_index(0)
                self._load_source_media()
                self._log_panel.info("Playback restarted from first source", source="UI")

            # 波形位置と時間表示を更新
            self._update_position_after_removal()
        elif not self._state.sources:
            # ソースが空になった場合
            self._source_list.set_sources([])
            self._waveform_widget.clear()
            # メディアプレーヤーを停止・クリア
            if self._media_player:
                self._media_player.stop()
                self._media_player.setSource(QUrl())
            # 時間表示をリセット
            self._time_label.setText("0:00:00.000 / 0:00:00.000")
            self._log_panel.info("All sources removed", source="UI")

    def _remove_chapter_grouped(self, selected_rows: list):
        """埋め込みチャプター時のグループ削除処理

        選択された行のsource_indexに対応するソースファイルと
        そのソースに属するすべてのチャプターを削除する。
        """
        # 削除対象のsource_indexを収集（重複除去）
        source_indices_to_remove = set()
        for row in selected_rows:
            item = self._table.item(row, 0)
            if item:
                source_idx = item.data(Qt.ItemDataRole.UserRole + 1)
                if source_idx is not None:
                    source_indices_to_remove.add(source_idx)

        if not source_indices_to_remove:
            return

        # 現在再生中のソースインデックスを取得
        current_playing_idx = self._source_list.get_current_index()
        need_reload_media = current_playing_idx in source_indices_to_remove

        # 削除対象のソースファイル名をログ出力
        for idx in sorted(source_indices_to_remove, reverse=True):
            if idx < len(self._state.sources):
                removed_source = self._state.sources[idx]
                self._log_panel.info(
                    f"Removing source: {removed_source.path.name}",
                    source="UI"
                )

        # 変更前のオフセットを保存
        old_offsets = self._get_source_offsets()

        # ソースを逆順で削除（インデックスがずれないように）
        for idx in sorted(source_indices_to_remove, reverse=True):
            if idx < len(self._state.sources):
                self._state.sources.pop(idx)

        self._chapters_edited = True

        # ソースが残っている場合、チャプターを再構築
        if self._state.sources:
            self._rebuild_chapters_after_source_move(
                removed_indices=source_indices_to_remove,
                old_offsets=old_offsets
            )
            # UI更新
            self._source_list.set_sources(self._state.sources)
            # 波形を再生成
            self._start_waveform_generation(self._state.sources[0].path)

            # 再生中のソースが削除された場合、先頭から再生を開始
            if need_reload_media:
                self._source_list.set_current_index(0)
                self._load_source_media()
                self._log_panel.info("Playback restarted from first source", source="UI")

            # 波形位置と時間表示を更新
            self._update_position_after_removal()
        else:
            # ソースが空になった場合
            self._table.setRowCount(0)
            self._state.chapters = []
            self._has_embedded_chapters = False
            self._chapter_title_label.setText("Chapters")
            self._chapter_title_label.setTextFormat(Qt.TextFormat.PlainText)
            self._source_list.set_sources([])
            self._waveform_widget.clear()
            # メディアプレーヤーを停止・クリア
            if self._media_player:
                self._media_player.stop()
                self._media_player.setSource(QUrl())
            # 時間表示をリセット
            self._time_label.setText("0:00:00.000 / 0:00:00.000")
            self._log_panel.info("All sources removed", source="UI")

        self._log_panel.info(
            f"Removed {len(source_indices_to_remove)} source(s) with all their chapters",
            source="UI"
        )

    def _update_position_after_removal(self):
        """削除後の波形位置と時間表示を更新"""
        if not self._state.sources:
            return

        # 現在再生中のソースと位置を取得
        current_playing_url = self._media_player.source() if self._media_player else None
        current_local_pos = 0
        current_idx = 0

        if current_playing_url and not current_playing_url.isEmpty():
            current_playing_path = current_playing_url.toLocalFile()
            current_local_pos = self._media_player.position() if self._media_player else 0
            # 現在のパスがソースリストのどこにあるか検索
            for idx, src in enumerate(self._state.sources):
                if str(src.path) == current_playing_path:
                    current_idx = idx
                    break

        # 仮想位置を再計算
        virtual_pos = self._source_to_virtual(current_idx, current_local_pos)
        total_duration = self._get_total_duration()

        # 時間表示を更新
        self._time_label.setText(
            f"{self._format_time(virtual_pos)} / {self._format_time(total_duration)}"
        )

        # 波形位置を更新
        if total_duration > 0 and self._waveform_widget:
            self._waveform_widget.set_position(virtual_pos / total_duration)

        # 現在再生中のチャプターをハイライト
        self._highlight_current_chapter(virtual_pos)

    def _recalculate_chapter_times(self):
        """ソースの順序に基づいてチャプター時間を再計算"""
        if not self._state.sources:
            return

        if self._table.rowCount() != len(self._state.sources):
            return

        self._table.blockSignals(True)

        cumulative_ms = 0
        new_chapters = []
        for i, src in enumerate(self._state.sources):
            # 既存のタイトルを保持
            title_item = self._table.item(i, 1)
            title = title_item.text() if title_item else src.path.stem

            chapter = ChapterInfo(time_ms=cumulative_ms, title=title)
            new_chapters.append(chapter)

            # テーブルの時間を更新
            self._table.setItem(i, 0, QTableWidgetItem(chapter.time_str))

            cumulative_ms += src.duration_ms

        self._table.blockSignals(False)
        self._state.chapters = new_chapters

    def _on_chapter_edited(self, row: int, column: int):
        """チャプター編集後に波形を更新"""
        self._chapters_edited = True
        self._update_waveform_chapters()
        self._update_chapter_buttons()

    def _on_chapter_row_moved(self, logical_index: int, old_visual: int, new_visual: int):
        """チャプター行がドラッグ＆ドロップで移動された時の処理

        ソースの順序も連動して変更し、チャプター時間を再計算する。
        """
        self._log_panel.info(
            f"Row moved signal: logical={logical_index}, old_visual={old_visual}, new_visual={new_visual}",
            source="DnD"
        )

        # チャプターとソースの1:1対応が前提
        if len(self._state.sources) != self._table.rowCount():
            self._log_panel.warning(
                "Source count doesn't match chapter count, skipping reorder",
                source="UI"
            )
            return

        header = self._table.verticalHeader()
        row_count = self._table.rowCount()

        # 現在のビジュアル順序を取得（ドラッグ後のヘッダーマッピングから）
        visual_order = []
        for visual_idx in range(row_count):
            logical_idx = header.logicalIndex(visual_idx)
            visual_order.append(logical_idx)

        self._log_panel.debug(f"Visual order after drag: {visual_order}", source="DnD")

        # 現在のチャプターとソースのタイトルを保存（視覚順序で）
        old_titles = []
        for logical_idx in visual_order:
            title_item = self._table.item(logical_idx, 1)
            old_titles.append(title_item.text() if title_item else "")

        # ソースを新しい順序で並び替え
        new_sources = [self._state.sources[i] for i in visual_order]

        # チャプター時間を再計算（新しいソース順序に基づいて）
        cumulative_ms = 0
        new_chapters = []
        for i, src in enumerate(new_sources):
            chapter = ChapterInfo(time_ms=cumulative_ms, title=old_titles[i])
            new_chapters.append(chapter)
            self._log_panel.debug(
                f"Chapter {i}: {chapter.time_str} - {chapter.title} (src duration: {src.duration_ms}ms)",
                source="DnD"
            )
            cumulative_ms += src.duration_ms

        # 状態を更新
        self._state.sources = new_sources
        self._state.chapters = new_chapters
        self._chapters_edited = True

        # シグナルをブロック
        self._table.blockSignals(True)
        header.blockSignals(True)

        # ヘッダーセクションの視覚順序をリセット
        for logical_idx in range(row_count):
            visual_idx = header.visualIndex(logical_idx)
            if visual_idx != logical_idx:
                header.moveSection(visual_idx, logical_idx)

        # テーブルを完全に再構築
        self._table.setRowCount(0)
        for ch in new_chapters:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(ch.time_str))
            self._table.setItem(row, 1, QTableWidgetItem(ch.title))

        # シグナルを再有効化
        header.blockSignals(False)
        self._table.blockSignals(False)

        # UI更新
        self._source_list.set_sources(self._state.sources)
        self._update_waveform_chapters()

        # ドラッグ可否を更新
        self._update_chapter_drag_enabled()

        # 波形を再生成（ソース順序が変わったため）
        if self._state.sources:
            self._start_waveform_generation(self._state.sources[0].path)

        self._log_panel.info(
            f"Chapters reordered: row {old_visual} → {new_visual}",
            source="UI"
        )

    def _handle_row_move(self, source_row: int, target_row: int):
        """行移動を手動で処理（テーブルとソースを同時に更新）

        Args:
            source_row: 移動元の行インデックス
            target_row: 移動先の行インデックス

        埋め込みチャプターがある場合:
            同じsource_indexを持つチャプターをすべて連動して移動
        1:1対応の場合:
            チャプターとソースを1対1で移動
        """
        row_count = self._table.rowCount()
        source_count = len(self._state.sources)

        # 範囲チェック
        if source_row < 0 or source_row >= row_count or target_row < 0 or target_row >= row_count:
            return

        if source_row == target_row:
            return

        # 1:1モードかsource_indexモードか判定
        one_to_one = source_count == row_count

        # source_indexが設定されているかチェック
        source_item = self._table.item(source_row, 0)
        has_source_index = source_item and source_item.data(Qt.ItemDataRole.UserRole + 1) is not None

        if one_to_one and not has_source_index:
            # 1:1対応モード（source_indexなし）: 従来のロジック
            self._handle_row_move_one_to_one(source_row, target_row)
        elif has_source_index:
            # source_indexモード: source_indexでグループ移動
            self._handle_row_move_grouped(source_row, target_row)
        else:
            self._log_panel.warning(
                f"Cannot move: sources={source_count}, rows={row_count}",
                source="DnD"
            )

    def _handle_row_move_one_to_one(self, source_row: int, target_row: int):
        """1:1対応時の行移動処理"""
        row_count = self._table.rowCount()

        # 移動元の行データを取得
        title_item = self._table.item(source_row, 1)
        moved_title = title_item.text() if title_item else ""

        # 挿入位置を計算
        if source_row < target_row:
            insert_pos = target_row - 1
        else:
            insert_pos = target_row

        self._log_panel.info(
            f"Row move (1:1): {source_row} → {target_row} (insert at {insert_pos})",
            source="DnD"
        )

        # ソースの順序を変更
        sources = list(self._state.sources)
        moved_source = sources.pop(source_row)
        sources.insert(insert_pos, moved_source)
        self._state.sources = sources

        # タイトルリストも同様に並び替え
        titles = []
        for row in range(row_count):
            item = self._table.item(row, 1)
            titles.append(item.text() if item else "")
        moved_title = titles.pop(source_row)
        titles.insert(insert_pos, moved_title)

        # チャプター時間を再計算
        cumulative_ms = 0
        new_chapters = []
        for src, title in zip(self._state.sources, titles):
            chapter = ChapterInfo(time_ms=cumulative_ms, title=title)
            new_chapters.append(chapter)
            cumulative_ms += src.duration_ms

        self._state.chapters = new_chapters
        self._chapters_edited = True

        # テーブルを再構築
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for ch in new_chapters:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(ch.time_str))
            self._table.setItem(row, 1, QTableWidgetItem(ch.title))
        self._table.blockSignals(False)

        # 移動先の行を選択
        self._table.selectRow(insert_pos)

        self._finalize_row_move()

        self._log_panel.info(
            f"Row moved successfully (1:1): {source_row} → {insert_pos}",
            source="DnD"
        )

    def _handle_row_move_grouped(self, source_row: int, target_row: int):
        """埋め込みチャプター時のグループ移動処理

        ドラッグされた行のsource_indexと同じチャプターをすべて連動して移動。
        """
        # ドラッグ元の行のsource_indexを取得
        source_item = self._table.item(source_row, 0)
        if not source_item:
            return
        dragged_source_idx = source_item.data(Qt.ItemDataRole.UserRole + 1)
        if dragged_source_idx is None:
            self._log_panel.warning("No source_index found for dragged row", source="DnD")
            return

        # ターゲット行のsource_indexを取得
        target_item = self._table.item(target_row, 0)
        if not target_item:
            return
        target_source_idx = target_item.data(Qt.ItemDataRole.UserRole + 1)
        if target_source_idx is None:
            self._log_panel.warning("No source_index found for target row", source="DnD")
            return

        # 同じソース内での移動は無視
        if dragged_source_idx == target_source_idx:
            self._log_panel.debug(
                f"Same source move ignored: source_idx={dragged_source_idx}",
                source="DnD"
            )
            return

        self._log_panel.info(
            f"Grouped move: source[{dragged_source_idx}] → before source[{target_source_idx}]",
            source="DnD"
        )

        # 変更前のオフセットを保存
        old_offsets = self._get_source_offsets()

        # ソースの順序を変更
        sources = list(self._state.sources)

        # 移動先のインデックスを計算
        # dragged_source_idx < target_source_idx: popでインデックスがずれる
        if dragged_source_idx < target_source_idx:
            insert_pos = target_source_idx - 1
        else:
            insert_pos = target_source_idx

        moved_source = sources.pop(dragged_source_idx)
        sources.insert(insert_pos, moved_source)
        self._state.sources = sources

        # 全チャプターを再構築（source_indexを更新）
        self._rebuild_chapters_after_source_move(
            dragged_source_idx, insert_pos, old_offsets=old_offsets
        )

        # 移動したソースの最初のチャプター行を選択
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole + 1) == insert_pos:
                self._table.selectRow(row)
                break

        self._finalize_row_move()

        self._log_panel.info(
            f"Grouped move completed: source[{dragged_source_idx}] → source[{insert_pos}]",
            source="DnD"
        )

    def _rebuild_chapters_after_source_move(
        self,
        old_source_idx: int = -1,
        new_source_idx: int = -1,
        removed_indices: set = None,
        old_offsets: list = None
    ):
        """ソース移動後にチャプターを再構築

        現在のテーブル内容を保持しながら、source_indexと時間を更新。
        手動追加されたチャプターも保持される。

        Args:
            old_source_idx: 移動前のソースインデックス（-1の場合は移動なし）
            new_source_idx: 移動後のソースインデックス（-1の場合は移動なし）
            removed_indices: 削除されたソースインデックスの集合（削除モード用）
            old_offsets: 変更前のソースオフセット（ローカル時間計算用）
        """
        # 現在のテーブルからチャプター情報を収集
        table_chapters = []
        for row in range(self._table.rowCount()):
            time_item = self._table.item(row, 0)
            title_item = self._table.item(row, 1)
            if not time_item or not title_item:
                continue

            old_idx = time_item.data(Qt.ItemDataRole.UserRole + 1)
            color = time_item.data(Qt.ItemDataRole.UserRole)
            title = title_item.text()

            # このチャプターのソース内でのローカル時間を計算
            chapter = ChapterInfo.from_time_str(time_item.text(), title)
            if old_offsets and old_idx is not None and 0 <= old_idx < len(old_offsets):
                # 変更前のオフセットを使用してローカル時間を計算
                local_time_ms = max(0, chapter.time_ms - old_offsets[old_idx])
            else:
                local_time_ms = self._get_local_time_in_source(chapter.time_ms, old_idx)

            table_chapters.append({
                'old_source_idx': old_idx,
                'local_time_ms': local_time_ms,
                'title': title,
                'color': color,
            })

        # source_indexのマッピングを計算
        def map_source_index(old_idx):
            if old_idx is None:
                return -1

            if removed_indices:
                # 削除モード: 削除されたインデックスはスキップ、残りはずらす
                if old_idx in removed_indices:
                    return -1  # 削除対象
                # old_idxより小さい削除済みインデックスの数だけずらす
                shift = sum(1 for r in removed_indices if r < old_idx)
                return old_idx - shift

            if old_source_idx >= 0:
                # 移動モード
                if old_idx == old_source_idx:
                    return new_source_idx
                elif old_source_idx < new_source_idx:
                    # 前から後ろへ移動
                    if old_source_idx < old_idx <= new_source_idx:
                        return old_idx - 1
                else:
                    # 後ろから前へ移動
                    if new_source_idx <= old_idx < old_source_idx:
                        return old_idx + 1

            return old_idx

        # 各チャプターの新しいsource_indexを計算
        for ch in table_chapters:
            ch['new_source_idx'] = map_source_index(ch['old_source_idx'])

        # 新しいsource_index順、その中でlocal_time順にソート
        table_chapters.sort(key=lambda x: (x['new_source_idx'], x['local_time_ms']))

        # ソースのオフセットを計算
        source_offsets = []
        cumulative = 0
        for src in self._state.sources:
            source_offsets.append(cumulative)
            cumulative += src.duration_ms

        # テーブルを再構築
        self._table.blockSignals(True)
        self._table.setRowCount(0)

        default_color = QColor("#f0f0f0")
        all_chapters = []

        for ch in table_chapters:
            new_idx = ch['new_source_idx']
            if new_idx < 0 or new_idx >= len(self._state.sources):
                continue  # 無効なインデックスはスキップ

            # 新しい絶対時間を計算
            new_time_ms = source_offsets[new_idx] + ch['local_time_ms']
            chapter = ChapterInfo(time_ms=new_time_ms, title=ch['title'], source_index=new_idx)
            all_chapters.append(chapter)

            row = self._table.rowCount()
            self._table.insertRow(row)

            time_item = QTableWidgetItem(chapter.time_str)
            title_item = QTableWidgetItem(ch['title'])

            # 色を復元
            color = ch['color'] if ch['color'] else default_color
            time_item.setForeground(QBrush(color))
            title_item.setForeground(QBrush(color))
            time_item.setData(Qt.ItemDataRole.UserRole, color)
            title_item.setData(Qt.ItemDataRole.UserRole, color)
            time_item.setData(Qt.ItemDataRole.UserRole + 1, new_idx)
            title_item.setData(Qt.ItemDataRole.UserRole + 1, new_idx)

            self._table.setItem(row, 0, time_item)
            self._table.setItem(row, 1, title_item)

        self._table.blockSignals(False)
        self._state.chapters = all_chapters
        self._chapters_edited = True

    def _finalize_row_move(self):
        """行移動後の共通処理"""
        # 現在再生中のソースを特定（パスで）
        current_playing_url = self._media_player.source() if self._media_player else None
        current_playing_path = None
        current_local_pos = 0
        if current_playing_url and not current_playing_url.isEmpty():
            current_playing_path = current_playing_url.toLocalFile()
            current_local_pos = self._media_player.position() if self._media_player else 0

        # UI更新
        self._source_list.set_sources(self._state.sources)
        self._update_waveform_chapters()

        # 現在再生中のソースの新しいインデックスを設定
        if current_playing_path:
            for idx, src in enumerate(self._state.sources):
                if str(src.path) == current_playing_path:
                    self._source_list.set_current_index(idx)
                    break

        # 波形位置を更新（仮想位置を再計算）
        virtual_pos = 0
        if len(self._state.sources) > 1:
            current_idx = self._source_list.get_current_index()
            virtual_pos = self._source_to_virtual(current_idx, current_local_pos)
            total_duration = self._get_total_duration()
            if total_duration > 0 and self._waveform_widget:
                self._waveform_widget.set_position(virtual_pos / total_duration)

        # 現在再生中のチャプターをハイライト
        self._highlight_current_chapter(virtual_pos)

        # 波形を再生成
        if self._state.sources:
            self._start_waveform_generation(self._state.sources[0].path)

    def _update_chapter_drag_enabled(self):
        """チャプターのドラッグ＆ドロップ可否を更新

        以下のいずれかの場合にドラッグを許可：
        1. ソース数とチャプター数が1:1対応
        2. 全チャプターにsource_indexが設定されている（埋め込みまたは手動追加）

        曲内に複数のチャプターマーカーがある場合は、
        ソースと連動して移動する。
        """
        row_count = self._table.rowCount()
        source_count = len(self._state.sources)

        # 全チャプターにsource_indexが設定されているかチェック
        all_have_source_index = row_count > 0
        for row in range(row_count):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole + 1) is None:
                all_have_source_index = False
                break

        # ドラッグ許可条件：
        # 1. 1:1対応の場合
        # 2. 全チャプターにsource_indexが設定されている場合
        one_to_one = source_count == row_count and source_count > 1
        has_source_index = all_have_source_index and source_count > 1
        can_drag = one_to_one or has_source_index

        # テーブルのドラッグを有効/無効化
        self._table.setDragEnabled(can_drag)

        self._log_panel.debug(
            f"Drag update: sources={source_count}, rows={row_count}, "
            f"has_source_index={all_have_source_index}, can_drag={can_drag}",
            source="DnD"
        )

        # ツールチップで状態を表示
        if can_drag:
            if has_source_index and not one_to_one:
                self._table.setToolTip("行をドラッグして曲順を変更（チャプターも連動）")
            else:
                self._table.setToolTip("行をドラッグして曲順を変更")
        elif source_count == 1:
            self._table.setToolTip("")
        elif row_count == 0:
            self._table.setToolTip("")
        else:
            self._table.setToolTip("チャプター数とソース数が一致しないため並び替え無効")

    def _on_selection_changed(self):
        """選択変更時のスタイル更新"""
        # 現在の選択行を取得
        selected_row = self._table.currentRow()
        self._log_panel.debug(f"Selection changed: row={selected_row}, playing={self._current_chapter_row}", source="UI")

        # 全行のボールドをリセット（再生中ハイライト行は除く）
        for row in range(self._table.rowCount()):
            is_playing = (row == self._current_chapter_row)
            is_selected = (row == selected_row)
            should_bold = is_playing or is_selected
            for col in range(2):
                item = self._table.item(row, col)
                if item:
                    font = item.font()
                    font.setBold(should_bold)
                    item.setFont(font)

        # 選択行が有効ならスクロールして表示
        if selected_row >= 0:
            item = self._table.item(selected_row, 0)
            if item:
                self._table.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)

        # 波形ウィジェットの選択ソースハイライトを更新
        self._update_waveform_selected_range(selected_row)

    def _on_current_cell_changed(self, current_row: int, current_col: int, prev_row: int, prev_col: int):
        """現在セル変更時のスタイル更新（キーボード操作対応）"""
        if current_row == prev_row:
            return  # 行が変わっていなければ何もしない

        self._log_panel.debug(f"Current cell changed: row {prev_row} -> {current_row}", source="UI")

        # 全行のボールドを更新
        for row in range(self._table.rowCount()):
            is_playing = (row == self._current_chapter_row)
            is_selected = (row == current_row)
            should_bold = is_playing or is_selected
            for col in range(2):
                item = self._table.item(row, col)
                if item:
                    font = item.font()
                    font.setBold(should_bold)
                    item.setFont(font)

        # 新しい選択行をスクロールして表示
        if current_row >= 0:
            item = self._table.item(current_row, 0)
            if item:
                self._table.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)

    def _update_waveform_selected_range(self, selected_row: int):
        """選択された行のソース範囲を波形ウィジェットにハイライト表示

        Args:
            selected_row: 選択された行番号（-1の場合はクリア）
        """
        if not self._waveform_widget:
            return

        # 複数ソースモードでない場合はハイライト不要
        if len(self._state.sources) <= 1:
            self._waveform_widget.clear_selected_source_range()
            return

        # 無効な行の場合はクリア
        if selected_row < 0:
            self._waveform_widget.clear_selected_source_range()
            return

        # 選択行のsource_indexを取得
        item = self._table.item(selected_row, 0)
        if not item:
            self._waveform_widget.clear_selected_source_range()
            return

        source_idx = item.data(Qt.ItemDataRole.UserRole + 1)
        if source_idx is None or source_idx < 0 or source_idx >= len(self._state.sources):
            self._waveform_widget.clear_selected_source_range()
            return

        # ソースの正規化範囲を計算
        total_duration = self._get_total_duration()
        if total_duration <= 0:
            self._waveform_widget.clear_selected_source_range()
            return

        offsets = self._get_source_offsets()
        start_ms = offsets[source_idx] if source_idx < len(offsets) else 0
        end_ms = start_ms + self._state.sources[source_idx].duration_ms

        start_norm = start_ms / total_duration
        end_norm = end_ms / total_duration

        self._waveform_widget.set_selected_source_range(start_norm, end_norm)

    def _update_waveform_chapters(self):
        """テーブルからチャプターを取得して波形ウィジェットに反映"""
        # ハイライトをリセット（行が変わった可能性があるため）
        self._current_chapter_row = -1

        if not self._waveform_widget:
            return

        chapters = self._get_table_chapters()

        # 仮想タイムラインモードの場合は全体の長さを使用
        if len(self._state.sources) > 1:
            duration = self._get_total_duration()
        else:
            duration = self._media_player.duration() if self._media_player else 0

        self._waveform_widget.set_chapters(chapters, duration)

    def _remove_row(self, row: int):
        """指定行削除"""
        self._table.removeRow(row)

    def _on_chapter_clicked(self, row: int, column: int):
        """チャプタークリックでその位置にシーク（仮想タイムライン対応）"""
        time_item = self._table.item(row, 0)
        if not time_item:
            return

        time_str = time_item.text()

        # ChapterInfoを使って時間をパース
        try:
            chapter = ChapterInfo.from_time_str(time_str, "")
            position_ms = chapter.time_ms
        except ValueError:
            self._log_panel.warning(f"Invalid time format: {time_str}", source="Chapter")
            return

        # 仮想タイムラインでシーク
        self._seek_virtual(position_ms)
        self._log_panel.debug(f"Seek to chapter: {time_str}", source="Chapter")

    def _goto_prev_chapter(self):
        """前のチャプターにジャンプ（仮想タイムライン対応）"""
        if self._table.rowCount() == 0:
            return

        # 仮想タイムライン位置を使用
        current_pos = self._get_virtual_position()

        # 現在位置より前のチャプターを探す（少しマージンを持たせる）
        prev_row = -1
        for row in range(self._table.rowCount()):
            time_item = self._table.item(row, 0)
            if time_item:
                try:
                    chapter = ChapterInfo.from_time_str(time_item.text(), "")
                    # 現在位置より1秒以上前のチャプターを探す
                    if chapter.time_ms < current_pos - 1000:
                        prev_row = row
                    else:
                        break
                except ValueError:
                    continue

        if prev_row >= 0:
            self._on_chapter_clicked(prev_row, 0)
            self._table.selectRow(prev_row)
        elif self._table.rowCount() > 0:
            # 最初のチャプターにジャンプ
            self._on_chapter_clicked(0, 0)
            self._table.selectRow(0)

    def _goto_next_chapter(self):
        """次のチャプターにジャンプ（仮想タイムライン対応）"""
        if self._table.rowCount() == 0:
            return

        # 仮想タイムライン位置を使用
        current_pos = self._get_virtual_position()

        # 現在位置より後のチャプターを探す
        for row in range(self._table.rowCount()):
            time_item = self._table.item(row, 0)
            if time_item:
                try:
                    chapter = ChapterInfo.from_time_str(time_item.text(), "")
                    # 現在位置より少し後のチャプターを探す
                    if chapter.time_ms > current_pos + 500:
                        self._on_chapter_clicked(row, 0)
                        self._table.selectRow(row)
                        return
                except ValueError:
                    continue

        # 見つからなければ最後のチャプターにジャンプ
        last_row = self._table.rowCount() - 1
        if last_row >= 0:
            self._on_chapter_clicked(last_row, 0)
            self._table.selectRow(last_row)

    def _update_chapter_buttons(self):
        """チャプタースキップボタンの有効/無効を更新

        チャプターリストが編集された場合にのみ有効化
        """
        has_chapters = self._table.rowCount() > 0
        has_media = self._media_player and self._media_player.duration() > 0
        enabled = has_chapters and has_media and self._chapters_edited
        self._prev_chapter_btn.setEnabled(enabled)
        self._next_chapter_btn.setEnabled(enabled)

    def _update_seek_buttons(self, enabled: bool):
        """時間移動ボタンの有効/無効を更新"""
        # 戻る系
        self._btn_m10s.setEnabled(enabled)
        self._btn_m1s.setEnabled(enabled)
        self._btn_m03s.setEnabled(enabled)
        self._btn_m1f.setEnabled(enabled)
        # 進む系
        self._btn_p1f.setEnabled(enabled)
        self._btn_p03s.setEnabled(enabled)
        self._btn_p1s.setEnabled(enabled)
        self._btn_p10s.setEnabled(enabled)

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
            if self._waveform_widget:
                # 仮想タイムラインモードの場合は全体の長さを使用
                if len(self._state.sources) > 1:
                    duration = self._get_total_duration()
                else:
                    duration = self._media_player.duration() if self._media_player else 0
                self._waveform_widget.set_chapters(chapters, duration)

            self._log_panel.info(f"Loaded {len(chapters)} chapters from: {Path(file_path).name}", source="Chapter")
            self._update_chapter_drag_enabled()

            # 最初のチャプターを選択・ハイライト（クリック時と同じ動作）
            if self._table.rowCount() > 0:
                self._table.selectRow(0)
                self._highlight_current_chapter(0)

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
                try:
                    chapter = ChapterInfo.from_time_str(time_str, title)
                    chapters.append(chapter)
                except ValueError:
                    continue

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

        # 先頭チャプター（0:00:00.000）がなければ追加
        if chapters[0].time_ms != 0:
            first_chapter = ChapterInfo(time_ms=0, title=chapters[0].title)
            chapters.insert(0, first_chapter)
            self._log_panel.info("Added chapter at 0:00:00.000", source="Chapter")

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

        # 最初のチャプターを選択・ハイライト（クリック時と同じ動作）
        if self._table.rowCount() > 0:
            self._table.selectRow(0)
            self._highlight_current_chapter(0)

    def _load_all_embedded_chapters(self):
        """全ソースファイルから埋め込みチャプターを読み込んでテーブルに追加

        各ファイルの埋め込みチャプターを連結し、source_indexで所属を追跡。
        埋め込みチャプターがないファイルはファイル名をチャプター名として使用。
        """
        if not self._state.sources:
            return

        all_chapters: List[ChapterInfo] = []
        cumulative_ms = 0
        has_any_embedded = False

        for source_idx, source in enumerate(self._state.sources):
            # このファイルの埋め込みチャプターを取得
            file_chapters = self._extract_chapters_from_media(source.path)

            if file_chapters:
                has_any_embedded = True
                # 先頭チャプター（0:00:00）がなければ追加
                if file_chapters[0].time_ms != 0:
                    first_ch = ChapterInfo(
                        time_ms=0,
                        title=file_chapters[0].title,
                        source_index=source_idx
                    )
                    file_chapters.insert(0, first_ch)

                # 各チャプターの時間をオフセットして追加
                for ch in file_chapters:
                    adjusted_chapter = ChapterInfo(
                        time_ms=cumulative_ms + ch.time_ms,
                        title=ch.title,
                        source_index=source_idx
                    )
                    all_chapters.append(adjusted_chapter)
            else:
                # 埋め込みチャプターがない場合はファイル名をチャプター名に
                chapter = ChapterInfo(
                    time_ms=cumulative_ms,
                    title=source.path.stem,
                    source_index=source_idx
                )
                all_chapters.append(chapter)

            cumulative_ms += source.duration_ms

        if not all_chapters:
            self._has_embedded_chapters = False
            return

        # テーブルをクリアして新しいチャプターを追加
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        self._has_embedded_chapters = has_any_embedded

        # チャプターグループのタイトルを更新
        if hasattr(self, '_chapter_title_label'):
            if has_any_embedded:
                self._chapter_title_label.setText('Chapters <span style="color: #22c55e;">(埋め込み)</span>')
                self._chapter_title_label.setTextFormat(Qt.TextFormat.RichText)
            else:
                self._chapter_title_label.setText("Chapters")
                self._chapter_title_label.setTextFormat(Qt.TextFormat.PlainText)

        # デフォルトの白色
        default_color = QColor("#f0f0f0")

        for ch in all_chapters:
            row = self._table.rowCount()
            self._table.insertRow(row)

            time_item = QTableWidgetItem(ch.time_str)
            title_item = QTableWidgetItem(ch.title)

            # source_indexをUserRole+1に保存（UserRoleは色に使用）
            time_item.setData(Qt.ItemDataRole.UserRole, default_color)
            title_item.setData(Qt.ItemDataRole.UserRole, default_color)
            time_item.setData(Qt.ItemDataRole.UserRole + 1, ch.source_index)
            title_item.setData(Qt.ItemDataRole.UserRole + 1, ch.source_index)

            self._table.setItem(row, 0, time_item)
            self._table.setItem(row, 1, title_item)

        self._table.blockSignals(False)
        self._state.chapters = all_chapters

        self._log_panel.info(
            f"Loaded {len(all_chapters)} chapters from {len(self._state.sources)} files "
            f"(embedded={has_any_embedded})",
            source="Chapter"
        )

        # ドラッグ可否を更新
        self._update_chapter_drag_enabled()

        # 最初のチャプターを選択・ハイライト
        if self._table.rowCount() > 0:
            self._table.selectRow(0)
            self._highlight_current_chapter(0)

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
                try:
                    chapter = ChapterInfo.from_time_str(time_str, title)
                    chapters.append(chapter)
                except ValueError:
                    continue

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

        # 先頭チャプター（0:00:00.000）がなければ追加
        if chapters[0].time_ms != 0:
            # 最初のチャプターのタイトルを使用して先頭に追加
            first_chapter = ChapterInfo(time_ms=0, title=chapters[0].title)
            chapters.insert(0, first_chapter)
            self._log_panel.info("Added chapter at 0:00:00.000", source="Paste")

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
        self._chapters_edited = True
        self._update_waveform_chapters()
        self._update_chapter_buttons()
        self._update_chapter_drag_enabled()
        self._log_panel.info(f"Pasted {len(chapters)} chapters from clipboard", source="Paste")

        # 最初のチャプターを選択・ハイライト（クリック時と同じ動作）
        if self._table.rowCount() > 0:
            self._table.selectRow(0)
            self._highlight_current_chapter(0)

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
                try:
                    chapter = ChapterInfo.from_time_str(time_str, title)
                    chapters.append(chapter)
                except ValueError:
                    continue
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

        # 設定をQSettingsから取得
        settings = ExportSettingsDialog.load_settings_static()
        encoder_id = settings["encoder"]
        quality_index = settings["quality_index"]
        embed_chapters = settings["embed_chapters"]
        cut_excluded = settings["cut_excluded"]
        split_chapters = settings["split_chapters"]

        # 品質設定を取得（音声のみの場合は固定）
        if getattr(self, '_is_audio_only', False):
            bitrate, crf = self._audio_quality_options[0][1], self._audio_quality_options[0][2]
        else:
            if 0 <= quality_index < len(self._video_quality_options):
                _, bitrate, crf = self._video_quality_options[quality_index]
            else:
                bitrate, crf = 0, 23  # デフォルト

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

        # Split Chapters モードの場合
        if split_chapters:
            self._log_panel.info(f"Split export started: {len(chapters)} chapters", source="Export")

            # SplitExportWorkerを作成して開始
            self._export_worker = SplitExportWorker(
                input_file=str(input_path),
                output_dir=str(self._state.work_dir),
                output_base=Path(output_base).name,
                chapters=chapters,
                total_duration_ms=duration_ms,
                encoder_id=encoder_id,
                bitrate_kbps=bitrate,
                crf=crf,
                colorspace=colorspace,
                is_audio_only=input_path.suffix.lower() in AUDIO_EXTENSIONS,
                overlay_title=embed_chapters  # Embed Chapがチェックされている場合、タイトル焼き込み
            )

            # シグナル接続
            self._export_worker.progress_update.connect(self._on_export_progress)
            self._export_worker.progress_percent.connect(self._on_export_percent)
            self._export_worker.chapter_completed.connect(self._on_chapter_completed)
            self._export_worker.export_completed.connect(self._on_split_export_completed)
            self._export_worker.error_occurred.connect(self._on_export_error)

            self._export_worker.start()
            self.export_requested.emit()
            return

        # 通常エクスポート（単一ファイル）
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
        self._update_seek_buttons(True)

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

    def _on_chapter_completed(self, chapter_num: int, output_path: str):
        """チャプター分割エクスポート: 個別チャプター完了"""
        self._log_panel.info(f"Chapter {chapter_num} exported: {Path(output_path).name}", source="Export")

    def _on_split_export_completed(self, count: int):
        """チャプター分割エクスポート完了"""
        self._log_panel.info(f"Split export completed: {count} files", source="Export")
        # ボタンをExportモードに戻す
        self._reset_export_btn()
        # ステータスバー用シグナル
        self.export_finished.emit(True, f"{count} chapters exported")

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
        self._update_seek_buttons(True)
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
            # 作業ディレクトリをファイルの親フォルダに設定
            self._state.work_dir = video_path.parent
            self.work_dir_changed.emit(self._state.work_dir)
            self._log_panel.info(f"Working directory: {video_path.parent}", source="Drop")
            # ソースをクリアして新しい動画を設定
            self._state.sources = [SourceFile(path=video_path)]
            self._prepare_for_new_source()
            self._load_source_media()
            self._log_panel.info(f"Dropped video: {video_path.name}", source="Drop")
        elif audios:
            # 作業ディレクトリを最初のファイルの親フォルダに設定
            self._state.work_dir = audios[0].parent
            self.work_dir_changed.emit(self._state.work_dir)
            self._log_panel.info(f"Working directory: {audios[0].parent}", source="Drop")
            # 音声ファイル: ソースとして設定
            self._state.sources = [SourceFile(path=p) for p in audios]
            self._prepare_for_new_source()
            # 複数MP3の場合、チャプターを自動生成
            if len(audios) > 1:
                self._generate_chapters_from_sources()
            self._load_source_media()
            if len(audios) == 1:
                self._log_panel.info(f"Dropped audio: {audios[0].name}", source="Drop")
            else:
                self._log_panel.info(f"Dropped {len(audios)} audio files", source="Drop")

    def _on_folder_dropped(self, folder_path: str):
        """フォルダドロップ時の処理: 作業ディレクトリを設定してソース選択ダイアログを開く"""
        path = Path(folder_path)
        if not path.is_dir():
            return

        self._state.work_dir = path
        self.work_dir_changed.emit(self._state.work_dir)
        self._log_panel.info(f"Working directory changed: {path}", source="Drop")

        # ソース選択ダイアログを開く（Select Sourceボタンと同じ挙動）
        self._open_source_dialog()

    def cleanup(self):
        """リソースクリーンアップ"""
        # 波形スレッドをクリーンアップ
        self._cleanup_waveform_thread()

        # スペクトログラムスレッドをクリーンアップ
        if self._spectrogram_worker:
            self._spectrogram_worker.cancel()
            self._spectrogram_worker = None

        if self._spectrogram_thread and self._spectrogram_thread.isRunning():
            self._spectrogram_thread.quit()
            self._spectrogram_thread.wait(1000)
            self._spectrogram_thread = None

        # YouTubeダウンロードワーカーをクリーンアップ
        if self._youtube_worker and self._youtube_worker.isRunning():
            self._youtube_worker.cancel()
            self._youtube_worker.wait(1000)
            self._youtube_worker = None

        # プレイリストワーカーをクリーンアップ
        if self._playlist_info_worker and self._playlist_info_worker.isRunning():
            self._playlist_info_worker.terminate()
            self._playlist_info_worker.wait(1000)
            self._playlist_info_worker = None

        if self._playlist_worker and self._playlist_worker.isRunning():
            self._playlist_worker.cancel()
            self._playlist_worker.wait(1000)
            self._playlist_worker = None

        # エクスポートワーカーをクリーンアップ
        if hasattr(self, '_export_worker') and self._export_worker is not None:
            if self._export_worker.isRunning():
                self._export_worker.cancel()
                self._export_worker.wait(1000)
            self._export_worker = None

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
                    # 編集中でなければTitle列（列1）を編集開始
                    index = self._table.currentIndex()
                    if index.isValid():
                        # Title列（列1）のインデックスを作成
                        title_index = self._table.model().index(index.row(), 1)
                        # 一時的にトリガーを有効にして編集開始
                        self._table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
                        self._table.edit(title_index)
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

        # ビューポート: ダブルクリックでシーク、ドロップで行順序同期
        elif obj == self._table.viewport():
            if event.type() == QEvent.Type.MouseButtonDblClick:
                # ビューポート座標でセルを検出
                pos = event.position().toPoint()
                index = self._table.indexAt(pos)
                if index.isValid():
                    self._on_chapter_clicked(index.row(), index.column())
                return True  # 編集をブロック

            elif event.type() == QEvent.Type.MouseButtonPress:
                # マウスプレス時にドラッグ元行を保存（ドラッグ開始前に確実に取得）
                pos = event.position().toPoint()
                index = self._table.indexAt(pos)
                if index.isValid():
                    self._drag_source_row = index.row()
                else:
                    self._drag_source_row = -1

            elif event.type() == QEvent.Type.Drop:
                # カスタムテーブルの挿入位置インジケーターを使用
                indicator_row = self._table._drop_indicator_row
                indicator_above = self._table._drop_indicator_above

                source_row = getattr(self, '_drag_source_row', -1)

                # 挿入位置を計算
                if indicator_row >= 0:
                    if indicator_above:
                        # 行の上に挿入 → その行の位置に挿入
                        target_row = indicator_row
                    else:
                        # 行の下に挿入 → 次の行の位置に挿入
                        target_row = indicator_row + 1

                    # ソース行より後ろに移動する場合は調整
                    if source_row < target_row:
                        target_row -= 1
                else:
                    # インジケーターがない場合は従来のロジック
                    drop_pos = event.position().toPoint()
                    drop_index = self._table.indexAt(drop_pos)
                    target_row = drop_index.row() if drop_index.isValid() else self._table.rowCount() - 1

                self._log_panel.debug(
                    f"Drop event: source={source_row}, target={target_row}, indicator={indicator_row}, above={indicator_above}",
                    source="DnD"
                )

                # インジケーターをリセット
                self._table._drop_indicator_row = -1
                self._table.viewport().update()

                if source_row >= 0 and source_row != target_row:
                    # デフォルトのドロップ処理を無効化し、自分で処理
                    self._handle_row_move(source_row, target_row)
                    return True  # デフォルト処理をブロック

        # ビデオコンテナ: リサイズ時に子ウィジェットのサイズを調整
        elif obj == self._video_container:
            if event.type() == QEvent.Type.Resize:
                self._resize_video_overlays()

        return super().eventFilter(obj, event)
