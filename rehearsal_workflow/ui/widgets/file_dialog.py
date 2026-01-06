"""
file_dialog.py - カスタムファイルダイアログ

中央配置 + ダークテーマ対応のファイルダイアログ。
"""

from PySide6.QtWidgets import QFileDialog, QDialog, QListView, QTreeView
from PySide6.QtCore import QTimer


class CenteredFileDialog(QFileDialog):
    """中央配置ファイルダイアログ"""

    def __init__(self, parent=None, caption="", directory="", filter=""):
        super().__init__(parent, caption, directory, filter)
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self._filter_str = filter
        self._apply_style()
        # フィルター変更時にファイルリストにフォーカス
        self.filterSelected.connect(lambda _: QTimer.singleShot(50, self._focus_file_list))

    def _apply_extension_filter(self):
        """拡張子フィルタを適用（対象外ファイルを非表示）"""
        if not self._filter_str:
            return
        import re
        extensions = re.findall(r'\*\.\w+', self._filter_str)
        if extensions:
            from PySide6.QtWidgets import QFileSystemModel
            for model in self.findChildren(QFileSystemModel):
                model.setNameFilters(extensions)
                model.setNameFilterDisables(False)

    def _apply_style(self):
        """ダークテーマスタイルを適用"""
        self.setStyleSheet("""
            QFileDialog {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }
            QFileDialog QLabel {
                color: #e0e0e0;
            }
            QFileDialog QLineEdit {
                background-color: #3c3c3c;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px;
            }
            QFileDialog QPushButton {
                background-color: #404040;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px 15px;
                min-width: 80px;
            }
            QFileDialog QPushButton:hover {
                background-color: #4a4a4a;
            }
            QFileDialog QPushButton:pressed {
                background-color: #353535;
            }
            QFileDialog QTreeView, QFileDialog QListView {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #555;
                selection-background-color: #0078d4;
            }
            QFileDialog QTreeView::item:hover, QFileDialog QListView::item:hover {
                background-color: #3c3c3c;
            }
            QFileDialog QComboBox {
                background-color: #3c3c3c;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px;
            }
            QFileDialog QComboBox::drop-down {
                border: none;
            }
            QFileDialog QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                color: #e0e0e0;
                selection-background-color: #0078d4;
            }
            QFileDialog QHeaderView::section {
                background-color: #353535;
                color: #e0e0e0;
                border: 1px solid #555;
                padding: 4px;
            }
            QFileDialog QToolButton {
                background-color: #404040;
                border: 1px solid #555;
                border-radius: 3px;
            }
            QFileDialog QToolButton:hover {
                background-color: #4a4a4a;
            }
            QFileDialog QScrollBar:vertical {
                background-color: #2b2b2b;
                width: 12px;
            }
            QFileDialog QScrollBar::handle:vertical {
                background-color: #555;
                border-radius: 4px;
                min-height: 20px;
            }
            QFileDialog QScrollBar::add-line:vertical, QFileDialog QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    def showEvent(self, event):
        """表示時に親ウィンドウの中央に配置 + 拡張子フィルタ適用"""
        super().showEvent(event)
        self._apply_extension_filter()
        self._center_on_parent()
        # ファイルリストにフォーカスを設定（初期化完了後に遅延実行）
        QTimer.singleShot(50, self._focus_file_list)

    def _focus_file_list(self):
        """ファイルリスト（QListView）にフォーカスを設定"""
        # QFileDialogの内部ビューを探す
        # 1. QListView（アイコン表示モード）
        # 2. QTreeView（詳細表示モード）
        from PySide6.QtWidgets import QAbstractItemView

        # サイズが最も大きい可視のQAbstractItemViewを探す（メインのファイルリスト）
        best_view = None
        best_size = 0

        for view in self.findChildren(QAbstractItemView):
            if view.isVisible() and view.width() > 100:  # 小さすぎるものは除外
                size = view.width() * view.height()
                if size > best_size:
                    best_size = size
                    best_view = view

        if best_view:
            best_view.setFocus()

    def _center_on_parent(self):
        """親ウィンドウの中央に配置"""
        parent = self.parent()
        if parent:
            window = parent.window() if hasattr(parent, 'window') else parent
            window_geo = window.frameGeometry()
            self_geo = self.geometry()
            x = window_geo.x() + (window_geo.width() - self_geo.width()) // 2
            y = window_geo.y() + (window_geo.height() - self_geo.height()) // 2
            self.move(x, y)

    @staticmethod
    def getOpenFileName(parent=None, caption="", directory="", filter="", **kwargs):
        """ファイルを開くダイアログ（中央配置版）"""
        dialog = CenteredFileDialog(parent, caption, directory, filter)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            files = dialog.selectedFiles()
            return (files[0] if files else "", dialog.selectedNameFilter())
        return ("", "")

    @staticmethod
    def getOpenFileNames(parent=None, caption="", directory="", filter="", **kwargs):
        """複数ファイルを開くダイアログ（中央配置版）"""
        dialog = CenteredFileDialog(parent, caption, directory, filter)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return (dialog.selectedFiles(), dialog.selectedNameFilter())
        return ([], "")

    @staticmethod
    def getSaveFileName(parent=None, caption="", directory="", filter="", **kwargs):
        """保存ダイアログ（中央配置版）"""
        dialog = CenteredFileDialog(parent, caption, directory, filter)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            files = dialog.selectedFiles()
            return (files[0] if files else "", dialog.selectedNameFilter())
        return ("", "")

    @staticmethod
    def getExistingDirectory(parent=None, caption="", directory="", **kwargs):
        """ディレクトリ選択ダイアログ（中央配置版）"""
        dialog = CenteredFileDialog(parent, caption, directory, "")
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            files = dialog.selectedFiles()
            return files[0] if files else ""
        return ""
