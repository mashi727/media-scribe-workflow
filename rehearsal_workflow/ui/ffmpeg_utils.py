"""
ffmpeg_utils.py - FFmpeg/FFprobe パス解決ユーティリティ

PyInstallerでバンドルされた環境でも動作するよう、
imageio-ffmpegまたはシステムのffmpegを自動検出する。
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any

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

    raise RuntimeError("FFmpegが見つかりません")


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

    raise RuntimeError("FFprobeが見つかりません")


def get_subprocess_kwargs(timeout: int = 30, capture_output: bool = True) -> Dict[str, Any]:
    """
    クロスプラットフォーム対応のsubprocess.run() kwargs を取得

    Windowsでは:
    - コンソールウィンドウを非表示 (CREATE_NO_WINDOW)
    - UTF-8エンコーディングを明示的に指定
    - エンコーディングエラーを置換

    Args:
        timeout: タイムアウト秒数
        capture_output: 出力をキャプチャするかどうか

    Returns:
        subprocess.run() に渡すkwargs
    """
    kwargs: Dict[str, Any] = {
        'text': True,
        'timeout': timeout,
        'encoding': 'utf-8',
        'errors': 'replace',
    }
    if capture_output:
        kwargs['capture_output'] = True

    # Windowsではコンソールウィンドウを非表示
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

    return kwargs


def get_popen_kwargs() -> Dict[str, Any]:
    """
    クロスプラットフォーム対応のsubprocess.Popen() kwargs を取得

    Windowsではコンソールウィンドウを非表示にする。

    Returns:
        subprocess.Popen() に渡すkwargs (creationflagsのみ)
    """
    kwargs: Dict[str, Any] = {}

    # Windowsではコンソールウィンドウを非表示
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

    return kwargs


def extract_chapters_with_ffmpeg(file_path: str) -> list:
    """
    ffmpegの出力からチャプター情報を抽出（ffprobeの代替）

    ffmpegの -i オプションの出力をパースしてチャプター情報を取得。
    imageio-ffmpegにはffprobeが含まれないため、このフォールバックを使用。

    Args:
        file_path: メディアファイルパス

    Returns:
        チャプター情報のリスト [{"start_time": float, "title": str}, ...]
    """
    import re

    try:
        ffmpeg = get_ffmpeg_path()
        kwargs = get_subprocess_kwargs(timeout=30)

        result = subprocess.run([ffmpeg, '-i', file_path], **kwargs)
        # ffmpegは入力のみの場合、returncode=1で終了するがstderrに情報が出力される
        output = result.stderr if result.stderr else ""

        chapters = []
        # Chapter #0:0: start 0.000000, end 180.000000
        #   Metadata:
        #     title           : Chapter Title
        chapter_pattern = re.compile(
            r'Chapter #\d+:\d+: start (\d+\.?\d*), end (\d+\.?\d*)'
        )
        title_pattern = re.compile(r'^\s+title\s*:\s*(.+)$', re.MULTILINE)

        lines = output.split('\n')
        i = 0
        while i < len(lines):
            match = chapter_pattern.search(lines[i])
            if match:
                start_time = float(match.group(1))
                # 次の行からタイトルを探す
                title = f"Chapter {len(chapters) + 1}"
                for j in range(i + 1, min(i + 5, len(lines))):
                    title_match = title_pattern.match(lines[j])
                    if title_match:
                        title = title_match.group(1).strip()
                        break
                    # 次のChapterが始まったら終了
                    if 'Chapter #' in lines[j]:
                        break
                chapters.append({
                    "start_time": start_time,
                    "title": title
                })
            i += 1

        return chapters

    except Exception:
        return []


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
        kwargs = get_subprocess_kwargs(timeout=5)

        result = subprocess.run([ffmpeg, "-version"], **kwargs)
        # 最初の行からバージョンを抽出
        if result.stdout:
            first_line = result.stdout.split('\n')[0]
            return first_line
        return None
    except Exception:
        return None
