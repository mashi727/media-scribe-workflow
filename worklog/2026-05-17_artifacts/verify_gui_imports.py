"""GUI 抽出後の段階的 import 検証スクリプト。

video-chapter-editor リポジトリ直下で python3 verify_gui_imports.py
で実行する想定。PySide6 が無くても package/utils/pipeline は import 通る。
"""
import sys
sys.path.insert(0, '.')

checks = [
    ('package', 'import media_scribe_workflow'),
    ('utils', 'import media_scribe_workflow.utils'),
    ('pipeline.srt_parser', 'from media_scribe_workflow.pipeline.srt_parser import SRTParser'),
    ('ui.workers.base', 'import media_scribe_workflow.ui.workers.base'),
    ('ui.app', 'import media_scribe_workflow.ui.app'),
]

for label, stmt in checks:
    try:
        exec(stmt)
        print(f'{label}: OK')
    except Exception as e:
        print(f'{label} FAILED: {type(e).__name__}: {e}')
