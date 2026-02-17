"""
project_io.py - プロジェクトファイルI/O

v1.0/v2.0両対応のプロジェクトファイル読み書き。
パス解決、バージョンマイグレーションも担当。

プロジェクトファイル形式:
- v1.0: sources + chapters 形式
- v2.0: sources + timeline.clips 形式
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .state import (
    SourceFile,
    ClipChapter,
    Clip,
    VirtualTimeline,
    AppState,
    ExportSettings,
    OutputFormat,
    EncoderType,
    QualityPreset,
    VideoSettings,
    AudioSettings,
    ChapterExportSettings,
    OverlaySettings,
)
from .converters import (
    v1_to_v2_project,
    v2_to_v1_project,
)


# =============================================================================
# プロジェクトファイルバージョン
# =============================================================================

class ProjectVersion:
    """プロジェクトファイルバージョン定数"""
    V1_0 = "1.0"
    V2_0 = "2.0"
    CURRENT = V2_0


# =============================================================================
# プロジェクトファイル読み込み結果
# =============================================================================

@dataclass
class ProjectLoadResult:
    """プロジェクト読み込み結果"""
    success: bool
    app_state: Optional[AppState] = None
    raw_data: Optional[dict] = None
    version: str = ProjectVersion.V1_0
    error_message: Optional[str] = None
    missing_sources: Optional[list[str]] = None
    warnings: Optional[list[str]] = None

    def __post_init__(self):
        if self.missing_sources is None:
            object.__setattr__(self, 'missing_sources', [])
        if self.warnings is None:
            object.__setattr__(self, 'warnings', [])


@dataclass
class ProjectSaveResult:
    """プロジェクト保存結果"""
    success: bool
    file_path: Optional[Path] = None
    error_message: Optional[str] = None


# =============================================================================
# プロジェクトファイル読み込み
# =============================================================================

def load_project(
    file_path: Path,
    resolve_paths: bool = True
) -> ProjectLoadResult:
    """プロジェクトファイルを読み込み

    v1.0/v2.0どちらの形式も自動判定して読み込む。

    Args:
        file_path: プロジェクトファイルパス
        resolve_paths: ソースパスを解決するか

    Returns:
        ProjectLoadResult
    """
    if not file_path.exists():
        return ProjectLoadResult(
            success=False,
            error_message=f"Project file not found: {file_path}"
        )

    # ファイル読み込み
    try:
        raw_data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return ProjectLoadResult(
            success=False,
            error_message=f"Invalid JSON: {e}"
        )
    except Exception as e:
        return ProjectLoadResult(
            success=False,
            error_message=f"Failed to read file: {e}"
        )

    # バージョン判定
    version = raw_data.get("version", ProjectVersion.V1_0)
    project_dir = file_path.parent

    # v1.0の場合はv2.0に変換
    if version.startswith("1."):
        v2_data = v1_to_v2_project(raw_data)
    else:
        v2_data = raw_data

    # パス解決
    warnings: list[str] = []
    missing_sources: list[str] = []

    if resolve_paths:
        resolved_sources = []
        for src in v2_data.get("sources", []):
            src_path = src.get("path", "")
            resolved_path, found = _resolve_source_path(src_path, project_dir)
            if found:
                src["path"] = str(resolved_path)
                # duration_msがない場合は後で検出する必要がある
            else:
                missing_sources.append(src_path)
                warnings.append(f"Source not found: {src_path}")
            resolved_sources.append(src)
        v2_data["sources"] = resolved_sources

    # AppStateに変換
    try:
        app_state = _v2_data_to_app_state(
            v2_data,
            project_dir=project_dir,
            project_path=file_path
        )
    except Exception as e:
        return ProjectLoadResult(
            success=False,
            error_message=f"Failed to parse project data: {e}",
            raw_data=raw_data,
            version=version
        )

    return ProjectLoadResult(
        success=True,
        app_state=app_state,
        raw_data=raw_data,
        version=version,
        missing_sources=missing_sources,
        warnings=warnings
    )


def _resolve_source_path(
    source_path: str,
    project_dir: Path
) -> tuple[Path, bool]:
    """ソースパスを解決

    まず相対パスとして解決を試み、失敗したら絶対パスとして試す。

    Args:
        source_path: ソースパス文字列
        project_dir: プロジェクトディレクトリ

    Returns:
        (解決済みパス, 存在するか)
    """
    # 相対パスとして試す
    rel_path = project_dir / source_path
    if rel_path.exists():
        return rel_path.resolve(), True

    # 絶対パスとして試す
    abs_path = Path(source_path)
    if abs_path.exists():
        return abs_path.resolve(), True

    # 見つからない場合は相対パスを返す
    return rel_path, False


def _v2_data_to_app_state(
    v2_data: dict,
    project_dir: Path,
    project_path: Path
) -> AppState:
    """v2.0形式データをAppStateに変換"""
    # ソース
    sources: list[SourceFile] = []
    for src_data in v2_data.get("sources", []):
        source = SourceFile(
            id=src_data.get("id", ""),
            path=Path(src_data.get("path", "")),
            duration_ms=src_data.get("duration_ms", 0),
            file_type=src_data.get("file_type", "")
        )
        sources.append(source)

    # Clip
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
        work_dir=project_dir,
        project_path=project_path,
        is_modified=False
    )


# =============================================================================
# プロジェクトファイル保存
# =============================================================================

def save_project(
    app_state: AppState,
    file_path: Path,
    version: str = ProjectVersion.CURRENT,
    relative_paths: bool = True,
    include_export_settings: bool = True,
    export_settings: Optional[ExportSettings] = None,
    status: str = "draft"
) -> ProjectSaveResult:
    """プロジェクトをファイルに保存

    Args:
        app_state: 保存するAppState
        file_path: 保存先パス
        version: 保存するバージョン（デフォルト: 2.0）
        relative_paths: ソースパスを相対パスで保存するか
        include_export_settings: エクスポート設定を含めるか
        export_settings: エクスポート設定（Noneの場合はデフォルト）
        status: プロジェクトステータス（"draft" or "complete"）

    Returns:
        ProjectSaveResult
    """
    project_dir = file_path.parent

    # v2.0形式でデータを構築
    v2_data = _app_state_to_v2_data(
        app_state,
        project_dir=project_dir,
        relative_paths=relative_paths,
        status=status
    )

    # エクスポート設定を追加
    if include_export_settings:
        settings = export_settings or ExportSettings()
        v2_data["export_settings"] = _export_settings_to_dict(settings)

    # v1.0形式で保存する場合は変換
    if version.startswith("1."):
        save_data = v2_to_v1_project(v2_data)
        save_data["version"] = version
    else:
        save_data = v2_data
        save_data["version"] = version

    # タイムスタンプ追加
    save_data["modified"] = datetime.now().isoformat()
    if "created" not in save_data:
        save_data["created"] = save_data["modified"]

    # 保存
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(save_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        return ProjectSaveResult(success=True, file_path=file_path)
    except Exception as e:
        return ProjectSaveResult(
            success=False,
            error_message=f"Failed to save project: {e}"
        )


def _app_state_to_v2_data(
    app_state: AppState,
    project_dir: Path,
    relative_paths: bool = True,
    status: str = "draft"
) -> dict:
    """AppStateをv2.0形式データに変換"""
    sources = []
    for src in app_state.sources:
        src_path = src.path
        if relative_paths:
            try:
                src_path = src.path.relative_to(project_dir)
            except ValueError:
                pass  # 相対パスにできない場合は絶対パス
        sources.append({
            "id": src.id,
            "path": str(src_path),
            "duration_ms": src.duration_ms,
            "file_type": src.file_type
        })

    clips = []
    for clip in app_state.timeline.clips:
        clips.append({
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
        })

    return {
        "version": ProjectVersion.V2_0,
        "status": status,
        "sources": sources,
        "timeline": {
            "clips": clips
        }
    }


def _export_settings_to_dict(settings: ExportSettings) -> dict:
    """ExportSettingsを辞書に変換"""
    return {
        "output_format": settings.output_format.value,
        "video": {
            "encoder": settings.video.encoder.value,
            "quality_preset": settings.video.quality_preset.name.lower(),
            "bitrate_kbps": settings.video.bitrate_kbps,
            "crf": settings.video.crf,
            "max_width": settings.video.max_width,
            "max_height": settings.video.max_height,
            "frame_rate": settings.video.frame_rate
        },
        "audio": {
            "codec": settings.audio.codec,
            "bitrate_kbps": settings.audio.bitrate_kbps,
            "sample_rate": settings.audio.sample_rate,
            "channels": settings.audio.channels
        },
        "chapters": {
            "embed": settings.chapters.embed_chapters,
            "cut_excluded": settings.chapters.cut_excluded,
            "split_by_chapter": settings.chapters.split_by_chapter
        },
        "overlay": {
            "enabled": settings.overlay.enabled,
            "font_name": settings.overlay.font_name,
            "font_size": settings.overlay.font_size,
            "position": settings.overlay.position,
            "duration_sec": settings.overlay.duration_sec
        },
        "filename_template": settings.filename_template
    }


def _dict_to_export_settings(data: dict) -> ExportSettings:
    """辞書をExportSettingsに変換"""
    video_data = data.get("video", {})
    audio_data = data.get("audio", {})
    chapters_data = data.get("chapters", {})
    overlay_data = data.get("overlay", {})

    # エンコーダ
    encoder_str = video_data.get("encoder", "libx264")
    try:
        encoder = EncoderType(encoder_str)
    except ValueError:
        encoder = EncoderType.LIBX264

    # 品質プリセット
    quality_str = video_data.get("quality_preset", "medium").upper()
    try:
        quality = QualityPreset[quality_str]
    except KeyError:
        quality = QualityPreset.MEDIUM

    # 出力形式
    format_str = data.get("output_format", "mp4")
    try:
        output_format = OutputFormat(format_str)
    except ValueError:
        output_format = OutputFormat.MP4

    return ExportSettings(
        output_format=output_format,
        video=VideoSettings(
            encoder=encoder,
            quality_preset=quality,
            bitrate_kbps=video_data.get("bitrate_kbps"),
            crf=video_data.get("crf"),
            max_width=video_data.get("max_width"),
            max_height=video_data.get("max_height"),
            frame_rate=video_data.get("frame_rate")
        ),
        audio=AudioSettings(
            codec=audio_data.get("codec", "aac"),
            bitrate_kbps=audio_data.get("bitrate_kbps", 192),
            sample_rate=audio_data.get("sample_rate", 48000),
            channels=audio_data.get("channels", 2)
        ),
        chapters=ChapterExportSettings(
            embed_chapters=chapters_data.get("embed", True),
            cut_excluded=chapters_data.get("cut_excluded", True),
            split_by_chapter=chapters_data.get("split_by_chapter", False)
        ),
        overlay=OverlaySettings(
            enabled=overlay_data.get("enabled", False),
            font_name=overlay_data.get("font_name", "Helvetica"),
            font_size=overlay_data.get("font_size", 48),
            position=overlay_data.get("position", "top"),
            duration_sec=overlay_data.get("duration_sec", 5.0)
        ),
        filename_template=data.get("filename_template", "{base}_{index:02d}_{title}")
    )


# =============================================================================
# バージョンマイグレーション
# =============================================================================

def migrate_project_file(
    file_path: Path,
    target_version: str = ProjectVersion.CURRENT,
    backup: bool = True
) -> ProjectSaveResult:
    """プロジェクトファイルを新しいバージョンにマイグレーション

    Args:
        file_path: プロジェクトファイルパス
        target_version: ターゲットバージョン
        backup: バックアップを作成するか

    Returns:
        ProjectSaveResult
    """
    # 読み込み
    result = load_project(file_path, resolve_paths=False)
    if not result.success:
        return ProjectSaveResult(
            success=False,
            error_message=result.error_message
        )

    # すでにターゲットバージョン以上の場合はスキップ
    if result.version >= target_version:
        return ProjectSaveResult(
            success=True,
            file_path=file_path
        )

    # バックアップ
    if backup:
        backup_path = file_path.with_suffix(f".v{result.version}.bak.json")
        try:
            backup_path.write_text(
                file_path.read_text(encoding="utf-8"),
                encoding="utf-8"
            )
        except Exception as e:
            return ProjectSaveResult(
                success=False,
                error_message=f"Failed to create backup: {e}"
            )

    # 保存（新しいバージョンで）
    return save_project(
        result.app_state,
        file_path,
        version=target_version,
        relative_paths=True
    )


# =============================================================================
# ユーティリティ
# =============================================================================

def get_project_info(file_path: Path) -> Optional[dict]:
    """プロジェクトファイルの基本情報を取得（読み込みせず）

    Args:
        file_path: プロジェクトファイルパス

    Returns:
        基本情報辞書（version, sources数、clips数など）
    """
    if not file_path.exists():
        return None

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        version = data.get("version", "1.0")

        if version.startswith("2."):
            source_count = len(data.get("sources", []))
            clip_count = len(data.get("timeline", {}).get("clips", []))
        else:
            source_count = len(data.get("sources", []))
            clip_count = source_count  # v1.0ではsource = clipと見なす

        return {
            "version": version,
            "status": data.get("status", "draft"),
            "source_count": source_count,
            "clip_count": clip_count,
            "created": data.get("created"),
            "modified": data.get("modified")
        }
    except Exception:
        return None


def is_project_file(file_path: Path) -> bool:
    """ファイルが有効なプロジェクトファイルかどうか判定

    Args:
        file_path: ファイルパス

    Returns:
        有効なプロジェクトファイルかどうか
    """
    if not file_path.exists():
        return False
    if not file_path.suffix.lower() == ".json":
        return False
    if not file_path.stem.endswith(".vce"):
        return False

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        # バージョンとソースが存在すればプロジェクトファイル
        return "version" in data and "sources" in data
    except Exception:
        return False
