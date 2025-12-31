"""
app.py - アプリケーションメインウィンドウ

Video Chapter Editor v2.0 エントリーポイント。
クロスプラットフォーム対応（macOS / Windows）
"""

import sys
import platform
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QMenuBar, QMenu, QStatusBar, QLabel, QProgressBar
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QFontDatabase

from .main_workspace import MainWorkspace
from .log_panel import LogLevel


# === クロスプラットフォーム設定 ===

# デフォルトウィンドウサイズ
WINDOW_WIDTH = 1680
WINDOW_HEIGHT = 1050

# 最小ウィンドウサイズ
MIN_WINDOW_WIDTH = 1120
MIN_WINDOW_HEIGHT = 700

# アスペクト比 (8:5)
ASPECT_RATIO = WINDOW_WIDTH / WINDOW_HEIGHT

# プラットフォーム別フォント設定
def get_system_fonts() -> dict:
    """プラットフォーム別のフォント名を取得"""
    system = platform.system()

    if system == "Darwin":  # macOS
        # SF Pro/SF Monoは別途インストールが必要なため、標準フォントを優先
        return {
            "ui": "Helvetica Neue",
            "ui_fallback": "Helvetica",
            "mono": "Menlo",
            "mono_fallback": "Monaco",
        }
    elif system == "Windows":
        return {
            "ui": "Segoe UI",
            "ui_fallback": "Arial",
            "mono": "Consolas",
            "mono_fallback": "Courier New",
        }
    else:  # Linux
        return {
            "ui": "DejaVu Sans",
            "ui_fallback": "Liberation Sans",
            "mono": "DejaVu Sans Mono",
            "mono_fallback": "Liberation Mono",
        }


def get_monospace_font(size: int = 11) -> QFont:
    """クロスプラットフォーム対応の等幅フォントを取得"""
    fonts = get_system_fonts()

    # 優先フォントを試行
    for font_name in [fonts["mono"], fonts["mono_fallback"]]:
        if QFontDatabase.hasFamily(font_name) and QFontDatabase.isFixedPitch(font_name):
            return QFont(font_name, size)

    # フォールバック: システムの等幅フォント
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(size)
    return font


def get_ui_font(size: int = 13) -> QFont:
    """クロスプラットフォーム対応のUIフォントを取得"""
    fonts = get_system_fonts()

    for font_name in [fonts["ui"], fonts["ui_fallback"]]:
        font = QFont(font_name, size)
        if font.exactMatch() or QFontDatabase.hasFamily(font_name):
            return font

    # フォールバック: システムフォント
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSize(size)
    return font


