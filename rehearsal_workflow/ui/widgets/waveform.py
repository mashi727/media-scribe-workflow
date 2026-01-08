"""
waveform.py - 波形/スペクトログラム表示ウィジェット

min-max法による解像度適応型の波形表示。
除外チャプター（--プレフィックス）の区間をハッチングで表示。
"""

from typing import List

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QImage

from ..models import ChapterInfo

# numpy の有無をチェック
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class WaveformWidget(QWidget):
    """波形表示ウィジェット

    - min-max法による解像度適応型の波形表示
    - numpyを使用した高速な間引き処理
    - 上下対称の波形描画（緑色）
    - 除外チャプター（--プレフィックス）の区間をハッチングで表示
    """

    # シグナル
    position_clicked = Signal(float)  # クリック位置（0.0-1.0）

    # 表示モード定数
    MODE_WAVEFORM = 0
    MODE_SPECTROGRAM = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._waveform_data = None  # numpy配列 or list
        self._spectrogram_data = None  # 2D numpy配列
        self._spectrogram_image = None  # QImage（キャッシュ）
        self._display_cache: List[tuple] = []  # 表示用キャッシュ [(min, max), ...]
        self._cache_width: int = 0  # キャッシュ生成時の幅
        self._playback_position: float = 0.0  # 0.0-1.0
        self._is_loading = False
        self._loading_progress = 0
        self._loading_type = ""  # "waveform" or "spectrogram"
        self._error_message = ""
        self._display_mode = self.MODE_WAVEFORM  # 表示モード

        # チャプター表示用
        self._chapters: List[ChapterInfo] = []
        self._duration_ms: int = 0

        # ファイル境界位置（仮想タイムライン用）
        self._file_boundaries: List[float] = []  # 0.0-1.0 の正規化座標

        # 選択されたソース範囲（ハイライト用）
        self._selected_range: tuple = None  # (start: float, end: float) 0.0-1.0

        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMouseTracking(True)

    def set_chapters(self, chapters: List[ChapterInfo], duration_ms: int):
        """チャプター情報を設定"""
        self._chapters = chapters
        # duration_msが0の場合は既存値を保持
        if duration_ms > 0:
            self._duration_ms = duration_ms
        self.update()

    def set_file_boundaries(self, boundaries: List[float]):
        """ファイル境界位置を設定（仮想タイムライン用）

        Args:
            boundaries: ファイル境界の正規化位置（0.0-1.0）のリスト
        """
        self._file_boundaries = boundaries
        self.update()

    def clear_file_boundaries(self):
        """ファイル境界をクリア"""
        self._file_boundaries = []
        self.update()

    def set_selected_source_range(self, start: float = None, end: float = None):
        """選択されたソースファイルの範囲を設定（ハイライト表示用）

        Args:
            start: 開始位置（0.0-1.0）、Noneでクリア
            end: 終了位置（0.0-1.0）、Noneでクリア
        """
        if start is not None and end is not None:
            self._selected_range = (start, end)
        else:
            self._selected_range = None
        self.update()

    def clear_selected_source_range(self):
        """選択ソース範囲をクリア"""
        self._selected_range = None
        self.update()

    def _get_excluded_regions(self) -> List[tuple]:
        """除外チャプター（--で始まる）の区間を取得

        Returns:
            List of (start_ms, end_ms) tuples
        """
        if not self._chapters or self._duration_ms <= 0:
            return []

        excluded_regions = []
        sorted_chapters = sorted(self._chapters, key=lambda c: c.time_ms)

        for i, ch in enumerate(sorted_chapters):
            if ch.title.startswith("--"):
                start_ms = ch.time_ms
                # 次のチャプターの開始時間、またはメディアの終端
                if i + 1 < len(sorted_chapters):
                    end_ms = sorted_chapters[i + 1].time_ms
                else:
                    end_ms = self._duration_ms
                excluded_regions.append((start_ms, end_ms))

        return excluded_regions

    def set_waveform(self, data, duration_ms: int = 0):
        """波形データを設定

        Args:
            data: 波形サンプル値（numpy配列 or list、正規化済み）
            duration_ms: 動画の長さ（ミリ秒）
        """
        self._waveform_data = data
        if duration_ms > 0:
            self._duration_ms = duration_ms

        # キャッシュをクリア（次回描画時に再生成）
        self._display_cache = []
        self._cache_width = 0

        self._is_loading = False
        self._error_message = ""
        self.update()

    def set_spectrogram(self, data, duration_ms: int = 0):
        """スペクトログラムデータを設定

        Args:
            data: スペクトログラム（2D numpy配列、正規化済み0-1）
            duration_ms: 動画の長さ（ミリ秒）
        """
        self._spectrogram_data = data
        self._spectrogram_image = None  # キャッシュをクリア
        if duration_ms > 0:
            self._duration_ms = duration_ms

        self._is_loading = False
        self._error_message = ""
        self.update()

    def set_display_mode(self, mode: int):
        """表示モードを設定

        Args:
            mode: MODE_WAVEFORM or MODE_SPECTROGRAM
        """
        if self._display_mode != mode:
            self._display_mode = mode
            self.update()

    def has_waveform_data(self) -> bool:
        """波形データがあるか"""
        return self._waveform_data is not None and len(self._waveform_data) > 0

    def has_spectrogram_data(self) -> bool:
        """スペクトログラムデータがあるか"""
        return self._spectrogram_data is not None

    def _downsample_preserve_peaks(self, data, target_width: int) -> List[tuple]:
        """ピークを保持しながら波形データを間引く

        各ピクセルに対応するサンプル区間の最小値と最大値を返す。
        これにより、画面解像度が低くても波形のピークが失われない。

        Args:
            data: 元の波形データ（numpy配列 or list）
            target_width: 表示幅（ピクセル数）

        Returns:
            List of (min_value, max_value) for each pixel
        """
        if data is None or len(data) == 0:
            return []

        num_samples = len(data)
        result = []

        if num_samples <= target_width:
            # サンプル数が表示幅より少ない場合はそのまま使用
            for i in range(num_samples):
                val = float(data[i])
                result.append((val, val))
            # 残りを0で埋める
            for _ in range(target_width - num_samples):
                result.append((0.0, 0.0))
        else:
            # 各ピクセルに対応する区間の最小値・最大値を取得
            samples_per_pixel = num_samples / target_width

            if HAS_NUMPY and hasattr(data, '__array__'):
                # numpy配列の場合は高速処理
                for x in range(target_width):
                    start_idx = int(x * samples_per_pixel)
                    end_idx = int((x + 1) * samples_per_pixel)
                    end_idx = min(end_idx, num_samples)

                    if start_idx < end_idx:
                        chunk = data[start_idx:end_idx]
                        min_val = float(np.min(chunk))
                        max_val = float(np.max(chunk))
                        result.append((min_val, max_val))
                    else:
                        result.append((0.0, 0.0))
            else:
                # リストの場合
                for x in range(target_width):
                    start_idx = int(x * samples_per_pixel)
                    end_idx = int((x + 1) * samples_per_pixel)
                    end_idx = min(end_idx, num_samples)

                    if start_idx < end_idx:
                        chunk = data[start_idx:end_idx]
                        min_val = min(chunk)
                        max_val = max(chunk)
                        result.append((float(min_val), float(max_val)))
                    else:
                        result.append((0.0, 0.0))

        return result

    def set_loading(self, progress: int, loading_type: str = "waveform"):
        """ロード中状態を設定

        Args:
            progress: 進捗（0-100）
            loading_type: "waveform" or "spectrogram"
        """
        self._is_loading = True
        self._loading_progress = progress
        self._loading_type = loading_type
        self.update()

    def set_error(self, message: str):
        """エラー状態を設定"""
        self._is_loading = False
        self._error_message = message
        self.update()

    def set_position(self, position: float):
        """再生位置を設定（0.0-1.0）"""
        self._playback_position = max(0.0, min(1.0, position))
        self.update()

    def clear(self):
        """クリア"""
        self._waveform_data = None
        self._spectrogram_data = None
        self._spectrogram_image = None
        self._display_cache = []
        self._cache_width = 0
        self._playback_position = 0.0
        self._is_loading = False
        self._loading_type = ""
        self._error_message = ""
        self._display_mode = self.MODE_WAVEFORM
        self._file_boundaries = []
        self._selected_range = None
        self.update()

    def resizeEvent(self, event):
        """リサイズ時にキャッシュを無効化"""
        self._display_cache = []
        self._cache_width = 0
        self._spectrogram_image = None  # スペクトログラム画像もクリア
        super().resizeEvent(event)

    def paintEvent(self, event):
        """描画"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        center_y = h // 2

        # 背景
        painter.fillRect(0, 0, w, h, QColor(26, 26, 26))

        if self._error_message:
            # エラー表示
            painter.setPen(QColor("#ef4444"))
            painter.drawText(
                0, 0, w, h,
                Qt.AlignmentFlag.AlignCenter,
                self._error_message
            )
            return

        # 波形ローディング中（波形データがまだない場合）
        if self._is_loading and self._loading_type == "waveform":
            painter.setPen(QColor("#666666"))
            painter.drawText(
                0, 0, w, h,
                Qt.AlignmentFlag.AlignCenter,
                f"Loading waveform... {self._loading_progress}%"
            )
            return

        # 表示モードに応じて描画
        if self._display_mode == self.MODE_SPECTROGRAM:
            self._paint_spectrogram(painter, w, h)
        else:
            self._paint_waveform(painter, w, h, center_y)

        # スペクトログラム計算中は波形の上にオーバーレイ表示
        if self._is_loading and self._loading_type == "spectrogram":
            # 半透明の背景
            painter.fillRect(0, h - 24, w, 24, QColor(0, 0, 0, 180))
            painter.setPen(QColor("#66b3ff"))
            painter.drawText(
                0, h - 24, w, 24,
                Qt.AlignmentFlag.AlignCenter,
                f"Generating spectrogram... {self._loading_progress}%"
            )

    def _paint_waveform(self, painter: QPainter, w: int, h: int, center_y: int):
        """波形を描画"""
        if self._waveform_data is None or len(self._waveform_data) == 0:
            # 空状態
            painter.setPen(QColor("#444444"))
            painter.drawText(
                0, 0, w, h,
                Qt.AlignmentFlag.AlignCenter,
                "No waveform data"
            )
            return

        # 表示キャッシュを構築（幅が変わった場合のみ）
        if self._cache_width != w or not self._display_cache:
            self._display_cache = self._downsample_preserve_peaks(self._waveform_data, w)
            self._cache_width = w

        # 波形の色（緑色）
        painter.setPen(QColor(76, 175, 80))

        # 波形描画（上下対称）
        for x in range(len(self._display_cache)):
            if x >= w:
                break
            min_val, max_val = self._display_cache[x]
            # 上下対称に描画（絶対値の最大を使用）
            peak = max(abs(min_val), abs(max_val))
            bar_height = int(peak * (h - 10) / 2)
            painter.drawLine(x, center_y - bar_height, x, center_y + bar_height)

        # 共通描画を呼び出し
        self._paint_overlays(painter, w, h)

    def _paint_spectrogram(self, painter: QPainter, w: int, h: int):
        """スペクトログラムを描画"""
        if self._spectrogram_data is None:
            # 空状態
            painter.setPen(QColor("#444444"))
            painter.drawText(
                0, 0, w, h,
                Qt.AlignmentFlag.AlignCenter,
                "No spectrogram data"
            )
            return

        # スペクトログラム画像をキャッシュから取得または生成
        if self._spectrogram_image is None or self._spectrogram_image.width() != w or self._spectrogram_image.height() != h:
            self._spectrogram_image = self._create_spectrogram_image(w, h)

        if self._spectrogram_image:
            painter.drawImage(0, 0, self._spectrogram_image)

        # 共通描画を呼び出し
        self._paint_overlays(painter, w, h)

    def _create_spectrogram_image(self, w: int, h: int):
        """スペクトログラムをQImageに変換（黒→青→シアン カラーマップ）"""
        if self._spectrogram_data is None:
            return None

        try:
            import numpy as np

            data = self._spectrogram_data.copy()

            # サイズ調整（最近傍補間）
            if data.shape[1] != w or data.shape[0] != h:
                x_indices = np.linspace(0, data.shape[1] - 1, w).astype(int)
                y_indices = np.linspace(0, data.shape[0] - 1, h).astype(int)
                data = data[np.ix_(y_indices, x_indices)]

            # カラーマップ: 黒→青→黄緑寄りのシアン
            data = np.power(data, 0.8)

            r = np.zeros_like(data, dtype=np.uint8)
            g = np.zeros_like(data, dtype=np.uint8)
            b = np.zeros_like(data, dtype=np.uint8)

            # 0.0-0.5: 黒→青
            mask = data < 0.5
            t = data[mask] / 0.5
            b[mask] = (t * 255).astype(np.uint8)

            # 0.5-1.0: 青→黄緑寄りシアン RGB(80, 255, 120)
            mask = data >= 0.5
            t = (data[mask] - 0.5) / 0.5
            r[mask] = (t * 80).astype(np.uint8)
            g[mask] = (t * 255).astype(np.uint8)
            b[mask] = (255 - t * 135).astype(np.uint8)  # 255→120

            # RGBA形式のバイト配列を作成
            rgba = np.zeros((h, w, 4), dtype=np.uint8)
            rgba[:, :, 0] = r
            rgba[:, :, 1] = g
            rgba[:, :, 2] = b
            rgba[:, :, 3] = 255  # アルファ

            # QImageを作成
            image = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
            return image.copy()  # データのコピーを返す

        except Exception:
            return None

    def _paint_overlays(self, painter: QPainter, w: int, h: int):
        """共通のオーバーレイ描画（除外区間、チャプターマーカー、再生位置）"""

        # 除外区間のハッチング描画
        if self._duration_ms > 0:
            excluded_regions = self._get_excluded_regions()

            # 除外区間: 赤系（両モード共通）
            fill_color = QColor(255, 0, 0, 40)
            hatch_color = QColor(255, 100, 100, 120)

            for start_ms, end_ms in excluded_regions:
                start_x = int(start_ms * w / self._duration_ms)
                end_x = int(end_ms * w / self._duration_ms)
                region_width = end_x - start_x

                # 半透明の背景
                painter.fillRect(start_x, 0, region_width, h, fill_color)

                # 斜線ハッチングパターン
                pen = QPen(hatch_color)
                pen.setWidthF(1.5)
                painter.setPen(pen)
                spacing = 10  # 斜線の間隔
                for offset in range(-h, region_width + h, spacing):
                    x1 = start_x + offset
                    y1 = 0
                    x2 = start_x + offset + h
                    y2 = h

                    # クリッピング
                    if x1 < start_x:
                        y1 = start_x - x1
                        x1 = start_x
                    if x2 > end_x:
                        y2 = h - (x2 - end_x)
                        x2 = end_x

                    if x1 < end_x and x2 > start_x:
                        painter.drawLine(x1, y1, x2, y2)

        # 複数ファイルモードかどうか
        is_multi_file = len(self._file_boundaries) > 0
        marker_height = 12  # 上下のマーカー高さ

        # 選択されたソース範囲をハイライト（半透明背景のみ）
        if self._selected_range and is_multi_file:
            start_norm, end_norm = self._selected_range
            start_x = int(start_norm * w)
            end_x = int(end_norm * w)
            region_width = end_x - start_x

            if region_width > 0:
                # 半透明の青い背景
                fill_color = QColor(100, 180, 255, 40)
                painter.fillRect(start_x, 0, region_width, h, fill_color)

        # ファイル境界を描画（仮想タイムライン用）- 上下の短い線
        if self._file_boundaries:
            pen = QPen(QColor(100, 180, 255, 220))  # 水色
            pen.setWidth(3)
            painter.setPen(pen)
            for boundary_pos in self._file_boundaries:
                x = int(boundary_pos * w)
                # 上部の短い線
                painter.drawLine(x, 0, x, marker_height)
                # 下部の短い線
                painter.drawLine(x, h - marker_height, x, h)

        # チャプターマーカーを描画（ファイル境界と被らないように）
        if self._duration_ms > 0 and self._chapters:
            # チャプターマーカー: 黄色（両モード共通）
            pen = QPen(QColor(255, 193, 7))
            pen.setWidthF(1.5)
            painter.setPen(pen)
            for ch in self._chapters:
                x = int(ch.time_ms * w / self._duration_ms)
                if is_multi_file:
                    # 複数ファイル: 中央部分（青のファイル境界と被らない）
                    painter.drawLine(x, marker_height, x, h - marker_height)
                else:
                    # 単一ファイル: 全高の線
                    painter.drawLine(x, 0, x, h)

        # 再生位置インジケータ（明るい黄色、太め）
        if self._duration_ms > 0:
            pos_x = int(self._playback_position * w)
            pen = QPen(QColor(253, 224, 71))  # 明るい黄色 #fde047
            pen.setWidth(3)  # 太さ3px
            painter.setPen(pen)
            painter.drawLine(pos_x, 0, pos_x, h)

    def mousePressEvent(self, event):
        """クリックで再生位置を変更"""
        has_data = (self._waveform_data is not None and len(self._waveform_data) > 0) or \
                   (self._spectrogram_data is not None)
        if has_data:
            if event.button() == Qt.MouseButton.LeftButton:
                position = event.position().x() / self.width()
                self.position_clicked.emit(position)
