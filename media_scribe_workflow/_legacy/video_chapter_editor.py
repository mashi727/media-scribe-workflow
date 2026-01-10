#!/usr/bin/env python3
"""
prep_gui.py - 素材準備ツール

音声/動画素材の前処理を行うGUIツール。
- タブ1: MP3結合（曲別MP3を1つに結合 + チャプター生成）
- タブ2: 編集（カット、チャプター、カバー画像）
- タブ3: 書出（最終MP4出力）

作成日: 2024-12-26
"""

import sys
import os
import subprocess
import json
import re
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox, QFileDialog,
    QComboBox, QCheckBox, QProgressBar, QTabWidget, QScrollArea,
    QMessageBox, QSplitter, QFrame, QPlainTextEdit, QListWidget,
    QListWidgetItem, QSlider, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy, QDialog, QMenuBar, QMenu
)
from PySide6.QtCore import Qt, QProcess, QTimer, Signal, Slot, QUrl, QSize, QThread, QRectF, QPointF, QBuffer, QIODevice, QSettings
from PySide6.QtGui import QFont, QColor, QPalette, QImage, QPixmap, QPainter, QBrush, QTransform, QPen, QAction
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices, QAudioDevice
from PySide6.QtMultimediaWidgets import QVideoWidget

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

import tempfile
import wave
import struct
import platform


# ==============================================================================
# モダンダーク UI カラーパレット
# ==============================================================================

class Theme:
    """統一されたUIテーマ定義"""
    # 背景色（暗い順）
    BG_DARKEST = "#0f0f0f"      # 最も暗い背景
    BG_DARK = "#1a1a1a"         # ダーク背景
    BG_BASE = "#242424"         # ベース背景
    BG_ELEVATED = "#2d2d2d"     # 浮いた要素
    BG_HOVER = "#363636"        # ホバー時
    BG_ACTIVE = "#404040"       # アクティブ時

    # テキスト色
    TEXT_PRIMARY = "#f0f0f0"    # メインテキスト
    TEXT_SECONDARY = "#a0a0a0"  # セカンダリテキスト
    TEXT_MUTED = "#666666"      # 控えめなテキスト

    # アクセントカラー
    ACCENT = "#3b82f6"          # メインアクセント（ブルー）
    ACCENT_HOVER = "#2563eb"    # ホバー時
    ACCENT_ACTIVE = "#1d4ed8"   # アクティブ時

    # ステータスカラー
    SUCCESS = "#22c55e"         # 成功（グリーン）
    WARNING = "#f59e0b"         # 警告（オレンジ）
    DANGER = "#ef4444"          # 危険（レッド）
    DANGER_HOVER = "#dc2626"

    # ボーダー
    BORDER = "#3a3a3a"
    BORDER_LIGHT = "#4a4a4a"

    # その他
    RADIUS = "8px"
    RADIUS_SM = "4px"
    SHADOW = "0 4px 12px rgba(0, 0, 0, 0.3)"

    @classmethod
    def button_primary(cls) -> str:
        return f"""
            QPushButton {{
                background: {cls.ACCENT};
                color: white;
                border: none;
                border-radius: {cls.RADIUS};
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background: {cls.ACCENT_HOVER}; }}
            QPushButton:pressed {{ background: {cls.ACCENT_ACTIVE}; }}
            QPushButton:disabled {{ background: {cls.BG_HOVER}; color: {cls.TEXT_MUTED}; }}
        """

    @classmethod
    def button_secondary(cls) -> str:
        return f"""
            QPushButton {{
                background: {cls.BG_ELEVATED};
                color: {cls.TEXT_PRIMARY};
                border: 1px solid {cls.BORDER};
                border-radius: {cls.RADIUS};
                padding: 10px 20px;
                font-size: 14px;
            }}
            QPushButton:hover {{ background: {cls.BG_HOVER}; border-color: {cls.BORDER_LIGHT}; }}
            QPushButton:pressed {{ background: {cls.BG_ACTIVE}; }}
        """

    @classmethod
    def button_danger(cls) -> str:
        return f"""
            QPushButton {{
                background: {cls.DANGER};
                color: white;
                border: none;
                border-radius: {cls.RADIUS};
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background: {cls.DANGER_HOVER}; }}
            QPushButton:pressed {{ background: #b91c1c; }}
        """

    @classmethod
    def input_style(cls) -> str:
        return f"""
            QLineEdit, QSpinBox, QComboBox {{
                background: {cls.BG_DARK};
                color: {cls.TEXT_PRIMARY};
                border: 1px solid {cls.BORDER};
                border-radius: {cls.RADIUS_SM};
                padding: 8px 12px;
                font-size: 14px;
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border-color: {cls.ACCENT};
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox::down-arrow {{ image: none; }}
        """

    @classmethod
    def main_window_style(cls) -> str:
        return f"""
            QMainWindow, QWidget {{
                background: {cls.BG_BASE};
                color: {cls.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {cls.TEXT_PRIMARY};
            }}
            QGroupBox {{
                background: {cls.BG_ELEVATED};
                border: 1px solid {cls.BORDER};
                border-radius: {cls.RADIUS};
                margin-top: 16px;
                padding: 16px;
                font-weight: 500;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: {cls.TEXT_PRIMARY};
            }}
            QTabWidget::pane {{
                background: {cls.BG_ELEVATED};
                border: 1px solid {cls.BORDER};
                border-radius: {cls.RADIUS};
            }}
            QTabBar::tab {{
                background: {cls.BG_DARK};
                color: {cls.TEXT_SECONDARY};
                padding: 10px 24px;
                margin-right: 2px;
                border-top-left-radius: {cls.RADIUS};
                border-top-right-radius: {cls.RADIUS};
            }}
            QTabBar::tab:selected {{
                background: {cls.BG_ELEVATED};
                color: {cls.TEXT_PRIMARY};
            }}
            QTabBar::tab:hover:!selected {{
                background: {cls.BG_HOVER};
            }}
            QScrollBar:vertical {{
                background: {cls.BG_DARK};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {cls.BG_HOVER};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {cls.BG_ACTIVE};
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                height: 0;
            }}
            QTableWidget {{
                background: {cls.BG_DARK};
                border: 1px solid {cls.BORDER};
                border-radius: {cls.RADIUS_SM};
                gridline-color: {cls.BORDER};
            }}
            QTableWidget::item {{
                padding: 8px;
            }}
            QTableWidget::item:selected {{
                background: {cls.ACCENT};
            }}
            QHeaderView::section {{
                background: {cls.BG_ELEVATED};
                color: {cls.TEXT_SECONDARY};
                padding: 8px;
                border: none;
                border-bottom: 1px solid {cls.BORDER};
            }}
            QProgressBar {{
                background: {cls.BG_DARK};
                border: none;
                border-radius: {cls.RADIUS_SM};
                height: 8px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: {cls.ACCENT};
                border-radius: {cls.RADIUS_SM};
            }}
            QCheckBox {{
                color: {cls.TEXT_PRIMARY};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid {cls.BORDER};
                background: {cls.BG_DARK};
            }}
            QCheckBox::indicator:checked {{
                background: {cls.ACCENT};
                border-color: {cls.ACCENT};
            }}
            QSlider::groove:horizontal {{
                background: {cls.BG_DARK};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {cls.ACCENT};
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {cls.ACCENT_HOVER};
            }}
            QListWidget {{
                background: {cls.BG_DARK};
                border: 1px solid {cls.BORDER};
                border-radius: {cls.RADIUS_SM};
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: {cls.RADIUS_SM};
            }}
            QListWidget::item:selected {{
                background: {cls.ACCENT};
            }}
            QListWidget::item:hover:!selected {{
                background: {cls.BG_HOVER};
            }}
        """


# ==============================================================================
# GPUエンコーダ検出
# ==============================================================================

def detect_available_encoders() -> List[Tuple[str, str, str]]:
    """
    利用可能なH.264エンコーダを検出

    Returns:
        List of (encoder_id, display_name, description)
        例: [("h264_videotoolbox", "GPU (VideoToolbox)", "Apple GPU高速エンコード")]
    """
    encoders = []

    # プラットフォーム別のGPUエンコーダ候補
    if platform.system() == "Darwin":
        # macOS: VideoToolbox
        gpu_candidates = [
            ("h264_videotoolbox", "GPU (VideoToolbox)", "Apple GPUで高速エンコード"),
        ]
    elif platform.system() == "Windows":
        # Windows: NVENC, QSV, AMF
        gpu_candidates = [
            ("h264_nvenc", "GPU (NVIDIA)", "NVIDIA GPUで高速エンコード"),
            ("h264_qsv", "GPU (Intel QSV)", "Intel GPUで高速エンコード"),
            ("h264_amf", "GPU (AMD)", "AMD GPUで高速エンコード"),
        ]
    else:
        # Linux
        gpu_candidates = [
            ("h264_nvenc", "GPU (NVIDIA)", "NVIDIA GPUで高速エンコード"),
            ("h264_vaapi", "GPU (VAAPI)", "VAAPI GPUで高速エンコード"),
            ("h264_qsv", "GPU (Intel QSV)", "Intel GPUで高速エンコード"),
        ]

    # ffmpegでエンコーダの利用可否を確認
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5
        )
        available_output = result.stdout

        for encoder_id, display_name, description in gpu_candidates:
            if encoder_id in available_output:
                encoders.append((encoder_id, display_name, description))
    except Exception as e:
        print(f"[Encoder] GPU検出エラー: {e}")

    # CPUエンコーダは常に利用可能
    encoders.append(("libx264", "CPU (x264)", "CPU処理・高画質"))

    return encoders


def detect_system_font() -> str:
    """プラットフォームに応じた日本語フォントパスを検出"""
    system = platform.system()

    if system == "Darwin":
        # macOS: ヒラギノ角ゴシック優先
        candidates = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
    elif system == "Windows":
        # Windows: メイリオ、游ゴシック、MSゴシック
        fonts_dir = "C:/Windows/Fonts"
        candidates = [
            f"{fonts_dir}/meiryo.ttc",      # メイリオ
            f"{fonts_dir}/YuGothM.ttc",     # 游ゴシック Medium
            f"{fonts_dir}/YuGothR.ttc",     # 游ゴシック Regular
            f"{fonts_dir}/msgothic.ttc",    # MS ゴシック
            f"{fonts_dir}/msmincho.ttc",    # MS 明朝
        ]
    else:
        # Linux等: Noto Sans CJK
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

    for font_path in candidates:
        if Path(font_path).exists():
            return font_path

    # フォールバック: ffmpegのデフォルトフォントを使用
    return ""


def get_encoder_args(encoder_id: str, bitrate_kbps: int = 4000, crf: int = 23) -> List[str]:
    """
    エンコーダIDに応じたffmpegオプションを返す

    Args:
        encoder_id: "h264_videotoolbox", "h264_nvenc", "libx264" など
        bitrate_kbps: GPUエンコーダ用ビットレート（kbps）
        crf: CPUエンコーダ(libx264)用の品質値（低いほど高画質）

    Returns:
        ffmpegコマンド引数リスト
    """
    bitrate = f"{bitrate_kbps}k"
    maxrate = f"{int(bitrate_kbps * 1.2)}k"  # 最大ビットレート（指定の1.2倍）
    bufsize = f"{bitrate_kbps * 2}k"  # バッファサイズ（指定の2倍）

    if encoder_id == "h264_videotoolbox":
        # macOS VideoToolbox
        return [
            '-c:v', 'h264_videotoolbox',
            '-b:v', bitrate,
            '-maxrate', maxrate,
            '-bufsize', bufsize,
            '-pix_fmt', 'yuv420p',
        ]
    elif encoder_id == "h264_nvenc":
        # NVIDIA NVENC
        return [
            '-c:v', 'h264_nvenc',
            '-preset', 'p4',  # バランス（p1=最速, p7=最高画質）
            '-b:v', bitrate,
            '-maxrate', maxrate,
            '-bufsize', bufsize,
            '-pix_fmt', 'yuv420p',
        ]
    elif encoder_id == "h264_qsv":
        # Intel Quick Sync
        return [
            '-c:v', 'h264_qsv',
            '-preset', 'medium',
            '-b:v', bitrate,
            '-maxrate', maxrate,
            '-bufsize', bufsize,
            '-pix_fmt', 'nv12',
        ]
    elif encoder_id == "h264_amf":
        # AMD AMF
        return [
            '-c:v', 'h264_amf',
            '-quality', 'balanced',
            '-b:v', bitrate,
            '-maxrate', maxrate,
            '-bufsize', bufsize,
            '-pix_fmt', 'yuv420p',
        ]
    elif encoder_id == "h264_vaapi":
        # VAAPI (Linux)
        return [
            '-c:v', 'h264_vaapi',
            '-b:v', bitrate,
            '-maxrate', maxrate,
            '-bufsize', bufsize,
        ]
    else:
        # CPU (libx264) - CRFで品質ベースエンコード
        return [
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', str(crf),
            '-pix_fmt', 'yuv420p',
        ]


def detect_video_bitrate(file_path: str) -> Optional[int]:
    """
    動画のビットレートを取得（kbps単位）

    Args:
        file_path: 動画ファイルパス

    Returns:
        ビットレート（kbps）、取得失敗時はNone
    """
    try:
        # まず動画ストリームのビットレートを試行
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=bit_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        bitrate_str = result.stdout.strip()

        if bitrate_str and bitrate_str != "N/A":
            bitrate_bps = int(bitrate_str)
            return bitrate_bps // 1000  # bps → kbps

        # 動画ストリームで取得できない場合、format全体のビットレートを使用
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=bit_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        bitrate_str = result.stdout.strip()

        if bitrate_str and bitrate_str != "N/A":
            bitrate_bps = int(bitrate_str)
            return bitrate_bps // 1000  # bps → kbps

    except Exception as e:
        print(f"[Bitrate] 検出エラー: {e}")

    return None


@dataclass
class ColorspaceInfo:
    """色空間情報"""
    color_space: str = ""
    color_primaries: str = ""
    color_transfer: str = ""

    def get_ffmpeg_args(self) -> List[str]:
        """ffmpeg用の色空間引数を返す"""
        args = []
        if self.color_space and self.color_space != "unknown":
            args.extend(['-colorspace', self.color_space])
        if self.color_primaries and self.color_primaries != "unknown":
            args.extend(['-color_primaries', self.color_primaries])
        if self.color_transfer and self.color_transfer != "unknown":
            args.extend(['-color_trc', self.color_transfer])
        return args


