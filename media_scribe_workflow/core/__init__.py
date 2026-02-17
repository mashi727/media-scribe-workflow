"""
core - イミュータブルなデータモデルと状態管理

設計書に基づく新しいClipベースのデータモデルを提供。
既存のChapterInfo/SourceFileとの相互変換も可能。

主要クラス:
- SourceFile: ソースファイル（イミュータブル）
- ClipChapter: Clip内のチャプター（イミュータブル）
- Clip: タイムライン上の基本単位（イミュータブル）
- VirtualTimeline: 仮想タイムライン（イミュータブル）
- PlaybackState: 再生状態（イミュータブル）
- AppState: アプリケーション全体の状態（イミュータブル）
"""

from .state import (
    # ユーティリティ
    format_time_ms,
    parse_time_str,
    # 基本データ型
    SourceFile,
    ClipChapter,
    Clip,
    # タイムライン
    VirtualTimeline,
    # 再生状態
    PlaybackStatus,
    PlaybackState,
    # エクスポート設定
    EncoderType,
    QualityPreset,
    OutputFormat,
    ColorspaceSettings,
    OverlaySettings,
    ChapterExportSettings,
    AudioSettings,
    VideoSettings,
    ExportSettings,
    # エクスポートスナップショット
    ExportStatus,
    ExportSnapshot,
    # アプリケーション状態
    AppState,
)

from .converters import (
    # SourceFile変換
    old_source_to_new,
    new_source_to_old,
    old_sources_to_new,
    new_sources_to_old,
    # ChapterInfo / ClipChapter変換
    old_chapter_to_new,
    new_chapter_to_old,
    # プロジェクト変換
    v1_to_v2_project,
    v2_to_v1_project,
    v2_project_to_app_state,
    app_state_to_v2_project,
    v1_project_to_app_state,
    load_project_to_app_state,
    create_app_state_from_legacy,
)

from .project_io import (
    # バージョン定数
    ProjectVersion,
    # 結果クラス
    ProjectLoadResult,
    ProjectSaveResult,
    # I/O関数
    load_project,
    save_project,
    migrate_project_file,
    # ユーティリティ
    get_project_info,
    is_project_file,
)

__all__ = [
    # ユーティリティ
    "format_time_ms",
    "parse_time_str",
    # 基本データ型
    "SourceFile",
    "ClipChapter",
    "Clip",
    # タイムライン
    "VirtualTimeline",
    # 再生状態
    "PlaybackStatus",
    "PlaybackState",
    # エクスポート設定
    "EncoderType",
    "QualityPreset",
    "OutputFormat",
    "ColorspaceSettings",
    "OverlaySettings",
    "ChapterExportSettings",
    "AudioSettings",
    "VideoSettings",
    "ExportSettings",
    # エクスポートスナップショット
    "ExportStatus",
    "ExportSnapshot",
    # アプリケーション状態
    "AppState",
    # 変換関数
    "old_source_to_new",
    "new_source_to_old",
    "old_sources_to_new",
    "new_sources_to_old",
    "old_chapter_to_new",
    "new_chapter_to_old",
    "v1_to_v2_project",
    "v2_to_v1_project",
    "v2_project_to_app_state",
    "app_state_to_v2_project",
    "v1_project_to_app_state",
    "load_project_to_app_state",
    "create_app_state_from_legacy",
    # プロジェクトI/O
    "ProjectVersion",
    "ProjectLoadResult",
    "ProjectSaveResult",
    "load_project",
    "save_project",
    "migrate_project_file",
    "get_project_info",
    "is_project_file",
]
