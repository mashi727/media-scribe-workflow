"""
dialogs.py - モーダルダイアログ群

ソース選択・カバー画像設定用のダイアログ。
閉じると自動的にメインワークスペースに反映される。
"""

from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QFrame,
    QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage


@dataclass
class SourceFile:
    """ソースファイル情報"""
    path: Path
    duration_ms: int = 0  # ミリ秒
    file_type: str = ""   # "mp3", "mp4", etc.

    @property
    def duration_str(self) -> str:
        """HH:MM:SS形式"""
        total_sec = self.duration_ms // 1000
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


class SourceSelectionDialog(QDialog):
    """
    ソース選択ダイアログ

    機能:
    - MP3/MP4ファイルの選択（複数可）
    - ドラッグ&ドロップで並び替え
    - 複数MP3選択時は自動結合
    - 閉じると選択内容を返却

    使用例:
        dialog = SourceSelectionDialog(parent)
        if dialog.exec() == QDialog.Accepted:
            sources = dialog.get_sources()
            # sources: List[SourceFile]
    """

    # シグナル
    sources_changed = Signal(list)  # List[SourceFile]

    def __init__(self, parent=None, initial_sources: Optional[List[SourceFile]] = None):
        super().__init__(parent)
        self._sources: List[SourceFile] = initial_sources or []
        self._setup_ui()
        self._load_sources()

    def _setup_ui(self):
        """UI構築"""
        self.setWindowTitle("Select Source Files")
        self.setMinimumSize(500, 400)
        self.setStyleSheet("""
            QDialog {
                background: #1a1a1a;
            }
            QLabel {
                color: #f0f0f0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ヘッダー
        header = QLabel("Select audio/video files to edit")
        header.setStyleSheet("font-size: 14px; color: #a0a0a0;")
        layout.addWidget(header)

        # ファイルリスト
        self._file_list = QListWidget()
        self._file_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._file_list.setStyleSheet("""
            QListWidget {
                background: #0f0f0f;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 8px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background: #3b82f6;
            }
            QListWidget::item:hover {
                background: #2d2d2d;
            }
        """)
        layout.addWidget(self._file_list)

        # ファイル操作ボタン
        file_buttons = QHBoxLayout()

        add_btn = QPushButton("Add Files...")
        add_btn.setStyleSheet(self._button_style())
        add_btn.clicked.connect(self._add_files)
        file_buttons.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setStyleSheet(self._button_style())
        remove_btn.clicked.connect(self._remove_selected)
        file_buttons.addWidget(remove_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.setStyleSheet(self._button_style())
        clear_btn.clicked.connect(self._clear_all)
        file_buttons.addWidget(clear_btn)

        file_buttons.addStretch()
        layout.addLayout(file_buttons)

        # 情報表示
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #666666;")
        layout.addWidget(self._info_label)

        # ダイアログボタン
        dialog_buttons = QHBoxLayout()
        dialog_buttons.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(self._button_style())
        cancel_btn.clicked.connect(self.reject)
        dialog_buttons.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(self._button_style(primary=True))
        ok_btn.clicked.connect(self.accept)
        dialog_buttons.addWidget(ok_btn)

        layout.addLayout(dialog_buttons)

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

    def _load_sources(self):
        """ソースをリストに読み込み"""
        self._file_list.clear()
        for src in self._sources:
            item = QListWidgetItem(f"{src.path.name} ({src.duration_str})")
            item.setData(Qt.ItemDataRole.UserRole, src)
            self._file_list.addItem(item)
        self._update_info()

    def _add_files(self):
        """ファイル追加"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files",
            "",
            "Audio/Video Files (*.mp3 *.mp4 *.m4a *.wav);;All Files (*)"
        )
        for f in files:
            path = Path(f)
            # TODO: ffprobeでduration取得
            src = SourceFile(path=path, file_type=path.suffix[1:])
            self._sources.append(src)

        self._load_sources()

    def _remove_selected(self):
        """選択項目を削除"""
        for item in self._file_list.selectedItems():
            src = item.data(Qt.ItemDataRole.UserRole)
            if src in self._sources:
                self._sources.remove(src)
        self._load_sources()

    def _clear_all(self):
        """全削除"""
        self._sources.clear()
        self._load_sources()

    def _update_info(self):
        """情報表示更新"""
        count = len(self._sources)
        if count == 0:
            self._info_label.setText("No files selected")
        elif count == 1:
            self._info_label.setText("1 file selected")
        else:
            types = set(s.file_type for s in self._sources)
            if types == {"mp3"}:
                self._info_label.setText(f"{count} MP3 files (will be merged)")
            else:
                self._info_label.setText(f"{count} files selected")

    def get_sources(self) -> List[SourceFile]:
        """選択されたソースを取得"""
        # リストの順序を反映
        sources = []
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            src = item.data(Qt.ItemDataRole.UserRole)
            if src:
                sources.append(src)
        return sources