def detect_video_colorspace(file_path: str) -> ColorspaceInfo:
    """
    動画の色空間情報を取得

    Args:
        file_path: 動画ファイルパス

    Returns:
        ColorspaceInfo
    """
    info = ColorspaceInfo()
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=color_space,color_primaries,color_transfer",
                "-of", "default=noprint_wrappers=1",
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        for line in result.stdout.strip().split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                if key == "color_space":
                    info.color_space = value
                elif key == "color_primaries":
                    info.color_primaries = value
                elif key == "color_transfer":
                    info.color_transfer = value

        print(f"[Colorspace] 検出: space={info.color_space}, primaries={info.color_primaries}, transfer={info.color_transfer}")

    except Exception as e:
        print(f"[Colorspace] 検出エラー: {e}")

    return info


# ==============================================================================
# カスタムファイルダイアログ（中央配置 + フィルタ機能）
# ==============================================================================

class CenteredFileDialog(QFileDialog):
    """中央配置ファイルダイアログ"""

    def __init__(self, parent=None, caption="", directory="", filter=""):
        super().__init__(parent, caption, directory, filter)
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self._filter_str = filter  # showEventで使用
        self._apply_style()

    def _apply_extension_filter(self):
        """拡張子フィルタを適用（対象外ファイルを非表示）"""
        if not self._filter_str:
            return
        # フィルタ文字列から拡張子を抽出 (例: "*.mp4 *.mp3" → ['*.mp4', '*.mp3'])
        import re
        extensions = re.findall(r'\*\.\w+', self._filter_str)
        if extensions:
            from PySide6.QtWidgets import QFileSystemModel
            for model in self.findChildren(QFileSystemModel):
                model.setNameFilters(extensions)
                model.setNameFilterDisables(False)  # False=非表示、True=グレーアウト

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

    def _center_on_parent(self):
        """親ウィンドウの中央に配置（ウィンドウ移動後も正しく動作）"""
        parent = self.parent()
        if parent:
            # トップレベルウィンドウを取得
            window = parent.window() if hasattr(parent, 'window') else parent
            # frameGeometry()でウィンドウ装飾を含む位置を取得
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


# ==============================================================================
# ビデオコントローラ（movie-viewerと同じ仕様）
# ==============================================================================

class VideoController:
    """ビデオ制御を担当するクラス"""

    def __init__(self, media_player: QMediaPlayer):
        self.media_player = media_player
        self.frame_rate = 25.0  # デフォルトフレームレート

    def seek_by_milliseconds(self, milliseconds: int) -> int:
        """指定されたミリ秒分シーク"""
        current_position = self.media_player.position()
        new_position = max(0, current_position + milliseconds)
        duration = self.media_player.duration()
        if duration > 0:
            new_position = min(new_position, duration)
        self.media_player.setPosition(new_position)
        return new_position

    def seek_by_frame(self, frame_count: int = 1) -> int:
        """フレーム単位でシーク"""
        frame_duration_ms = 1000 / self.frame_rate
        milliseconds = int(frame_duration_ms * frame_count)
        return self.seek_by_milliseconds(milliseconds)

    def set_frame_rate(self, frame_rate: float):
        """フレームレートを設定"""
        if frame_rate > 0:
            self.frame_rate = frame_rate

    @staticmethod
    def get_frame_rate(video_path: str) -> float:
        """動画ファイルのフレームレートを取得"""
        if not HAS_CV2:
            return 25.0

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return 25.0

        frame_rate = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        return frame_rate if frame_rate > 0 else 25.0


# ==============================================================================
# アスペクト比維持ウィジェット
# ==============================================================================

class AspectRatioWidget(QWidget):
    """指定したアスペクト比を維持するコンテナウィジェット"""

    # 内部ウィジェットの幅が変更されたときのシグナル
    innerWidthChanged = Signal(int)

    def __init__(self, widget: QWidget, aspect_ratio: float = 16/9, parent=None):
        super().__init__(parent)
        self.aspect_ratio = aspect_ratio
        self.inner_widget = widget
        self._current_inner_width = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(widget)

        self.setStyleSheet("background-color: #000;")

    def resizeEvent(self, event):
        """リサイズ時にアスペクト比を維持"""
        super().resizeEvent(event)

        w = self.width()
        h = self.height()

        # 利用可能な領域に収まる最大サイズを計算
        if w / h > self.aspect_ratio:
            # 幅が広すぎる → 高さに合わせる
            new_h = h
            new_w = int(h * self.aspect_ratio)
        else:
            # 高さが高すぎる → 幅に合わせる
            new_w = w
            new_h = int(w / self.aspect_ratio)

        # 内部ウィジェットのサイズを設定
        self.inner_widget.setFixedSize(new_w, new_h)

        # 幅が変わったらシグナルを発火
        if new_w != self._current_inner_width:
            self._current_inner_width = new_w
            self.innerWidthChanged.emit(new_w)

    def get_inner_width(self) -> int:
        """内部ウィジェットの現在の幅を取得"""
        return self._current_inner_width


# ==============================================================================
# 波形ウィジェット
# ==============================================================================

