"""
converters.py - 旧モデル ↔ 新モデルの変換

旧データモデル（ChapterInfo, SourceFile from ui/models.py）と
新データモデル（Clip, ClipChapter, SourceFile from core/state.py）の
相互変換を提供。

プロジェクトファイルのバージョン変換（v1.0 → v2.0）も含む。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .state import (
    SourceFile as NewSourceFile,
    ClipChapter,
    Clip,
    VirtualTimeline,
    AppState,
)

if TYPE_CHECKING:
    from ..ui.models import ChapterInfo as OldChapterInfo
    from ..ui.models import SourceFile as OldSourceFile


# =============================================================================
# SourceFile変換
# =============================================================================

def old_source_to_new(old_source: "OldSourceFile") -> NewSourceFile:
    """旧SourceFile → 新SourceFile

    Args:
        old_source: 旧SourceFile（ui/models.py）

    Returns:
        新SourceFile（core/state.py）
    """
    return NewSourceFile.create(
        path=old_source.path,
        duration_ms=old_source.duration_ms
    )


def new_source_to_old(new_source: NewSourceFile) -> "OldSourceFile":
    """新SourceFile → 旧SourceFile

    Args:
        new_source: 新SourceFile（core/state.py）

    Returns:
        旧SourceFile（ui/models.py）
    """
    # 遅延インポート（循環参照回避）
    from ..ui.models import SourceFile as OldSourceFile
    return OldSourceFile(
        path=new_source.path,
        duration_ms=new_source.duration_ms,
        file_type=new_source.file_type
    )


def old_sources_to_new(old_sources: list["OldSourceFile"]) -> tuple[NewSourceFile, ...]:
    """旧SourceFileリスト → 新SourceFileタプル"""
    return tuple(old_source_to_new(s) for s in old_sources)


def new_sources_to_old(new_sources: tuple[NewSourceFile, ...]) -> list["OldSourceFile"]:
    """新SourceFileタプル → 旧SourceFileリスト"""
    return [new_source_to_old(s) for s in new_sources]


# =============================================================================
# ChapterInfo / ClipChapter変換
# =============================================================================

def old_chapter_to_new(old_chapter: "OldChapterInfo") -> ClipChapter:
    """旧ChapterInfo → 新ClipChapter

    注意: 旧ChapterInfoはsource_indexとlocal_time_msを持つが、
    ClipChapterはClip内のoffset_msのみ持つ。
    この変換ではlocal_time_msをoffset_msとして使用する。

    Args:
        old_chapter: 旧ChapterInfo（ui/models.py）

    Returns:
        新ClipChapter（core/state.py）
    """
    return ClipChapter.create(
        offset_ms=old_chapter.local_time_ms,
        title=old_chapter.title
    )


def new_chapter_to_old(
    new_chapter: ClipChapter,
    source_index: int,
    clip_offset_in_source: int = 0
) -> "OldChapterInfo":
    """新ClipChapter → 旧ChapterInfo

    Args:
        new_chapter: 新ClipChapter（core/state.py）
        source_index: ソースファイルのインデックス
        clip_offset_in_source: Clipのin_point_ms（ソース内オフセット）

    Returns:
        旧ChapterInfo（ui/models.py）
    """
    # 遅延インポート（循環参照回避）
    from ..ui.models import ChapterInfo as OldChapterInfo
    return OldChapterInfo(
        local_time_ms=clip_offset_in_source + new_chapter.offset_ms,
        title=new_chapter.title,
        source_index=source_index
    )


# =============================================================================
# プロジェクトv1.0 → v2.0変換
# =============================================================================

def v1_to_v2_project(v1_data: dict) -> dict:
    """プロジェクトv1.0 → v2.0変換

    v1.0形式（ソースは文字列またはdict）:
    {
        "version": "1.0",
        "sources": ["video.mp4", ...] または [{"path": ..., "duration_ms": ...}, ...],
        "chapters": [{"title": ..., "source_index": ..., "local_time_ms": ...}, ...]
    }

    v2.0形式:
    {
        "version": "2.0",
        "sources": [{"id": ..., "path": ..., "duration_ms": ...}, ...],
        "timeline": {
            "clips": [
                {
                    "id": ...,
                    "source_id": ...,
                    "in_point_ms": ...,
                    "out_point_ms": ...,
                    "chapters": [{"id": ..., "offset_ms": ..., "title": ...}, ...]
                },
                ...
            ]
        }
    }

    Args:
        v1_data: v1.0形式のプロジェクトデータ

    Returns:
        v2.0形式のプロジェクトデータ
    """
    import uuid

    # ソースファイルを変換（IDを付与）
    v2_sources = []
    source_id_map = {}  # 旧index → 新ID

    for idx, old_source in enumerate(v1_data.get("sources", [])):
        source_id = str(uuid.uuid4())
        source_id_map[idx] = source_id

        # old_sourceが文字列（ファイル名）かdictかを判定
        if isinstance(old_source, str):
            # 文字列の場合（ファイル名のみ）
            source_path = old_source
            duration_ms = 0
        else:
            # dictの場合
            source_path = old_source.get("path", "")
            duration_ms = old_source.get("duration_ms", 0)

        v2_sources.append({
            "id": source_id,
            "path": source_path,
            "duration_ms": duration_ms,
            "file_type": Path(source_path).suffix[1:].lower() if source_path else ""
        })

    # チャプターをソースごとにグループ化
    chapters_by_source: dict[int, list[dict]] = {}
    for old_ch in v1_data.get("chapters", []):
        source_idx = old_ch.get("source_index", 0)
        if source_idx not in chapters_by_source:
            chapters_by_source[source_idx] = []
        chapters_by_source[source_idx].append(old_ch)

    # 各ソースに対応するClipを作成
    v2_clips = []
    for source_idx, v2_source in enumerate(v2_sources):
        source_id = v2_source["id"]
        duration_ms = v2_source["duration_ms"]

        # このソースに紐づくチャプター
        source_chapters = chapters_by_source.get(source_idx, [])

        # ClipChapterに変換
        v2_chapters = []
        for old_ch in sorted(source_chapters, key=lambda x: x.get("local_time_ms", 0)):
            v2_chapters.append({
                "id": str(uuid.uuid4()),
                "offset_ms": old_ch.get("local_time_ms", 0),
                "title": old_ch.get("title", ""),
                "is_excluded": old_ch.get("title", "").startswith("--")
            })

        # チャプターがない場合はファイル名でデフォルトチャプターを作成
        if not v2_chapters:
            v2_chapters.append({
                "id": str(uuid.uuid4()),
                "offset_ms": 0,
                "title": Path(v2_source["path"]).stem if v2_source["path"] else "Untitled",
                "is_excluded": False
            })

        v2_clips.append({
            "id": str(uuid.uuid4()),
            "source_id": source_id,
            "in_point_ms": 0,
            "out_point_ms": duration_ms,
            "chapters": v2_chapters
        })

    # v2.0形式を構築
    v2_data = {
        "version": "2.0",
        "sources": v2_sources,
        "timeline": {
            "clips": v2_clips
        }
    }

    # その他のフィールドを保持（export_settingsなど）
    for key, value in v1_data.items():
        if key not in ("version", "sources", "chapters"):
            v2_data[key] = value

    return v2_data


def v2_to_v1_project(v2_data: dict) -> dict:
    """プロジェクトv2.0 → v1.0変換（後方互換用）

    Args:
        v2_data: v2.0形式のプロジェクトデータ

    Returns:
        v1.0形式のプロジェクトデータ
    """
    # source_idからインデックスへのマッピング
    source_index_map: dict[str, int] = {}
    v1_sources: list[str] = []  # v1.0ではソースはファイル名の文字列リスト

    for idx, v2_source in enumerate(v2_data.get("sources", [])):
        source_index_map[v2_source.get("id", "")] = idx
        # v1.0形式ではパス（ファイル名）のみ
        v1_sources.append(v2_source.get("path", ""))

    # Clipからチャプターを抽出
    v1_chapters = []
    timeline = v2_data.get("timeline", {})

    for clip in timeline.get("clips", []):
        source_id = clip.get("source_id", "")
        source_index = source_index_map.get(source_id, 0)
        in_point_ms = clip.get("in_point_ms", 0)

        for chapter in clip.get("chapters", []):
            # Clip内オフセット + Clipのin_point_ms = ソース内ローカル時間
            local_time_ms = in_point_ms + chapter.get("offset_ms", 0)
            v1_chapters.append({
                "title": chapter.get("title", ""),
                "source_index": source_index,
                "local_time_ms": local_time_ms
            })

    # 時間順にソート
    v1_chapters.sort(key=lambda x: (x["source_index"], x["local_time_ms"]))

    v1_data = {
        "version": "1.0",
        "sources": v1_sources,
        "chapters": v1_chapters
    }

    # その他のフィールドを保持
    for key, value in v2_data.items():
        if key not in ("version", "sources", "timeline"):
            v1_data[key] = value

    return v1_data


# =============================================================================
# AppState変換
# =============================================================================

def v2_project_to_app_state(
    v2_data: dict,
    work_dir: Path | None = None,
    project_path: Path | None = None
) -> AppState:
    """v2.0プロジェクトデータ → AppState

    Args:
        v2_data: v2.0形式のプロジェクトデータ
        work_dir: 作業ディレクトリ
        project_path: プロジェクトファイルパス

    Returns:
        AppState
    """
    # ソースを変換
    sources: list[NewSourceFile] = []
    source_id_map: dict[str, NewSourceFile] = {}

    for src_data in v2_data.get("sources", []):
        source = NewSourceFile(
            id=src_data.get("id", ""),
            path=Path(src_data.get("path", "")),
            duration_ms=src_data.get("duration_ms", 0),
            file_type=src_data.get("file_type", "")
        )
        sources.append(source)
        source_id_map[source.id] = source

    # Clipを変換
    clips: list[Clip] = []
    timeline_data = v2_data.get("timeline", {})

    for clip_data in timeline_data.get("clips", []):
        chapters = tuple(
            ClipChapter(
                id=ch.get("id", ""),
                offset_ms=ch.get("offset_ms", 0),
                title=ch.get("title", ""),
                is_excluded=ch.get("is_excluded", False)
            )
            for ch in clip_data.get("chapters", [])
        )

        clip = Clip(
            id=clip_data.get("id", ""),
            source_id=clip_data.get("source_id", ""),
            in_point_ms=clip_data.get("in_point_ms", 0),
            out_point_ms=clip_data.get("out_point_ms", 0),
            chapters=chapters
        )
        clips.append(clip)

    timeline = VirtualTimeline(clips=tuple(clips))

    return AppState(
        sources=tuple(sources),
        timeline=timeline,
        work_dir=work_dir,
        project_path=project_path,
        is_modified=False
    )


def app_state_to_v2_project(state: AppState) -> dict:
    """AppState → v2.0プロジェクトデータ

    Args:
        state: AppState

    Returns:
        v2.0形式のプロジェクトデータ
    """
    from datetime import datetime

    sources = [
        {
            "id": src.id,
            "path": str(src.path),
            "duration_ms": src.duration_ms,
            "file_type": src.file_type
        }
        for src in state.sources
    ]

    clips = [
        {
            "id": clip.id,
            "source_id": clip.source_id,
            "in_point_ms": clip.in_point_ms,
            "out_point_ms": clip.out_point_ms,
            "chapters": [
                {
                    "id": ch.id,
                    "offset_ms": ch.offset_ms,
                    "title": ch.title,
                    "is_excluded": ch.is_excluded
                }
                for ch in clip.chapters
            ]
        }
        for clip in state.timeline.clips
    ]

    return {
        "version": "2.0",
        "created": datetime.now().isoformat(),
        "modified": datetime.now().isoformat(),
        "sources": sources,
        "timeline": {
            "clips": clips
        }
    }


# =============================================================================
# v1.0プロジェクトから直接AppStateへ
# =============================================================================

def v1_project_to_app_state(
    v1_data: dict,
    work_dir: Path | None = None,
    project_path: Path | None = None
) -> AppState:
    """v1.0プロジェクトデータ → AppState（v2.0経由）

    Args:
        v1_data: v1.0形式のプロジェクトデータ
        work_dir: 作業ディレクトリ
        project_path: プロジェクトファイルパス

    Returns:
        AppState
    """
    v2_data = v1_to_v2_project(v1_data)
    return v2_project_to_app_state(v2_data, work_dir, project_path)


def load_project_to_app_state(
    project_data: dict,
    work_dir: Path | None = None,
    project_path: Path | None = None
) -> AppState:
    """プロジェクトデータ（v1.0/v2.0）→ AppState

    バージョンを自動判定して適切な変換を行う。

    Args:
        project_data: プロジェクトデータ（任意のバージョン）
        work_dir: 作業ディレクトリ
        project_path: プロジェクトファイルパス

    Returns:
        AppState
    """
    version = project_data.get("version", "1.0")

    if version.startswith("2."):
        return v2_project_to_app_state(project_data, work_dir, project_path)
    else:
        # v1.0として扱う
        return v1_project_to_app_state(project_data, work_dir, project_path)


# =============================================================================
# 旧モデルからAppStateへ（互換用）
# =============================================================================

def create_app_state_from_legacy(
    old_sources: list["OldSourceFile"],
    old_chapters: list["OldChapterInfo"],
    work_dir: Path | None = None
) -> AppState:
    """旧モデル（SourceFile, ChapterInfo）からAppStateを生成

    Args:
        old_sources: 旧SourceFileのリスト
        old_chapters: 旧ChapterInfoのリスト
        work_dir: 作業ディレクトリ

    Returns:
        AppState
    """
    # ソースを変換
    new_sources: list[NewSourceFile] = []
    source_id_map: dict[int, str] = {}  # old_index → new_id

    for idx, old_src in enumerate(old_sources):
        new_src = old_source_to_new(old_src)
        new_sources.append(new_src)
        source_id_map[idx] = new_src.id

    # チャプターをソースごとにグループ化
    chapters_by_source: dict[int, list["OldChapterInfo"]] = {}
    for ch in old_chapters:
        source_idx = ch.source_index if ch.source_index is not None else 0
        if source_idx not in chapters_by_source:
            chapters_by_source[source_idx] = []
        chapters_by_source[source_idx].append(ch)

    # 各ソースに対応するClipを作成
    clips: list[Clip] = []
    for idx, new_src in enumerate(new_sources):
        source_chapters = chapters_by_source.get(idx, [])

        # ClipChapterに変換
        clip_chapters = tuple(
            old_chapter_to_new(ch)
            for ch in sorted(source_chapters, key=lambda x: x.local_time_ms)
        )

        # チャプターがない場合はファイル名でデフォルトチャプターを作成
        if not clip_chapters:
            clip_chapters = (ClipChapter.create(0, new_src.path.stem),)

        clip = Clip.create(
            source_id=new_src.id,
            in_point_ms=0,
            out_point_ms=new_src.duration_ms,
            chapters=clip_chapters
        )
        clips.append(clip)

    timeline = VirtualTimeline(clips=tuple(clips))

    return AppState(
        sources=tuple(new_sources),
        timeline=timeline,
        work_dir=work_dir,
        is_modified=False
    )
