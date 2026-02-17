"""
state.py - イミュータブルなデータモデル

設計書に基づく新しいClipベースのデータモデル。
全てのデータクラスは frozen=True でイミュータブル。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional


# =============================================================================
# 時間フォーマットユーティリティ
# =============================================================================

def format_time_ms(time_ms: int, include_ms: bool = True) -> str:
    """ミリ秒を時間文字列に変換するヘルパー関数"""
    total_sec = time_ms // 1000
    ms = time_ms % 1000
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if include_ms:
        return f"{h}:{m:02d}:{s:02d}.{ms:03d}"
    return f"{h}:{m:02d}:{s:02d}"


def parse_time_str(time_str: str) -> int:
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


# =============================================================================
# 基本データ型（イミュータブル）
# =============================================================================

@dataclass(frozen=True)
class SourceFile:
    """ソースファイル（イミュータブル）

    ソースファイルはプールに格納され、Clipから参照される。
    IDによる参照を使用することで、同一ソースを複数Clipで共有可能。
    """
    id: str
    path: Path
    duration_ms: int
    file_type: str  # "mp4", "mov", "mp3", etc.

    @staticmethod
    def create(path: Path, duration_ms: int) -> SourceFile:
        """新しいSourceFileを生成"""
        return SourceFile(
            id=str(uuid.uuid4()),
            path=path,
            duration_ms=duration_ms,
            file_type=path.suffix[1:].lower() if path.suffix else ""
        )

    @property
    def duration_str(self) -> str:
        """HH:MM:SS形式"""
        return format_time_ms(self.duration_ms, include_ms=False)

    @property
    def is_audio_only(self) -> bool:
        """音声ファイルかどうか"""
        return self.file_type in ("mp3", "m4a", "aac", "wav", "flac", "ogg")


@dataclass(frozen=True)
class ClipChapter:
    """Clip内のチャプター（イミュータブル）

    チャプターはClipに紐づき、Clipと共に移動する。
    offset_msはClip先頭からの相対位置。
    """
    id: str
    offset_ms: int  # Clip先頭からの相対位置
    title: str
    is_excluded: bool = False  # "--"プレフィックス相当

    @staticmethod
    def create(offset_ms: int, title: str) -> ClipChapter:
        """新しいClipChapterを生成"""
        return ClipChapter(
            id=str(uuid.uuid4()),
            offset_ms=offset_ms,
            title=title,
            is_excluded=title.startswith("--")
        )

    @property
    def time_str(self) -> str:
        """HH:MM:SS.mmm形式"""
        return format_time_ms(self.offset_ms)

    @property
    def time_str_youtube(self) -> str:
        """YouTube用 HH:MM:SS形式"""
        return format_time_ms(self.offset_ms, include_ms=False)

    def with_offset(self, new_offset_ms: int) -> ClipChapter:
        """オフセットを変更した新しいClipChapterを返す"""
        return ClipChapter(
            id=self.id,
            offset_ms=new_offset_ms,
            title=self.title,
            is_excluded=self.is_excluded
        )

    def with_title(self, new_title: str) -> ClipChapter:
        """タイトルを変更した新しいClipChapterを返す"""
        return ClipChapter(
            id=self.id,
            offset_ms=self.offset_ms,
            title=new_title,
            is_excluded=new_title.startswith("--")
        )


@dataclass(frozen=True)
class Clip:
    """タイムライン上の基本単位（イミュータブル）

    Clipはソースファイルの一部分を参照する。
    in_point_ms/out_point_msはソース内の絶対位置。
    """
    id: str
    source_id: str  # SourceFile.id への参照
    in_point_ms: int  # ソース内IN点
    out_point_ms: int  # ソース内OUT点
    chapters: tuple[ClipChapter, ...] = field(default_factory=tuple)

    @property
    def duration_ms(self) -> int:
        """Clipの長さ（ミリ秒）"""
        return self.out_point_ms - self.in_point_ms

    @property
    def duration_str(self) -> str:
        """HH:MM:SS形式"""
        return format_time_ms(self.duration_ms, include_ms=False)

    @staticmethod
    def create(
        source_id: str,
        in_point_ms: int,
        out_point_ms: int,
        chapters: tuple[ClipChapter, ...] = ()
    ) -> Clip:
        """新しいClipを生成"""
        return Clip(
            id=str(uuid.uuid4()),
            source_id=source_id,
            in_point_ms=in_point_ms,
            out_point_ms=out_point_ms,
            chapters=chapters
        )

    @staticmethod
    def from_source(source: SourceFile) -> Clip:
        """ソースファイル全体からClipを生成"""
        return Clip.create(
            source_id=source.id,
            in_point_ms=0,
            out_point_ms=source.duration_ms,
            chapters=(ClipChapter.create(0, source.path.stem),)
        )

    def with_chapters(self, chapters: tuple[ClipChapter, ...]) -> Clip:
        """チャプターを更新した新しいClipを返す"""
        return Clip(
            id=self.id,
            source_id=self.source_id,
            in_point_ms=self.in_point_ms,
            out_point_ms=self.out_point_ms,
            chapters=chapters
        )

    def with_in_out(self, in_point_ms: int, out_point_ms: int) -> Clip:
        """IN/OUT点を更新した新しいClipを返す"""
        return Clip(
            id=self.id,
            source_id=self.source_id,
            in_point_ms=in_point_ms,
            out_point_ms=out_point_ms,
            chapters=self.chapters
        )

    def add_chapter(self, chapter: ClipChapter) -> Clip:
        """チャプターを追加した新しいClipを返す"""
        # オフセット順にソート
        new_chapters = tuple(
            sorted(
                self.chapters + (chapter,),
                key=lambda ch: ch.offset_ms
            )
        )
        return self.with_chapters(new_chapters)

    def remove_chapter(self, chapter_id: str) -> Clip:
        """チャプターを削除した新しいClipを返す"""
        new_chapters = tuple(ch for ch in self.chapters if ch.id != chapter_id)
        return self.with_chapters(new_chapters)

    def split(self, split_offset_ms: int) -> tuple[Clip, Clip]:
        """Clipを分割

        Args:
            split_offset_ms: Clip内の分割位置（Clip先頭からの相対位置）

        Returns:
            (前半Clip, 後半Clip)
        """
        split_point_in_source = self.in_point_ms + split_offset_ms

        # 前半Clip: 分割点より前のチャプターを保持
        chapters_a = tuple(
            ch for ch in self.chapters
            if ch.offset_ms < split_offset_ms
        )

        # 後半Clip: 分割点以降のチャプターのオフセットを再計算
        chapters_b = tuple(
            ch.with_offset(ch.offset_ms - split_offset_ms)
            for ch in self.chapters
            if ch.offset_ms >= split_offset_ms
        )

        clip_a = Clip(
            id=str(uuid.uuid4()),
            source_id=self.source_id,
            in_point_ms=self.in_point_ms,
            out_point_ms=split_point_in_source,
            chapters=chapters_a
        )

        clip_b = Clip(
            id=str(uuid.uuid4()),
            source_id=self.source_id,
            in_point_ms=split_point_in_source,
            out_point_ms=self.out_point_ms,
            chapters=chapters_b
        )

        return clip_a, clip_b


# =============================================================================
# タイムライン
# =============================================================================

@dataclass(frozen=True)
class VirtualTimeline:
    """仮想タイムライン（イミュータブル）

    Clipの順序付きリスト。タイムライン位置とClip位置の相互変換を提供。
    """
    clips: tuple[Clip, ...] = field(default_factory=tuple)

    @property
    def duration_ms(self) -> int:
        """タイムライン全体の長さ"""
        return sum(clip.duration_ms for clip in self.clips)

    @property
    def duration_str(self) -> str:
        """HH:MM:SS形式"""
        return format_time_ms(self.duration_ms, include_ms=False)

    @property
    def clip_count(self) -> int:
        """Clip数"""
        return len(self.clips)

    @property
    def is_empty(self) -> bool:
        """空かどうか"""
        return len(self.clips) == 0

    def get_clip_offsets(self) -> tuple[int, ...]:
        """各Clipの開始オフセット（累積）"""
        offsets: list[int] = []
        cumulative = 0
        for clip in self.clips:
            offsets.append(cumulative)
            cumulative += clip.duration_ms
        return tuple(offsets)

    def timeline_to_clip(self, timeline_pos_ms: int) -> tuple[int, int]:
        """タイムライン位置 → (clip_index, offset_in_clip)

        Args:
            timeline_pos_ms: タイムライン上の位置（ミリ秒）

        Returns:
            (clip_index, offset_in_clip) のタプル
        """
        cumulative = 0
        for idx, clip in enumerate(self.clips):
            if cumulative + clip.duration_ms > timeline_pos_ms:
                return (idx, timeline_pos_ms - cumulative)
            cumulative += clip.duration_ms
        # 末尾
        if self.clips:
            return (len(self.clips) - 1, self.clips[-1].duration_ms)
        return (0, 0)

    def clip_to_timeline(self, clip_index: int, offset_in_clip: int) -> int:
        """(clip_index, offset_in_clip) → タイムライン位置

        Args:
            clip_index: Clipのインデックス
            offset_in_clip: Clip内のオフセット（ミリ秒）

        Returns:
            タイムライン上の位置（ミリ秒）
        """
        offsets = self.get_clip_offsets()
        if 0 <= clip_index < len(offsets):
            return offsets[clip_index] + offset_in_clip
        return 0

    def clip_to_source(self, clip_index: int, offset_in_clip: int) -> int:
        """Clip内オフセット → ソース内位置

        Args:
            clip_index: Clipのインデックス
            offset_in_clip: Clip内のオフセット（ミリ秒）

        Returns:
            ソース内の位置（ミリ秒）
        """
        if 0 <= clip_index < len(self.clips):
            clip = self.clips[clip_index]
            return clip.in_point_ms + offset_in_clip
        return 0

    def get_clip_by_id(self, clip_id: str) -> Optional[Clip]:
        """IDでClipを検索"""
        for clip in self.clips:
            if clip.id == clip_id:
                return clip
        return None

    def get_clip_index_by_id(self, clip_id: str) -> Optional[int]:
        """IDでClipのインデックスを検索"""
        for idx, clip in enumerate(self.clips):
            if clip.id == clip_id:
                return idx
        return None

    # ========================================
    # 更新メソッド（新しいVirtualTimelineを返す）
    # ========================================

    def with_clips(self, clips: tuple[Clip, ...]) -> VirtualTimeline:
        """Clipリストを置き換えた新しいVirtualTimelineを返す"""
        return VirtualTimeline(clips=clips)

    def add_clip(self, clip: Clip) -> VirtualTimeline:
        """Clipを末尾に追加した新しいVirtualTimelineを返す"""
        return self.with_clips(self.clips + (clip,))

    def insert_clip(self, index: int, clip: Clip) -> VirtualTimeline:
        """指定位置にClipを挿入した新しいVirtualTimelineを返す"""
        new_clips = self.clips[:index] + (clip,) + self.clips[index:]
        return self.with_clips(new_clips)

    def remove_clip(self, index: int) -> VirtualTimeline:
        """Clipを削除した新しいVirtualTimelineを返す"""
        if 0 <= index < len(self.clips):
            new_clips = self.clips[:index] + self.clips[index + 1:]
            return self.with_clips(new_clips)
        return self

    def move_clip(self, from_index: int, to_index: int) -> VirtualTimeline:
        """Clipを移動した新しいVirtualTimelineを返す"""
        if not (0 <= from_index < len(self.clips) and 0 <= to_index < len(self.clips)):
            return self

        clips_list = list(self.clips)
        clip = clips_list.pop(from_index)
        clips_list.insert(to_index, clip)
        return self.with_clips(tuple(clips_list))

    def update_clip(self, index: int, clip: Clip) -> VirtualTimeline:
        """指定位置のClipを更新した新しいVirtualTimelineを返す"""
        if 0 <= index < len(self.clips):
            new_clips = self.clips[:index] + (clip,) + self.clips[index + 1:]
            return self.with_clips(new_clips)
        return self

    def split_clip(self, clip_index: int, split_offset_ms: int) -> VirtualTimeline:
        """Clipを分割した新しいVirtualTimelineを返す"""
        if not (0 <= clip_index < len(self.clips)):
            return self

        clip = self.clips[clip_index]
        if not (0 < split_offset_ms < clip.duration_ms):
            return self

        clip_a, clip_b = clip.split(split_offset_ms)
        new_clips = self.clips[:clip_index] + (clip_a, clip_b) + self.clips[clip_index + 1:]
        return self.with_clips(new_clips)


# =============================================================================
# 再生状態
# =============================================================================

class PlaybackStatus(Enum):
    """再生ステータス"""
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()
    SEEKING = auto()
    BUFFERING = auto()


@dataclass(frozen=True)
class PlaybackState:
    """再生状態（イミュータブル）"""
    status: PlaybackStatus = PlaybackStatus.STOPPED
    position_ms: int = 0  # タイムライン上の位置

    @property
    def is_playing(self) -> bool:
        return self.status == PlaybackStatus.PLAYING

    @property
    def is_paused(self) -> bool:
        return self.status == PlaybackStatus.PAUSED

    @property
    def is_stopped(self) -> bool:
        return self.status == PlaybackStatus.STOPPED

    def with_status(self, status: PlaybackStatus) -> PlaybackState:
        """ステータスを変更した新しいPlaybackStateを返す"""
        return PlaybackState(status=status, position_ms=self.position_ms)

    def with_position(self, position_ms: int) -> PlaybackState:
        """位置を変更した新しいPlaybackStateを返す"""
        return PlaybackState(status=self.status, position_ms=position_ms)

    def play(self) -> PlaybackState:
        """再生開始"""
        return self.with_status(PlaybackStatus.PLAYING)

    def pause(self) -> PlaybackState:
        """一時停止"""
        return self.with_status(PlaybackStatus.PAUSED)

    def stop(self) -> PlaybackState:
        """停止"""
        return PlaybackState(status=PlaybackStatus.STOPPED, position_ms=0)

    def seek(self, position_ms: int) -> PlaybackState:
        """シーク"""
        return PlaybackState(status=PlaybackStatus.SEEKING, position_ms=position_ms)


# =============================================================================
# エクスポート設定
# =============================================================================

class EncoderType(Enum):
    """エンコーダー種別"""
    LIBX264 = "libx264"
    LIBX265 = "libx265"
    H264_VIDEOTOOLBOX = "h264_videotoolbox"  # macOS HW
    HEVC_VIDEOTOOLBOX = "hevc_videotoolbox"  # macOS HW
    H264_NVENC = "h264_nvenc"  # NVIDIA HW
    HEVC_NVENC = "hevc_nvenc"  # NVIDIA HW
    H264_QSV = "h264_qsv"  # Intel QSV
    H264_AMF = "h264_amf"  # AMD AMF
    COPY = "copy"  # 再エンコードなし


class QualityPreset(Enum):
    """品質プリセット"""
    HIGH = auto()  # 8Mbps / CRF 20
    MEDIUM = auto()  # 4Mbps / CRF 23
    LOW = auto()  # 2Mbps / CRF 26
    SOURCE = auto()  # ソースと同じビットレート


class OutputFormat(Enum):
    """出力形式"""
    MP4 = "mp4"
    MOV = "mov"
    MKV = "mkv"
    MP3 = "mp3"  # 音声のみ
    M4A = "m4a"  # 音声のみ


@dataclass(frozen=True)
class ColorspaceSettings:
    """色空間設定"""
    color_primaries: Optional[str] = None  # bt709, bt2020, etc.
    color_transfer: Optional[str] = None  # srgb, smpte2084 (HDR), etc.
    color_matrix: Optional[str] = None  # bt709, bt2020nc, etc.
    is_hdr: bool = False


@dataclass(frozen=True)
class OverlaySettings:
    """オーバーレイ設定"""
    enabled: bool = False
    font_name: str = "Helvetica"
    font_size: int = 48
    font_color: str = "white"
    background_color: Optional[str] = "black@0.5"  # 半透明背景
    position: str = "top"  # top, bottom, center
    margin: int = 20
    duration_sec: float = 5.0  # 表示時間


@dataclass(frozen=True)
class ChapterExportSettings:
    """チャプターエクスポート設定"""
    embed_chapters: bool = True  # メタデータに埋め込み
    cut_excluded: bool = True  # "--"チャプター区間を除外
    split_by_chapter: bool = False  # チャプターごとにファイル分割


@dataclass(frozen=True)
class AudioSettings:
    """音声設定"""
    codec: str = "aac"
    bitrate_kbps: int = 192
    sample_rate: int = 48000
    channels: int = 2


@dataclass(frozen=True)
class VideoSettings:
    """映像設定"""
    encoder: EncoderType = EncoderType.LIBX264
    quality_preset: QualityPreset = QualityPreset.MEDIUM
    bitrate_kbps: Optional[int] = None  # None = プリセットに従う
    crf: Optional[int] = None  # None = プリセットに従う
    max_width: Optional[int] = None  # リサイズ上限
    max_height: Optional[int] = None
    frame_rate: Optional[float] = None  # None = ソースのまま
    colorspace: ColorspaceSettings = field(default_factory=ColorspaceSettings)


@dataclass(frozen=True)
class ExportSettings:
    """エクスポート設定（統合）"""
    output_format: OutputFormat = OutputFormat.MP4
    video: VideoSettings = field(default_factory=VideoSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    chapters: ChapterExportSettings = field(default_factory=ChapterExportSettings)
    overlay: OverlaySettings = field(default_factory=OverlaySettings)

    # 出力ファイル名テンプレート（チャプター分割時）
    filename_template: str = "{base}_{index:02d}_{title}"

    @property
    def is_audio_only(self) -> bool:
        return self.output_format in (OutputFormat.MP3, OutputFormat.M4A)


# =============================================================================
# エクスポートスナップショット
# =============================================================================

class ExportStatus(Enum):
    """エクスポートステータス"""
    IDLE = auto()
    PREPARING = auto()
    ENCODING = auto()
    SPLITTING = auto()
    COMPLETED = auto()
    ERROR = auto()
    CANCELLED = auto()


@dataclass(frozen=True)
class ExportSnapshot:
    """エクスポート用スナップショット（イミュータブル）

    エンコード開始時点のデータをキャプチャ。
    エンコード中も元のタイムラインは編集可能。
    """
    # スナップショット対象のデータ
    sources: tuple[SourceFile, ...]
    timeline: VirtualTimeline

    # 出力先
    output_dir: Path
    output_base_name: str

    # 設定
    settings: ExportSettings

    # カバー画像（音声ファイル用）
    cover_image_path: Optional[Path] = None

    # 状態
    status: ExportStatus = ExportStatus.IDLE
    progress_percent: int = 0
    current_phase: str = ""  # "Extracting", "Encoding", "Merging", etc.
    error_message: Optional[str] = None

    # 結果
    output_files: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def output_path(self) -> Path:
        """単一ファイル出力時のパス"""
        ext = self.settings.output_format.value
        return self.output_dir / f"{self.output_base_name}.{ext}"

    @property
    def is_split_export(self) -> bool:
        return self.settings.chapters.split_by_chapter

    @property
    def is_completed(self) -> bool:
        return self.status == ExportStatus.COMPLETED

    @property
    def is_error(self) -> bool:
        return self.status == ExportStatus.ERROR

    @property
    def is_running(self) -> bool:
        return self.status in (ExportStatus.PREPARING, ExportStatus.ENCODING, ExportStatus.SPLITTING)

    def with_status(self, status: ExportStatus) -> ExportSnapshot:
        """ステータスを変更した新しいExportSnapshotを返す"""
        return ExportSnapshot(
            sources=self.sources,
            timeline=self.timeline,
            output_dir=self.output_dir,
            output_base_name=self.output_base_name,
            settings=self.settings,
            cover_image_path=self.cover_image_path,
            status=status,
            progress_percent=self.progress_percent,
            current_phase=self.current_phase,
            error_message=self.error_message,
            output_files=self.output_files
        )

    def with_progress(self, percent: int, phase: str = "") -> ExportSnapshot:
        """進捗を更新した新しいExportSnapshotを返す"""
        return ExportSnapshot(
            sources=self.sources,
            timeline=self.timeline,
            output_dir=self.output_dir,
            output_base_name=self.output_base_name,
            settings=self.settings,
            cover_image_path=self.cover_image_path,
            status=self.status,
            progress_percent=percent,
            current_phase=phase if phase else self.current_phase,
            error_message=self.error_message,
            output_files=self.output_files
        )


# =============================================================================
# アプリケーション状態（ルート）
# =============================================================================

@dataclass(frozen=True)
class AppState:
    """アプリケーション全体の状態（イミュータブル）

    単一の状態ツリー。全ての状態変更は新しいAppStateの生成を通じて行う。
    """
    # ソースプール
    sources: tuple[SourceFile, ...] = field(default_factory=tuple)

    # タイムライン
    timeline: VirtualTimeline = field(default_factory=VirtualTimeline)

    # 再生状態
    playback: PlaybackState = field(default_factory=PlaybackState)

    # エクスポート（実行中のみ）
    export: Optional[ExportSnapshot] = None

    # 作業ディレクトリ
    work_dir: Optional[Path] = None

    # 編集フラグ
    is_modified: bool = False

    # プロジェクトファイルパス
    project_path: Optional[Path] = None

    # ========================================
    # ヘルパーメソッド
    # ========================================

    def get_source_by_id(self, source_id: str) -> Optional[SourceFile]:
        """IDでソースを検索"""
        for source in self.sources:
            if source.id == source_id:
                return source
        return None

    def get_all_chapters(self) -> list[tuple[int, ClipChapter]]:
        """全チャプターを (timeline_position_ms, chapter) のリストで取得"""
        result: list[tuple[int, ClipChapter]] = []
        offsets = self.timeline.get_clip_offsets()
        for idx, clip in enumerate(self.timeline.clips):
            clip_offset = offsets[idx] if idx < len(offsets) else 0
            for chapter in clip.chapters:
                result.append((clip_offset + chapter.offset_ms, chapter))
        return result

    def get_chapters_for_export(self, exclude_marked: bool = False) -> list[tuple[int, ClipChapter]]:
        """エクスポート用チャプターを取得

        Args:
            exclude_marked: "--"プレフィックスのチャプターを除外するか
        """
        all_chapters = self.get_all_chapters()
        if not exclude_marked:
            return all_chapters
        return [
            (pos, ch) for pos, ch in all_chapters
            if not ch.is_excluded
        ]

    @property
    def is_empty(self) -> bool:
        """ソースが空かどうか"""
        return len(self.sources) == 0

    @property
    def is_exporting(self) -> bool:
        """エクスポート中かどうか"""
        return self.export is not None and self.export.is_running

    @property
    def total_duration_ms(self) -> int:
        """タイムラインの総時間"""
        return self.timeline.duration_ms

    # ========================================
    # 更新メソッド（新しいAppStateを返す）
    # ========================================

    def with_sources(self, sources: tuple[SourceFile, ...]) -> AppState:
        """ソースを置き換えた新しいAppStateを返す"""
        return AppState(
            sources=sources,
            timeline=self.timeline,
            playback=self.playback,
            export=self.export,
            work_dir=self.work_dir,
            is_modified=True,
            project_path=self.project_path
        )

    def with_timeline(self, timeline: VirtualTimeline) -> AppState:
        """タイムラインを置き換えた新しいAppStateを返す"""
        return AppState(
            sources=self.sources,
            timeline=timeline,
            playback=self.playback,
            export=self.export,
            work_dir=self.work_dir,
            is_modified=True,
            project_path=self.project_path
        )

    def with_playback(self, playback: PlaybackState) -> AppState:
        """再生状態を置き換えた新しいAppStateを返す"""
        return AppState(
            sources=self.sources,
            timeline=self.timeline,
            playback=playback,
            export=self.export,
            work_dir=self.work_dir,
            is_modified=self.is_modified,
            project_path=self.project_path
        )

    def with_export(self, export: Optional[ExportSnapshot]) -> AppState:
        """エクスポート状態を置き換えた新しいAppStateを返す"""
        return AppState(
            sources=self.sources,
            timeline=self.timeline,
            playback=self.playback,
            export=export,
            work_dir=self.work_dir,
            is_modified=self.is_modified,
            project_path=self.project_path
        )

    def with_work_dir(self, work_dir: Optional[Path]) -> AppState:
        """作業ディレクトリを置き換えた新しいAppStateを返す"""
        return AppState(
            sources=self.sources,
            timeline=self.timeline,
            playback=self.playback,
            export=self.export,
            work_dir=work_dir,
            is_modified=self.is_modified,
            project_path=self.project_path
        )

    def with_project_path(self, project_path: Optional[Path]) -> AppState:
        """プロジェクトパスを設定した新しいAppStateを返す"""
        return AppState(
            sources=self.sources,
            timeline=self.timeline,
            playback=self.playback,
            export=self.export,
            work_dir=self.work_dir,
            is_modified=self.is_modified,
            project_path=project_path
        )

    def mark_saved(self) -> AppState:
        """保存済みとしてマークした新しいAppStateを返す"""
        return AppState(
            sources=self.sources,
            timeline=self.timeline,
            playback=self.playback,
            export=self.export,
            work_dir=self.work_dir,
            is_modified=False,
            project_path=self.project_path
        )

    def add_source(self, source: SourceFile) -> AppState:
        """ソースを追加した新しいAppStateを返す"""
        new_sources = self.sources + (source,)
        new_clip = Clip.from_source(source)
        new_timeline = self.timeline.add_clip(new_clip)
        return AppState(
            sources=new_sources,
            timeline=new_timeline,
            playback=self.playback,
            export=self.export,
            work_dir=self.work_dir,
            is_modified=True,
            project_path=self.project_path
        )

    def clear(self) -> AppState:
        """状態をクリアした新しいAppStateを返す"""
        return AppState(
            work_dir=self.work_dir,
            project_path=None
        )
