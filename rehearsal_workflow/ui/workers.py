"""
workers.py - バックグラウンドワーカー

音声結合、動画書出などの長時間処理を別スレッドで実行。
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple

from PySide6.QtCore import QThread, Signal, QObject

from .models import (
    ChapterInfo,
    ColorspaceInfo,
    get_encoder_args,
    detect_system_font,
)
from .ffmpeg_utils import get_ffmpeg_path, get_ffprobe_path


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
                        [get_ffprobe_path(), '-v', 'quiet', '-show_entries', 'format=duration',
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
            concat_cmd = [get_ffmpeg_path(), '-y', '-f', 'concat', '-safe', '0',
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
                 cut_excluded: bool = True,
                 cover_image: Optional[str] = None,
                 is_audio_only: bool = False,
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
        self.cut_excluded = cut_excluded  # 除外区間をカットするかどうか
        self.cover_image = cover_image  # カバー画像パス（音声のみの場合）
        self.is_audio_only = is_audio_only  # 音声のみ入力フラグ
        self._temp_files: List[str] = []  # 一時ファイル管理
        self.font_path = detect_system_font()  # プラットフォーム別フォント
        self._cancelled = False  # キャンセルフラグ
        self._process: Optional[subprocess.Popen] = None  # ffmpegプロセス

        # 除外チャプターの処理
        self._excluded_segments: List[Tuple[int, int]] = []  # (start_ms, end_ms)
        self._keep_segments: List[Tuple[int, int]] = []  # (start_ms, end_ms)
        self._adjusted_chapters: List[ChapterInfo] = []  # 時間調整後のチャプター
        self._adjusted_duration_ms: int = 0  # 調整後の動画長
        if self.cut_excluded:
            self._process_excluded_chapters()
        else:
            # カットしない場合は通常処理（全チャプターをそのまま使用）
            self._keep_segments = [(0, self.total_duration_ms)] if self.total_duration_ms > 0 else []
            self._adjusted_chapters = self.chapters.copy()
            self._adjusted_duration_ms = self.total_duration_ms

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
        """除外区間があり、かつカットが有効かどうか"""
        return self.cut_excluded and len(self._excluded_segments) > 0

    def _create_trim_concat_filter(self) -> str:
        """
        除外区間をカットして結合するffmpegフィルターを生成

        Returns:
            複合フィルター文字列
        """
        if not self._keep_segments:
            return ""

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

    def _escape_ffmetadata(self, text: str) -> str:
        """FFMETADATA形式用のエスケープ処理

        FFMETADATAではバックスラッシュ、等号、セミコロン、シャープ、改行をエスケープする必要がある。
        """
        # バックスラッシュを最初にエスケープ（他のエスケープに影響しないよう）
        text = text.replace('\\', '\\\\')
        # その他の特殊文字をエスケープ
        text = text.replace('=', '\\=')
        text = text.replace(';', '\\;')
        text = text.replace('#', '\\#')
        text = text.replace('\n', '\\\n')
        return text

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
                title = self._escape_ffmetadata(Path(self.output_file).stem)
                f.write(f"title={title}\n")

            # チャプターを埋め込む場合
            if self.embed_chapters and chapters_to_use:
                for i, ch in enumerate(chapters_to_use):
                    # 次のチャプターの開始時間または動画終了時間をENDとする
                    if i + 1 < len(chapters_to_use):
                        end_ms = chapters_to_use[i + 1].time_ms
                    else:
                        end_ms = duration_to_use if duration_to_use > 0 else ch.time_ms + 60000

                    escaped_title = self._escape_ffmetadata(ch.title)
                    f.write("\n[CHAPTER]\n")
                    f.write("TIMEBASE=1/1000\n")
                    f.write(f"START={ch.time_ms}\n")
                    f.write(f"END={end_ms}\n")
                    f.write(f"title={escaped_title}\n")

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
        """チャプタータイトル表示用のdrawtextフィルターを生成"""
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

            # drawtext フィルター
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

    def _create_audio_trim_filter(self) -> str:
        """音声の除外区間をカットして結合するffmpegフィルターを生成"""
        if not self._keep_segments:
            return ""

        audio_parts = []
        audio_labels = []

        for i, (start_ms, end_ms) in enumerate(self._keep_segments):
            start_sec = start_ms / 1000.0
            end_sec = end_ms / 1000.0

            # 音声のatrimフィルター（入力1が音声）
            audio_parts.append(
                f"[1:a]atrim=start={start_sec:.3f}:end={end_sec:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
            audio_labels.append(f"[a{i}]")

        n = len(self._keep_segments)

        # 音声のconcat
        audio_filter = ";".join(audio_parts)
        audio_filter += f";{''.join(audio_labels)}concat=n={n}:v=0:a=1[outa]"

        return audio_filter

    def _export_audio_with_cover(self):
        """音声ファイル + カバー画像 → 動画としてエクスポート

        video_chapter_editor.py と同じ処理:
        - 除外区間（--で始まるチャプター）のカット
        - 調整後チャプター時間の使用
        - チャプター埋め込み、タイトル焼き込み
        """
        self.progress_update.emit("音声 + カバー画像からMP4を生成します...")

        # カバー画像がない場合は黒背景を生成
        if not self.cover_image or not os.path.exists(self.cover_image):
            self.progress_update.emit("カバー画像なし: 黒背景を使用")
            # 黒背景の一時画像を生成
            black_image = os.path.join(tempfile.gettempdir(), "black_cover.jpg")
            black_cmd = [
                get_ffmpeg_path(), '-y',
                '-f', 'lavfi', '-i', 'color=c=black:s=1280x720:d=1',
                '-frames:v', '1',
                black_image
            ]
            subprocess.run(black_cmd, capture_output=True)
            self.cover_image = black_image
            self._temp_files.append(black_image)

        # 除外区間の処理状況を判定
        has_excluded = self._has_excluded_segments()

        # 使用するチャプターと長さを決定
        chapters_to_use = self._adjusted_chapters if has_excluded else self.chapters
        duration_to_use = self._adjusted_duration_ms if has_excluded else self.total_duration_ms

        # 除外区間の情報を表示
        if has_excluded:
            excluded_count = len(self._excluded_segments)
            excluded_duration = sum(end - start for start, end in self._excluded_segments)
            self.progress_update.emit(f"除外区間: {excluded_count}件 (計 {excluded_duration // 1000}秒)")
            self.progress_update.emit(f"保持区間: {len(self._keep_segments)}件")

        # メタデータファイルを生成（調整後の時間を使用）
        metadata_file = None
        if self.embed_chapters or self.embed_title:
            metadata_file = self._create_metadata_file()
            self.progress_update.emit(f"メタデータファイル生成")

        # チャプタータイトル用テキストファイルを生成（調整後チャプターを使用）
        textfiles = []
        if self.overlay_chapter_titles and chapters_to_use:
            textfiles = self._create_chapter_textfiles(chapters_to_use)

        # エンコーダ引数を取得（静止画なのでCRF 32で十分）
        encoder_args = get_encoder_args(self.encoder_id, self.bitrate_kbps, crf=32)

        # ffmpegコマンドを構築
        # -loop 1: 画像をループ
        cmd = [
            get_ffmpeg_path(), '-y',
            '-loop', '1',
            '-i', self.cover_image,
            '-i', self.input_file,
        ]

        # メタデータファイルがある場合は追加
        metadata_input_index = 2  # 0=画像, 1=音声, 2=メタデータ
        if metadata_file:
            cmd.extend(['-i', metadata_file, '-map_metadata', str(metadata_input_index)])

        # 除外区間がある場合は複合フィルターを使用
        if has_excluded:
            # 音声のトリム＆結合フィルター
            audio_trim_filter = self._create_audio_trim_filter()

            # 映像フィルター（カバー画像はループなのでトリム不要）
            vf_parts = []

            # チャプタータイトル焼き込み（調整後の時間で）
            if self.overlay_chapter_titles and chapters_to_use and textfiles:
                self.progress_update.emit(f"チャプタータイトル: {len(chapters_to_use)}件を焼き込み")
                for i, ch in enumerate(chapters_to_use):
                    start_sec = ch.time_ms / 1000.0
                    if i + 1 < len(chapters_to_use):
                        end_sec = chapters_to_use[i + 1].time_ms / 1000.0
                    else:
                        end_sec = duration_to_use / 1000.0 if duration_to_use > 0 else start_sec + 3600

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
                    vf_parts.append(drawtext)

            # パディング追加（偶数サイズ保証）
            vf_parts.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            vf = ",".join(vf_parts)

            # 複合フィルター: 映像フィルター + 音声トリム
            combined_filter = f"[0:v]{vf}[outv];{audio_trim_filter}"

            cmd.extend([
                '-filter_complex', combined_filter,
                '-map', '[outv]',
                '-map', '[outa]',
            ] + encoder_args + [
                '-tune', 'stillimage',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '192k',
                '-movflags', '+faststart',
            ])

            # 出力長を調整後の長さに制限
            adjusted_sec = duration_to_use / 1000.0
            cmd.extend(['-t', f'{adjusted_sec:.3f}'])

        else:
            # 除外区間なし: 通常処理
            vf_parts = []

            # チャプタータイトル焼き込み
            if self.overlay_chapter_titles and chapters_to_use and textfiles:
                self.progress_update.emit(f"チャプタータイトル: {len(chapters_to_use)}件を焼き込み")
                for i, ch in enumerate(chapters_to_use):
                    start_sec = ch.time_ms / 1000.0
                    if i + 1 < len(chapters_to_use):
                        end_sec = chapters_to_use[i + 1].time_ms / 1000.0
                    else:
                        end_sec = duration_to_use / 1000.0 if duration_to_use > 0 else start_sec + 3600

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
                    vf_parts.append(drawtext)

            # パディング追加（偶数サイズ保証）
            vf_parts.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            vf = ",".join(vf_parts)

            cmd.extend([
                '-vf', vf,
                '-map', '0:v',
                '-map', '1:a',
            ] + encoder_args + [
                '-tune', 'stillimage',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '192k',
                '-shortest',
                '-movflags', '+faststart',
            ])

        # チャプター埋め込み
        if self.embed_chapters and chapters_to_use and metadata_file:
            cmd.extend(['-map_chapters', str(metadata_input_index)])

        cmd.append(self.output_file)

        self.progress_update.emit(f"コマンド: {' '.join(cmd[:10])}...")
        if has_excluded:
            self.progress_update.emit("除外区間をカット＆再エンコード中...")
        else:
            self.progress_update.emit("エンコード中...")

        # ffmpegを実行
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # stderrから進捗を読み取る（調整後の長さを使用）
        stderr_output = []
        total_sec = duration_to_use / 1000.0 if duration_to_use > 0 else 0

        while True:
            if self._cancelled:
                self._process.kill()
                self._process.wait()
                self._cleanup_temp_files()
                if os.path.exists(self.output_file):
                    os.remove(self.output_file)
                self.error_occurred.emit("エクスポートを中止しました")
                return

            line = self._process.stderr.readline()
            if not line and self._process.poll() is not None:
                break
            if line:
                stderr_output.append(line)
                match = re.search(r'time=(\d+):(\d+):(\d+)\.(\d+)', line)
                if match and total_sec > 0:
                    h, m, s, cs = map(int, match.groups())
                    current_sec = h * 3600 + m * 60 + s + cs / 100.0
                    percent = min(int(current_sec / total_sec * 100), 99)
                    time_str = f"{h}:{m:02d}:{s:02d}"
                    self.progress_percent.emit(percent, time_str)

        returncode = self._process.wait()
        self._process = None

        self._cleanup_temp_files()

        if returncode != 0:
            error_text = ''.join(stderr_output[-20:])
            self.error_occurred.emit(f"ffmpegエラー (code={returncode}): {error_text[:500]}")
            return

        # 出力ファイルの確認
        if os.path.exists(self.output_file):
            file_size = os.path.getsize(self.output_file)
            size_mb = file_size / (1024 * 1024)
            self.progress_percent.emit(100, "完了")
            self.progress_update.emit(f"書出完了: {size_mb:.1f} MB")

            # チャプターファイルを保存（調整後の時間を使用）
            if chapters_to_use:
                chapter_file_path = Path(self.output_file).with_suffix('.chapters')
                with open(chapter_file_path, 'w', encoding='utf-8') as f:
                    for ch in chapters_to_use:
                        f.write(f"{ch.time_str} {ch.title}\n")
                self.progress_update.emit(f"チャプター保存: {chapter_file_path.name}")

            self.export_completed.emit(self.output_file)
        else:
            self.error_occurred.emit("出力ファイルが生成されませんでした")

    def run(self):
        """バックグラウンドで書出処理を実行"""
        try:
            self.progress_update.emit("書出を開始します...")

            # 音声のみ + カバー画像の場合は専用処理
            if self.is_audio_only:
                self._export_audio_with_cover()
                return

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
            cmd = [get_ffmpeg_path(), '-y', '-i', self.input_file]

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


class WaveformWorker(QObject):
    """波形データ生成ワーカー（別スレッドで実行）

    video_chapter_editor.py と同じ処理:
    - パイプ経由で直接データ読み込み（ディスクI/O回避）
    - 98パーセンタイル正規化（上位2%のスパイクを無視）
    - ソフトクリッピング（tanh）
    """

    # シグナル
    progress = Signal(int)  # 進捗（0-100）
    finished = Signal(object)  # 波形データ（numpy配列 or list）
    error = Signal(str)  # エラーメッセージ

    def __init__(self, file_path: str, num_samples: int = 5000):
        super().__init__()
        self._file_path = file_path
        self._num_samples = num_samples
        self._cancelled = False

    def cancel(self):
        """処理をキャンセル"""
        self._cancelled = True

    def run(self):
        """波形データを生成（別スレッドで呼び出される）"""
        try:
            import numpy as np
        except ImportError:
            # numpyがない場合はフォールバック
            self._run_without_numpy()
            return

        try:
            if self._cancelled:
                return

            self.progress.emit(5)

            # FFmpegからパイプで直接読み込み（ディスクI/O回避）
            process = subprocess.Popen([
                get_ffmpeg_path(), '-i', str(self._file_path),
                '-ac', '1',        # モノラル
                '-ar', '4000',     # 4kHz（高速化）
                '-f', 's16le',     # 生のPCMデータ
                '-acodec', 'pcm_s16le',
                '-v', 'quiet',     # 出力抑制
                '-'
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

            # データを少しずつ読み込んで進捗を更新
            chunks = []
            chunk_size = 32768  # 32KB
            bytes_read = 0
            last_progress = 5

            while True:
                if self._cancelled:
                    process.kill()
                    return

                chunk = process.stdout.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
                bytes_read += len(chunk)

                # 10%〜50%の範囲で進捗を更新（読み込みバイト数に基づく）
                # 予想サイズ: 4kHz * 2bytes * 動画秒数（不明なので推定）
                # 1分の動画で約480KB、10分で約4.8MB
                estimated_total = 5 * 1024 * 1024  # 5MB（約10分相当）
                read_progress = min(bytes_read / estimated_total, 1.0)
                current_progress = int(10 + read_progress * 40)  # 10%〜50%

                if current_progress > last_progress:
                    self.progress.emit(current_progress)
                    last_progress = current_progress

            process.wait()
            raw_data = b''.join(chunks)

            if self._cancelled:
                return

            self.progress.emit(60)

            if not raw_data:
                self.error.emit("No audio data found")
                return

            # バイトデータをnumpy配列に変換
            samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)

            if self._cancelled:
                return

            self.progress.emit(70)

            # パーセンタイルベースの正規化（極端なスパイクを無視）
            abs_samples = np.abs(samples)
            # 98パーセンタイル値で正規化（上位2%のスパイクを無視）
            percentile_val = np.percentile(abs_samples, 98)
            if percentile_val > 0:
                samples = samples / percentile_val
                # ソフトクリッピング（1.0を超えた部分を滑らかに圧縮）
                samples = np.tanh(samples)

            if self._cancelled:
                return

            self.progress.emit(85)

            # リサンプル
            if len(samples) > self._num_samples:
                indices = np.linspace(0, len(samples) - 1, self._num_samples, dtype=int)
                samples = samples[indices]

            self.progress.emit(100)
            self.finished.emit(samples)

        except subprocess.TimeoutExpired:
            self.error.emit("Waveform generation timed out")
        except RuntimeError as e:
            self.error.emit(str(e))
        except FileNotFoundError:
            self.error.emit("ffmpeg not found")
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")

    def _run_without_numpy(self):
        """numpy なしのフォールバック実装"""
        import struct

        try:
            if self._cancelled:
                return

            self.progress.emit(10)

            # ffmpegで音声をraw PCMに変換
            with tempfile.NamedTemporaryFile(suffix='.raw', delete=False) as tmp:
                tmp_path = tmp.name

            try:
                cmd = [
                    get_ffmpeg_path(), '-y', '-i', str(self._file_path),
                    '-ac', '1',
                    '-ar', '4000',
                    '-f', 's16le',
                    '-vn',
                    tmp_path
                ]

                result = subprocess.run(cmd, capture_output=True, timeout=120)

                if self._cancelled:
                    return

                self.progress.emit(50)

                if result.returncode != 0:
                    self.error.emit(f"ffmpeg error: {result.stderr.decode()[:200]}")
                    return

                with open(tmp_path, 'rb') as f:
                    raw_data = f.read()

                if self._cancelled:
                    return

                self.progress.emit(70)

                num_total = len(raw_data) // 2
                if num_total == 0:
                    self.error.emit("No audio data found")
                    return

                # サンプル抽出
                step = max(1, num_total // self._num_samples)
                samples = []

                for i in range(0, num_total, step):
                    if self._cancelled:
                        return
                    offset = i * 2
                    if offset + 2 <= len(raw_data):
                        value = struct.unpack('<h', raw_data[offset:offset+2])[0]
                        samples.append(value / 32768.0)  # 正規化（符号付き）

                self.progress.emit(90)

                if len(samples) > self._num_samples:
                    samples = samples[:self._num_samples]

                self.progress.emit(100)
                self.finished.emit(samples)

            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except subprocess.TimeoutExpired:
            self.error.emit("Waveform generation timed out")
        except RuntimeError as e:
            self.error.emit(str(e))
        except FileNotFoundError:
            self.error.emit("ffmpeg not found")
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")


class SpectrogramWorker(QObject):
    """スペクトログラム生成ワーカー（別スレッドで実行）

    メルスケール変換を使用して、演奏とトーク（話し声）を
    区別しやすいスペクトログラムを生成。
    numpyのみで実装（scipy不要）。
    """

    # シグナル
    progress = Signal(int)  # 進捗（0-100）
    finished = Signal(object)  # スペクトログラムデータ（2D numpy配列）
    error = Signal(str)  # エラーメッセージ

    def __init__(self, file_path: str, target_width: int = 1000, target_height: int = 256):
        """
        Args:
            file_path: 音声/動画ファイルパス
            target_width: 出力画像の幅（時間軸）
            target_height: 出力画像の高さ（周波数軸）
        """
        super().__init__()
        self._file_path = file_path
        self._target_width = target_width
        self._target_height = target_height
        self._cancelled = False

    def cancel(self):
        """処理をキャンセル"""
        self._cancelled = True

    def _hz_to_mel(self, hz, np):
        """HzをMelスケールに変換"""
        return 2595 * np.log10(1 + hz / 700)

    def _mel_to_hz(self, mel, np):
        """MelスケールをHzに変換"""
        return 700 * (10 ** (mel / 2595) - 1)

    def _create_mel_filterbank(self, n_fft: int, sample_rate: int, n_mels: int, np):
        """メルフィルタバンクを作成

        低周波（話し声の基本周波数やフォルマント）を拡大し、
        高周波（楽器の倍音）を圧縮することで、
        演奏とトークの違いを視覚的に強調する。
        """
        # 周波数範囲（話し声を強調するため低域を重視）
        f_min = 50  # 50Hz（話し声の基本周波数下限）
        f_max = sample_rate / 2  # ナイキスト周波数

        # メルスケールで等間隔に分割
        mel_min = self._hz_to_mel(f_min, np)
        mel_max = self._hz_to_mel(f_max, np)
        mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
        hz_points = self._mel_to_hz(mel_points, np)

        # FFTビンに変換
        bin_points = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)

        # フィルタバンク作成（三角フィルタ）
        filterbank = np.zeros((n_mels, n_fft // 2))

        for i in range(n_mels):
            left = bin_points[i]
            center = bin_points[i + 1]
            right = bin_points[i + 2]

            # 左斜面
            for j in range(left, center):
                if j < n_fft // 2 and center > left:
                    filterbank[i, j] = (j - left) / (center - left)

            # 右斜面
            for j in range(center, right):
                if j < n_fft // 2 and right > center:
                    filterbank[i, j] = (right - j) / (right - center)

        return filterbank

    def run(self):
        """メルスペクトログラムを生成（別スレッドで呼び出される）"""
        try:
            import numpy as np
        except ImportError:
            self.error.emit("numpy is required for spectrogram")
            return

        try:
            if self._cancelled:
                return

            self.progress.emit(5)

            # FFmpegで音声を抽出（22.05kHz モノラル - 音声解析に適した周波数）
            sample_rate = 22050
            process = subprocess.Popen([
                get_ffmpeg_path(), '-i', str(self._file_path),
                '-ac', '1',
                '-ar', str(sample_rate),
                '-f', 's16le',
                '-acodec', 'pcm_s16le',
                '-v', 'quiet',
                '-'
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

            # データ読み込み
            chunks = []
            chunk_size = 65536
            while True:
                if self._cancelled:
                    process.kill()
                    return
                chunk = process.stdout.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)

            process.wait()
            raw_data = b''.join(chunks)

            if self._cancelled:
                return

            self.progress.emit(20)

            if not raw_data:
                self.error.emit("No audio data found")
                return

            # バイトデータをnumpy配列に変換
            samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0

            if self._cancelled:
                return

            self.progress.emit(25)

            # STFT パラメータ（より高い周波数分解能）
            n_fft = 2048  # 長めのFFTでフォルマントを捉えやすく
            n_mels = 128  # メルバンド数
            hop_length = len(samples) // self._target_width
            hop_length = max(hop_length, 1)

            # ハニング窓
            window = np.hanning(n_fft)

            # メルフィルタバンクを作成
            mel_filterbank = self._create_mel_filterbank(n_fft, sample_rate, n_mels, np)

            self.progress.emit(30)

            # STFT計算
            n_frames = (len(samples) - n_fft) // hop_length + 1
            if n_frames <= 0:
                self.error.emit("Audio too short for spectrogram")
                return

            mel_spectrogram = np.zeros((n_mels, n_frames), dtype=np.float32)

            for i in range(n_frames):
                if self._cancelled:
                    return

                start = i * hop_length
                frame = samples[start:start + n_fft]

                if len(frame) < n_fft:
                    frame = np.pad(frame, (0, n_fft - len(frame)))

                # 窓関数適用 + FFT
                windowed = frame * window
                fft_result = np.fft.rfft(windowed)

                # パワースペクトル
                power = np.abs(fft_result[:n_fft // 2]) ** 2

                # メルフィルタバンク適用
                mel_power = np.dot(mel_filterbank, power)
                mel_spectrogram[:, i] = mel_power

                # 進捗更新（30% - 75%）
                if i % 100 == 0:
                    progress = 30 + int(45 * i / n_frames)
                    self.progress.emit(progress)

            if self._cancelled:
                return

            self.progress.emit(80)

            # 対数スケールに変換（dB）
            mel_spectrogram = np.log10(mel_spectrogram + 1e-10) * 10

            # ダイナミックレンジ圧縮（話し声と演奏の差を強調）
            # 下位10%をカット（ノイズ除去）
            threshold = np.percentile(mel_spectrogram, 10)
            mel_spectrogram = np.maximum(mel_spectrogram, threshold)

            self.progress.emit(85)

            # 正規化（0-1）
            min_db = mel_spectrogram.min()
            max_db = mel_spectrogram.max()
            if max_db > min_db:
                mel_spectrogram = (mel_spectrogram - min_db) / (max_db - min_db)
            else:
                mel_spectrogram = np.zeros_like(mel_spectrogram)

            # コントラスト強調（ガンマ補正）
            # γ < 1 で暗部を持ち上げ、中間調の差を強調
            gamma = 0.7
            mel_spectrogram = np.power(mel_spectrogram, gamma)

            self.progress.emit(90)

            # 周波数軸を反転（低周波が下）
            mel_spectrogram = mel_spectrogram[::-1, :]

            # ターゲットサイズにリサイズ
            if mel_spectrogram.shape[1] != self._target_width or mel_spectrogram.shape[0] != self._target_height:
                # 簡易リサイズ（最近傍補間）
                x_indices = np.linspace(0, mel_spectrogram.shape[1] - 1, self._target_width).astype(int)
                y_indices = np.linspace(0, mel_spectrogram.shape[0] - 1, self._target_height).astype(int)
                mel_spectrogram = mel_spectrogram[np.ix_(y_indices, x_indices)]

            self.progress.emit(100)
            self.finished.emit(mel_spectrogram)

        except subprocess.TimeoutExpired:
            self.error.emit("Spectrogram generation timed out")
        except RuntimeError as e:
            self.error.emit(str(e))
        except FileNotFoundError:
            self.error.emit("ffmpeg not found")
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")
