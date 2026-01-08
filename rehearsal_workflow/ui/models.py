"""
models.py - データモデルとユーティリティ

ChapterInfo、ColorspaceInfo、エンコーダ検出などのコア機能を提供。
"""

import subprocess
import platform
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

from .ffmpeg_utils import get_ffmpeg_path, get_ffprobe_path


def _format_time_ms(time_ms: int, include_ms: bool = True) -> str:
    """ミリ秒を時間文字列に変換するヘルパー関数"""
    total_sec = time_ms // 1000
    ms = time_ms % 1000
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if include_ms:
        return f"{h}:{m:02d}:{s:02d}.{ms:03d}"
    return f"{h}:{m:02d}:{s:02d}"


def _parse_time_str(time_str: str) -> int:
    """時間文字列をミリ秒に変換するヘルパー関数

    サポートする形式:
    - HH:MM:SS.mmm (例: 1:23:45.678)
    - HH:MM:SS (例: 1:23:45)
    - MM:SS.mmm (例: 23:45.678)
    - MM:SS (例: 23:45)
    """
    parts = time_str.replace('.', ':').split(':')
    if len(parts) == 4:
        h, m, s, ms = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    elif len(parts) == 3:
        if '.' in time_str:
            h = 0
            m, s, ms = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            ms = 0
    elif len(parts) == 2:
        h = 0
        m, s = int(parts[0]), int(parts[1])
        ms = 0
    else:
        h, m, s, ms = 0, 0, 0, 0
    return ((h * 3600) + (m * 60) + s) * 1000 + ms


@dataclass
class ChapterInfo:
    """チャプター情報

    相対時間方式: チャプターはソースファイル内のローカル時間を保持し、
    表示時に累積時間（絶対時間）に変換する。
    """
    local_time_ms: int  # ソースファイル内のローカル時間（ミリ秒）
    title: str
    source_index: Optional[int] = None  # 所属するソースファイルのインデックス

    @property
    def local_time_str(self) -> str:
        """ローカル時間 HH:MM:SS.mmm形式"""
        return _format_time_ms(self.local_time_ms)

    @property
    def local_time_str_youtube(self) -> str:
        """ローカル時間 YouTube用 HH:MM:SS形式（ミリ秒なし）"""
        return _format_time_ms(self.local_time_ms, include_ms=False)

    def get_absolute_time_ms(self, source_offsets: List[int]) -> int:
        """累積時間（絶対時間）を計算

        Args:
            source_offsets: 各ソースファイルの開始オフセット（ミリ秒）のリスト

        Returns:
            累積時間（ミリ秒）
        """
        if self.source_index is not None and 0 <= self.source_index < len(source_offsets):
            return source_offsets[self.source_index] + self.local_time_ms
        return self.local_time_ms

    def get_absolute_time_str(self, source_offsets: List[int]) -> str:
        """累積時間を HH:MM:SS.mmm形式で取得"""
        return _format_time_ms(self.get_absolute_time_ms(source_offsets))

    def get_absolute_time_str_youtube(self, source_offsets: List[int]) -> str:
        """累積時間を YouTube用 HH:MM:SS形式で取得"""
        return _format_time_ms(self.get_absolute_time_ms(source_offsets), include_ms=False)

    @property
    def is_excluded(self) -> bool:
        """除外チャプターかどうか（--プレフィックス）"""
        return self.title.startswith("--")

    # ============================================
    # 後方互換性のためのプロパティ（非推奨）
    # ============================================
    @property
    def time_ms(self) -> int:
        """後方互換性: local_time_msを返す（非推奨）"""
        return self.local_time_ms

    @property
    def time_str(self) -> str:
        """後方互換性: local_time_strを返す（非推奨）"""
        return self.local_time_str

    @property
    def time_str_youtube(self) -> str:
        """後方互換性: local_time_str_youtubeを返す（非推奨）"""
        return self.local_time_str_youtube

    @classmethod
    def from_time_str(cls, time_str: str, title: str, source_index: Optional[int] = None) -> "ChapterInfo":
        """時間文字列からChapterInfoを生成（ローカル時間として解釈）"""
        return cls(local_time_ms=_parse_time_str(time_str), title=title, source_index=source_index)

    @classmethod
    def from_absolute_time(
        cls,
        absolute_time_ms: int,
        title: str,
        source_index: int,
        source_offsets: List[int]
    ) -> "ChapterInfo":
        """累積時間からChapterInfoを生成（ローカル時間に変換）

        Args:
            absolute_time_ms: 累積時間（ミリ秒）
            title: チャプタータイトル
            source_index: ソースファイルのインデックス
            source_offsets: 各ソースファイルの開始オフセット（ミリ秒）のリスト

        Returns:
            ChapterInfo（ローカル時間に変換済み）
        """
        if 0 <= source_index < len(source_offsets):
            local_time_ms = absolute_time_ms - source_offsets[source_index]
        else:
            local_time_ms = absolute_time_ms
        return cls(local_time_ms=max(0, local_time_ms), title=title, source_index=source_index)


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


@dataclass
class ProjectState:
    """プロジェクト状態"""
    work_dir: Path = field(default_factory=Path.cwd)
    sources: List['SourceFile'] = field(default_factory=list)
    cover_image_path: Optional[Path] = None
    chapters: List[ChapterInfo] = field(default_factory=list)
    output_path: Optional[Path] = None
    output_dir: Optional[Path] = None  # 出力先ディレクトリ（Noneの場合はwork_dir）
    video_path: Optional[Path] = None
    video_duration_ms: int = 0
    colorspace: Optional[ColorspaceInfo] = None


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
                get_ffprobe_path(), "-v", "quiet",
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

    except Exception as e:
        print(f"[Colorspace] 検出エラー: {e}")

    return info


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
                get_ffprobe_path(), "-v", "quiet",
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
                get_ffprobe_path(), "-v", "quiet",
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
            return bitrate_bps // 1000

    except Exception as e:
        print(f"[Bitrate] 検出エラー: {e}")

    return None


def detect_video_duration(file_path: str) -> Optional[int]:
    """
    動画の長さを取得（ミリ秒単位）

    Args:
        file_path: 動画ファイルパス

    Returns:
        長さ（ミリ秒）、取得失敗時はNone
    """
    try:
        result = subprocess.run(
            [
                get_ffprobe_path(), "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        duration_str = result.stdout.strip()

        if duration_str and duration_str != "N/A":
            duration_sec = float(duration_str)
            return int(duration_sec * 1000)

    except Exception as e:
        print(f"[Duration] 検出エラー: {e}")

    return None


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
            [get_ffmpeg_path(), "-hide_banner", "-encoders"],
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

    # CPUエンコーダは常に利用可能（デフォルトとして先頭に）
    encoders.insert(0, ("libx264", "CPU (x264)", "CPU処理・高画質"))

    return encoders


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
            '-threads', '0',  # 全CPUコアを使用
            '-pix_fmt', 'yuv420p',
        ]


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
