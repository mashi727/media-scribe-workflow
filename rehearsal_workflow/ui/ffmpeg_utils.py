"""
ffmpeg_utils.py - FFmpeg/FFprobe パス解決ユーティリティ

PyInstallerでバンドルされた環境でも動作するよう、
imageio-ffmpegまたはシステムのffmpegを自動検出する。
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

# キャッシュ
_ffmpeg_path: Optional[str] = None
_ffprobe_path: Optional[str] = None


def get_ffmpeg_path() -> str:
    """
    FFmpegの実行パスを取得

    優先順位:
    1. imageio-ffmpeg (バンドル版)
    2. システムのffmpeg (PATH)

    Returns:
        ffmpegの実行パス

    Raises:
        RuntimeError: ffmpegが見つからない場合
    """
    global _ffmpeg_path

    if _ffmpeg_path is not None:
        return _ffmpeg_path

    # 1. imageio-ffmpegを試行
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and Path(path).exists():
            _ffmpeg_path = path
            return _ffmpeg_path
    except ImportError:
        pass
    except Exception:
        pass

    # 2. システムのffmpegを試行
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        _ffmpeg_path = system_ffmpeg
        return _ffmpeg_path

    raise RuntimeError(
        "FFmpegが見つかりません。\n"
        "以下のいずれかの方法でインストールしてください:\n"
        "- macOS: brew install ffmpeg\n"
        "- Windows: https://ffmpeg.org/download.html からダウンロード\n"
        "- pip install imageio-ffmpeg"
    )


def get_ffprobe_path() -> str:
    """
    FFprobeの実行パスを取得

    優先順位:
    1. ffmpegと同じディレクトリのffprobe
    2. システムのffprobe (PATH)

    Returns:
        ffprobeの実行パス

    Raises:
        RuntimeError: ffprobeが見つからない場合
    """
    global _ffprobe_path

    if _ffprobe_path is not None:
        return _ffprobe_path

    # 1. ffmpegと同じディレクトリを確認
    try:
        ffmpeg_path = get_ffmpeg_path()
        ffmpeg_dir = Path(ffmpeg_path).parent

        # ffprobeの候補
        candidates = [
            ffmpeg_dir / "ffprobe",
            ffmpeg_dir / "ffprobe.exe",
        ]

        for candidate in candidates:
            if candidate.exists():
                _ffprobe_path = str(candidate)
                return _ffprobe_path
    except RuntimeError:
        pass

    # 2. システムのffprobeを試行
    system_ffprobe = shutil.which("ffprobe")
    if system_ffprobe:
        _ffprobe_path = system_ffprobe
        return _ffprobe_path

    raise RuntimeError(
        "FFprobeが見つかりません。\n"
        "FFmpegをインストールすると通常ffprobeも含まれます。\n"
        "- macOS: brew install ffmpeg\n"
        "- Windows: https://ffmpeg.org/download.html からダウンロード"
    )


def check_ffmpeg_available() -> bool:
    """FFmpegが利用可能かチェック"""
    try:
        get_ffmpeg_path()
        return True
    except RuntimeError:
        return False


def check_ffprobe_available() -> bool:
    """FFprobeが利用可能かチェック"""
    try:
        get_ffprobe_path()
        return True
    except RuntimeError:
        return False


def get_ffmpeg_version() -> Optional[str]:
    """FFmpegのバージョンを取得"""
    try:
        ffmpeg = get_ffmpeg_path()
        result = subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # 最初の行からバージョンを抽出
        first_line = result.stdout.split('\n')[0]
        return first_line
    except Exception:
        return None
