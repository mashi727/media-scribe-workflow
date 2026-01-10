# VCE ダイアグラム・PAD図 対応表

## 概要

機能図（Mermaid）からPAD図（実装詳細）への対応関係を示す。

## ダイアグラム一覧

### 機能図（Mermaid）

| ファイル | 説明 | 詳細度 |
|----------|------|--------|
| `vce_functional_diagram_complete.mmd` | 全体機能図 | 概要 |
| `vce_functional_diagram_detailed.mmd` | 詳細機能図（PAD参照付き） | 詳細 |
| `vce_input_flow_pad_mapping.mmd` | 入力処理フロー（PADマッピング） | 実装レベル |

### PAD図（実装詳細）

| ファイル | 対応メソッド | 責務 |
|----------|-------------|------|
| `pad_on_files_dropped_v2.png` | `MainWorkspace._on_files_dropped()` | エントリーポイント、分類、モード分岐 |
| `pad_handle_initial_drop_v2.png` | `MainWorkspace._handle_initial_drop()` | 初回ロード処理、UI更新 |
| `pad_add_sources_to_existing_v2.png` | `MainWorkspace._add_sources_to_existing()` | 追加モード処理、UI更新 |
| `pad_source_manager_handle_initial_load.png` | `SourceFileManager.handle_initial_load()` | 初回ソース構築（データ層） |
| `pad_source_manager_handle_add_sources.png` | `SourceFileManager.handle_add_sources()` | ソース追加（データ層） |

## 対応関係

```
┌─────────────────────────────────────────────────────────────────────┐
│                    vce_functional_diagram_complete.mmd              │
│                         （全体機能図）                                │
├─────────────────────────────────────────────────────────────────────┤
│  External  →  UI・表示層  →  編集・ダイアログ層  →  内部処理層  →  Output  │
└─────────────────────────────────────────────────────────────────────┘
                    ↓ 詳細化
┌─────────────────────────────────────────────────────────────────────┐
│                    vce_functional_diagram_detailed.mmd              │
│                      （詳細機能図・PAD参照付き）                       │
├─────────────────────────────────────────────────────────────────────┤
│  入力処理 → ロードモード分岐 → UI操作 → 表示 → UI更新               │
│     ↓              ↓                              ↓                  │
│  SourceFileManager詳細 ←─────────────────────────→ Manager           │
└─────────────────────────────────────────────────────────────────────┘
                    ↓ PAD図対応
┌─────────────────────────────────────────────────────────────────────┐
│                    vce_input_flow_pad_mapping.mmd                   │
│                       （PADマッピング図）                            │
├─────────────────────────────────────────────────────────────────────┤
│  _on_files_dropped ─→ _handle_initial_drop ─→ handle_initial_load  │
│         │                      │                      │             │
│         ↓                      ↓                      ↓             │
│  pad_on_files_   pad_handle_initial_  pad_source_manager_          │
│  dropped_v2.png    drop_v2.png         handle_initial_load.png     │
└─────────────────────────────────────────────────────────────────────┘
```

## 入力処理フロー詳細

### 1. エントリーポイント

**機能図**: `UI・表示層 > UI操作 > Open/Add, D&D`

**PAD図**: `pad_on_files_dropped_v2.png`

```
ファイルドロップ/Open
    ↓
_on_files_dropped()
    ↓
SourceFileManager.classify_dropped_files()
    ↓
ClassifiedFiles {
    projects: [],  // .vce.json
    videos: [],    // .mp4, .mov, .avi, .mkv
    audios: [],    // .mp3, .m4a, .wav
    chapters: []   // .txt
}
```

### 2. 初回モード（sources が空）

**機能図**: `UI・表示層 > ロードモード分岐 > 初回モード`

**PAD図**: `pad_handle_initial_drop_v2.png`, `pad_source_manager_handle_initial_load.png`

```
_handle_initial_drop(classified)
    ↓
SourceFileManager.handle_initial_load(classified)
    ↓
InitialLoadResult {
    work_dir: Path,
    sources: List[SourceFile],
    media_type: "video" | "audio",
    is_single: bool
}
    ↓
UI更新: _prepare_for_new_source() → _load_source_media()
    ↓
チャプター読み込み: _try_load_chapter_file() or _load_chapters_for_all_sources()
```

### 3. 追加モード（sources が存在）

**機能図**: `UI・表示層 > ロードモード分岐 > 追加モード`

**PAD図**: `pad_add_sources_to_existing_v2.png`, `pad_source_manager_handle_add_sources.png`

```
型チェック（audio mode / video mode）
    ↓
_add_sources_to_existing(new_paths, chapters)
    ↓
SourceFileManager.handle_add_sources(new_paths, current_idx)
    ↓
AddSourcesResult {
    inserted_at: int,
    sources_added: List[SourceFile],
    skipped_paths: List[Path]
}
    ↓
UI更新: _rebuild_chapters_after_insert() → 5つのUI更新メソッド
    ↓
波形再生成: _start_waveform_generation()
```

## データクラス

### ClassifiedFiles（Phase 1）

```python
@dataclass
class ClassifiedFiles:
    projects: List[Path]   # .vce.json
    videos: List[Path]     # 動画
    audios: List[Path]     # 音声
    chapters: List[Path]   # チャプター

    # Properties
    has_project: bool
    has_media: bool
    has_video: bool
    has_audio: bool
    has_chapter_only: bool
    is_single_media: bool
    is_multiple_media: bool
```

### InitialLoadResult（Phase 2）

```python
@dataclass
class InitialLoadResult:
    work_dir: Path
    sources: List[SourceFile]
    media_type: str  # "video" | "audio"
    is_single: bool

    # Properties
    first_source: Optional[SourceFile]
    first_path: Optional[Path]
```

### AddSourcesResult（Phase 3）

```python
@dataclass
class AddSourcesResult:
    inserted_at: int
    sources_added: List[SourceFile]
    skipped_paths: List[Path]

    # Properties
    count_added: int
    has_skipped: bool
```

## 責務分離

| レイヤー | クラス | 責務 |
|---------|--------|------|
| UI層 | MainWorkspace | UI更新、イベント処理、シグナル発火 |
| データ層 | SourceFileManager | ソース管理、duration検出、時間変換 |
| データ層 | ChapterManager | チャプターCRUD、永続化 |
| データ層 | PlaybackManager | 再生制御、仮想タイムライン |
| データ層 | ExportOrchestrator | エクスポートワークフロー |