class WaveformWidget(QWidget):
    """音声波形を表示するウィジェット"""

    clicked = Signal(float)  # クリック位置（0.0-1.0）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.waveform_data: Optional[np.ndarray] = None
        self.duration_ms: int = 0
        self.position_ms: int = 0
        self.chapters: List[ChapterInfo] = []

        self.setMinimumHeight(80)
        self.setMaximumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background-color: #1a1a1a;")

    def set_waveform(self, data: np.ndarray, duration_ms: int):
        """波形データを設定"""
        self.waveform_data = data
        self.duration_ms = duration_ms
        self.update()

    def set_position(self, position_ms: int):
        """再生位置を設定"""
        self.position_ms = position_ms
        self.update()

    def set_chapters(self, chapters: List['ChapterInfo']):
        """チャプター情報を設定"""
        self.chapters = chapters
        self.update()

    def clear(self):
        """波形をクリア"""
        self.waveform_data = None
        self.duration_ms = 0
        self.position_ms = 0
        self.chapters = []
        self.update()

    def _downsample_preserve_peaks(self, data: np.ndarray, target_width: int) -> List[Tuple[float, float]]:
        """
        ピークを保持しながら波形データを間引く

        各ピクセルに対応するサンプル区間の最小値と最大値を返す。
        これにより、画面解像度が低くても波形のピークが失われない。

        Args:
            data: 元の波形データ
            target_width: 表示幅（ピクセル数）

        Returns:
            List of (min_value, max_value) for each pixel
        """
        if not HAS_NUMPY or len(data) == 0:
            return []

        num_samples = len(data)
        result = []

        if num_samples <= target_width:
            # サンプル数が表示幅より少ない場合はそのまま使用
            for i in range(num_samples):
                val = data[i]
                result.append((val, val))
            # 残りを0で埋める
            for _ in range(target_width - num_samples):
                result.append((0.0, 0.0))
        else:
            # 各ピクセルに対応する区間の最小値・最大値を取得
            samples_per_pixel = num_samples / target_width

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

        return result

    def _get_excluded_regions(self) -> List[Tuple[int, int]]:
        """除外チャプター（--で始まる）の区間を取得

        Returns:
            List of (start_ms, end_ms) tuples for excluded regions
        """
        if not self.chapters or self.duration_ms <= 0:
            return []

        excluded_regions = []
        sorted_chapters = sorted(self.chapters, key=lambda c: c.time_ms)

        for i, ch in enumerate(sorted_chapters):
            if ch.title.startswith("--"):
                start_ms = ch.time_ms
                # 次のチャプターの開始時間、またはメディアの終端
                if i + 1 < len(sorted_chapters):
                    end_ms = sorted_chapters[i + 1].time_ms
                else:
                    end_ms = self.duration_ms
                excluded_regions.append((start_ms, end_ms))

        return excluded_regions

    def paintEvent(self, event):
        """描画イベント"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        center_y = height // 2

        # 背景
        painter.fillRect(0, 0, width, height, QColor(26, 26, 26))

        if self.waveform_data is not None and len(self.waveform_data) > 0 and HAS_NUMPY:
            num_samples = len(self.waveform_data)

            # ピークを保持した間引き処理
            # 各ピクセルに対応するサンプル区間の最大値・最小値を使用
            display_data = self._downsample_preserve_peaks(self.waveform_data, width)

            # 波形の色
            painter.setPen(QColor(76, 175, 80))  # 緑色

            for x in range(len(display_data)):
                min_val, max_val = display_data[x]
                # 上下対称に描画（絶対値の最大を使用）
                peak = max(abs(min_val), abs(max_val))
                bar_height = int(peak * (height - 10) / 2)
                painter.drawLine(x, center_y - bar_height, x, center_y + bar_height)

        # 除外区間のハッチング描画
        if self.duration_ms > 0:
            excluded_regions = self._get_excluded_regions()
            for start_ms, end_ms in excluded_regions:
                start_x = int(start_ms * width / self.duration_ms)
                end_x = int(end_ms * width / self.duration_ms)
                region_width = end_x - start_x

                # 半透明の赤い背景
                painter.fillRect(start_x, 0, region_width, height, QColor(255, 0, 0, 40))

                # 斜線ハッチングパターン
                painter.setPen(QColor(255, 100, 100, 120))
                spacing = 8  # 斜線の間隔
                for offset in range(-height, region_width + height, spacing):
                    x1 = start_x + offset
                    y1 = 0
                    x2 = start_x + offset + height
                    y2 = height

                    # クリッピング
                    if x1 < start_x:
                        y1 = start_x - x1
                        x1 = start_x
                    if x2 > end_x:
                        y2 = height - (x2 - end_x)
                        x2 = end_x

                    if x1 < end_x and x2 > start_x:
                        painter.drawLine(x1, y1, x2, y2)

        # チャプターマーカーを描画
        if self.duration_ms > 0:
            painter.setPen(QColor(255, 193, 7))  # 黄色
            for ch in self.chapters:
                x = int(ch.time_ms * width / self.duration_ms)
                painter.drawLine(x, 0, x, height)

        # 再生位置インジケータ
        if self.duration_ms > 0:
            pos_x = int(self.position_ms * width / self.duration_ms)
            painter.setPen(QColor(244, 67, 54))  # 赤色
            painter.drawLine(pos_x, 0, pos_x, height)

        painter.end()

    def mousePressEvent(self, event):
        """クリックで再生位置を変更"""
        if self.duration_ms > 0:
            ratio = event.position().x() / self.width()
            ratio = max(0.0, min(1.0, ratio))
            self.clicked.emit(ratio)

    @staticmethod
    def extract_waveform(media_path: str, num_samples: int = 5000) -> Optional[np.ndarray]:
        """メディアファイルから波形データを抽出（高速版）"""
        if not HAS_NUMPY:
            return None

        try:
            # FFmpegからパイプで直接読み込み（ディスクI/O回避）
            process = subprocess.Popen([
                'ffmpeg', '-i', media_path,
                '-ac', '1',        # モノラル
                '-ar', '4000',     # 4kHz（高速化）
                '-f', 's16le',     # 生のPCMデータ
                '-acodec', 'pcm_s16le',
                '-v', 'quiet',     # 出力抑制
                '-'
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

            raw_data, _ = process.communicate()

            if not raw_data:
                return None

            # バイトデータをnumpy配列に変換
            samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)

            # パーセンタイルベースの正規化（極端なスパイクを無視）
            abs_samples = np.abs(samples)
            # 98パーセンタイル値で正規化（上位2%のスパイクを無視）
            percentile_val = np.percentile(abs_samples, 98)
            if percentile_val > 0:
                samples = samples / percentile_val
                # ソフトクリッピング（1.0を超えた部分を滑らかに圧縮）
                samples = np.tanh(samples)

            # リサンプル
            if len(samples) > num_samples:
                indices = np.linspace(0, len(samples) - 1, num_samples, dtype=int)
                samples = samples[indices]

            return samples

        except Exception as e:
            print(f"[Waveform] Error extracting waveform: {e}")
            return None


class WaveformWorker(QThread):
    """波形抽出をバックグラウンドで実行するワーカー"""
    finished = Signal(object)  # 波形データ or None

    def __init__(self, media_path: str, parent=None):
        super().__init__(parent)
        self.media_path = media_path

    def run(self):
        """バックグラウンドで波形抽出"""
        waveform = WaveformWidget.extract_waveform(self.media_path)
        self.finished.emit(waveform)


# ==============================================================================
# カバー画像クロップウィジェット
# ==============================================================================

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
        """スプリットビュープレビューを描画（左: オリジナル、右: JPEG圧縮後）"""
        # 1280x720を中央に配置（ウィジェットに収まるようスケール）
        preview_x = (self.width() - self.OUTPUT_WIDTH) / 2
        preview_y = (self.height() - self.OUTPUT_HEIGHT) / 2

        scale = 1.0
        if self.width() < self.OUTPUT_WIDTH + 20 or self.height() < self.OUTPUT_HEIGHT + 20:
            scale_x = (self.width() - 20) / self.OUTPUT_WIDTH
            scale_y = (self.height() - 20) / self.OUTPUT_HEIGHT
            scale = min(scale_x, scale_y)
            display_w = int(self.OUTPUT_WIDTH * scale)
            display_h = int(self.OUTPUT_HEIGHT * scale)
            preview_x = (self.width() - display_w) / 2
            preview_y = (self.height() - display_h) / 2
        else:
            display_w = self.OUTPUT_WIDTH
            display_h = self.OUTPUT_HEIGHT

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

        # 解像度情報
        info_rect = QRectF(preview_x, preview_y + display_h + 5, display_w, 20)
        painter.setPen(QColor(180, 180, 180))
        scale_info = f"1280x720 @ {int(scale * 100)}%" if scale < 1.0 else "1280x720 (1:1)"
        painter.drawText(info_rect, Qt.AlignmentFlag.AlignCenter, scale_info)

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


# ==============================================================================
# データモデル
# ==============================================================================

@dataclass
class ChapterInfo:
    """チャプター情報"""
    time_ms: int  # ミリ秒
    title: str

    @property
    def time_str(self) -> str:
        """HH:MM:SS.mmm形式"""
        total_sec = self.time_ms // 1000
        ms = self.time_ms % 1000
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        s = total_sec % 60
        return f"{h}:{m:02d}:{s:02d}.{ms:03d}"

    @property
    def time_str_youtube(self) -> str:
        """YouTube用 HH:MM:SS形式（ミリ秒なし）"""
        total_sec = self.time_ms // 1000
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        s = total_sec % 60
        return f"{h}:{m:02d}:{s:02d}"

    @classmethod
    def from_time_str(cls, time_str: str, title: str) -> "ChapterInfo":
        """時間文字列からChapterInfoを生成"""
        parts = time_str.replace('.', ':').split(':')
        if len(parts) == 4:
            h, m, s, ms = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        elif len(parts) == 3:
            h, m, s, ms = 0, int(parts[0]), int(parts[1]), int(parts[2]) if '.' in time_str else 0
            if '.' not in time_str:
                h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                ms = 0
        else:
            h, m, s, ms = 0, 0, 0, 0
        time_ms = ((h * 3600) + (m * 60) + s) * 1000 + ms
        return cls(time_ms=time_ms, title=title)


@dataclass
class ProjectState:
    """プロジェクト状態"""
    # 入力ファイル
    source_files: List[str] = field(default_factory=list)
    merged_audio: str = ""
    cover_image: str = ""

    # チャプター
    chapters: List[ChapterInfo] = field(default_factory=list)

    # カット情報
    cut_points: List[Tuple[int, int]] = field(default_factory=list)  # (start_ms, end_ms)

    # 出力設定
    output_name: str = ""
    output_dir: str = ""


# ==============================================================================
# タブ1: MP3結合
# ==============================================================================

class MergeWorker(QThread):
    """音声ファイル結合の準備処理を行うワーカースレッド"""
    log_message = Signal(str)
    progress_update = Signal(str, float)  # (title, duration_sec)
    preparation_done = Signal(list, int, str, str)  # (chapters, total_ms, temp_audio, concat_file)
    error_occurred = Signal(str)

    def __init__(self, ordered_files: List[str], parent=None):
        super().__init__(parent)
        self.ordered_files = ordered_files
        self.chapters: List[ChapterInfo] = []
        self.total_duration_ms = 0

    def _detect_encoding_strategy(self) -> tuple:
        """入力ファイルの形式を判定し、エンコード戦略を決定

        Returns:
            (temp_file_path, codec_args, strategy_description)
        """
        extensions = {Path(f).suffix.lower() for f in self.ordered_files}
        temp_dir = tempfile.gettempdir()

        if extensions == {'.mp3'}:
            # MP3のみ → ストリームコピー（劣化なし）
            return (os.path.join(temp_dir, "merged_temp.mp3"), ['-c', 'copy'], "MP3のみ → ストリームコピー")
        elif extensions == {'.m4a'}:
            # M4Aのみ → ストリームコピー（劣化なし）
            return (os.path.join(temp_dir, "merged_temp.m4a"), ['-c', 'copy'], "M4Aのみ → ストリームコピー")
        elif extensions == {'.aac'}:
            # AACのみ → ストリームコピー（劣化なし）
            return (os.path.join(temp_dir, "merged_temp.aac"), ['-c', 'copy'], "AACのみ → ストリームコピー")
        else:
            # 混在またはWAV/FLAC → AACに再エンコード
            ext_str = ', '.join(sorted(extensions))
            return (os.path.join(temp_dir, "merged_temp.m4a"), ['-c:a', 'aac', '-b:a', '192k'],
                    f"形式混在({ext_str}) → AAC再エンコード")

    def run(self):
        """バックグラウンドで準備処理を実行"""
        try:
            # チャプター情報を生成
            current_time_ms = 0
            for f in self.ordered_files:
                title = Path(f).stem
                self.chapters.append(ChapterInfo(time_ms=current_time_ms, title=title))
                # ffprobeで長さを取得
                try:
                    result = subprocess.run(
                        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                         '-of', 'default=noprint_wrappers=1:nokey=1', f],
                        capture_output=True, text=True
                    )
                    duration_sec = float(result.stdout.strip())
                    current_time_ms += int(duration_sec * 1000)
                    self.progress_update.emit(title, duration_sec)
                except Exception as e:
                    self.log_message.emit(f"  エラー: {title} - {e}")

            self.total_duration_ms = current_time_ms

            # エンコード戦略を決定
            temp_audio, codec_args, strategy_desc = self._detect_encoding_strategy()
            concat_file = os.path.join(tempfile.gettempdir(), "concat_list.txt")

            with open(concat_file, 'w') as f:
                for path in self.ordered_files:
                    escaped_path = path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            self.log_message.emit(f"結合方式: {strategy_desc}")
            self.log_message.emit("音声ファイルを結合中...")
            concat_cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                          '-i', concat_file] + codec_args + [temp_audio]
            self.log_message.emit(f"コマンド: {' '.join(concat_cmd)}")

            result = subprocess.run(concat_cmd, capture_output=True, text=True)
            if result.stdout:
                self.log_message.emit(f"[stdout]\n{result.stdout}")
            if result.stderr:
                self.log_message.emit(f"[stderr]\n{result.stderr}")
            if result.returncode != 0:
                self.error_occurred.emit(f"ffmpeg終了コード {result.returncode}")
                return

            # 準備完了を通知
            self.preparation_done.emit(self.chapters, self.total_duration_ms, temp_audio, concat_file)

        except Exception as e:
            self.error_occurred.emit(str(e))


class ExportWorker(QThread):
    """動画書出ワーカー"""
    progress_update = Signal(str)  # 進捗メッセージ
    progress_percent = Signal(int, str)  # 進捗率(0-100), 時間文字列
    export_completed = Signal(str)  # 出力ファイルパス
    error_occurred = Signal(str)

    # チャプタータイトル表示設定（動画高さに対する割合）
    # 1080p で約58px相当 (1080 * 0.054 ≈ 58)
    FONT_SIZE_RATIO = 0.054

    # 除外チャプターのプレフィックス
    EXCLUDE_PREFIX = "--"

    def __init__(self, input_file: str, output_file: str,
                 chapters: List[ChapterInfo] = None,
                 embed_chapters: bool = True,
                 embed_title: bool = True,
                 overlay_chapter_titles: bool = False,
                 total_duration_ms: int = 0,
                 encoder_id: str = "libx264",
                 bitrate_kbps: int = 4000,
                 crf: int = 23,
                 colorspace: Optional[ColorspaceInfo] = None,
                 parent=None):
        super().__init__(parent)
        self.input_file = input_file
        self.output_file = output_file
        self.chapters = chapters or []
        self.embed_chapters = embed_chapters
        self.embed_title = embed_title
        self.overlay_chapter_titles = overlay_chapter_titles
        self.total_duration_ms = total_duration_ms
        self.encoder_id = encoder_id
        self.bitrate_kbps = bitrate_kbps
        self.crf = crf
        self.colorspace = colorspace or ColorspaceInfo()
        self._temp_files: List[str] = []  # 一時ファイル管理
        self.font_path = detect_system_font()  # プラットフォーム別フォント
        self._cancelled = False  # キャンセルフラグ
        self._process: Optional[subprocess.Popen] = None  # ffmpegプロセス

        # 除外チャプターの処理
        self._excluded_segments: List[Tuple[int, int]] = []  # (start_ms, end_ms)
        self._keep_segments: List[Tuple[int, int]] = []  # (start_ms, end_ms)
        self._adjusted_chapters: List[ChapterInfo] = []  # 時間調整後のチャプター
        self._adjusted_duration_ms: int = 0  # 調整後の動画長
        self._process_excluded_chapters()

    def cancel(self):
        """エクスポートをキャンセル"""
        self._cancelled = True
        # プロセスが動作中なら強制終了
        if self._process and self._process.poll() is None:
            self._process.kill()

    def _process_excluded_chapters(self):
        """除外チャプター（--で始まる）を処理し、保持区間と調整後チャプターを計算"""
        if not self.chapters:
            return

        # 1. 除外区間を特定
        self._excluded_segments = []
        for i, ch in enumerate(self.chapters):
            if ch.title.startswith(self.EXCLUDE_PREFIX):
                start_ms = ch.time_ms
                # 次のチャプターの開始時間、または動画終了時間
                if i + 1 < len(self.chapters):
                    end_ms = self.chapters[i + 1].time_ms
                else:
                    end_ms = self.total_duration_ms
                self._excluded_segments.append((start_ms, end_ms))

        # 除外区間がない場合は通常処理
        if not self._excluded_segments:
            self._keep_segments = [(0, self.total_duration_ms)]
            self._adjusted_chapters = self.chapters.copy()
            self._adjusted_duration_ms = self.total_duration_ms
            return

        # 2. 保持区間を計算（除外区間の補集合）
        self._keep_segments = []
        current_pos = 0
        for start_ms, end_ms in sorted(self._excluded_segments):
            if current_pos < start_ms:
                self._keep_segments.append((current_pos, start_ms))
            current_pos = end_ms
        # 最後の保持区間
        if current_pos < self.total_duration_ms:
            self._keep_segments.append((current_pos, self.total_duration_ms))

        # 3. 調整後のチャプター時間を計算
        self._adjusted_chapters = []
        total_cut_before = 0  # これまでにカットした累計時間

        for ch in self.chapters:
            # "--"で始まるチャプターは除外
            if ch.title.startswith(self.EXCLUDE_PREFIX):
                continue

            # このチャプターより前にカットされた時間を計算
            cut_before_this = 0
            for ex_start, ex_end in self._excluded_segments:
                if ex_end <= ch.time_ms:
                    # 完全にこのチャプターより前の除外区間
                    cut_before_this += (ex_end - ex_start)
                elif ex_start < ch.time_ms:
                    # 部分的に重なる（通常はないはず）
                    cut_before_this += (ch.time_ms - ex_start)

            adjusted_time_ms = ch.time_ms - cut_before_this
            self._adjusted_chapters.append(ChapterInfo(
                time_ms=adjusted_time_ms,
                title=ch.title
            ))

        # 4. 調整後の動画長を計算
        self._adjusted_duration_ms = sum(end - start for start, end in self._keep_segments)

    def _has_excluded_segments(self) -> bool:
        """除外区間があるかどうか"""
        return len(self._excluded_segments) > 0

    def _create_trim_concat_filter(self) -> Tuple[str, str]:
        """
        除外区間をカットして結合するffmpegフィルターを生成

        Returns:
            (video_filter, audio_filter) のタプル
        """
        if not self._keep_segments:
            return "", ""

        video_parts = []
        audio_parts = []
        video_labels = []
        audio_labels = []

        for i, (start_ms, end_ms) in enumerate(self._keep_segments):
            start_sec = start_ms / 1000.0
            end_sec = end_ms / 1000.0

            # 映像のtrimフィルター
            video_parts.append(
                f"[0:v]trim=start={start_sec:.3f}:end={end_sec:.3f},setpts=PTS-STARTPTS[v{i}]"
            )
            video_labels.append(f"[v{i}]")

            # 音声のatrimフィルター
            audio_parts.append(
                f"[0:a]atrim=start={start_sec:.3f}:end={end_sec:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
            audio_labels.append(f"[a{i}]")

        n = len(self._keep_segments)

        # 映像のconcat
        video_filter = ";".join(video_parts)
        video_filter += f";{''.join(video_labels)}concat=n={n}:v=1:a=0[outv]"

        # 音声のconcat
        audio_filter = ";".join(audio_parts)
        audio_filter += f";{''.join(audio_labels)}concat=n={n}:v=0:a=1[outa]"

        # 映像と音声を結合
        full_filter = video_filter + ";" + audio_filter

        return full_filter

    def _create_metadata_file(self) -> str:
        """ffmpeg用メタデータファイルを生成（除外区間がある場合は調整後の時間を使用）"""
        metadata_path = os.path.join(tempfile.gettempdir(), "export_metadata.txt")

        # 除外区間がある場合は調整後のチャプターと動画長を使用
        chapters_to_use = self._adjusted_chapters if self._has_excluded_segments() else self.chapters
        duration_to_use = self._adjusted_duration_ms if self._has_excluded_segments() else self.total_duration_ms

        with open(metadata_path, 'w', encoding='utf-8') as f:
            f.write(";FFMETADATA1\n")

            # タイトルを埋め込む場合
            if self.embed_title:
                title = Path(self.output_file).stem
                f.write(f"title={title}\n")

            # チャプターを埋め込む場合
            if self.embed_chapters and chapters_to_use:
                for i, ch in enumerate(chapters_to_use):
                    # 次のチャプターの開始時間または動画終了時間をENDとする
                    if i + 1 < len(chapters_to_use):
                        end_ms = chapters_to_use[i + 1].time_ms
                    else:
                        end_ms = duration_to_use if duration_to_use > 0 else ch.time_ms + 60000

                    f.write("\n[CHAPTER]\n")
                    f.write("TIMEBASE=1/1000\n")
                    f.write(f"START={ch.time_ms}\n")
                    f.write(f"END={end_ms}\n")
                    f.write(f"title={ch.title}\n")

        return metadata_path

    def _create_chapter_textfiles(self, chapters: List[ChapterInfo] = None) -> List[str]:
        """各チャプターのタイトル用一時ファイルを生成"""
        chapters_to_use = chapters if chapters is not None else self.chapters
        textfiles = []
        for i, ch in enumerate(chapters_to_use):
            tmpfile = os.path.join(tempfile.gettempdir(), f"chapter_title_{i}.txt")
            with open(tmpfile, 'w', encoding='utf-8') as f:
                f.write(ch.title)
            textfiles.append(tmpfile)
            self._temp_files.append(tmpfile)
        return textfiles

    def _create_drawtext_filter(self) -> str:
        """チャプタータイトル表示用のdrawtextフィルターを生成（除外区間がある場合は調整後の時間を使用）"""
        # 除外区間がある場合は調整後のチャプターと動画長を使用
        chapters_to_use = self._adjusted_chapters if self._has_excluded_segments() else self.chapters
        duration_to_use = self._adjusted_duration_ms if self._has_excluded_segments() else self.total_duration_ms

        if not chapters_to_use:
            return ""

        # 各チャプター用のテキストファイルを生成
        textfiles = self._create_chapter_textfiles(chapters_to_use)

        filters = []
        for i, ch in enumerate(chapters_to_use):
            start_sec = ch.time_ms / 1000.0
            # 次のチャプターの開始時間まで、または動画終了まで表示
            if i + 1 < len(chapters_to_use):
                end_sec = chapters_to_use[i + 1].time_ms / 1000.0
            else:
                end_sec = duration_to_use / 1000.0 if duration_to_use > 0 else start_sec + 3600

            # drawtext フィルター（既存スクリプトのスタイルを踏襲）
            # textfile を使用して日本語対応
            # fontsize: 動画高さに対する割合で指定（解像度非依存）
            drawtext = (
                f"drawtext=fontfile='{self.font_path}'"
                f":textfile='{textfiles[i]}'"
                f":fontsize=h*{self.FONT_SIZE_RATIO}"
                f":fontcolor=white"
                f":borderw=2:bordercolor=black"
                f":box=1:boxcolor=black@0.6:boxborderw=15"
                f":x=(w-text_w)/2:y=h*0.325-th/2"
                f":enable='between(t,{start_sec:.3f},{end_sec:.3f})'"
            )
            filters.append(drawtext)

        # パディング追加（偶数サイズ保証）
        filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")

        return ",".join(filters)

    def _cleanup_temp_files(self):
        """一時ファイルを削除"""
        for f in self._temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        self._temp_files.clear()

    def run(self):
        """バックグラウンドで書出処理を実行"""
        try:
            self.progress_update.emit("書出を開始します...")

            # エンコーダ情報を表示
            encoder_name = {
                "h264_videotoolbox": "GPU (VideoToolbox)",
                "h264_nvenc": "GPU (NVIDIA NVENC)",
                "h264_qsv": "GPU (Intel QSV)",
                "h264_amf": "GPU (AMD AMF)",
                "h264_vaapi": "GPU (VAAPI)",
                "libx264": "CPU (x264)",
            }.get(self.encoder_id, self.encoder_id)
            self.progress_update.emit(f"エンコーダ: {encoder_name}")

            # 除外区間の情報を表示
            if self._has_excluded_segments():
                excluded_count = len(self._excluded_segments)
                excluded_duration = sum(end - start for start, end in self._excluded_segments)
                self.progress_update.emit(f"除外区間: {excluded_count}件 (計 {excluded_duration // 1000}秒)")
                self.progress_update.emit(f"保持区間: {len(self._keep_segments)}件")

            # メタデータファイルを生成
            metadata_file = None
            if self.embed_chapters or self.embed_title:
                metadata_file = self._create_metadata_file()
                self.progress_update.emit(f"メタデータファイル生成: {metadata_file}")

            # ffmpegコマンドを構築
            cmd = ['ffmpeg', '-y', '-i', self.input_file]

            # メタデータファイルがある場合は追加
            if metadata_file:
                cmd.extend(['-i', metadata_file, '-map_metadata', '1'])

            # 除外区間がある場合は複合フィルターを使用
            has_excluded = self._has_excluded_segments()
            chapters_to_use = self._adjusted_chapters if has_excluded else self.chapters

            if has_excluded:
                # 除外区間をカット＆結合するフィルター
                trim_concat_filter = self._create_trim_concat_filter()

                if self.overlay_chapter_titles and chapters_to_use:
                    # drawtextフィルターを取得（調整後の時間で生成される）
                    drawtext_filter = self._create_drawtext_filter()
                    # trim/concat後の映像にdrawtextを適用
                    # [outv]にdrawtextを適用して[finalv]を出力
                    combined_filter = trim_concat_filter + f";[outv]{drawtext_filter}[finalv]"
                    self.progress_update.emit(f"チャプタータイトル: {len(chapters_to_use)}件を映像に焼き込み")

                    encoder_args = get_encoder_args(self.encoder_id, self.bitrate_kbps, self.crf)
                    colorspace_args = self.colorspace.get_ffmpeg_args()
                    cmd.extend([
                        '-filter_complex', combined_filter,
                        '-map', '[finalv]',
                        '-map', '[outa]',
                    ] + encoder_args + colorspace_args + [
                        '-c:a', 'aac', '-b:a', '192k',
                        '-movflags', '+faststart'
                    ])
                else:
                    # カット＆結合のみ（オーバーレイなし）
                    encoder_args = get_encoder_args(self.encoder_id, self.bitrate_kbps, self.crf)
                    colorspace_args = self.colorspace.get_ffmpeg_args()
                    cmd.extend([
                        '-filter_complex', trim_concat_filter,
                        '-map', '[outv]',
                        '-map', '[outa]',
                    ] + encoder_args + colorspace_args + [
                        '-c:a', 'aac', '-b:a', '192k',
                        '-movflags', '+faststart'
                    ])
            elif self.overlay_chapter_titles and self.chapters:
                # 除外区間なし、オーバーレイあり
                vf = self._create_drawtext_filter()
                self.progress_update.emit(f"チャプタータイトル: {len(self.chapters)}件を映像に焼き込み")

                encoder_args = get_encoder_args(self.encoder_id, self.bitrate_kbps, self.crf)
                colorspace_args = self.colorspace.get_ffmpeg_args()
                cmd.extend([
                    '-vf', vf,
                ] + encoder_args + colorspace_args + [
                    '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart'
                ])
            else:
                # ストリームコピー（再エンコードなし）
                cmd.extend(['-c', 'copy'])

            # チャプターのコピー設定
            if self.embed_chapters and chapters_to_use:
                cmd.extend(['-map_chapters', '1'])

            cmd.append(self.output_file)

            self.progress_update.emit(f"コマンド: {' '.join(cmd[:10])}...")  # 長すぎるので省略
            if has_excluded or self.overlay_chapter_titles:
                self.progress_update.emit("再エンコード中...")
            else:
                self.progress_update.emit("ffmpeg実行中...")

            # ffmpegを実行（リアルタイム進捗取得）
            import re
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            # stderrから進捗を読み取る（調整後の動画長を使用）
            stderr_output = []
            duration_for_progress = self._adjusted_duration_ms if has_excluded else self.total_duration_ms
            total_sec = duration_for_progress / 1000.0 if duration_for_progress > 0 else 0

            while True:
                # キャンセルチェック
                if self._cancelled:
                    self._process.kill()
                    self._process.wait()
                    self._cleanup_temp_files()
                    # 出力途中のファイルを削除
                    if os.path.exists(self.output_file):
                        os.remove(self.output_file)
                    self.error_occurred.emit("エクスポートを中止しました")
                    return

                line = self._process.stderr.readline()
                if not line and self._process.poll() is not None:
                    break
                if line:
                    stderr_output.append(line)
                    # time=HH:MM:SS.xx を抽出
                    match = re.search(r'time=(\d+):(\d+):(\d+)\.(\d+)', line)
                    if match and total_sec > 0:
                        h, m, s, cs = map(int, match.groups())
                        current_sec = h * 3600 + m * 60 + s + cs / 100.0
                        percent = min(int(current_sec / total_sec * 100), 99)
                        time_str = f"{h}:{m:02d}:{s:02d}"
                        self.progress_percent.emit(percent, time_str)

            returncode = self._process.wait()
            self._process = None

            # 一時ファイルをクリーンアップ
            self._cleanup_temp_files()

            if returncode != 0:
                error_text = ''.join(stderr_output[-20:])  # 最後の20行
                self.error_occurred.emit(f"ffmpegエラー (コード {returncode}):\n{error_text[-500:]}")
                return

            # 出力ファイルの確認
            if os.path.exists(self.output_file):
                file_size = os.path.getsize(self.output_file)
                size_mb = file_size / (1024 * 1024)
                self.progress_percent.emit(100, "完了")
                self.progress_update.emit(f"書出完了: {size_mb:.1f} MB")

                # チャプターファイルを保存（調整後の時間を使用）
                chapters_to_save = self._adjusted_chapters if self._has_excluded_segments() else self.chapters
                if chapters_to_save:
                    chapter_file_path = Path(self.output_file).with_suffix('.chapters')
                    with open(chapter_file_path, 'w', encoding='utf-8') as f:
                        for ch in chapters_to_save:
                            f.write(f"{ch.time_str} {ch.title}\n")
                    self.progress_update.emit(f"チャプター保存: {chapter_file_path.name}")

                self.export_completed.emit(self.output_file)
            else:
                self.error_occurred.emit("出力ファイルが生成されませんでした")

        except Exception as e:
            self.error_occurred.emit(f"エラー: {str(e)}")


class MergeTab(QWidget):
    """MP3結合タブ"""
    merge_completed = Signal(str, list, str)  # (merged_file, chapters, cover_image)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.files: List[str] = []
        self.cover_image: str = ""
        # ワーカースレッド
        self.merge_worker: Optional[MergeWorker] = None
        # エンコード状態管理
        self.encode_process: Optional[QProcess] = None
        self.encode_output_file: str = ""
        self.encode_temp_audio: str = ""
        self.encode_temp_cover: Optional[str] = None
        self.encode_chapters: List = []
        self.encode_chapter_file: str = ""
        self.encode_total_duration_ms: int = 0
        # 出力設定（ワーカー完了時に使用）
        self._pending_output_dir: Optional[Path] = None
        self._pending_output_name: str = ""
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(12)

        # ========== 左側: ファイル一覧・設定 ==========
        left_widget = QWidget()
        left_widget.setFixedWidth(440)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # ファイルリスト
        list_label = QLabel("MP3ファイル一覧（ドラッグで並べ替え）")
        list_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        left_layout.addWidget(list_label)

        self.file_list = QListWidget()
        self.file_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        left_layout.addWidget(self.file_list, stretch=1)

        # MP3ファイル操作ボタン
        mp3_btn_layout = QHBoxLayout()
        mp3_btn_layout.setSpacing(8)

        add_btn = QPushButton("追加")
        add_btn.setStyleSheet(Theme.button_secondary())
        add_btn.setToolTip("MP3ファイルを追加")
        add_btn.clicked.connect(self.add_files)
        mp3_btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("削除")
        remove_btn.setStyleSheet(Theme.button_secondary())
        remove_btn.setToolTip("選択したファイルを削除")
        remove_btn.clicked.connect(self.remove_selected)
        mp3_btn_layout.addWidget(remove_btn)

        clear_btn = QPushButton("全削除")
        clear_btn.setStyleSheet(Theme.button_secondary())
        clear_btn.setToolTip("すべてのファイルを削除")
        clear_btn.clicked.connect(self.clear_files)
        mp3_btn_layout.addWidget(clear_btn)

        mp3_btn_layout.addStretch()
        left_layout.addLayout(mp3_btn_layout)

        # 出力設定
        settings_group = QWidget()
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setContentsMargins(0, 8, 0, 8)
        settings_layout.setSpacing(8)

        # 出力ファイル名
        output_layout = QHBoxLayout()
        output_label = QLabel("出力名:")
        output_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        output_label.setFixedWidth(60)
        output_layout.addWidget(output_label)
        self.output_name = QLineEdit()
        self.output_name.setPlaceholderText("merged_audio")
        self.output_name.setStyleSheet(Theme.input_style())
        output_layout.addWidget(self.output_name)
        settings_layout.addLayout(output_layout)

        # 出力先ディレクトリ
        dir_layout = QHBoxLayout()
        dir_label = QLabel("出力先:")
        dir_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        dir_label.setFixedWidth(60)
        dir_layout.addWidget(dir_label)
        self.output_dir = QLineEdit()
        self.output_dir.setPlaceholderText("（最初のファイルと同じ場所）")
        self.output_dir.setReadOnly(True)
        self.output_dir.setStyleSheet(f"background: {Theme.BG_DARK}; color: {Theme.TEXT_MUTED}; border: 1px solid {Theme.BORDER}; border-radius: {Theme.RADIUS_SM}; padding: 8px;")
        dir_layout.addWidget(self.output_dir)
        dir_btn = QPushButton("...")
        dir_btn.setFixedWidth(40)
        dir_btn.setStyleSheet(Theme.button_secondary())
        dir_btn.setToolTip("出力先を変更")
        dir_btn.clicked.connect(self._select_output_dir)
        dir_layout.addWidget(dir_btn)
        settings_layout.addLayout(dir_layout)

        left_layout.addWidget(settings_group)

        # ログ
        log_label = QLabel("ログ")
        log_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        left_layout.addWidget(log_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(100)
        self.log.setStyleSheet(f"background: {Theme.BG_DARK}; border: 1px solid {Theme.BORDER}; border-radius: {Theme.RADIUS_SM}; padding: 8px;")
        left_layout.addWidget(self.log)

        # ========== ボタン群（ログの下）==========
        action_btn_layout = QHBoxLayout()
        action_btn_layout.setSpacing(10)
        action_btn_layout.addStretch()

        # 結合実行（メインアクション）
        self.merge_btn = QPushButton("結合実行")
        self.merge_btn.setStyleSheet(Theme.button_primary())
        self.merge_btn.setMinimumWidth(120)
        self.merge_btn.setToolTip("MP3を結合してMP4を作成")
        self.merge_btn.clicked.connect(self.execute_merge)
        action_btn_layout.addWidget(self.merge_btn)

        # キャンセルボタン（エンコード中のみ表示）
        self.cancel_btn = QPushButton("中止")
        self.cancel_btn.setStyleSheet(Theme.button_danger())
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.setToolTip("エンコードを中止")
        self.cancel_btn.clicked.connect(self.cancel_encoding)
        self.cancel_btn.hide()  # 初期状態は非表示
        action_btn_layout.addWidget(self.cancel_btn)

        left_layout.addLayout(action_btn_layout)

        layout.addWidget(left_widget)

        # ========== 右側: カバー画像クロップ ==========
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # カバー画像ヘッダー
        cover_header = QHBoxLayout()
        cover_title = QLabel("カバー画像")
        cover_title.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        cover_header.addWidget(cover_title)

        self.cover_label = QLabel("未選択")
        self.cover_label.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        cover_header.addWidget(self.cover_label)
        cover_header.addStretch()
        right_layout.addLayout(cover_header)

        # クロップウィジェット
        self.crop_widget = ImageCropWidget()
        self.crop_widget.compressionChanged.connect(self._on_compression_changed)
        right_layout.addWidget(self.crop_widget, stretch=1)

        # カバー画像操作ボタン（クロップウィジェットの下）
        cover_btn_layout = QHBoxLayout()
        cover_btn_layout.setSpacing(8)

        # トグルボタン用スタイル
        toggle_btn_style = f"""
            QPushButton {{
                background: {Theme.BG_ELEVATED};
                color: {Theme.TEXT_SECONDARY};
                border: 1px solid {Theme.BORDER};
                border-radius: {Theme.RADIUS};
                padding: 10px 20px;
            }}
            QPushButton:hover {{ background: {Theme.BG_HOVER}; }}
            QPushButton:checked {{
                background: {Theme.SUCCESS};
                color: white;
                border-color: {Theme.SUCCESS};
            }}
            QPushButton:checked:hover {{ background: #34d399; }}
        """

        btn_width = 110

        self.cover_select_btn = QPushButton("選択")
        self.cover_select_btn.setStyleSheet(Theme.button_secondary())
        self.cover_select_btn.setFixedWidth(btn_width)
        self.cover_select_btn.setToolTip("ファイルからカバー画像を選択")
        self.cover_select_btn.clicked.connect(self.select_cover)
        cover_btn_layout.addWidget(self.cover_select_btn)

        self.cover_paste_btn = QPushButton("貼り付け")
        self.cover_paste_btn.setStyleSheet(Theme.button_secondary())
        self.cover_paste_btn.setFixedWidth(btn_width)
        self.cover_paste_btn.setToolTip("クリップボードから画像を貼り付け (Cmd+V)")
        self.cover_paste_btn.clicked.connect(self.paste_cover_from_clipboard)
        cover_btn_layout.addWidget(self.cover_paste_btn)

        self.preview_btn = QPushButton("プレビュー")
        self.preview_btn.setStyleSheet(toggle_btn_style)
        self.preview_btn.setFixedWidth(btn_width)
        self.preview_btn.setCheckable(True)
        self.preview_btn.setToolTip("圧縮プレビュー表示 (左: 元画像 / 右: 圧縮後)")
        self.preview_btn.toggled.connect(self._on_preview_toggled)
        cover_btn_layout.addWidget(self.preview_btn)

        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(Theme.button_secondary())
        save_btn.setFixedWidth(btn_width)
        save_btn.setToolTip("クロップした画像を保存")
        save_btn.clicked.connect(self._save_cover)
        cover_btn_layout.addWidget(save_btn)

        cover_btn_layout.addStretch()
        right_layout.addLayout(cover_btn_layout)

        # コントロール
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(10)

        # 回転
        rotate_label = QLabel("回転:")
        rotate_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        ctrl_layout.addWidget(rotate_label)
        self.rotation_slider = QSlider(Qt.Orientation.Horizontal)
        self.rotation_slider.setRange(0, 359)
        self.rotation_slider.setFixedWidth(80)
        self.rotation_slider.valueChanged.connect(self._on_rotation_changed)
        ctrl_layout.addWidget(self.rotation_slider)

        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(0, 359)
        self.rotation_spin.setSuffix("°")
        self.rotation_spin.setFixedWidth(65)
        self.rotation_spin.valueChanged.connect(self._on_rotation_spin_changed)
        ctrl_layout.addWidget(self.rotation_spin)

        # 回転ボタン（小型）
        small_btn_style = f"""
            QPushButton {{
                background: {Theme.BG_ELEVATED};
                color: {Theme.TEXT_SECONDARY};
                border: 1px solid {Theme.BORDER};
                border-radius: {Theme.RADIUS_SM};
                padding: 6px 10px;
            }}
            QPushButton:hover {{ background: {Theme.BG_HOVER}; }}
        """
        btn_90cw = QPushButton("+90")
        btn_90cw.setFixedWidth(50)
        btn_90cw.setStyleSheet(small_btn_style)
        btn_90cw.clicked.connect(lambda: self._rotate_by(90))
        ctrl_layout.addWidget(btn_90cw)

        btn_90ccw = QPushButton("-90")
        btn_90ccw.setFixedWidth(50)
        btn_90ccw.setStyleSheet(small_btn_style)
        btn_90ccw.clicked.connect(lambda: self._rotate_by(-90))
        ctrl_layout.addWidget(btn_90ccw)

        ctrl_layout.addSpacing(16)

        # 品質
        quality_label = QLabel("品質:")
        quality_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        ctrl_layout.addWidget(quality_label)
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(85)
        self.quality_slider.setFixedWidth(80)
        self.quality_slider.valueChanged.connect(self._on_quality_changed)
        ctrl_layout.addWidget(self.quality_slider)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(85)
        self.quality_spin.setSuffix("%")
        self.quality_spin.setFixedWidth(65)
        self.quality_spin.valueChanged.connect(self._on_quality_spin_changed)
        ctrl_layout.addWidget(self.quality_spin)

        ctrl_layout.addStretch()

        # サイズ表示
        self.size_label = QLabel("--")
        self.size_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        ctrl_layout.addWidget(self.size_label)

        right_layout.addLayout(ctrl_layout)

        layout.addWidget(right_widget, stretch=1)

    def add_files(self):
        files, _ = CenteredFileDialog.getOpenFileNames(
            self, "MP3ファイルを選択", "",
            "Audio Files (*.mp3 *.m4a *.wav *.flac)"
        )
        for f in files:
            if f not in self.files:
                self.files.append(f)
                item = QListWidgetItem(Path(f).name)
                item.setData(Qt.ItemDataRole.UserRole, f)
                self.file_list.addItem(item)
                # 最初のファイル追加時に出力先を設定
                if len(self.files) == 1:
                    self.output_dir.setText(str(Path(f).parent))

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            if path in self.files:
                self.files.remove(path)
            self.file_list.takeItem(self.file_list.row(item))

    def clear_files(self):
        self.files.clear()
        self.file_list.clear()
        self.output_dir.clear()

    def _select_output_dir(self):
        """出力先ディレクトリを選択"""
        current = self.output_dir.text() or str(Path.home())
        dir_path = CenteredFileDialog.getExistingDirectory(
            self, "出力先を選択", current
        )
        if dir_path:
            self.output_dir.setText(dir_path)

    def select_cover(self):
        file_path, _ = CenteredFileDialog.getOpenFileName(
            self, "カバー画像を選択", "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_path:
            if self.crop_widget.load_image(file_path):
                self.cover_label.setText(Path(file_path).name)
                self.rotation_slider.setValue(0)
                self.rotation_spin.setValue(0)

    def paste_cover_from_clipboard(self):
        """クリップボードから画像を貼り付け"""
        clipboard = QApplication.clipboard()
        image = clipboard.image()
        if not image.isNull():
            if self.crop_widget.load_image_from_qimage(image):
                self.cover_label.setText("クリップボードから貼り付け")
                self.rotation_slider.setValue(0)
                self.rotation_spin.setValue(0)
                self.log.appendPlainText("カバー画像: クリップボードから貼り付け")
                return True
        return False

    def keyPressEvent(self, event):
        """キーボードイベント処理"""
        # Cmd+V (macOS) / Ctrl+V (Windows) でクリップボードから画像貼り付け
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.paste_cover_from_clipboard():
                event.accept()
                return
        super().keyPressEvent(event)

    def _on_rotation_changed(self, value):
        self.rotation_spin.blockSignals(True)
        self.rotation_spin.setValue(value)
        self.rotation_spin.blockSignals(False)
        self.crop_widget.set_rotation(value)

    def _on_rotation_spin_changed(self, value):
        self.rotation_slider.blockSignals(True)
        self.rotation_slider.setValue(value)
        self.rotation_slider.blockSignals(False)
        self.crop_widget.set_rotation(value)

    def _rotate_by(self, degrees):
        new_angle = (self.rotation_slider.value() + degrees) % 360
        self.rotation_slider.setValue(new_angle)

    def _on_quality_changed(self, value):
        self.quality_spin.blockSignals(True)
        self.quality_spin.setValue(value)
        self.quality_spin.blockSignals(False)
        self.crop_widget.set_compression_quality(value)

    def _on_quality_spin_changed(self, value):
        self.quality_slider.blockSignals(True)
        self.quality_slider.setValue(value)
        self.quality_slider.blockSignals(False)
        self.crop_widget.set_compression_quality(value)

    def _on_preview_toggled(self, checked):
        """プレビュートグルボタンの状態変更"""
        self.crop_widget.set_compression_preview(checked)

    def _on_compression_changed(self, size_bytes):
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
        self.size_label.setText(size_str)

    def _save_cover(self):
        if self.crop_widget.rotated_image is None:
            QMessageBox.warning(self, "エラー", "画像が選択されていません")
            return

        default_path = str(Path.cwd() / "cover.jpg")
        path, _ = CenteredFileDialog.getSaveFileName(
            self, "カバー画像を保存", default_path, "JPEG Files (*.jpg *.jpeg)"
        )

        if path:
            success, file_size = self.crop_widget.export_cropped_image(path)
            if success:
                self.cover_image = path
                self.cover_label.setText(Path(path).name)
                size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024 * 1024):.2f} MB"
                self.log.appendPlainText(f"カバー画像保存: {path} ({size_str})")
            else:
                QMessageBox.warning(self, "エラー", "画像の保存に失敗しました")

    def execute_merge(self):
        if not self.files:
            QMessageBox.warning(self, "エラー", "ファイルが選択されていません")
            return

        # 出力設定を保存
        self._pending_output_name = self.output_name.text() or "merged_audio"
        output_dir = self.output_dir.text()
        if not output_dir and self.files:
            output_dir = str(Path(self.files[0]).parent)
        self._pending_output_dir = Path(output_dir) if output_dir else Path.cwd()

        # 現在の順序でファイルリストを取得
        ordered_files = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            ordered_files.append(item.data(Qt.ItemDataRole.UserRole))

        self.log.appendPlainText(f"結合開始: {len(ordered_files)} ファイル")
        self.log.appendPlainText(f"出力先: {self._pending_output_dir}")

        # ボタン状態を変更
        self.merge_btn.setEnabled(False)
        self.cancel_btn.show()

        # ワーカースレッドを作成・開始
        self.merge_worker = MergeWorker(ordered_files, self)
        self.merge_worker.log_message.connect(self.log.appendPlainText)
        self.merge_worker.progress_update.connect(self._on_worker_progress)
        self.merge_worker.preparation_done.connect(self._on_preparation_done)
        self.merge_worker.error_occurred.connect(self._on_worker_error)
        self.merge_worker.start()

    def _on_worker_progress(self, title: str, duration_sec: float):
        """ワーカーからの進捗更新"""
        self.log.appendPlainText(f"  {title}: {duration_sec:.2f}秒")

    def _on_worker_error(self, error_msg: str):
        """ワーカーエラー時の処理"""
        self.log.appendPlainText(f"エラー: {error_msg}")
        self.merge_btn.setEnabled(True)
        self.cancel_btn.hide()

    def _on_preparation_done(self, chapters: list, total_duration_ms: int, temp_audio: str, concat_file: str):
        """準備完了時にMP4エンコードを開始"""
        output_file = str(self._pending_output_dir / f"{self._pending_output_name}.mp4")
        self.log.appendPlainText("MP4に変換中...")

        # ビデオフィルター（偶数サイズにパディング）
        vf_pad = "pad=ceil(iw/2)*2:ceil(ih/2)*2"

        # 音声コーデック選択（M4A/AACならコピー、それ以外は再エンコード）
        temp_ext = Path(temp_audio).suffix.lower()
        if temp_ext in ('.m4a', '.aac'):
            audio_codec_args = ['-c:a', 'copy']
            self.log.appendPlainText("音声: ストリームコピー（AAC）")
        else:
            audio_codec_args = ['-c:a', 'aac', '-b:a', '192k']
            self.log.appendPlainText("音声: AAC再エンコード")

        # カバー画像の準備（未保存の場合は一時ファイルに出力）
        cover_to_use = self.cover_image
        temp_cover = None
        if not cover_to_use and self.crop_widget.rotated_image is not None:
            temp_cover = os.path.join(tempfile.gettempdir(), "temp_cover.jpg")
            success, _ = self.crop_widget.export_cropped_image(temp_cover)
            if success:
                cover_to_use = temp_cover
                self.log.appendPlainText("クロップ済みカバー画像を使用")

        if cover_to_use and Path(cover_to_use).exists():
            # カバー画像がある場合（mp3tomp4と同じオプション）
            self.log.appendPlainText(f"カバー画像: {Path(cover_to_use).name}")
            cmd = [
                'ffmpeg', '-y',
                '-loop', '1', '-i', cover_to_use,
                '-i', temp_audio,
                '-c:v', 'libx264', '-preset', 'ultrafast',
                '-tune', 'stillimage', '-crf', '32',
                '-threads', '0',
            ] + audio_codec_args + [
                '-vf', vf_pad,
                '-pix_fmt', 'yuv420p',
                '-shortest', '-movflags', '+faststart',
                output_file
            ]
        else:
            # カバー画像がない場合は黒背景
            self.log.appendPlainText("カバー画像なし（黒背景を使用）")
            cmd = [
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', 'color=c=black:s=1920x1080:r=1',
                '-i', temp_audio,
                '-c:v', 'libx264', '-preset', 'ultrafast',
                '-tune', 'stillimage', '-crf', '32',
                '-threads', '0',
            ] + audio_codec_args + [
                '-vf', vf_pad,
                '-pix_fmt', 'yuv420p',
                '-shortest', '-movflags', '+faststart',
                output_file
            ]

        # コマンド表示
        self.log.appendPlainText(f"コマンド: {' '.join(cmd)}")

        # QProcessでリアルタイム進捗表示
        self.encode_process = QProcess(self)
        self.encode_output_file = output_file
        self.encode_temp_audio = temp_audio
        self.encode_temp_cover = temp_cover
        self.encode_chapters = chapters
        self.encode_chapter_file = str(self._pending_output_dir / f"{self._pending_output_name}.chapters")
        self.encode_total_duration_ms = total_duration_ms

        # シグナル接続
        self.encode_process.readyReadStandardError.connect(self._on_encode_stderr)
        self.encode_process.readyReadStandardOutput.connect(self._on_encode_stdout)
        self.encode_process.finished.connect(self._on_encode_finished)

        # 実行
        self.encode_process.start(cmd[0], cmd[1:])

    def _on_encode_stderr(self):
        """ffmpegのstderr出力を処理（進捗情報含む）"""
        data = self.encode_process.readAllStandardError().data().decode('utf-8', errors='replace')

        # 進捗情報をパース（time=HH:MM:SS.ms形式）
        time_match = re.search(r'time=(\d+):(\d+):(\d+)\.(\d+)', data)
        if time_match:
            h, m, s, ms = map(int, time_match.groups())
            current_ms = h * 3600000 + m * 60000 + s * 1000 + ms * 10
            if self.encode_total_duration_ms > 0:
                progress = min(100, current_ms * 100 / self.encode_total_duration_ms)

                # 追加情報をパース
                fps_match = re.search(r'fps=\s*([\d.]+)', data)
                speed_match = re.search(r'speed=\s*([\d.]+)x', data)
                size_match = re.search(r'size=\s*(\d+)kB', data)

                fps = fps_match.group(1) if fps_match else "-"
                speed = speed_match.group(1) if speed_match else "-"
                size_kb = int(size_match.group(1)) if size_match else 0
                size_str = f"{size_kb/1024:.1f}MB" if size_kb >= 1024 else f"{size_kb}kB"

                progress_text = f"進捗: {progress:.1f}% ({h:02d}:{m:02d}:{s:02d}) | fps:{fps} speed:{speed}x size:{size_str}"

                # 最終行を更新（改行なし）
                cursor = self.log.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                cursor.movePosition(cursor.MoveOperation.StartOfBlock, cursor.MoveMode.KeepAnchor)
                selected = cursor.selectedText()
                if selected.startswith("進捗:"):
                    cursor.removeSelectedText()
                    cursor.insertText(progress_text)
                else:
                    self.log.appendPlainText(progress_text)
                # スクロールを最下部に
                self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        else:
            # 進捗以外のメッセージ（エラーなど）
            for line in data.strip().split('\n'):
                if line and not line.startswith('frame='):
                    self.log.appendPlainText(line)

    def _on_encode_stdout(self):
        """ffmpegのstdout出力を処理"""
        data = self.encode_process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        if data.strip():
            self.log.appendPlainText(data.strip())

    def _on_encode_finished(self, exit_code, exit_status):
        """ffmpegエンコード完了時の処理"""
        self.merge_btn.setEnabled(True)
        self.cancel_btn.hide()

        if exit_code != 0:
            if exit_code == -1:  # キャンセルされた場合
                self.log.appendPlainText("エンコードを中止しました")
            else:
                self.log.appendPlainText(f"エラー: ffmpeg終了コード {exit_code}")
            return

        self.log.appendPlainText(f"結合完了: {self.encode_output_file}")

        # 一時ファイル削除
        Path(self.encode_temp_audio).unlink(missing_ok=True)
        if self.encode_temp_cover:
            Path(self.encode_temp_cover).unlink(missing_ok=True)

        # チャプターファイルも保存
        with open(self.encode_chapter_file, 'w') as f:
            for ch in self.encode_chapters:
                f.write(f"{ch.time_str} {ch.title}\n")
        self.log.appendPlainText(f"チャプター保存: {self.encode_chapter_file}")

        self.merge_completed.emit(self.encode_output_file, self.encode_chapters, self.cover_image)

    def cancel_encoding(self):
        """エンコードを中止"""
        # MergeWorker を停止
        if hasattr(self, 'merge_worker') and self.merge_worker.isRunning():
            self.merge_worker.terminate()
            self.merge_worker.wait()
            self.log.appendPlainText("準備処理を中止しました")

        # QProcess (ffmpeg) を停止
        if self.encode_process and self.encode_process.state() != QProcess.ProcessState.NotRunning:
            self.encode_process.kill()
            self.log.appendPlainText("エンコードを中止しています...")
        else:
            # プロセスが動いていない場合はボタンを戻す
            self.merge_btn.setEnabled(True)
            self.cancel_btn.hide()


# ==============================================================================
# タブ2: 編集
# ==============================================================================

class EditTab(QWidget):
    """編集タブ（カット、チャプター）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.media_file = ""
        self.chapters: List[ChapterInfo] = []
        self.video_controller: Optional[VideoController] = None
        self._pending_waveform: Optional[np.ndarray] = None
        self._waveform_worker: Optional[WaveformWorker] = None
        self._export_worker: Optional[ExportWorker] = None
        self.init_ui()
        self._setup_media_player()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # メインエリア（水平分割）
        main_layout = QHBoxLayout()
        main_layout.setSpacing(12)

        # ========== 左側: 動画プレーヤー ==========
        left_widget = QWidget()
        left_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # ビデオウィジェット（16:9）
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #000;")

        self.video_container = AspectRatioWidget(self.video_widget, aspect_ratio=16/9)
        self.video_container.setMinimumSize(480, 270)
        self.video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.video_container, stretch=1)

        # 波形・コントロール用コンテナ（映像幅に同期）
        self.bottom_container = QWidget()
        bottom_layout = QVBoxLayout(self.bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(4)

        # 波形ウィジェット
        self.waveform_widget = WaveformWidget()
        self.waveform_widget.setMinimumHeight(60)
        self.waveform_widget.setMaximumHeight(80)
        self.waveform_widget.clicked.connect(self._on_waveform_clicked)
        bottom_layout.addWidget(self.waveform_widget)

        # シークバー
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 6px; background: {Theme.BG_DARK}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -5px 0; background: {Theme.ACCENT}; border-radius: 8px; }}
            QSlider::handle:horizontal:hover {{ background: {Theme.ACCENT_HOVER}; }}
            QSlider::sub-page:horizontal {{ background: {Theme.ACCENT_ACTIVE}; border-radius: 3px; }}
        """)
        bottom_layout.addWidget(self.seek_slider)

        # コントロールエリア（ボタン中央、時間/出力は右端固定）
        ctrl_widget = QWidget()
        ctrl_layout = QHBoxLayout(ctrl_widget)
        ctrl_layout.setContentsMargins(0, 4, 0, 0)
        ctrl_layout.setSpacing(0)

        # 左側スペーサー（右側の情報エリアと同じ幅を確保）
        left_spacer = QWidget()
        left_spacer.setFixedWidth(200)
        ctrl_layout.addWidget(left_spacer)

        # 中央：再生ボタン（2行分の高さ）
        btn_container = QHBoxLayout()
        btn_container.setSpacing(8)

        play_ctrl_style = f"""
            QPushButton {{
                background: {Theme.ACCENT};
                color: white;
                border: none;
                border-radius: {Theme.RADIUS};
                padding: 12px 20px;
                font-size: 20px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {Theme.ACCENT_HOVER}; }}
            QPushButton:pressed {{ background: {Theme.ACCENT_ACTIVE}; }}
        """

        for text, delta in [("<<", -10000), ("<", -1000)]:
            btn = QPushButton(text)
            btn.setStyleSheet(play_ctrl_style)
            btn.clicked.connect(lambda checked, d=delta: self.skip(d))
            btn_container.addWidget(btn)

        self.play_btn = QPushButton("Play")
        self.play_btn.setStyleSheet(play_ctrl_style)
        self.play_btn.setFixedWidth(120)
        self.play_btn.clicked.connect(self.toggle_play)
        btn_container.addWidget(self.play_btn)

        for text, delta in [(">", 1000), (">>", 10000)]:
            btn = QPushButton(text)
            btn.setStyleSheet(play_ctrl_style)
            btn.clicked.connect(lambda checked, d=delta: self.skip(d))
            btn_container.addWidget(btn)

        ctrl_layout.addStretch()
        ctrl_layout.addLayout(btn_container)
        ctrl_layout.addStretch()

        # 右側：時間表示と音声出力（2行・右寄せ）
        right_info = QVBoxLayout()
        right_info.setSpacing(6)

        # 時間表示
        time_style = f"""
            font-family: 'Inconsolata', 'Menlo', 'Courier', 'Monaco';
            font-size: 22px;
            color: {Theme.SUCCESS};
        """
        self.time_label = QLabel("0:00:00.000 / 0:00:00.000")
        self.time_label.setStyleSheet(time_style)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        right_info.addWidget(self.time_label)
        self._current_duration = 0

        # 音声出力デバイス（右寄せ）
        audio_row = QHBoxLayout()
        audio_row.setSpacing(8)
        audio_row.addStretch()
        output_label = QLabel("出力:")
        output_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        audio_row.addWidget(output_label)
        self.audio_device_combo = QComboBox()
        self.audio_device_combo.setStyleSheet(f"""
            QComboBox {{
                background: {Theme.BG_ELEVATED};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER};
                border-radius: {Theme.RADIUS_SM};
                padding: 6px 10px;
                min-width: 140px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {Theme.BG_ELEVATED};
                color: {Theme.TEXT_PRIMARY};
                selection-background-color: {Theme.ACCENT};
            }}
        """)
        self._populate_audio_devices()
        self.audio_device_combo.currentIndexChanged.connect(self._on_audio_device_changed)
        audio_row.addWidget(self.audio_device_combo)
        right_info.addLayout(audio_row)

        ctrl_layout.addLayout(right_info)
        bottom_layout.addWidget(ctrl_widget)

        # メディアプレーヤー（後で初期化）
        self.player: Optional[QMediaPlayer] = None
        self.audio_output: Optional[QAudioOutput] = None

        # bottom_containerを中央配置するためのラッパー
        bottom_wrapper = QHBoxLayout()
        bottom_wrapper.setContentsMargins(0, 0, 0, 0)
        bottom_wrapper.addStretch()
        bottom_wrapper.addWidget(self.bottom_container)
        bottom_wrapper.addStretch()
        left_layout.addLayout(bottom_wrapper)

        # 映像幅に波形・コントロールを同期
        self.video_container.innerWidthChanged.connect(self._sync_bottom_width)

        main_layout.addWidget(left_widget, stretch=1)

        # ========== 右側: チャプター & ファイル情報 ==========
        right_widget = QWidget()
        right_widget.setFixedWidth(320)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.setSpacing(10)

        # ファイル情報
        file_label = QLabel("ファイル")
        file_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        right_layout.addWidget(file_label)

        self.media_label = QLabel("未選択")
        self.media_label.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
        self.media_label.setWordWrap(True)
        right_layout.addWidget(self.media_label)

        # チャプターセクション
        chapter_header = QLabel("チャプター")
        chapter_header.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        right_layout.addWidget(chapter_header)

        # チャプターテーブル（Themeのmain_window_styleで設定済み）
        self.chapter_table = QTableWidget()
        self.chapter_table.setColumnCount(2)
        self.chapter_table.setHorizontalHeaderLabels(["時間", "タイトル"])
        self.chapter_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.chapter_table.horizontalHeader().resizeSection(0, 110)
        self.chapter_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.chapter_table.verticalHeader().setVisible(False)
        self.chapter_table.doubleClicked.connect(self.jump_to_chapter)
        self.chapter_table.itemChanged.connect(self._on_chapter_table_changed)
        right_layout.addWidget(self.chapter_table, stretch=1)

        # チャプターボタン
        ch_btn_layout = QHBoxLayout()
        ch_btn_layout.setContentsMargins(0, 0, 0, 0)
        ch_btn_layout.setSpacing(6)

        add_ch_btn = QPushButton("+")
        add_ch_btn.setStyleSheet(Theme.button_secondary())
        add_ch_btn.setToolTip("現在位置にチャプター追加")
        add_ch_btn.clicked.connect(self.add_chapter)
        ch_btn_layout.addWidget(add_ch_btn, stretch=1)

        del_ch_btn = QPushButton("-")
        del_ch_btn.setStyleSheet(Theme.button_secondary())
        del_ch_btn.setToolTip("選択チャプターを削除")
        del_ch_btn.clicked.connect(self.delete_chapter)
        ch_btn_layout.addWidget(del_ch_btn, stretch=1)

        load_ch_btn = QPushButton("読込")
        load_ch_btn.setStyleSheet(Theme.button_secondary())
        load_ch_btn.setToolTip("チャプターファイルを読込")
        load_ch_btn.clicked.connect(self.load_chapters)
        ch_btn_layout.addWidget(load_ch_btn, stretch=1)

        save_ch_btn = QPushButton("保存")
        save_ch_btn.setStyleSheet(Theme.button_secondary())
        save_ch_btn.setToolTip("チャプターファイルを保存")
        save_ch_btn.clicked.connect(self.save_chapters)
        ch_btn_layout.addWidget(save_ch_btn, stretch=1)

        copy_yt_btn = QPushButton("YT")
        copy_yt_btn.setStyleSheet(Theme.button_secondary())
        copy_yt_btn.setToolTip("YouTube用チャプターをコピー")
        copy_yt_btn.clicked.connect(self.copy_youtube_chapters)
        ch_btn_layout.addWidget(copy_yt_btn, stretch=1)

        right_layout.addLayout(ch_btn_layout)

        # ジャンプ・再生ボタン（別行）
        play_btn_layout = QHBoxLayout()
        play_btn_layout.setSpacing(8)

        jump_btn = QPushButton("ジャンプ")
        jump_btn.setStyleSheet(Theme.button_secondary())
        jump_btn.setToolTip("選択チャプターにジャンプ")
        jump_btn.clicked.connect(self.jump_to_selected_chapter)
        play_btn_layout.addWidget(jump_btn, stretch=1)

        self.play_pause_btn = QPushButton("一時停止")
        self.play_pause_btn.setStyleSheet(Theme.button_secondary())
        self.play_pause_btn.setToolTip("再生/一時停止")
        self.play_pause_btn.clicked.connect(self.toggle_play)
        play_btn_layout.addWidget(self.play_pause_btn, stretch=1)

        right_layout.addLayout(play_btn_layout)

        # ========== 書出セクション ==========
        right_layout.addSpacing(12)

        export_header = QLabel("書出")
        export_header.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        right_layout.addWidget(export_header)

        # ファイル名
        name_layout = QHBoxLayout()
        name_layout.setSpacing(4)
        name_label = QLabel("名前:")
        name_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        name_label.setFixedWidth(45)
        name_layout.addWidget(name_label)
        self.export_name = QLineEdit()
        self.export_name.setPlaceholderText("output")
        self.export_name.setStyleSheet(Theme.input_style())
        name_layout.addWidget(self.export_name)
        right_layout.addLayout(name_layout)

        # 出力先
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(4)
        dir_label = QLabel("出力:")
        dir_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        dir_label.setFixedWidth(45)
        dir_layout.addWidget(dir_label)
        self.export_dir = QLineEdit()
        self.export_dir.setStyleSheet(Theme.input_style())
        self.export_dir.setPlaceholderText("出力先フォルダ")
        dir_layout.addWidget(self.export_dir)
        dir_btn = QPushButton("...")
        dir_btn.setFixedWidth(36)
        dir_btn.setStyleSheet(Theme.button_secondary())
        dir_btn.clicked.connect(self._select_export_dir)
        dir_layout.addWidget(dir_btn)
        right_layout.addLayout(dir_layout)

        # 埋め込みオプション（Themeのmain_window_styleでチェックボックスは設定済み）
        embed_layout = QHBoxLayout()
        embed_layout.setSpacing(12)

        self.embed_chapters_check = QCheckBox("チャプター埋込")
        self.embed_chapters_check.setChecked(True)
        embed_layout.addWidget(self.embed_chapters_check)

        self.overlay_titles_check = QCheckBox("チャプター名表示")
        self.overlay_titles_check.setChecked(True)
        self.overlay_titles_check.setToolTip("各チャプター区間中、チャプター名を常時表示（再エンコード）")
        embed_layout.addWidget(self.overlay_titles_check)

        embed_layout.addStretch()
        right_layout.addLayout(embed_layout)

        # エンコーダ選択
        encoder_layout = QHBoxLayout()
        encoder_layout.setSpacing(4)
        encoder_label = QLabel("エンコーダ:")
        encoder_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        encoder_label.setFixedWidth(80)
        encoder_layout.addWidget(encoder_label)

        self.encoder_combo = QComboBox()
        self.encoder_combo.setStyleSheet(Theme.input_style())
        # 利用可能なエンコーダを検出して追加
        self._available_encoders = detect_available_encoders()
        for encoder_id, display_name, description in self._available_encoders:
            self.encoder_combo.addItem(display_name, encoder_id)
            # ツールチップにdescriptionを設定
            idx = self.encoder_combo.count() - 1
            self.encoder_combo.setItemData(idx, description, Qt.ItemDataRole.ToolTipRole)
        encoder_layout.addWidget(self.encoder_combo)
        encoder_layout.addStretch()
        right_layout.addLayout(encoder_layout)

        # 品質選択
        quality_layout = QHBoxLayout()
        quality_layout.setSpacing(4)
        quality_label = QLabel("品質:")
        quality_label.setStyleSheet(f"color: {Theme.TEXT_SECONDARY};")
        quality_label.setFixedWidth(80)
        quality_layout.addWidget(quality_label)

        self.quality_combo = QComboBox()
        self.quality_combo.setStyleSheet(Theme.input_style())
        # 品質オプション: (display_name, bitrate_kbps, crf)
        # bitrate_kbps=0 は「元と同じ」を意味する
        self._detected_bitrate_kbps: Optional[int] = None  # 検出したビットレート
        self._detected_colorspace: Optional[ColorspaceInfo] = None  # 検出した色空間
        self._quality_options = [
            ("元と同じ (自動)", 0, 23),  # 検出ビットレートを使用
            ("高画質 (6Mbps)", 6000, 20),
            ("標準 (4Mbps)", 4000, 23),
            ("軽量 (2Mbps)", 2000, 28),
            ("最小 (1Mbps)", 1000, 32),
            ("静止画用 (500kbps)", 500, 35),
        ]
        for display_name, bitrate, crf in self._quality_options:
            self.quality_combo.addItem(display_name, (bitrate, crf))
        self.quality_combo.setCurrentIndex(0)  # デフォルト: 元と同じ
        self.quality_combo.setToolTip("ビットレート設定\n「元と同じ」で元動画のビットレートを維持")
        quality_layout.addWidget(self.quality_combo)
        quality_layout.addStretch()
        right_layout.addLayout(quality_layout)

        # アクションボタン（開く + 書出）- 幅2分割
        action_layout = QHBoxLayout()
        action_layout.setSpacing(6)

        load_btn = QPushButton("開く")
        load_btn.setStyleSheet(Theme.button_secondary())
        load_btn.setToolTip("動画/音声ファイルを開く")
        load_btn.clicked.connect(self.load_media)
        action_layout.addWidget(load_btn, stretch=1)

        self.export_btn = QPushButton("書出")
        self.export_btn.setStyleSheet(Theme.button_primary())
        self.export_btn.setToolTip("編集した動画を書き出す")
        self.export_btn.clicked.connect(self._on_export_btn_clicked)
        action_layout.addWidget(self.export_btn, stretch=1)

        # ボタンスタイル保存（トグル用）
        self._btn_style_action = Theme.button_primary()
        self._btn_style_cancel = Theme.button_danger()
        self._is_exporting = False  # エクスポート中フラグ

        right_layout.addLayout(action_layout)

        # 進捗バー（Themeのmain_window_styleで設定済み）
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(0)
        self.export_progress.setTextVisible(True)
        self.export_progress.setFormat("%p%")
        self.export_progress.hide()  # 初期状態では非表示
        right_layout.addWidget(self.export_progress)

        main_layout.addWidget(right_widget)
        layout.addLayout(main_layout)

    def _setup_media_player(self):
        """メディアプレーヤーの設定（movie-viewerと同じ仕様）"""
        # メディアプレーヤーを親を指定して作成
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)

        # VideoOutput を先に設定（重要）
        self.player.setVideoOutput(self.video_widget)
        self.player.setAudioOutput(self.audio_output)

        # ビデオコントローラーを初期化
        self.video_controller = VideoController(self.player)

        # シグナル接続
        self.seek_slider.sliderMoved.connect(self.seek_position)
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)

        # エラーシグナル接続（デバッグ用）
        self.player.errorOccurred.connect(self._on_media_error)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        # 再生状態変更時のシグナル接続（ボタン同期用）
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

    def _on_playback_state_changed(self, state):
        """再生状態変更時のハンドラ（全再生ボタンを同期）"""
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        self._update_play_button(is_playing)

    def _on_media_error(self, error, error_string):
        """メディアエラー時のハンドラ"""
        print(f"[Media Error] {error}: {error_string}")

    def _on_media_status_changed(self, status):
        """メディアステータス変更時のハンドラ"""
        status_names = {
            QMediaPlayer.MediaStatus.NoMedia: "NoMedia",
            QMediaPlayer.MediaStatus.LoadingMedia: "LoadingMedia",
            QMediaPlayer.MediaStatus.LoadedMedia: "LoadedMedia",
            QMediaPlayer.MediaStatus.StalledMedia: "StalledMedia",
            QMediaPlayer.MediaStatus.BufferingMedia: "BufferingMedia",
            QMediaPlayer.MediaStatus.BufferedMedia: "BufferedMedia",
            QMediaPlayer.MediaStatus.EndOfMedia: "EndOfMedia",
            QMediaPlayer.MediaStatus.InvalidMedia: "InvalidMedia",
        }
        print(f"[Media Status] {status_names.get(status, status)}")

    def _populate_audio_devices(self):
        """音声出力デバイス一覧を取得してコンボボックスに設定"""
        self.audio_device_combo.clear()
        devices = QMediaDevices.audioOutputs()
        default_device = QMediaDevices.defaultAudioOutput()

        for i, device in enumerate(devices):
            self.audio_device_combo.addItem(device.description(), device)
            # デフォルトデバイスを選択
            if device.id() == default_device.id():
                self.audio_device_combo.setCurrentIndex(i)

    def _on_audio_device_changed(self, index):
        """音声出力デバイスが変更されたとき"""
        if index < 0:
            return
        device = self.audio_device_combo.currentData()
        if device and self.audio_output:
            self.audio_output.setDevice(device)
            print(f"[Audio] Output changed to: {device.description()}")

    def load_media(self):
        file_path, _ = CenteredFileDialog.getOpenFileName(
            self, "音声/動画ファイルを選択", "",
            "Media Files (*.mp4 *.mp3 *.m4a *.wav *.mov *.avi *.mkv)"
        )
        if file_path:
            self._initialize_media(file_path)
            # 動画のみ読み込みの場合、0:00:00.000 開始を追加
            self.chapters = [ChapterInfo(time_ms=0, title="開始")]
            self.update_chapter_table()

    def _initialize_media(self, file_path: str):
        """メディアファイルを初期化"""
        self.media_file = file_path
        self.media_label.setText(Path(file_path).name)
        self.player.setSource(QUrl.fromLocalFile(file_path))

        # 書出ファイル名を動画ファイル名_chapteredに設定
        video_stem = Path(file_path).stem
        self.export_name.setText(f"{video_stem}_chaptered")
        # 出力先も動画と同じディレクトリに設定
        self.export_dir.setText(str(Path(file_path).parent))

        # フレームレートを取得して設定
        frame_rate = VideoController.get_frame_rate(file_path)
        self.video_controller.set_frame_rate(frame_rate)
        print(f"[Init] Loaded: {file_path}, Frame rate: {frame_rate:.2f} fps")

        # 波形をバックグラウンドで抽出
        print("[Waveform] Extracting waveform (background)...")
        if self._waveform_worker is not None:
            self._waveform_worker.quit()
            self._waveform_worker.wait()
        self._waveform_worker = WaveformWorker(file_path, self)
        self._waveform_worker.finished.connect(self._on_waveform_ready)
        self._waveform_worker.start()

        # ビットレートを検出して品質を自動選択
        self._auto_select_quality(file_path)

        # 自動再生
        QTimer.singleShot(100, self.player.play)

    def _on_waveform_ready(self, waveform_data):
        """波形抽出完了時のコールバック"""
        if waveform_data is not None:
            self._pending_waveform = waveform_data
            print(f"[Waveform] Extracted {len(waveform_data)} samples")
            # durationが既に取得できていれば即座に設定
            if self.player.duration() > 0:
                self.waveform_widget.set_waveform(waveform_data, self.player.duration())
                self.waveform_widget.set_chapters(self.chapters)
        else:
            self._pending_waveform = None
            print("[Waveform] Failed to extract waveform")

    def _auto_select_quality(self, file_path: str):
        """動画のビットレートと色空間を検出して保存"""
        # ビットレート検出
        self._detected_bitrate_kbps = detect_video_bitrate(file_path)

        if self._detected_bitrate_kbps is None:
            print("[Quality] ビットレート取得失敗、標準 (4Mbps) を使用")
            self._detected_bitrate_kbps = 4000  # フォールバック
        else:
            print(f"[Quality] 検出ビットレート: {self._detected_bitrate_kbps} kbps")

        # 色空間検出
        self._detected_colorspace = detect_video_colorspace(file_path)

        # 「元と同じ」の表示を更新
        display_text = f"元と同じ ({self._detected_bitrate_kbps} kbps)"
        self.quality_combo.setItemText(0, display_text)
        self.quality_combo.setCurrentIndex(0)  # 「元と同じ」を選択

    def set_media_file(self, file_path: str, chapters: List[ChapterInfo] = None):
        """外部からメディアファイルを設定"""
        self._initialize_media(file_path)
        if chapters:
            self.chapters = chapters
            self.update_chapter_table()

    def toggle_play(self):
        # playbackStateChangedシグナルで自動的にボタンが更新される
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _update_play_button(self, is_playing: bool):
        """再生/一時停止ボタンのテキストを更新"""
        if is_playing:
            self.play_btn.setText("Pause")
            if hasattr(self, 'play_pause_btn'):
                self.play_pause_btn.setText("一時停止")
        else:
            self.play_btn.setText("Play")
            if hasattr(self, 'play_pause_btn'):
                self.play_pause_btn.setText("再生")

    def skip(self, delta_ms: int):
        """指定ミリ秒分スキップ"""
        if self.video_controller:
            self.video_controller.seek_by_milliseconds(delta_ms)

    def seek_position(self, position):
        self.player.setPosition(position)

    def update_position(self, position):
        self.seek_slider.setValue(position)
        self._update_time_label(position)
        # 波形の再生位置を更新
        self.waveform_widget.set_position(position)

    def update_duration(self, duration):
        self.seek_slider.setMaximum(duration)
        self._current_duration = duration
        self._update_time_label(self.player.position() if self.player else 0)
        # 波形にdurationを設定
        if hasattr(self, '_pending_waveform') and self._pending_waveform is not None:
            self.waveform_widget.set_waveform(self._pending_waveform, duration)
            self.waveform_widget.set_chapters(self.chapters)
            self._pending_waveform = None

    def _update_time_label(self, position: int):
        """時間ラベルを更新（movie-viewer形式）"""
        current = self._format_time(position)
        total = self._format_time(self._current_duration)
        self.time_label.setText(f"{current} / {total}")

    def _sync_bottom_width(self, width: int):
        """映像の幅に波形・コントロールを同期"""
        self.bottom_container.setFixedWidth(width)

    def _on_waveform_clicked(self, ratio: float):
        """波形クリック時のハンドラ"""
        if self.player.duration() > 0:
            position = int(ratio * self.player.duration())
            self.player.setPosition(position)

    def _format_time(self, ms: int) -> str:
        total_sec = ms // 1000
        millis = ms % 1000
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        s = total_sec % 60
        return f"{h}:{m:02d}:{s:02d}.{millis:03d}"

    def add_chapter(self):
        current_pos = self.player.position()
        chapter = ChapterInfo(time_ms=current_pos, title="新しいチャプター")
        self.chapters.append(chapter)
        self.chapters.sort(key=lambda c: c.time_ms)
        self.update_chapter_table()

    def delete_chapter(self):
        row = self.chapter_table.currentRow()
        if row >= 0 and row < len(self.chapters):
            del self.chapters[row]
            self.update_chapter_table()

    def update_chapter_table(self):
        # テーブル更新中はitemChangedシグナルをブロック
        self.chapter_table.blockSignals(True)
        self.chapter_table.setRowCount(len(self.chapters))
        for i, ch in enumerate(self.chapters):
            time_item = QTableWidgetItem(ch.time_str)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.chapter_table.setItem(i, 0, time_item)
            self.chapter_table.setItem(i, 1, QTableWidgetItem(ch.title))
        self.chapter_table.blockSignals(False)
        # 波形にもチャプターを反映
        self.waveform_widget.set_chapters(self.chapters)

    def _on_chapter_table_changed(self, item: QTableWidgetItem):
        """チャプターテーブルが編集されたときの処理"""
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self.chapters):
            return

        # chaptersリストを更新
        if col == 0:  # 時間列
            ch = ChapterInfo.from_time_str(item.text(), self.chapters[row].title)
            self.chapters[row] = ch
            # 時間が変わった場合はソートが必要かもしれないが、ここではしない
        elif col == 1:  # タイトル列
            self.chapters[row] = ChapterInfo(
                time_ms=self.chapters[row].time_ms,
                title=item.text()
            )

        # 波形ウィジェットを更新（ハッチング再描画）
        self.waveform_widget.set_chapters(self.chapters)

    def jump_to_chapter(self, index):
        """ダブルクリックでチャプターにジャンプ"""
        row = index.row()
        if row >= 0 and row < len(self.chapters):
            self.player.setPosition(self.chapters[row].time_ms)
            print(f"[Jump] {self.chapters[row].title} ({self.chapters[row].time_str})")

    def jump_to_selected_chapter(self):
        """選択中のチャプターにジャンプ"""
        row = self.chapter_table.currentRow()
        if row >= 0 and row < len(self.chapters):
            self.player.setPosition(self.chapters[row].time_ms)
            print(f"[Jump] {self.chapters[row].title} ({self.chapters[row].time_str})")

    def load_chapters(self):
        file_path, _ = CenteredFileDialog.getOpenFileName(
            self, "チャプターファイルを開く", "",
            "Chapter Files (*.chapters *.txt)"
        )
        if file_path:
            self.chapters.clear()
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        parts = line.split(' ', 1)
                        if len(parts) == 2:
                            ch = ChapterInfo.from_time_str(parts[0], parts[1])
                            self.chapters.append(ch)
            # ソートして0:00:00.000から始まらない場合は"--開始"を追加
            self.chapters.sort(key=lambda c: c.time_ms)
            if self.chapters and self.chapters[0].time_ms != 0:
                self.chapters.insert(0, ChapterInfo(time_ms=0, title="--開始"))
            self.update_chapter_table()

    def save_chapters(self):
        # テーブルから最新の値を取得
        self.chapters.clear()
        for i in range(self.chapter_table.rowCount()):
            time_item = self.chapter_table.item(i, 0)
            title_item = self.chapter_table.item(i, 1)
            if time_item and title_item:
                ch = ChapterInfo.from_time_str(time_item.text(), title_item.text())
                self.chapters.append(ch)

        file_path, _ = CenteredFileDialog.getSaveFileName(
            self, "チャプターファイルを保存", "",
            "Chapter Files (*.chapters)"
        )
        if file_path:
            with open(file_path, 'w') as f:
                for ch in self.chapters:
                    f.write(f"{ch.time_str} {ch.title}\n")

    def copy_youtube_chapters(self):
        """YouTube用チャプターをクリップボードにコピー"""
        # テーブルから最新の値を取得
        self.chapters.clear()
        for i in range(self.chapter_table.rowCount()):
            time_item = self.chapter_table.item(i, 0)
            title_item = self.chapter_table.item(i, 1)
            if time_item and title_item:
                ch = ChapterInfo.from_time_str(time_item.text(), title_item.text())
                self.chapters.append(ch)

        if not self.chapters:
            return

        # YouTube用フォーマット（ミリ秒なし）でテキスト生成
        lines = [f"{ch.time_str_youtube} {ch.title}" for ch in self.chapters]
        text = "\n".join(lines)

        # クリップボードにコピー
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        print(f"[Clipboard] YouTube用チャプター {len(self.chapters)}件をコピー")

    def paste_youtube_chapters(self):
        """クリップボードからYouTubeチャプター形式を貼り付け"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if not text:
            return False

        # YouTubeチャプター形式をパース
        # 形式: "H:MM:SS タイトル" または "M:SS タイトル" または "MM:SS タイトル"
        chapters = []
        lines = text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 時間とタイトルを分離（最初のスペースで分割）
            match = re.match(r'^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$', line)
            if match:
                time_str = match.group(1)
                title = match.group(2)

                # 時間をミリ秒に変換
                parts = time_str.split(':')
                if len(parts) == 2:
                    # M:SS または MM:SS 形式
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    time_ms = (minutes * 60 + seconds) * 1000
                elif len(parts) == 3:
                    # H:MM:SS 形式
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = int(parts[2])
                    time_ms = (hours * 3600 + minutes * 60 + seconds) * 1000
                else:
                    continue

                chapters.append(ChapterInfo(time_ms=time_ms, title=title))

        if not chapters:
            return False

        # チャプターをソート
        chapters.sort(key=lambda c: c.time_ms)

        # 0:00:00.000から始まらない場合、"--開始"を追加
        if chapters[0].time_ms != 0:
            chapters.insert(0, ChapterInfo(time_ms=0, title="--開始"))

        # チャプターを設定
        self.chapters = chapters
        self.update_chapter_table()
        print(f"[Clipboard] YouTubeチャプター {len(chapters)}件を貼り付け")
        return True

    def keyPressEvent(self, event):
        """キーボードイベント処理"""
        # Cmd+V (Mac) または Ctrl+V (Windows/Linux) でYouTubeチャプターを貼り付け
        if event.key() == Qt.Key.Key_V and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if self.paste_youtube_chapters():
                event.accept()
                return
        super().keyPressEvent(event)

    # ========== 書出機能 ==========

    def _select_export_dir(self):
        """出力先ディレクトリを選択"""
        dir_path = CenteredFileDialog.getExistingDirectory(self, "出力先を選択")
        if dir_path:
            self.export_dir.setText(dir_path)

    def _on_export_btn_clicked(self):
        """書出ボタンクリック（トグル動作）"""
        if self._is_exporting:
            self._cancel_export()
        else:
            self._execute_export()

    def _execute_export(self):
        """書出を実行"""
        if not self.media_file:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "エラー", "メディアファイルが読み込まれていません")
            return

        # 既に書出中の場合は警告
        if self._export_worker is not None and self._export_worker.isRunning():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "書出中", "書出処理が実行中です")
            return

        # 出力設定を取得
        output_name = self.export_name.text() or "output"
        output_dir = self.export_dir.text()
        if not output_dir:
            output_dir = str(Path(self.media_file).parent)

        output_path = str(Path(output_dir) / f"{output_name}.mp4")

        # 出力先の確認（上書き警告）
        if os.path.exists(output_path):
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "確認",
                f"ファイルが既に存在します。上書きしますか？\n{output_path}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # チャプターを保存（テーブルから最新の値を取得）
        self.chapters.clear()
        for i in range(self.chapter_table.rowCount()):
            time_item = self.chapter_table.item(i, 0)
            title_item = self.chapter_table.item(i, 1)
            if time_item and title_item:
                ch = ChapterInfo.from_time_str(time_item.text(), title_item.text())
                self.chapters.append(ch)

        # 埋め込みオプション
        embed_chapters = self.embed_chapters_check.isChecked()
        overlay_titles = self.overlay_titles_check.isChecked()

        # 動画の総再生時間を取得
        total_duration_ms = self.player.duration()

        print(f"[Export] 出力: {output_path}")
        print(f"[Export] チャプター埋込: {embed_chapters}")
        print(f"[Export] チャプター名表示: {overlay_titles}")
        print(f"[Export] チャプター数: {len(self.chapters)}")
        print(f"[Export] 動画長: {total_duration_ms}ms")

        # ボタンを中止モードに切り替え・進捗バー表示
        self._is_exporting = True
        self.export_btn.setText("中止")
        self.export_btn.setStyleSheet(self._btn_style_cancel)
        self.export_btn.setToolTip("エクスポートを中止")
        self.export_progress.setValue(0)
        self.export_progress.setFormat("0% - 準備中...")
        self.export_progress.show()

        # 選択されたエンコーダと品質を取得
        encoder_id = self.encoder_combo.currentData()
        bitrate_kbps, crf = self.quality_combo.currentData()

        # 「元と同じ」が選択されている場合の処理
        if bitrate_kbps == 0:
            base_bitrate = self._detected_bitrate_kbps or 4000
            if encoder_id == "libx264":
                # CPU: CRFモードで高画質（ビットレートは使わない）
                bitrate_kbps = base_bitrate  # 参考値として保持
                crf = 18  # 高画質CRF
                print(f"[Export] 「元と同じ」選択 → CRF {crf}（高画質）")
            else:
                # GPU: ビットレート×1.5で再エンコード劣化を補償
                bitrate_kbps = int(base_bitrate * 1.5)
                print(f"[Export] 「元と同じ」選択 → {bitrate_kbps} kbps（元{base_bitrate}の1.5倍）")
        else:
            print(f"[Export] 指定ビットレート: {bitrate_kbps} kbps")

        print(f"[Export] エンコーダ: {encoder_id}")

        # ワーカーを起動
        self._export_worker = ExportWorker(
            input_file=self.media_file,
            output_file=output_path,
            chapters=self.chapters.copy(),
            embed_chapters=embed_chapters,
            embed_title=True,  # メタデータタイトルは常に埋め込む
            overlay_chapter_titles=overlay_titles,
            total_duration_ms=total_duration_ms,
            encoder_id=encoder_id,
            bitrate_kbps=bitrate_kbps,
            crf=crf,
            colorspace=self._detected_colorspace,
            parent=self
        )
        self._export_worker.progress_update.connect(self._on_export_progress)
        self._export_worker.progress_percent.connect(self._on_export_percent)
        self._export_worker.export_completed.connect(self._on_export_completed)
        self._export_worker.error_occurred.connect(self._on_export_error)
        self._export_worker.start()

    def _on_export_progress(self, message: str):
        """書出進捗"""
        print(f"[Export] {message}")

    def _on_export_percent(self, percent: int, time_str: str):
        """書出進捗率"""
        self.export_progress.setValue(percent)
        self.export_progress.setFormat(f"{percent}% - {time_str}")

    def _on_export_completed(self, output_path: str):
        """書出完了"""
        self._is_exporting = False
        self.export_btn.setText("書出")
        self.export_btn.setStyleSheet(self._btn_style_action)
        self.export_btn.setToolTip("編集した動画を書き出す")
        self.export_progress.setValue(100)
        self.export_progress.setFormat("100% - 完了")
        # 3秒後に進捗バーを非表示
        QTimer.singleShot(3000, self.export_progress.hide)
        print(f"[Export] 完了: {output_path}")

        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "書出完了", f"書出が完了しました\n{output_path}")

    def _on_export_error(self, error_msg: str):
        """書出エラー"""
        self._is_exporting = False
        self.export_btn.setText("書出")
        self.export_btn.setStyleSheet(self._btn_style_action)
        self.export_btn.setToolTip("編集した動画を書き出す")
        self.export_progress.hide()
        print(f"[Export] エラー: {error_msg}")

        # キャンセルの場合はメッセージを変更
        if "中止" in error_msg:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "中止", error_msg)
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "書出エラー", error_msg)

    def _cancel_export(self):
        """エクスポートを中止"""
        if hasattr(self, '_export_worker') and self._export_worker.isRunning():
            self._export_worker.cancel()
            print("[Export] 中止リクエスト送信")


