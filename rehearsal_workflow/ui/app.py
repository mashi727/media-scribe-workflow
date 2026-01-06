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
    QMenuBar, QMenu, QStatusBar, QLabel, QProgressBar, QMessageBox,
    QFileDialog
)
from PySide6.QtCore import Qt, QTimer, QThread
from PySide6.QtGui import QAction, QFont, QFontDatabase

from .main_workspace import MainWorkspace
from .log_panel import LogLevel
from .updater import (
    UpdateChecker, UpdateDownloader,
    open_in_file_manager, mount_and_open_dmg
)


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

    VERSION = "2.1.26"

    def __init__(self, work_dir: Optional[Path] = None):
        super().__init__()
        self._work_dir = work_dir or Path.cwd()

        # アップデート関連
        self._update_thread: Optional[QThread] = None
        self._update_checker: Optional[UpdateChecker] = None
        self._download_thread: Optional[QThread] = None
        self._downloader: Optional[UpdateDownloader] = None
        self._pending_update_url: Optional[str] = None
        self._pending_update_version: Optional[str] = None

        self._setup_window()
        self._setup_menu()
        self._setup_ui()
        self._setup_statusbar()

        # 起動後3秒でアップデートチェック
        QTimer.singleShot(3000, self._check_for_updates)

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

        chapter_overlay_action = QAction("Show Chapter Overlay", self)
        chapter_overlay_action.setCheckable(True)
        chapter_overlay_action.setChecked(True)  # デフォルトON
        chapter_overlay_action.triggered.connect(self._toggle_chapter_overlay)
        view_menu.addAction(chapter_overlay_action)

        view_menu.addSeparator()

        log_debug = QAction("Show Debug Logs", self)
        log_debug.setCheckable(True)
        log_debug.triggered.connect(lambda checked: self._set_log_level(LogLevel.DEBUG if checked else LogLevel.INFO))
        view_menu.addAction(log_debug)

        # Help メニュー
        help_menu = menubar.addMenu("Help")

        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)

        help_menu.addSeparator()

        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_ui(self):
        """メインUI設定"""
        self._workspace = MainWorkspace(work_dir=self._work_dir)
        self.setCentralWidget(self._workspace)

        # シグナル接続
        self._workspace.export_progress.connect(self._on_export_progress)
        self._workspace.export_finished.connect(self._on_export_finished)
        self._workspace.work_dir_changed.connect(self._on_work_dir_changed)

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
        self._set_progress_style_processing()  # デフォルトは処理中スタイル
        right_layout.addWidget(self._progress_bar)

        # 状態表示ラベル
        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #22c55e; font-weight: bold; font-size: 18px;")
        self._status_label.setMinimumWidth(200)
        right_layout.addWidget(self._status_label)

        self._statusbar.addPermanentWidget(right_widget)

    # === メニューアクション ===

    def _open_folder(self):
        """フォルダを開く（Select Sourceと同じ挙動）"""
        self._workspace._open_source_dialog()

    def _paste_chapters(self):
        """チャプターをペースト"""
        self._workspace.paste_chapters()

    def _toggle_chapter_overlay(self, checked: bool):
        """チャプターオーバーレイ表示切り替え"""
        self._workspace.set_chapter_overlay_enabled(checked)

    def _set_log_level(self, level: LogLevel):
        """ログレベル設定"""
        log = self._workspace.get_log_panel()
        log._level_combo.setCurrentIndex(level)
        log.info(f"Log level set to {log.LEVEL_NAMES[level]}", source="App")

    def _show_shortcuts(self):
        """キーボードショートカット表示"""
        shortcuts = """
<h3>キーボードショートカット</h3>

<table>
<tr><td><b>Space</b></td><td>再生 / 一時停止</td></tr>
<tr><td><b>←/→</b></td><td>5秒戻る / 5秒進む</td></tr>
<tr><td><b>Shift+←/→</b></td><td>1秒戻る / 1秒進む</td></tr>
<tr><td><b>↑/↓</b></td><td>前/次のチャプターへジャンプ</td></tr>
</table>

<h4>チャプター編集</h4>
<table>
<tr><td><b>Enter</b></td><td>セルを編集モードに</td></tr>
<tr><td><b>↑ (編集中)</b></td><td>カーソルを行頭へ</td></tr>
<tr><td><b>↓ (編集中)</b></td><td>カーソルを行末へ</td></tr>
<tr><td><b>Cmd+V / Ctrl+V</b></td><td>チャプターをペースト</td></tr>
</table>

<h4>ドラッグ＆ドロップ</h4>
<table>
<tr><td><b>動画ファイル</b></td><td>読み込み（複数の場合は最初のみ）</td></tr>
<tr><td><b>音声ファイル</b></td><td>読み込み（複数はチャプター自動生成）</td></tr>
<tr><td><b>フォルダ</b></td><td>作業ディレクトリとして設定</td></tr>
</table>
"""
        msg = QMessageBox(self)
        msg.setWindowTitle("Keyboard Shortcuts")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(shortcuts)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.exec()

    def _show_about(self):
        """About表示"""
        about_text = f"""
<h2>Video Chapter Editor</h2>
<p><b>Version {self.VERSION}</b></p>
<p>動画チャプター編集・書出ツール</p>

<h4>機能</h4>
<ul>
<li>動画プレビュー + 波形表示</li>
<li>チャプター編集（追加/削除/編集）</li>
<li>除外チャプター（カット区間）</li>
<li>YouTubeチャプター コピー＆ペースト</li>
<li>ffmpegによる動画書き出し</li>
<li>GPUハードウェアエンコード対応</li>
</ul>

<p>© 2024 mashi727</p>
<p><a href="https://github.com/mashi727/rehearsal-workflow">GitHub</a></p>
"""
        msg = QMessageBox(self)
        msg.setWindowTitle("About Video Chapter Editor")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(about_text)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.exec()

    # === エクスポート進捗ハンドラ ===

    def _on_export_progress(self, percent: int, status: str):
        """エクスポート進捗表示"""
        # プログレスバーを表示・更新
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(percent)

        # ステータステキスト（処理中は赤）
        self._status_label.setText(status)
        self._status_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 18px;")

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

    def _set_progress_style_processing(self):
        """プログレスバーを処理中スタイル（赤）に設定"""
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: #ef4444;
                border-radius: 3px;
            }
        """)

    def _on_work_dir_changed(self, new_dir):
        """作業ディレクトリ変更時"""
        self._work_dir = new_dir
        self._workdir_label.setText(f"Working Directory: {new_dir}")

    # === アップデート機能 ===

    def _check_for_updates(self):
        """バックグラウンドでアップデートをチェック"""
        self._update_thread = QThread()
        self._update_checker = UpdateChecker(self.VERSION)
        self._update_checker.moveToThread(self._update_thread)

        self._update_thread.started.connect(self._update_checker.run)
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.check_finished.connect(self._cleanup_update_check)
        self._update_checker.error.connect(self._on_update_check_error)

        self._update_thread.start()

    def _cleanup_update_check(self):
        """アップデートチェックスレッドをクリーンアップ"""
        if self._update_thread:
            self._update_thread.quit()
            self._update_thread.wait(1000)
            self._update_thread = None
            self._update_checker = None

    def _on_update_check_error(self, error: str):
        """アップデートチェックエラー（静かに無視）"""
        self._cleanup_update_check()
        # ログにのみ記録
        log = self._workspace.get_log_panel()
        log.debug(f"Update check failed: {error}", source="Updater")

    def _on_update_available(self, version: str, url: str, notes: str):
        """新バージョンが利用可能"""
        self._cleanup_update_check()

        self._pending_update_version = version
        self._pending_update_url = url

        # ステータスバーに通知を表示
        self._status_label.setText(f"🔄 v{version} available")
        self._status_label.setStyleSheet(
            "color: #f59e0b; font-weight: bold; font-size: 18px; cursor: pointer;"
        )
        self._status_label.setToolTip(f"Click to update to v{version}")

        # クリックでダウンロード開始
        self._status_label.mousePressEvent = lambda e: self._confirm_update()

        # ログにも記録
        log = self._workspace.get_log_panel()
        log.info(f"New version v{version} available", source="Updater")

    def _confirm_update(self):
        """アップデート確認ダイアログ"""
        if not self._pending_update_url:
            return

        reply = QMessageBox.question(
            self,
            "Update Available",
            f"Version {self._pending_update_version} is available.\n\n"
            "Download and install the update?\n\n"
            "(The app will open the download location in Finder/Explorer)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._start_download()

    def _start_download(self):
        """アップデートのダウンロードを開始"""
        if not self._pending_update_url:
            return

        # ファイル名を抽出
        filename = self._pending_update_url.split("/")[-1]

        self._download_thread = QThread()
        self._downloader = UpdateDownloader(self._pending_update_url, filename)
        self._downloader.moveToThread(self._download_thread)

        self._download_thread.started.connect(self._downloader.run)
        self._downloader.progress.connect(self._on_download_progress)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.error.connect(self._on_download_error)

        # UI更新（処理中は赤）
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._status_label.setText("Downloading update...")
        self._status_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 18px;")

        self._download_thread.start()

    def _on_download_progress(self, percent: int):
        """ダウンロード進捗"""
        self._progress_bar.setValue(percent)
        self._status_label.setText(f"Downloading... {percent}%")

    def _on_download_finished(self, file_path: str):
        """ダウンロード完了"""
        self._cleanup_download()

        self._progress_bar.setVisible(False)
        self._status_label.setText("Download complete!")
        self._status_label.setStyleSheet("color: #22c55e; font-weight: bold; font-size: 18px;")

        log = self._workspace.get_log_panel()
        log.info(f"Update downloaded: {file_path}", source="Updater")

        # macOSでDMGの場合はマウントして開く
        if file_path.endswith(".dmg"):
            if mount_and_open_dmg(file_path):
                log.info("DMG mounted - drag app to Applications folder", source="Updater")
                QMessageBox.information(
                    self,
                    "Update Ready",
                    "The update has been downloaded and mounted.\n\n"
                    "Please drag the new app to your Applications folder\n"
                    "to complete the update."
                )
            else:
                open_in_file_manager(file_path)
        else:
            # ZIPの場合はExplorerで開く
            open_in_file_manager(file_path)
            QMessageBox.information(
                self,
                "Update Ready",
                f"The update has been downloaded to:\n{file_path}\n\n"
                "Please extract and run the new version."
            )

        # ステータスをリセット
        QTimer.singleShot(5000, self._reset_status)

    def _on_download_error(self, error: str):
        """ダウンロードエラー"""
        self._cleanup_download()

        self._progress_bar.setVisible(False)
        self._status_label.setText("Download failed")
        self._status_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 18px;")

        log = self._workspace.get_log_panel()
        log.error(f"Download failed: {error}", source="Updater")

        QMessageBox.warning(
            self,
            "Download Failed",
            f"Failed to download update:\n{error}"
        )

        QTimer.singleShot(5000, self._reset_status)

    def _cleanup_download(self):
        """ダウンロードスレッドをクリーンアップ"""
        if self._download_thread:
            self._download_thread.quit()
            self._download_thread.wait(1000)
            self._download_thread = None
            self._downloader = None

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

    def closeEvent(self, event):
        """アプリケーション終了時のクリーンアップ"""
        # アップデートチェックスレッドをクリーンアップ
        self._cleanup_update_check()

        # ダウンロードスレッドをクリーンアップ
        self._cleanup_download()

        # MainWorkspaceのクリーンアップ
        if self._workspace:
            self._workspace.cleanup()

        super().closeEvent(event)


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
