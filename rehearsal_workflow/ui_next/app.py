"""
app.py - アプリケーションメインウィンドウ

次世代UIのエントリーポイント。
"""

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QMenuBar, QMenu, QStatusBar
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from .main_workspace import MainWorkspace
from .log_panel import LogLevel


class VideoChapterEditorNext(QMainWindow):
    """
    Video Chapter Editor (Next Generation)

    単一画面 + ダイアログパターンのメインウィンドウ。
    """

    VERSION = "2.0.0-alpha"

    def __init__(self, work_dir: Optional[Path] = None):
        super().__init__()
        self._work_dir = work_dir or Path.cwd()
        self._setup_window()
        self._setup_menu()
        self._setup_ui()
        self._setup_statusbar()

    def _setup_window(self):
        """ウィンドウ設定"""
        self.setWindowTitle(f"Video Chapter Editor (Next) - {self.VERSION}")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        # ダークテーマ
        self.setStyleSheet("""
            QMainWindow {
                background: #242424;
            }
            QMenuBar {
                background: #1a1a1a;
                color: #f0f0f0;
                border-bottom: 1px solid #3a3a3a;
            }
            QMenuBar::item:selected {
                background: #3b82f6;
            }
            QMenu {
                background: #1a1a1a;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
            }
            QMenu::item:selected {
                background: #3b82f6;
            }
            QStatusBar {
                background: #1a1a1a;
                color: #a0a0a0;
                border-top: 1px solid #3a3a3a;
            }
        """)

    def _setup_menu(self):
        """メニューバー設定"""
        menubar = self.menuBar()

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
        self._workspace = MainWorkspace()
        self.setCentralWidget(self._workspace)

        # ログパネルにアクセス
        log = self._workspace.get_log_panel()
        log.info(f"Video Chapter Editor {self.VERSION} started", source="App")
        log.info(f"Working directory: {self._work_dir}", source="App")

    def _setup_statusbar(self):
        """ステータスバー設定"""
        self._statusbar = self.statusBar()
        self._statusbar.showMessage("Ready")

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


def main():
    """エントリーポイント"""
    app = QApplication(sys.argv)

    # 作業ディレクトリ（コマンドライン引数から）
    work_dir = None
    if len(sys.argv) > 1:
        work_dir = Path(sys.argv[1])
        if not work_dir.is_dir():
            work_dir = None

    window = VideoChapterEditorNext(work_dir)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