class CoverImageDialog(QDialog):
    """
    カバー画像選択ダイアログ

    機能:
    - 画像ファイル選択
    - クロップ（16:9固定）
    - プレビュー表示
    - 閉じると選択内容を返却

    使用例:
        dialog = CoverImageDialog(parent)
        if dialog.exec() == QDialog.Accepted:
            image = dialog.get_image()
            # image: QImage (1920x1080)
    """

    # シグナル
    image_changed = Signal(object)  # QImage

    def __init__(self, parent=None, initial_image: Optional[QImage] = None):
        super().__init__(parent)
        self._image: Optional[QImage] = initial_image
        self._cropped_image: Optional[QImage] = None
        self._setup_ui()
        if initial_image:
            self._update_preview()

    def _setup_ui(self):
        """UI構築"""
        self.setWindowTitle("Select Cover Image")
        self.setMinimumSize(600, 500)
        self.setStyleSheet("""
            QDialog {
                background: #1a1a1a;
            }
            QLabel {
                color: #f0f0f0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ヘッダー
        header = QLabel("Select and crop cover image (16:9)")
        header.setStyleSheet("font-size: 14px; color: #a0a0a0;")
        layout.addWidget(header)

        # プレビューエリア
        self._preview_frame = QFrame()
        self._preview_frame.setStyleSheet("""
            QFrame {
                background: #0f0f0f;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
            }
        """)
        self._preview_frame.setMinimumHeight(300)

        preview_layout = QVBoxLayout(self._preview_frame)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._preview_label = QLabel("No image selected")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("color: #666666;")
        preview_layout.addWidget(self._preview_label)

        layout.addWidget(self._preview_frame)

        # 画像操作ボタン
        image_buttons = QHBoxLayout()

        select_btn = QPushButton("Select Image...")
        select_btn.setStyleSheet(self._button_style())
        select_btn.clicked.connect(self._select_image)
        image_buttons.addWidget(select_btn)

        # TODO: クロップUIボタン
        # crop_btn = QPushButton("Adjust Crop...")
        # crop_btn.setStyleSheet(self._button_style())
        # image_buttons.addWidget(crop_btn)

        image_buttons.addStretch()
        layout.addLayout(image_buttons)

        # 情報表示
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #666666;")
        layout.addWidget(self._info_label)

        # ダイアログボタン
        dialog_buttons = QHBoxLayout()
        dialog_buttons.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(self._button_style())
        cancel_btn.clicked.connect(self.reject)
        dialog_buttons.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(self._button_style(primary=True))
        ok_btn.clicked.connect(self.accept)
        dialog_buttons.addWidget(ok_btn)

        layout.addLayout(dialog_buttons)

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

    def _select_image(self):
        """画像選択"""
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Image Files (*.jpg *.jpeg *.png *.bmp);;All Files (*)"
        )
        if file:
            self._image = QImage(file)
            self._crop_to_16_9()
            self._update_preview()

    def _crop_to_16_9(self):
        """16:9にクロップ（中央基準）"""
        if not self._image:
            return

        w, h = self._image.width(), self._image.height()
        target_ratio = 16 / 9

        current_ratio = w / h
        if current_ratio > target_ratio:
            # 横長すぎる → 左右をクロップ
            new_w = int(h * target_ratio)
            x = (w - new_w) // 2
            self._cropped_image = self._image.copy(x, 0, new_w, h)
        else:
            # 縦長すぎる → 上下をクロップ
            new_h = int(w / target_ratio)
            y = (h - new_h) // 2
            self._cropped_image = self._image.copy(0, y, w, new_h)

        # 1920x1080にリサイズ
        self._cropped_image = self._cropped_image.scaled(
            1920, 1080,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

    def _update_preview(self):
        """プレビュー更新"""
        if self._cropped_image:
            # プレビューサイズにスケール
            preview = self._cropped_image.scaled(
                480, 270,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._preview_label.setPixmap(QPixmap.fromImage(preview))
            self._info_label.setText(f"Output: 1920x1080 (16:9)")
        else:
            self._preview_label.setText("No image selected")
            self._info_label.setText("")

    def get_image(self) -> Optional[QImage]:
        """クロップ済み画像を取得"""
        return self._cropped_image