class VideoChapterEditor(QMainWindow):
    """
    Video Chapter Editor v2.0

    単一画面 + ダイアログパターンのメインウィンドウ。
    """

    VERSION = "2.1.11"

    def __init__(self, work_dir: Optional[Path] = None):
        super().__init__()
        self._work_dir = work_dir or Path.cwd()
        self._setup_window()
        self._setup_menu()
        self._setup_ui()
        self._setup_statusbar()

    def _setup_window(self):
        """ウィンドウ設定"""
        self.setWindowTitle(f"Video Chapter Editor - {self.VERSION}")

        # リサイズ可能（アスペクト比維持）
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self._aspect_ratio = ASPECT_RATIO
        self._resizing = False  # リサイズ中フラグ（再帰防止）

        # アプリケーション全体のUIフォント設定
        app = QApplication.instance()
        if app:
            app.setFont(get_ui_font(16))

        # ダークテーマ
        self.setStyleSheet("""
            QMainWindow {
                background: #242424;
            }
            QMenuBar {
                background: #1a1a1a;
                color: #f0f0f0;
                border-bottom: 1px solid #3a3a3a;
                font-size: 16px;
            }
            QMenuBar::item:selected {
                background: #3b82f6;
            }
            QMenu {
                background: #1a1a1a;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                font-size: 16px;
            }
            QMenu::item:selected {
                background: #3b82f6;
            }
            QStatusBar {
                background: #1a1a1a;
                color: #a0a0a0;
                border-top: 1px solid #3a3a3a;
                padding: 8px 12px;
                min-height: 28px;
            }
        """)

    def _setup_menu(self):
        """メニューバー設定"""
        menubar = self.menuBar()

        # macOSでもウィンドウ内にメニューバーを表示（Windows/macOS統一UI）
        menubar.setNativeMenuBar(False)

        # File メニュー
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open Folder...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_folder)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit メニュー
        edit_menu = menubar.addMenu("Edit")

        paste_action = QAction("Paste Chapters", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(self._paste_chapters)
        edit_menu.addAction(paste_action)

        # View メニュー
        view_menu = menubar.addMenu("View")

        log_debug = QAction("Show Debug Logs", self)
        log_debug.setCheckable(True)
        log_debug.triggered.connect(lambda checked: self._set_log_level(LogLevel.DEBUG if checked else LogLevel.INFO))
        view_menu.addAction(log_debug)

        # Help メニュー
        help_menu = menubar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_ui(self):
        """メインUI設定"""
        self._workspace = MainWorkspace(work_dir=self._work_dir)
        self.setCentralWidget(self._workspace)

        # エクスポート進捗シグナル接続
        self._workspace.export_progress.connect(self._on_export_progress)
        self._workspace.export_finished.connect(self._on_export_finished)

        # ログパネルにアクセス
        log = self._workspace.get_log_panel()
        log.info(f"Video Chapter Editor {self.VERSION} started", source="App")
        log.info(f"Working directory: {self._work_dir}", source="App")

    def _setup_statusbar(self):
        """ステータスバー設定"""
        self._statusbar = self.statusBar()

        # Working Directory表示（左側）
        self._workdir_label = QLabel(f"Working Directory: {self._work_dir}")
        self._workdir_label.setStyleSheet("color: #a0a0a0; font-size: 18px;")
        self._statusbar.addWidget(self._workdir_label)

        # 右側: プログレスバー + 状態表示を統合
        right_widget = QWidget()
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # プログレスバー（通常は非表示）
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(150)
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: #3b82f6;
                border-radius: 3px;
            }
        """)
        right_layout.addWidget(self._progress_bar)

        # 状態表示ラベル
        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #22c55e; font-weight: bold; font-size: 18px;")
        self._status_label.setMinimumWidth(200)
        right_layout.addWidget(self._status_label)

        self._statusbar.addPermanentWidget(right_widget)

    # === メニューアクション ===

    def _open_folder(self):
        """フォルダを開く"""
        # TODO: 実装
        pass

    def _paste_chapters(self):
        """チャプターをペースト"""
        # TODO: 実装
        log = self._workspace.get_log_panel()
        log.info("Paste chapters triggered", source="App")

    def _set_log_level(self, level: LogLevel):
        """ログレベル設定"""
        log = self._workspace.get_log_panel()
        log._level_combo.setCurrentIndex(level)
        log.info(f"Log level set to {log.LEVEL_NAMES[level]}", source="App")

    def _show_about(self):
        """About表示"""
        log = self._workspace.get_log_panel()
        log.info(f"Video Chapter Editor {self.VERSION}", source="App")
        log.info("Next generation UI with single workspace + dialogs", source="App")

    # === エクスポート進捗ハンドラ ===

    def _on_export_progress(self, percent: int, status: str):
        """エクスポート進捗表示"""
        # プログレスバーを表示・更新
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(percent)

        # ステータステキスト（青字）
        self._status_label.setText(status)
        self._status_label.setStyleSheet("color: #3b82f6; font-weight: bold; font-size: 18px;")

    def _on_export_finished(self, success: bool, message: str):
        """エクスポート完了表示"""
        if success:
            # 完了時は100%表示してから非表示
            self._progress_bar.setValue(100)
            self._status_label.setText(f"Completed: {message}")
            self._status_label.setStyleSheet("color: #22c55e; font-weight: bold; font-size: 18px;")
            # 3秒後にプログレスバーを非表示、Readyに戻す
            QTimer.singleShot(3000, self._reset_status)
        else:
            self._progress_bar.setVisible(False)
            self._status_label.setText(f"Failed: {message}")
            self._status_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 18px;")
            # 5秒後にReadyに戻す
            QTimer.singleShot(5000, self._reset_status)

    def _reset_status(self):
        """ステータスを初期状態に戻す"""
        self._progress_bar.setVisible(False)
        self._progress_bar.setValue(0)
        self._status_label.setText("Ready")
        self._status_label.setStyleSheet("color: #22c55e; font-weight: bold; font-size: 18px;")

    def resizeEvent(self, event):
        """リサイズ時にアスペクト比を維持"""
        if self._resizing:
            return super().resizeEvent(event)

        self._resizing = True

        new_size = event.size()
        old_size = event.oldSize()

        # 幅と高さのどちらが変更されたかを判定
        width_changed = new_size.width() != old_size.width()
        height_changed = new_size.height() != old_size.height()

        if width_changed and height_changed:
            # 両方変更された場合は幅を基準にする
            new_width = new_size.width()
            new_height = int(new_width / self._aspect_ratio)
        elif width_changed:
            # 幅が変更された場合
            new_width = new_size.width()
            new_height = int(new_width / self._aspect_ratio)
        else:
            # 高さが変更された場合
            new_height = new_size.height()
            new_width = int(new_height * self._aspect_ratio)

        # 最小サイズを確保
        new_width = max(new_width, MIN_WINDOW_WIDTH)
        new_height = max(new_height, MIN_WINDOW_HEIGHT)

        # サイズが変更された場合のみリサイズ
        if new_width != new_size.width() or new_height != new_size.height():
            self.resize(new_width, new_height)

        self._resizing = False
        super().resizeEvent(event)


def main():
    """エントリーポイント"""
    # High DPI対応（QApplication作成前に設定）
    # PySide6では自動的にHigh DPI対応されるが、明示的に設定
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    # プラットフォーム情報をログ
    system = platform.system()
    print(f"Platform: {system}")
    print(f"Window size: {WINDOW_WIDTH}x{WINDOW_HEIGHT}")

    # 作業ディレクトリ（コマンドライン引数から）
    work_dir = None
    if len(sys.argv) > 1:
        work_dir = Path(sys.argv[1])
        if not work_dir.is_dir():
            work_dir = None

    window = VideoChapterEditor(work_dir)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
