"""
managers - MainWorkspaceから抽出されたマネージャークラス群

各マネージャーは単一責任の原則に従い、特定の機能ドメインを担当する。
"""

from .playback_manager import PlaybackManager

# 以下は順次実装予定
# from .chapter_manager import ChapterManager
# from .export_orchestrator import ExportOrchestrator
# from .source_manager import SourceFileManager

__all__ = [
    "PlaybackManager",
    # "ChapterManager",
    # "ExportOrchestrator",
    # "SourceFileManager",
]
