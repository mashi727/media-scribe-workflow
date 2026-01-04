"""
dialogs.py - モーダルダイアログ群

ソース選択・カバー画像設定用のダイアログ。
閉じると自動的にメインワークスペースに反映される。
"""

from pathlib import Path
from typing import Optional, List, Tuple

from .models import detect_video_duration, SourceFile

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QFrame,
    QAbstractItemView, QSizePolicy, QApplication, QWidget,
    QSlider, QSpinBox, QCheckBox, QLineEdit, QRadioButton,
    QStackedWidget, QButtonGroup, QGroupBox
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QBuffer, QIODevice
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QBrush, QColor, QTransform


class ImageCropWidget(QWidget):
    """16:9アスペクト比でクロップするウィジェット"""

    cropChanged = Signal()
    compressionChanged = Signal(int)  # ファイルサイズ（バイト）

    ASPECT_RATIO = 16 / 9
    OUTPUT_WIDTH = 1280
    OUTPUT_HEIGHT = 720

    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_image: Optional[QImage] = None
        self.rotated_image: Optional[QImage] = None
        self.rotation_angle = 0

        # クロップ矩形（画像座標系）
        self.crop_rect: Optional[QRectF] = None

        # 圧縮設定
        self.compression_quality = 85
        self.compressed_size = 0
        self.show_compression_preview = False
        self.compressed_image: Optional[QImage] = None
        self.original_preview_image: Optional[QImage] = None

        # インタラクション状態
        self.dragging = False
        self.resizing = False
        self.resize_corner = None
        self.drag_start = QPointF()
        self.crop_start = QRectF()

        # 表示変換キャッシュ
        self.display_rect = QRectF()
        self.scale_factor = 1.0

        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def load_image(self, path: str) -> bool:
        """画像ファイルを読み込み"""
        image = QImage(path)
        if image.isNull():
            return False
        return self.load_image_from_qimage(image)

    def load_image_from_qimage(self, image: QImage) -> bool:
        """QImageから画像を読み込み"""
        if image.isNull():
            return False
        self.original_image = image
        self.rotation_angle = 0
        self._apply_rotation()
        self._init_crop_rect()
        self._update_compressed_preview()
        self.update()
        return True

    def set_rotation(self, angle: int):
        """回転角度を設定"""
        self.rotation_angle = angle % 360
        self._apply_rotation()
        self._init_crop_rect()
        self._update_compressed_preview()
        self.update()

    def set_compression_quality(self, quality: int):
        """JPEG圧縮品質を設定（1-100）"""
        self.compression_quality = max(1, min(100, quality))
        if self.rotated_image is not None:
            self._update_compressed_preview()
            self.update()

    def set_compression_preview(self, enabled: bool):
        """圧縮プレビュー（スプリットビュー）の表示切替"""
        self.show_compression_preview = enabled
        self._update_compressed_preview()
        self.update()

    def _apply_rotation(self):
        """回転を適用"""
        if self.original_image is None:
            self.rotated_image = None
            return

        if self.rotation_angle == 0:
            self.rotated_image = self.original_image.copy()
        else:
            transform = QTransform()
            transform.rotate(self.rotation_angle)
            self.rotated_image = self.original_image.transformed(
                transform, Qt.TransformationMode.SmoothTransformation
            )

    def _init_crop_rect(self):
        """クロップ矩形を初期化（16:9で最大サイズ）"""
        if self.rotated_image is None:
            self.crop_rect = None
            return

        img_w = self.rotated_image.width()
        img_h = self.rotated_image.height()

        # 16:9に収まる最大矩形を計算
        if img_w / img_h > self.ASPECT_RATIO:
            crop_h = img_h
            crop_w = crop_h * self.ASPECT_RATIO
        else:
            crop_w = img_w
            crop_h = crop_w / self.ASPECT_RATIO

        # 中央に配置
        x = (img_w - crop_w) / 2
        y = (img_h - crop_h) / 2

        self.crop_rect = QRectF(x, y, crop_w, crop_h)
        self.cropChanged.emit()

    def _update_compressed_preview(self):
        """圧縮プレビューを更新"""
        if self.rotated_image is None or self.crop_rect is None:
            self.compressed_size = 0
            self.compressed_image = None
            self.original_preview_image = None
            return

        # クロップしてスケーリング
        cropped = self.rotated_image.copy(self.crop_rect.toRect())
        scaled = cropped.scaled(
            self.OUTPUT_WIDTH, self.OUTPUT_HEIGHT,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        # オリジナルプレビュー（PNG/ロスレス）
        orig_buffer = QBuffer()
        orig_buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(orig_buffer, "PNG")
        orig_buffer.close()
        orig_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.original_preview_image = QImage()
        self.original_preview_image.loadFromData(orig_buffer.data())
        orig_buffer.close()

        # JPEG圧縮してサイズとプレビュー画像を取得
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buffer, "JPEG", self.compression_quality)
        self.compressed_size = buffer.size()
        buffer.close()

        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.compressed_image = QImage()
        self.compressed_image.loadFromData(buffer.data())
        buffer.close()

        self.compressionChanged.emit(self.compressed_size)

    def _calculate_display_transform(self):
        """表示変換を計算"""
        if self.rotated_image is None:
            return

        img_w = self.rotated_image.width()
        img_h = self.rotated_image.height()

        widget_w = self.width() - 20
        widget_h = self.height() - 20

        scale_x = widget_w / img_w
        scale_y = widget_h / img_h
        self.scale_factor = min(scale_x, scale_y)

        disp_w = img_w * self.scale_factor
        disp_h = img_h * self.scale_factor
        disp_x = (self.width() - disp_w) / 2
        disp_y = (self.height() - disp_h) / 2

        self.display_rect = QRectF(disp_x, disp_y, disp_w, disp_h)

    def _image_to_widget(self, point: QPointF) -> QPointF:
        """画像座標→ウィジェット座標"""
        return QPointF(
            self.display_rect.x() + point.x() * self.scale_factor,
            self.display_rect.y() + point.y() * self.scale_factor
        )

    def _widget_to_image(self, point: QPointF) -> QPointF:
        """ウィジェット座標→画像座標"""
        return QPointF(
            (point.x() - self.display_rect.x()) / self.scale_factor,
            (point.y() - self.display_rect.y()) / self.scale_factor
        )

    def _get_crop_widget_rect(self) -> QRectF:
        """ウィジェット座標系でのクロップ矩形"""
        if self.crop_rect is None:
            return QRectF()
        tl = self._image_to_widget(self.crop_rect.topLeft())
        br = self._image_to_widget(self.crop_rect.bottomRight())
        return QRectF(tl, br)

    def _get_resize_handle(self, pos: QPointF) -> Optional[str]:
        """リサイズハンドルを判定"""
        if self.crop_rect is None:
            return None

        crop_widget = self._get_crop_widget_rect()
        handle_size = 12

        corners = {
            'tl': crop_widget.topLeft(),
            'tr': crop_widget.topRight(),
            'bl': crop_widget.bottomLeft(),
            'br': crop_widget.bottomRight(),
        }

        for name, corner in corners.items():
            rect = QRectF(
                corner.x() - handle_size / 2,
                corner.y() - handle_size / 2,
                handle_size, handle_size
            )
            if rect.contains(pos):
                return name
        return None

    def paintEvent(self, event):
        """描画"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景
        painter.fillRect(self.rect(), QColor(40, 40, 40))

        if self.rotated_image is None:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "画像を選択してください")
            return

        # プレビューモード: スプリットビューで表示
        if self.show_compression_preview and self.original_preview_image is not None and self.compressed_image is not None:
            self._draw_split_preview(painter)
            return

        self._calculate_display_transform()

        # 画像描画
        pixmap = QPixmap.fromImage(self.rotated_image)
        painter.drawPixmap(self.display_rect.toRect(), pixmap)

        # クロップオーバーレイ
        if self.crop_rect is not None:
            crop_widget = self._get_crop_widget_rect()

            # 外側を暗く
            overlay = QColor(0, 0, 0, 150)
            painter.fillRect(QRectF(
                self.display_rect.left(), self.display_rect.top(),
                self.display_rect.width(), crop_widget.top() - self.display_rect.top()
            ), overlay)
            painter.fillRect(QRectF(
                self.display_rect.left(), crop_widget.bottom(),
                self.display_rect.width(), self.display_rect.bottom() - crop_widget.bottom()
            ), overlay)
            painter.fillRect(QRectF(
                self.display_rect.left(), crop_widget.top(),
                crop_widget.left() - self.display_rect.left(), crop_widget.height()
            ), overlay)
            painter.fillRect(QRectF(
                crop_widget.right(), crop_widget.top(),
                self.display_rect.right() - crop_widget.right(), crop_widget.height()
            ), overlay)

            # クロップ枠
            painter.setPen(QPen(QColor(255, 200, 0), 2))
            painter.drawRect(crop_widget)

            # コーナーハンドル
            handle_size = 10
            painter.setBrush(QBrush(QColor(255, 200, 0)))
            for corner in [crop_widget.topLeft(), crop_widget.topRight(),
                          crop_widget.bottomLeft(), crop_widget.bottomRight()]:
                painter.drawRect(QRectF(
                    corner.x() - handle_size / 2,
                    corner.y() - handle_size / 2,
                    handle_size, handle_size
                ))

            # 3分割グリッド
            painter.setPen(QPen(QColor(255, 255, 255, 100), 1))
            third_w = crop_widget.width() / 3
            third_h = crop_widget.height() / 3
            for i in range(1, 3):
                painter.drawLine(
                    QPointF(crop_widget.left() + third_w * i, crop_widget.top()),
                    QPointF(crop_widget.left() + third_w * i, crop_widget.bottom())
                )
                painter.drawLine(
                    QPointF(crop_widget.left(), crop_widget.top() + third_h * i),
                    QPointF(crop_widget.right(), crop_widget.top() + third_h * i)
                )

    def mousePressEvent(self, event):
        """マウスプレス"""
        if event.button() != Qt.MouseButton.LeftButton or self.crop_rect is None:
            return

        pos = QPointF(event.position())
        handle = self._get_resize_handle(pos)
        crop_widget = self._get_crop_widget_rect()

        if handle:
            self.resizing = True
            self.resize_corner = handle
            self.drag_start = pos
            self.crop_start = QRectF(self.crop_rect)
        elif crop_widget.contains(pos):
            self.dragging = True
            self.drag_start = pos
            self.crop_start = QRectF(self.crop_rect)

    def mouseMoveEvent(self, event):
        """マウス移動"""
        pos = QPointF(event.position())

        # カーソル更新
        if self.crop_rect is not None:
            handle = self._get_resize_handle(pos)
            crop_widget = self._get_crop_widget_rect()

            if handle in ('tl', 'br'):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif handle in ('tr', 'bl'):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif crop_widget.contains(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

        if self.rotated_image is None or self.crop_rect is None:
            return

        img_w = self.rotated_image.width()
        img_h = self.rotated_image.height()

        if self.dragging:
            # クロップ矩形を移動
            delta = self._widget_to_image(pos) - self._widget_to_image(self.drag_start)
            new_rect = self.crop_start.translated(delta)

            # 境界制限
            if new_rect.left() < 0:
                new_rect.moveLeft(0)
            if new_rect.top() < 0:
                new_rect.moveTop(0)
            if new_rect.right() > img_w:
                new_rect.moveRight(img_w)
            if new_rect.bottom() > img_h:
                new_rect.moveBottom(img_h)

            self.crop_rect = new_rect
            self.cropChanged.emit()
            self.update()

        elif self.resizing:
            # リサイズ（アスペクト比維持）
            img_pos = self._widget_to_image(pos)

            if self.resize_corner == 'br':
                new_w = max(100, img_pos.x() - self.crop_rect.left())
                new_h = new_w / self.ASPECT_RATIO
                self.crop_rect.setWidth(new_w)
                self.crop_rect.setHeight(new_h)
            elif self.resize_corner == 'tl':
                anchor = self.crop_rect.bottomRight()
                new_w = max(100, anchor.x() - img_pos.x())
                new_h = new_w / self.ASPECT_RATIO
                self.crop_rect = QRectF(anchor.x() - new_w, anchor.y() - new_h, new_w, new_h)
            elif self.resize_corner == 'tr':
                anchor_x = self.crop_rect.left()
                anchor_y = self.crop_rect.bottom()
                new_w = max(100, img_pos.x() - anchor_x)
                new_h = new_w / self.ASPECT_RATIO
                self.crop_rect = QRectF(anchor_x, anchor_y - new_h, new_w, new_h)
            elif self.resize_corner == 'bl':
                anchor_x = self.crop_rect.right()
                anchor_y = self.crop_rect.top()
                new_w = max(100, anchor_x - img_pos.x())
                new_h = new_w / self.ASPECT_RATIO
                self.crop_rect = QRectF(anchor_x - new_w, anchor_y, new_w, new_h)

            # 境界制限
            if self.crop_rect.left() < 0:
                self.crop_rect.moveLeft(0)
            if self.crop_rect.top() < 0:
                self.crop_rect.moveTop(0)
            if self.crop_rect.right() > img_w:
                scale = (img_w - self.crop_rect.left()) / self.crop_rect.width()
                self.crop_rect.setWidth(self.crop_rect.width() * scale)
                self.crop_rect.setHeight(self.crop_rect.height() * scale)
            if self.crop_rect.bottom() > img_h:
                scale = (img_h - self.crop_rect.top()) / self.crop_rect.height()
                self.crop_rect.setWidth(self.crop_rect.width() * scale)
                self.crop_rect.setHeight(self.crop_rect.height() * scale)

            self.cropChanged.emit()
            self.update()

    def mouseReleaseEvent(self, event):
        """マウスリリース"""
        if self.dragging or self.resizing:
            self._update_compressed_preview()
        self.dragging = False
        self.resizing = False
        self.resize_corner = None

    def _draw_split_preview(self, painter: QPainter):
        """スプリットビュープレビューを描画（左: オリジナル、右: JPEG圧縮後）画面にフィット"""
        # ウィジェットサイズに合わせてスケーリング
        margin = 40
        available_w = self.width() - margin * 2
        available_h = self.height() - margin * 2

        # アスペクト比を保持してフィット
        scale = min(available_w / self.OUTPUT_WIDTH, available_h / self.OUTPUT_HEIGHT)
        display_w = self.OUTPUT_WIDTH * scale
        display_h = self.OUTPUT_HEIGHT * scale

        preview_x = (self.width() - display_w) / 2
        preview_y = (self.height() - display_h) / 2

        half_width = display_w / 2

        # 左半分: オリジナル（PNG）
        left_dest = QRectF(preview_x, preview_y, half_width, display_h)
        left_src = QRectF(0, 0, self.OUTPUT_WIDTH / 2, self.OUTPUT_HEIGHT)
        original_pixmap = QPixmap.fromImage(self.original_preview_image)
        painter.drawPixmap(left_dest.toRect(), original_pixmap, left_src.toRect())

        # 右半分: 圧縮後（JPEG）
        right_dest = QRectF(preview_x + half_width, preview_y, half_width, display_h)
        right_src = QRectF(self.OUTPUT_WIDTH / 2, 0, self.OUTPUT_WIDTH / 2, self.OUTPUT_HEIGHT)
        compressed_pixmap = QPixmap.fromImage(self.compressed_image)
        painter.drawPixmap(right_dest.toRect(), compressed_pixmap, right_src.toRect())

        # 枠線
        painter.setPen(QPen(QColor(255, 200, 0), 2))
        painter.drawRect(QRectF(preview_x, preview_y, display_w, display_h))

        # 中央の分割線
        mid_x = preview_x + half_width
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(QPointF(mid_x, preview_y), QPointF(mid_x, preview_y + display_h))

        # ラベル
        font = painter.font()
        font.setBold(True)
        font.setPointSize(11)
        painter.setFont(font)

        label_bg = QColor(0, 0, 0, 180)
        label_height = 24
        label_margin = 6

        # 左ラベル
        left_label_rect = QRectF(preview_x + label_margin, preview_y + label_margin,
                                  half_width - label_margin * 2, label_height)
        painter.fillRect(left_label_rect, label_bg)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(left_label_rect, Qt.AlignmentFlag.AlignCenter, "Original (PNG)")

        # 右ラベル（ファイルサイズ付き）
        if self.compressed_size < 1024:
            size_str = f"{self.compressed_size} B"
        elif self.compressed_size < 1024 * 1024:
            size_str = f"{self.compressed_size / 1024:.1f} KB"
        else:
            size_str = f"{self.compressed_size / (1024 * 1024):.2f} MB"

        right_label_rect = QRectF(mid_x + label_margin, preview_y + label_margin,
                                   half_width - label_margin * 2, label_height)
        painter.fillRect(right_label_rect, label_bg)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(right_label_rect, Qt.AlignmentFlag.AlignCenter,
                        f"JPEG Q{self.compression_quality} ({size_str})")

        # 解像度情報（スケール表示）
        scale_percent = int(scale * 100)
        info_rect = QRectF(preview_x, preview_y + display_h + 5, display_w, 20)
        painter.setPen(QColor(180, 180, 180))
        painter.drawText(info_rect, Qt.AlignmentFlag.AlignCenter, f"1280x720 ({scale_percent}%)")

    def get_cropped_image(self) -> Optional[QImage]:
        """クロップ済み画像を取得（1280x720）"""
        if self.rotated_image is None or self.crop_rect is None:
            return None

        cropped = self.rotated_image.copy(self.crop_rect.toRect())
        scaled = cropped.scaled(
            self.OUTPUT_WIDTH, self.OUTPUT_HEIGHT,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        return scaled

    def export_cropped_image(self, output_path: str) -> Tuple[bool, int]:
        """クロップした画像をJPEGとしてエクスポート"""
        if self.rotated_image is None or self.crop_rect is None:
            return False, 0

        cropped = self.rotated_image.copy(self.crop_rect.toRect())
        scaled = cropped.scaled(
            self.OUTPUT_WIDTH, self.OUTPUT_HEIGHT,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        success = scaled.save(output_path, "JPEG", self.compression_quality)
        if success:
            file_size = Path(output_path).stat().st_size
            return True, file_size
        return False, 0


class SourceSelectionDialog(QDialog):
    """
    ソース選択ダイアログ

    機能:
    - ローカルファイル選択（ワーキングディレクトリのファイルを表示）
    - YouTube URL入力（yt-dlpでダウンロード）
    - MP3/MP4トグルでフィルタリング
    - チェックボックスで複数選択
    - 複数MP3選択時は自動結合＆チャプター生成
    - カバー画像選択（音声ファイル用）

    使用例:
        dialog = SourceSelectionDialog(parent)
        if dialog.exec() == QDialog.Accepted:
            sources = dialog.get_sources()
            youtube_url = dialog.get_youtube_url()
            cover_image = dialog.get_cover_image()
    """

    # シグナル
    sources_changed = Signal(list)  # List[SourceFile]

    # ファイル拡張子
    AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.wav', '.aac', '.flac'}
    VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}

    # ダイアログサイズ
    DEFAULT_WIDTH = 800
    DEFAULT_HEIGHT = 700
    MIN_WIDTH = 600
    MIN_HEIGHT = 550
    ASPECT_RATIO = DEFAULT_WIDTH / DEFAULT_HEIGHT

    def __init__(self, parent=None, initial_sources: Optional[List[SourceFile]] = None,
                 work_dir: Optional[Path] = None, initial_cover_image: Optional[QImage] = None):
        super().__init__(parent)
        self._sources: List[SourceFile] = initial_sources or []
        self._work_dir = work_dir or Path.cwd()
        self._filter_mode = "mp3"  # "mp3" or "mp4"
        self._source_type = "local"  # "local" or "youtube"
        self._resizing = False  # リサイズ中フラグ
        self._cover_image: Optional[QImage] = initial_cover_image
        self._youtube_url: str = ""
        self._setup_ui()
        self._refresh_file_list()
        # カバー画像が既に設定されている場合は表示
        if initial_cover_image:
            self._cover_status.setText("Set")
            self._cover_status.setStyleSheet("color: #22c55e;")

    def _setup_ui(self):
        """UI構築"""
        self.setWindowTitle("Select Source")
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.setStyleSheet("""
            QDialog {
                background: #1a1a1a;
            }
            QLabel {
                color: #f0f0f0;
            }
            QRadioButton {
                color: #f0f0f0;
                font-size: 14px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
            QRadioButton::indicator:unchecked {
                border: 2px solid #666666;
                border-radius: 9px;
                background: transparent;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #3b82f6;
                border-radius: 9px;
                background: #3b82f6;
            }
            QGroupBox {
                color: #a0a0a0;
                font-size: 13px;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # === ソースタイプ選択 ===
        source_type_layout = QHBoxLayout()

        self._local_radio = QRadioButton("Local Files")
        self._local_radio.setChecked(True)
        self._local_radio.clicked.connect(lambda: self._set_source_type("local"))
        source_type_layout.addWidget(self._local_radio)

        self._youtube_radio = QRadioButton("YouTube URL")
        self._youtube_radio.clicked.connect(lambda: self._set_source_type("youtube"))
        source_type_layout.addWidget(self._youtube_radio)

        source_type_layout.addStretch()
        layout.addLayout(source_type_layout)

        # === スタックウィジェット（ローカルファイル / YouTube） ===
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        # --- ローカルファイルページ ---
        local_page = QWidget()
        local_layout = QVBoxLayout(local_page)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.setSpacing(8)

        # トグルボタン + ディレクトリ
        header_layout = QHBoxLayout()

        self._mp3_btn = QPushButton("MP3")
        self._mp3_btn.setCheckable(True)
        self._mp3_btn.setChecked(True)
        self._mp3_btn.setStyleSheet(self._toggle_button_style())
        self._mp3_btn.clicked.connect(lambda: self._set_filter_mode("mp3"))
        header_layout.addWidget(self._mp3_btn)

        self._mp4_btn = QPushButton("MP4")
        self._mp4_btn.setCheckable(True)
        self._mp4_btn.setChecked(False)
        self._mp4_btn.setStyleSheet(self._toggle_button_style())
        self._mp4_btn.clicked.connect(lambda: self._set_filter_mode("mp4"))
        header_layout.addWidget(self._mp4_btn)

        header_layout.addStretch()

        self._dir_label = QLabel(f"{self._work_dir}")
        self._dir_label.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        header_layout.addWidget(self._dir_label)

        browse_btn = QPushButton("Browse")
        browse_btn.setStyleSheet(self._button_style())
        browse_btn.setToolTip("ディレクトリを変更")
        browse_btn.clicked.connect(self._browse_directory)
        header_layout.addWidget(browse_btn)

        local_layout.addLayout(header_layout)

        # ファイルリスト
        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._file_list.setStyleSheet(self._list_style())
        self._file_list.itemSelectionChanged.connect(self._update_info)
        self._file_list.itemDoubleClicked.connect(self._on_double_click)
        local_layout.addWidget(self._file_list, 1)

        self._stack.addWidget(local_page)

        # --- YouTubeページ ---
        youtube_page = QWidget()
        youtube_layout = QVBoxLayout(youtube_page)
        youtube_layout.setContentsMargins(0, 0, 0, 0)
        youtube_layout.setSpacing(12)

        url_label = QLabel("YouTube URL:")
        url_label.setStyleSheet("color: #a0a0a0; font-size: 14px;")
        youtube_layout.addWidget(url_label)

        self._youtube_url_edit = QLineEdit()
        self._youtube_url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self._youtube_url_edit.setStyleSheet("""
            QLineEdit {
                background: #0f0f0f;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 12px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
            }
        """)
        self._youtube_url_edit.textChanged.connect(self._on_youtube_url_changed)
        youtube_layout.addWidget(self._youtube_url_edit)

        # YouTube情報表示エリア
        self._youtube_info = QLabel("Enter a YouTube URL to download")
        self._youtube_info.setStyleSheet("color: #666666; font-size: 13px;")
        youtube_layout.addWidget(self._youtube_info)

        youtube_layout.addStretch()

        self._stack.addWidget(youtube_page)

        # === カバー画像セクション（音声ファイル用） ===
        self._cover_group = QGroupBox("Cover Image (for audio files)")
        cover_layout = QHBoxLayout(self._cover_group)

        self._cover_btn = QPushButton("Select Image")
        self._cover_btn.setStyleSheet(self._button_style())
        self._cover_btn.clicked.connect(self._open_cover_dialog)
        cover_layout.addWidget(self._cover_btn)

        self._cover_status = QLabel("Not Set")
        self._cover_status.setStyleSheet("color: #ef4444;")
        cover_layout.addWidget(self._cover_status)

        cover_layout.addStretch()

        self._cover_clear_btn = QPushButton("Clear")
        self._cover_clear_btn.setStyleSheet(self._button_style())
        self._cover_clear_btn.clicked.connect(self._clear_cover_image)
        cover_layout.addWidget(self._cover_clear_btn)

        layout.addWidget(self._cover_group)

        # === 下部: 情報 + ボタン ===
        bottom_layout = QHBoxLayout()

        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #666666;")
        bottom_layout.addWidget(self._info_label)

        bottom_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(self._button_style())
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(self._button_style(primary=True))
        ok_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(ok_btn)

        layout.addLayout(bottom_layout)

        # 初期状態でカバー画像セクションを表示（MP3モード）
        self._update_cover_visibility()

    def _toggle_button_style(self) -> str:
        """トグルボタンスタイル"""
        return """
            QPushButton {
                background: #2d2d2d;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 10px 24px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #363636;
            }
            QPushButton:checked {
                background: #3b82f6;
                color: white;
                border: none;
            }
            QPushButton:checked:hover {
                background: #2563eb;
            }
        """

    def _list_style(self) -> str:
        """リストスタイル"""
        return """
            QListWidget {
                background: #0f0f0f;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
                outline: none;
            }
            QListWidget::item {
                padding: 10px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background: #2d2d2d;
            }
            QListWidget::item:selected {
                background: #3b82f6;
                color: white;
            }
            QListWidget::item:selected:hover {
                background: #2563eb;
            }
        """

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

    def _browse_directory(self):
        """ディレクトリを選択"""
        dialog = QFileDialog(self, "Select Directory", str(self._work_dir))
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setStyleSheet(self._file_dialog_style())

        if dialog.exec() == QDialog.DialogCode.Accepted:
            dirs = dialog.selectedFiles()
            if dirs:
                self._work_dir = Path(dirs[0])
                self._dir_label.setText(str(self._work_dir))
                self._refresh_file_list()

    def _file_dialog_style(self) -> str:
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
        """

    def _set_source_type(self, source_type: str):
        """ソースタイプを設定（local / youtube）"""
        self._source_type = source_type
        self._local_radio.setChecked(source_type == "local")
        self._youtube_radio.setChecked(source_type == "youtube")

        # スタックウィジェットを切替
        self._stack.setCurrentIndex(0 if source_type == "local" else 1)

        # カバー可視性を更新
        self._update_cover_visibility()

        # 情報表示を更新
        self._update_info()

    def _set_filter_mode(self, mode: str):
        """フィルタモードを設定"""
        self._filter_mode = mode
        self._mp3_btn.setChecked(mode == "mp3")
        self._mp4_btn.setChecked(mode == "mp4")

        # MP4モードは単一選択、MP3モードは複数選択
        if mode == "mp4":
            self._file_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        else:
            self._file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        self._refresh_file_list()

        # カバー可視性を更新
        self._update_cover_visibility()

    def _refresh_file_list(self):
        """ファイル一覧を更新（ファイル → フォルダの順）"""
        self._file_list.clear()

        if not self._work_dir.exists():
            return

        # フィルタに応じた拡張子
        extensions = self.AUDIO_EXTENSIONS if self._filter_mode == "mp3" else self.VIDEO_EXTENSIONS

        # ファイルとフォルダを分けて取得
        files = []
        folders = []
        for f in self._work_dir.iterdir():
            if f.is_file() and f.suffix.lower() in extensions:
                files.append(f)
            elif f.is_dir() and not f.name.startswith('.'):
                folders.append(f)

        # それぞれソート
        files.sort(key=lambda x: x.name.lower())
        folders.sort(key=lambda x: x.name.lower())

        # ファイルを先に追加
        for f in files:
            item = QListWidgetItem(f.name)
            item.setData(Qt.ItemDataRole.UserRole, f)
            self._file_list.addItem(item)

        # フォルダを後に追加
        for d in folders:
            item = QListWidgetItem(f"[DIR] {d.name}")
            item.setData(Qt.ItemDataRole.UserRole, d)
            # フォルダは選択不可（ダブルクリックでナビゲート用）
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(QColor("#888888"))
            self._file_list.addItem(item)

        self._update_info()

    def _update_info(self):
        """情報表示更新"""
        if self._source_type == "youtube":
            if self._youtube_url and self._is_valid_youtube_url(self._youtube_url):
                self._info_label.setText("YouTube video ready to download")
            else:
                self._info_label.setText("Enter a valid YouTube URL")
            return

        count = len(self._file_list.selectedItems())

        if count == 0:
            self._info_label.setText("No files selected")
        elif count == 1:
            self._info_label.setText("1 file selected")
        else:
            if self._filter_mode == "mp3":
                self._info_label.setText(f"{count} MP3 files (will be merged)")
            else:
                self._info_label.setText(f"{count} files selected")

    def _on_double_click(self, item: QListWidgetItem):
        """ダブルクリックで選択してOK、またはフォルダへナビゲート"""
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and path.is_dir():
            # フォルダの場合はナビゲート
            self._work_dir = path
            self._dir_label.setText(str(self._work_dir))
            self._refresh_file_list()
        else:
            # ファイルの場合はOK
            self.accept()

    def _on_youtube_url_changed(self, text: str):
        """YouTube URL入力時の処理"""
        self._youtube_url = text.strip()
        if not self._youtube_url:
            self._youtube_info.setText("Enter a YouTube URL to download")
            self._youtube_info.setStyleSheet("color: #666666;")
        elif self._is_valid_youtube_url(self._youtube_url):
            self._youtube_info.setText("Valid YouTube URL")
            self._youtube_info.setStyleSheet("color: #22c55e;")
        else:
            self._youtube_info.setText("Invalid YouTube URL")
            self._youtube_info.setStyleSheet("color: #ef4444;")

    def _is_valid_youtube_url(self, url: str) -> bool:
        """YouTube URLの簡易バリデーション"""
        youtube_patterns = [
            "youtube.com/watch",
            "youtu.be/",
            "youtube.com/shorts/",
            "youtube.com/live/",
        ]
        return any(pattern in url for pattern in youtube_patterns)

    def _update_cover_visibility(self):
        """カバー画像セクションの表示/非表示を更新"""
        # YouTube選択時、またはMP4モード時はカバー画像を非表示
        show_cover = self._source_type == "local" and self._filter_mode == "mp3"
        self._cover_group.setVisible(show_cover)

    def _open_cover_dialog(self):
        """カバー画像ダイアログを開く"""
        dialog = CoverImageDialog(self, initial_image=self._cover_image, work_dir=self._work_dir)
        if dialog.exec():
            image = dialog.get_image()
            if image:
                self._cover_image = image
                self._cover_status.setText("Set")
                self._cover_status.setStyleSheet("color: #22c55e;")

    def _clear_cover_image(self):
        """カバー画像をクリア"""
        self._cover_image = None
        self._cover_status.setText("Not Set")
        self._cover_status.setStyleSheet("color: #ef4444;")

    def get_sources(self) -> List[SourceFile]:
        """選択されたソースを取得"""
        sources = []

        for item in self._file_list.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            duration_ms = detect_video_duration(str(path)) or 0
            src = SourceFile(
                path=path,
                duration_ms=duration_ms,
                file_type=path.suffix[1:].lower()
            )
            sources.append(src)

        # ファイル名順でソート
        sources.sort(key=lambda s: s.path.name.lower())
        return sources

    def get_youtube_url(self) -> str:
        """YouTube URLを取得"""
        return self._youtube_url if self._source_type == "youtube" else ""

    def get_cover_image(self) -> Optional[QImage]:
        """カバー画像を取得"""
        return self._cover_image

    def get_source_type(self) -> str:
        """ソースタイプを取得（local / youtube）"""
        return self._source_type

    def get_work_dir(self) -> Path:
        """現在の作業ディレクトリを取得"""
        return self._work_dir

    def keyPressEvent(self, event):
        """Returnキーで選択確定"""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            selected = self._file_list.selectedItems()
            if selected:
                # ファイルが選択されている場合はOK
                self.accept()
                return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        """リサイズ時にアスペクト比を維持"""
        if self._resizing:
            return super().resizeEvent(event)

        self._resizing = True

        new_size = event.size()
        old_size = event.oldSize()

        width_changed = new_size.width() != old_size.width()
        height_changed = new_size.height() != old_size.height()

        if width_changed and height_changed:
            new_width = new_size.width()
            new_height = int(new_width / self.ASPECT_RATIO)
        elif width_changed:
            new_width = new_size.width()
            new_height = int(new_width / self.ASPECT_RATIO)
        else:
            new_height = new_size.height()
            new_width = int(new_height * self.ASPECT_RATIO)

        new_width = max(new_width, self.MIN_WIDTH)
        new_height = max(new_height, self.MIN_HEIGHT)

        if new_width != new_size.width() or new_height != new_size.height():
            self.resize(new_width, new_height)

        self._resizing = False
        super().resizeEvent(event)


class CoverImageDialog(QDialog):
    """
    カバー画像選択ダイアログ

    機能:
    - 画像ファイル選択
    - インタラクティブなクロップ（16:9固定）
    - 回転
    - JPEG圧縮品質調整とプレビュー
    - 閉じると選択内容を返却

    使用例:
        dialog = CoverImageDialog(parent)
        if dialog.exec() == QDialog.Accepted:
            image = dialog.get_image()
            # image: QImage (1280x720)
    """

    # シグナル
    image_changed = Signal(object)  # QImage

    # ダイアログサイズ
    DEFAULT_WIDTH = 1344
    DEFAULT_HEIGHT = 840
    MIN_WIDTH = 896
    MIN_HEIGHT = 560
    ASPECT_RATIO = DEFAULT_WIDTH / DEFAULT_HEIGHT

    def __init__(self, parent=None, initial_image: Optional[QImage] = None, work_dir: Optional[Path] = None):
        super().__init__(parent)
        self._work_dir = work_dir or Path.cwd()
        self._resizing = False  # リサイズ中フラグ
        self._setup_ui()
        if initial_image:
            self._crop_widget.load_image_from_qimage(initial_image)

    def _setup_ui(self):
        """UI構築"""
        self.setWindowTitle("Select Cover Image")
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.setStyleSheet("""
            QDialog {
                background: #1a1a1a;
                font-size: 18px;
            }
            QLabel {
                color: #f0f0f0;
                font-size: 18px;
            }
            QPushButton {
                font-size: 18px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #3a3a3a;
                height: 8px;
                background: #2d2d2d;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #3b82f6;
                border: none;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #2563eb;
            }
            QSpinBox {
                background: #2d2d2d;
                color: #f0f0f0;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 18px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ImageCropWidget（メインのクロップ/プレビューエリア）
        self._crop_widget = ImageCropWidget()
        self._crop_widget.compressionChanged.connect(self._on_compression_changed)
        layout.addWidget(self._crop_widget, 1)

        # 画像操作ボタン + 情報表示
        image_buttons = QHBoxLayout()

        select_btn = QPushButton("Select Image...")
        select_btn.setStyleSheet(self._button_style())
        select_btn.setFixedWidth(140)
        select_btn.setFixedHeight(40)
        select_btn.clicked.connect(self._select_image)
        image_buttons.addWidget(select_btn)

        paste_btn = QPushButton("Clipboard")
        paste_btn.setStyleSheet(self._button_style())
        paste_btn.setFixedWidth(140)
        paste_btn.setFixedHeight(40)
        paste_btn.setToolTip("クリップボードから画像を貼り付け (Cmd+V / Ctrl+V)")
        paste_btn.clicked.connect(self._paste_from_clipboard)
        image_buttons.addWidget(paste_btn)

        self._preview_btn = QPushButton("Preview")
        self._preview_btn.setStyleSheet(self._toggle_button_style())
        self._preview_btn.setFixedWidth(140)
        self._preview_btn.setFixedHeight(40)
        self._preview_btn.setCheckable(True)
        self._preview_btn.setToolTip("圧縮プレビュー表示（左: オリジナル / 右: JPEG圧縮後）")
        self._preview_btn.toggled.connect(self._on_preview_toggled)
        image_buttons.addWidget(self._preview_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(self._button_style(primary=True))
        ok_btn.setFixedWidth(100)
        ok_btn.setFixedHeight(40)
        ok_btn.clicked.connect(self.accept)
        image_buttons.addWidget(ok_btn)

        image_buttons.addStretch()

        # 情報表示（右揃え）
        self._info_label = QLabel("")
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        image_buttons.addWidget(self._info_label)

        layout.addLayout(image_buttons)

        # 回転コントロール
        rotation_layout = QHBoxLayout()
        rotation_label = QLabel("Rotation:")
        rotation_label.setMinimumWidth(100)
        rotation_layout.addWidget(rotation_label)

        self._rotation_slider = QSlider(Qt.Orientation.Horizontal)
        self._rotation_slider.setRange(0, 359)
        self._rotation_slider.setValue(0)
        self._rotation_slider.setFixedHeight(30)
        self._rotation_slider.setTickInterval(90)
        self._rotation_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._rotation_slider.valueChanged.connect(self._on_rotation_changed)
        rotation_layout.addWidget(self._rotation_slider, 1)

        self._rotation_spin = QSpinBox()
        self._rotation_spin.setRange(0, 359)
        self._rotation_spin.setSuffix("°")
        self._rotation_spin.setFixedWidth(100)
        self._rotation_spin.setFixedHeight(36)
        self._rotation_spin.valueChanged.connect(self._on_rotation_spin_changed)
        rotation_layout.addWidget(self._rotation_spin)

        # 90度単位回転ボタン
        rotate_ccw_btn = QPushButton("↺ 90°")
        rotate_ccw_btn.setStyleSheet(self._button_style())
        rotate_ccw_btn.setFixedWidth(80)
        rotate_ccw_btn.setFixedHeight(36)
        rotate_ccw_btn.clicked.connect(lambda: self._rotate_by(-90))
        rotation_layout.addWidget(rotate_ccw_btn)

        rotate_cw_btn = QPushButton("↻ 90°")
        rotate_cw_btn.setStyleSheet(self._button_style())
        rotate_cw_btn.setFixedWidth(80)
        rotate_cw_btn.setFixedHeight(36)
        rotate_cw_btn.clicked.connect(lambda: self._rotate_by(90))
        rotation_layout.addWidget(rotate_cw_btn)

        layout.addLayout(rotation_layout)

        # 品質コントロール
        quality_layout = QHBoxLayout()
        quality_label = QLabel("Quality:")
        quality_label.setMinimumWidth(100)
        quality_layout.addWidget(quality_label)

        self._quality_slider = QSlider(Qt.Orientation.Horizontal)
        self._quality_slider.setRange(1, 100)
        self._quality_slider.setValue(85)
        self._quality_slider.setFixedHeight(30)
        self._quality_slider.valueChanged.connect(self._on_quality_changed)
        quality_layout.addWidget(self._quality_slider, 1)

        self._quality_spin = QSpinBox()
        self._quality_spin.setRange(1, 100)
        self._quality_spin.setValue(85)
        self._quality_spin.setFixedWidth(100)
        self._quality_spin.setFixedHeight(36)
        self._quality_spin.valueChanged.connect(self._on_quality_spin_changed)
        quality_layout.addWidget(self._quality_spin)

        layout.addLayout(quality_layout)

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

    def _toggle_button_style(self) -> str:
        """トグルボタンスタイル"""
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
            QPushButton:checked {
                background: #3b82f6;
                color: white;
                border: none;
            }
            QPushButton:checked:hover {
                background: #2563eb;
            }
        """

    def _file_dialog_style(self) -> str:
        """ファイルダイアログ用ダークテーマスタイル"""
        return """
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
        """

    def _select_image(self):
        """画像選択"""
        dialog = QFileDialog(
            self,
            "Select Image",
            str(self._work_dir),
            "Image Files (*.jpg *.jpeg *.png *.bmp);;All Files (*)"
        )
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setStyleSheet(self._file_dialog_style())

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        files = dialog.selectedFiles()
        file = files[0] if files else ""
        if file:
            if self._crop_widget.load_image(file):
                self._info_label.setText(f"Source: {Path(file).name}")
                # 回転をリセット
                self._rotation_slider.setValue(0)
                self._rotation_spin.setValue(0)

    def _paste_from_clipboard(self) -> bool:
        """クリップボードから画像を貼り付け"""
        clipboard = QApplication.clipboard()
        image = clipboard.image()
        if not image.isNull():
            if self._crop_widget.load_image_from_qimage(image):
                self._info_label.setText("Source: Clipboard")
                # 回転をリセット
                self._rotation_slider.setValue(0)
                self._rotation_spin.setValue(0)
                return True
        return False

    def _on_rotation_changed(self, value: int):
        """回転スライダー変更"""
        self._rotation_spin.blockSignals(True)
        self._rotation_spin.setValue(value)
        self._rotation_spin.blockSignals(False)
        self._crop_widget.set_rotation(value)

    def _on_rotation_spin_changed(self, value: int):
        """回転スピンボックス変更"""
        self._rotation_slider.blockSignals(True)
        self._rotation_slider.setValue(value)
        self._rotation_slider.blockSignals(False)
        self._crop_widget.set_rotation(value)

    def _rotate_by(self, delta: int):
        """指定角度だけ回転"""
        current = self._rotation_slider.value()
        new_value = (current + delta) % 360
        self._rotation_slider.setValue(new_value)

    def _on_quality_changed(self, value: int):
        """品質スライダー変更"""
        self._quality_spin.blockSignals(True)
        self._quality_spin.setValue(value)
        self._quality_spin.blockSignals(False)
        self._crop_widget.set_compression_quality(value)

    def _on_quality_spin_changed(self, value: int):
        """品質スピンボックス変更"""
        self._quality_slider.blockSignals(True)
        self._quality_slider.setValue(value)
        self._quality_slider.blockSignals(False)
        self._crop_widget.set_compression_quality(value)

    def _on_preview_toggled(self, checked: bool):
        """プレビュートグル"""
        self._crop_widget.set_compression_preview(checked)

    def _on_compression_changed(self, size_bytes: int):
        """圧縮サイズ変更時"""
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
        self._info_label.setText(f"Output: 1280x720 (16:9) | JPEG size: {size_str}")

    def get_image(self) -> Optional[QImage]:
        """クロップ済み画像を取得"""
        return self._crop_widget.get_cropped_image()

    def keyPressEvent(self, event):
        """キーボードショートカット処理"""
        # Cmd+V (macOS) / Ctrl+V (Windows) でクリップボードから画像貼り付け
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self._paste_from_clipboard():
                event.accept()
                return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        """リサイズ時にアスペクト比を維持"""
        if self._resizing:
            return super().resizeEvent(event)

        self._resizing = True

        new_size = event.size()
        old_size = event.oldSize()

        width_changed = new_size.width() != old_size.width()
        height_changed = new_size.height() != old_size.height()

        if width_changed and height_changed:
            new_width = new_size.width()
            new_height = int(new_width / self.ASPECT_RATIO)
        elif width_changed:
            new_width = new_size.width()
            new_height = int(new_width / self.ASPECT_RATIO)
        else:
            new_height = new_size.height()
            new_width = int(new_height * self.ASPECT_RATIO)

        new_width = max(new_width, self.MIN_WIDTH)
        new_height = max(new_height, self.MIN_HEIGHT)

        if new_width != new_size.width() or new_height != new_size.height():
            self.resize(new_width, new_height)

        self._resizing = False
        super().resizeEvent(event)
