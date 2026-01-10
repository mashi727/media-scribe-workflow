"""
managers - MainWorkspaceから抽出されたマネージャークラス群

各マネージャーは単一責任の原則に従い、特定の機能ドメインを担当する。
"""

from .playback_manager import PlaybackManager
from .chapter_manager import ChapterManager, ChapterData
from .export_orchestrator import ExportOrchestrator, ExportState, ExportSettings, ExportJob

# 以下は順次実装予定
# from .source_manager import SourceFileManager

__all__ = [
    "PlaybackManager",
    "ChapterManager",
    "ChapterData",
    "ExportOrchestrator",
    "ExportState",
    "ExportSettings",
    "ExportJob",
    # "SourceFileManager",
]