# ==============================================================================
# メインウィンドウ
# ==============================================================================

class PrepGUI(QMainWindow):
    """素材準備GUIメインウィンドウ"""

    # レイアウト定数
    SIDEBAR_WIDTH = 320
    VIDEO_ASPECT = 16 / 9
    WINDOW_ASPECT = 16 / 9  # ウィンドウ全体のアスペクト比

    # フォントサイズ設定
    FONT_SIZES = [9, 10, 11, 12, 13, 14, 16, 18]  # 選択可能なサイズ
    DEFAULT_FONT_SIZE = 13

    def __init__(self, working_dir: str = None):
        super().__init__()
        self.project = ProjectState()
        self._resizing = False
        self.working_dir = working_dir
        if working_dir:
            os.chdir(working_dir)

        # 設定の読み込み
        self.settings = QSettings("mashi727", "VideoChapterEditor")
        self._load_and_apply_font_size()

        self.init_ui()
        self._create_menu_bar()

    def init_ui(self):
        title = "Video Chapter Editor"
        if self.working_dir:
            title = f"{title} - {Path(self.working_dir).name}"
        self.setWindowTitle(title)
        # 16:9映像がピッタリ収まる初期サイズ
        # 起動時のウィンドウサイズ: 1680 x 675
        self.setGeometry(100, 100, 1680, 675)

        # モダンダークテーマを適用
        self.setStyleSheet(Theme.main_window_style())

        # メインウィジェット
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # タブウィジェット
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("", 16))

        # タブ1: 結合
        self.merge_tab = MergeTab()
        self.merge_tab.merge_completed.connect(self.on_merge_completed)
        self.tabs.addTab(self.merge_tab, "1. 結合")

        # タブ2: 編集（書出機能を含む）
        self.edit_tab = EditTab()
        self.tabs.addTab(self.edit_tab, "2. 編集")

        main_layout.addWidget(self.tabs)

    def on_merge_completed(self, merged_file: str, chapters: list, cover_image: str):
        """結合完了時の処理"""
        self.project.merged_audio = merged_file
        self.project.chapters = chapters
        self.project.cover_image = cover_image

        # タブ2にファイルを設定
        self.edit_tab.set_media_file(merged_file, chapters)

        # タブ2に切り替え
        self.tabs.setCurrentIndex(1)

    def _create_menu_bar(self):
        """メニューバーを作成"""
        menubar = self.menuBar()

        # 表示メニュー
        view_menu = menubar.addMenu("表示")

        # フォントサイズサブメニュー
        font_menu = view_menu.addMenu("フォントサイズ")

        self.font_actions = []
        current_size = self.settings.value("font_size", self.DEFAULT_FONT_SIZE, type=int)

        for size in self.FONT_SIZES:
            action = QAction(f"{size}pt", self)
            action.setCheckable(True)
            action.setChecked(size == current_size)
            action.triggered.connect(lambda checked, s=size: self._set_font_size(s))
            font_menu.addAction(action)
            self.font_actions.append((size, action))

    def _load_and_apply_font_size(self):
        """保存されたフォントサイズを読み込んで適用"""
        size = self.settings.value("font_size", self.DEFAULT_FONT_SIZE, type=int)
        self._apply_font_size(size)

    def _set_font_size(self, size: int):
        """フォントサイズを設定して保存"""
        self.settings.setValue("font_size", size)
        self._apply_font_size(size)

        # メニューのチェック状態を更新
        for s, action in self.font_actions:
            action.setChecked(s == size)

    def _apply_font_size(self, size: int):
        """アプリ全体のフォントサイズを適用"""
        app = QApplication.instance()
        font = app.font()
        font.setPointSize(size)
        app.setFont(font)

    def resizeEvent(self, event):
        """ウィンドウリサイズ時にアスペクト比を維持"""
        if self._resizing:
            return
        self._resizing = True

        new_size = event.size()
        old_size = event.oldSize()

        # 幅と高さのどちらが変更されたかを判定
        if old_size.width() > 0 and old_size.height() > 0:
            width_changed = abs(new_size.width() - old_size.width()) > abs(new_size.height() - old_size.height())
        else:
            width_changed = True

        if width_changed:
            # 幅に基づいて高さを計算
            new_height = int(new_size.width() / self.WINDOW_ASPECT)
            self.resize(new_size.width(), new_height)
        else:
            # 高さに基づいて幅を計算
            new_width = int(new_size.height() * self.WINDOW_ASPECT)
            self.resize(new_width, new_size.height())

        self._resizing = False
        super().resizeEvent(event)

    def closeEvent(self, event):
        """アプリ終了時の処理（エンコード中のファイルを削除）"""
        # MergeTabのエンコード処理を確認
        merge_tab = self.merge_tab
        if merge_tab.encode_process and merge_tab.encode_process.state() != QProcess.ProcessState.NotRunning:
            # エンコード中のプロセスを終了
            merge_tab.encode_process.kill()
            merge_tab.encode_process.waitForFinished(3000)
            # 中途半端なファイルを削除
            if merge_tab.encode_output_file:
                output_path = Path(merge_tab.encode_output_file)
                if output_path.exists():
                    output_path.unlink()
                    print(f"中断されたファイルを削除: {output_path}")
            # 一時ファイルも削除
            if merge_tab.encode_temp_audio:
                Path(merge_tab.encode_temp_audio).unlink(missing_ok=True)
            if merge_tab.encode_temp_cover:
                Path(merge_tab.encode_temp_cover).unlink(missing_ok=True)

        # ワーカースレッドが動作中なら停止
        if merge_tab.merge_worker and merge_tab.merge_worker.isRunning():
            merge_tab.merge_worker.terminate()
            merge_tab.merge_worker.wait(3000)

        super().closeEvent(event)


# ==============================================================================
# エントリーポイント
# ==============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="動画チャプター編集・書出ツール",
        prog="video-chapter-editor"
    )
    parser.add_argument(
        "working_dir",
        nargs="?",
        default=None,
        help="作業ディレクトリ（フォルダをドロップして起動可能）"
    )
    args = parser.parse_args()

    # 作業ディレクトリの検証
    working_dir = None
    if args.working_dir:
        path = Path(args.working_dir)
        if path.is_dir():
            working_dir = str(path.resolve())
        elif path.is_file():
            # ファイルが指定された場合は親ディレクトリを使用
            working_dir = str(path.parent.resolve())

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # ダークテーマ
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(palette)

    window = PrepGUI(working_dir=working_dir)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
