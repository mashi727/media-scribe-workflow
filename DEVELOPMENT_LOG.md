# Development Log

開発ログ（2025-12-29〜）- 新しい順

過去のログは `DEVELOPMENT_LOG_as_of_2025-12-29.md` を参照。

---

## 今後の予定

### video-chapter-editor

#### 短期（リファクタリング）
- Phase 1: 重複コード抽出
  - `styles.py` 新規作成（色定数・ボタンスタイル）
  - `dialogs.py` の `_button_style()` 統一
  - `workers.py` の `build_drawtext_filter()` 追加
- Phase 2: ユーティリティクラス
  - `TempFileManagerMixin`
  - `CancellableWorkerMixin`
- Phase 3: God Class分割（main_workspace.py: 5000行超）
  - テスト環境構築
  - 責務分離（ChapterManager, MediaPlaybackController等）

#### 中期（アーキテクチャ改善）
- プロジェクトファイル（JSON）への移行 → 下記「設計検討事項」参照
- バッチエンコード機能
- 複数ソース時のチャプター操作改善

#### 長期
- UI大改造: スケルトン完成 → 機能実装へ
- 単一エンコードパス実装

### report-workflow

- 配管のプロトタイプは完了
- 陶器（GUI）の設計は video-chapter-editor 完成後

---

## 2026-01-08: 設計原則の明確化と今後の構想

### 設計原則: 非破壊編集（Non-destructive Editing）

```
入力（不変）           処理              出力（新規作成）
┌──────────┐                          ┌──────────────┐
│SourceA   │──┐                    ┌─→│ merged.mp4   │
│SourceB   │──┼─→ チャプター付加 ──┤  │ + chapters   │
│SourceC   │──┘     (メタデータ)   │  └──────────────┘
└──────────┘                       │
     ↑                             └─→ chapters.txt
   変更なし
```

**原則**:
- ソースファイルは読み取り専用（アプリは一切変更しない）
- チャプターはメタデータ（インデックス/ラベル）として存在
- エクスポート時に新しいファイルを生成
- ソース入れ替え時、チャプターはソースに紐付いて移動（実装済み）

### 設計検討事項（要決定）

#### 1. プロジェクトファイル（JSON）への移行

**現状の課題**:
- Saveボタンはチャプターテキストのみ保存
- 履歴管理が複雑（メモリ内で管理）
- エンコード設定が保持されない

**提案**: JSONベースのプロジェクトファイル

```json
{
  "version": "1.0",
  "sources": [
    {"path": "part1.mp4", "duration_ms": 1800000, "hash": "sha256:..."},
    {"path": "part2.mp4", "duration_ms": 2400000, "hash": "sha256:..."}
  ],
  "chapters": [
    {"source_index": 0, "local_time_ms": 0, "title": "イントロ"},
    {"source_index": 0, "local_time_ms": 330000, "title": "本編"},
    {"source_index": 1, "local_time_ms": 0, "title": "後半開始"}
  ],
  "export_settings": {
    "encoder": "hevc_videotoolbox",
    "quality": 65,
    "audio_bitrate": "256k"
  },
  "output": "output/rehearsal_2024-01-08.mp4"
}
```

**メリット**:
- 履歴管理不要（プロジェクトファイル = 状態のスナップショット）
- 複数ソースの紐付けが明示的
- バッチ処理の基盤

**決定が必要な項目**:
- [ ] ファイル拡張子（`.vce.json`? `.vceproj`?）
- [ ] 既存のチャプターテキスト形式との互換性維持方法
- [ ] 自動保存の有無・タイミング

#### 2. バッチエンコード機能

**提案**: 編集とエンコードの分離

```
日中: 編集作業
├─ プロジェクトA → project_a.vce.json 保存
├─ プロジェクトB → project_b.vce.json 保存
└─ プロジェクトC → project_c.vce.json 保存

夜間: バッチエンコード
$ vce-batch encode projects/*.vce.json
```

**UIイメージ**:
```
File メニュー
├── New Project
├── Open Project...
├── Save Project
├── Save Project As...
├── ─────────────────
├── Add to Queue...        ← 複数プロジェクト読み込み
├── Process Queue          ← バッチエンコード
└── ─────────────────
    Export for YouTube     ← 既存のコピー機能（維持）
```

**決定が必要な項目**:
- [ ] キューUIは別ウィンドウ？メイン画面内？
- [ ] CLIツール（`vce-batch`）の提供有無
- [ ] cron/launchdでのスケジュール実行対応

#### 3. 複数ソース時のチャプター操作

**課題**:
- チャプターファイル読み込み時: 絶対時間をどのソースに紐付けるか
- ペースト操作時: コピー元の`source_index`をどう扱うか

**提案**: 時間からソースを自動判定

```
読み込み例:
  00:12:00 エンディング
  ↓
  ソースA(10分) + ソースB(15分) の場合
  → ソースBの local_time=2:00 として解釈
```

**決定が必要な項目**:
- [ ] 自動判定で良いか、ユーザー確認を挟むか
- [ ] チャプターファイル形式の拡張（メタデータヘッダー追加）

#### 4. チャプターファイル形式の拡張（参考）

```
# VCE Chapter File v1
# source: rehearsal_2024-01-08.mp4
# duration: 3600000
# created: 2024-01-08T15:30:00+09:00
---
00:00:00 イントロ
00:05:30 本編
00:45:00 エンディング
```

YouTube形式との互換性を維持しつつ、`#` コメント行でメタデータを追加。

---

## 2026-01-08: チャプター時間管理の相対時間方式への移行

### 背景・課題

**問題**: ソースファイルの追加・削除・並べ替え時に、チャプターの再生時間計算が正しく動作しない、または挙動が不安定（全チャプターがクリアされるなど）

**原因分析**: 従来の「絶対時間方式」では、チャプターは累積時間（全ソースを通した位置）を保持していた。これにより:
- ソース追加時: 既存チャプターの時間を全て再計算する必要
- ソース削除時: 該当ソースのチャプターを削除後、後続の時間を再計算
- ソース並べ替え時: 全チャプターの時間を再計算

再計算ロジックが複雑になり、エラーが連鎖的に伝播しやすい構造だった。

### 設計判断

**相対時間方式（B案）を採用**:

| 方式 | 保持データ | メリット | デメリット |
|------|-----------|----------|-----------|
| A. 絶対時間 | 累積時間 | 表示がそのまま使える | 操作時に全チャプター再計算 |
| B. 相対時間 | ローカル時間 + source_index | 操作時の影響範囲が限定的 | 表示時に変換が必要 |

**B案のメリット**:
- ソース並べ替え: `source_index` のみ更新（時間は不変）
- ソース挿入: 後続チャプターの `source_index` をシフト
- ソース削除: 該当チャプターを削除、残りの `source_index` をシフト
- エラーが連鎖しにくい

### 実装変更

#### 1. ChapterInfo dataclass（models.py）

```python
# Before
@dataclass
class ChapterInfo:
    time_ms: int  # 累積時間（絶対時間）
    title: str

# After
@dataclass
class ChapterInfo:
    local_time_ms: int  # ソースファイル内のローカル時間
    title: str
    source_index: Optional[int] = None  # 所属ソースのインデックス

    def get_absolute_time_ms(self, source_offsets: List[int]) -> int:
        """累積時間（絶対時間）を計算"""
        if self.source_index is not None and 0 <= self.source_index < len(source_offsets):
            return source_offsets[self.source_index] + self.local_time_ms
        return self.local_time_ms

    # 後方互換プロパティ
    @property
    def time_ms(self) -> int:
        return self.local_time_ms
```

#### 2. テーブルのUserRoleデータ

```python
# 各セルに保持するデータ
time_item.setData(Qt.ItemDataRole.UserRole, color)           # 色
time_item.setData(Qt.ItemDataRole.UserRole + 1, source_idx)  # ソースインデックス
time_item.setData(Qt.ItemDataRole.UserRole + 2, local_time_ms)  # ローカル時間 (NEW)
```

#### 3. ヘルパーメソッド追加

- `_get_source_offsets()`: 各ソースの開始オフセット（累積時間）を計算
- `_rebuild_chapter_table_from_data()`: チャプターデータからテーブルを再構築

#### 4. 更新されたメソッド（main_workspace.py）

| メソッド | 変更内容 |
|----------|----------|
| `_add_chapter()` | ローカル時間を計算してUserRole+2に保存 |
| `_rebuild_chapters_after_insert()` | source_indexのシフトのみ（時間不変） |
| `_rebuild_chapters_after_source_move()` | source_indexの再マッピング |
| `_load_chapters()` | 絶対時間からローカル時間に変換 |
| `_load_embedded_chapters()` | 相対時間として読み込み |
| `_generate_chapters_from_sources()` | local_time_ms=0で生成 |

#### 5. Workers（workers.py）

`ChapterInfo(time_ms=...)` → `ChapterInfo(local_time_ms=...)` に全て更新

### 動作原理

```
[ソース1: 10分] [ソース2: 15分] [ソース3: 20分]
     ↓              ↓              ↓
  offset=0      offset=10      offset=25

チャプター例:
  - "イントロ": local=0, source=0 → 絶対時間=0
  - "サビ1": local=5分, source=0 → 絶対時間=5分
  - "曲2開始": local=0, source=1 → 絶対時間=10分
  - "サビ2": local=3分, source=1 → 絶対時間=13分

ソース2を削除した場合:
  - source=0 のチャプター: 変化なし
  - source=1 のチャプター: 削除
  - source=2 のチャプター: source_index を 2→1 にシフト
  - ローカル時間は全て不変
```

### 後方互換性

- `ChapterInfo.time_ms` プロパティは `local_time_ms` を返す
- `ChapterInfo.from_time_str()` は従来通り動作
- エクスポート時は絶対時間を使用（テーブル表示から取得）

### テスト項目

- [ ] Add Source でファイル追加後のチャプター時間が正しい
- [ ] Remove Source でのチャプター再計算が正しい
- [ ] ソースの順序変更時のチャプター時間更新
- [ ] エクスポート機能が正常動作

### 波形ハイライトのシンプル化

選択中ソースの波形ハイライト表示を簡素化。

**Before**:
- 半透明青背景 + 斜線ハッチ + 四角縁取り

**After**:
- 半透明青背景のみ `QColor(100, 180, 255, 40)`

**変更ファイル**: `rehearsal_workflow/ui/widgets/waveform.py`

---

## 2026-01-06: v2.1.27 リリース - デュアルアーキテクチャ対応 & ffmpeg/ffprobeバンドル

### ffmpeg/ffprobe のバンドル

**課題**: `imageio-ffmpeg` は ffmpeg のみを同梱し、ffprobe が含まれない。アプリは動画の長さ取得やビットレート検出に ffprobe を使用。

**解決策**: `static-ffmpeg` パッケージに移行

| パッケージ | ffmpeg | ffprobe |
|-----------|--------|---------|
| imageio-ffmpeg | ✅ | ❌ |
| static-ffmpeg | ✅ | ✅ |

**変更ファイル**:
- `pyproject.toml`: `imageio-ffmpeg` → `static-ffmpeg`
- `ffmpeg_utils.py`: バイナリ検出ロジックを更新
- `video_chapter_editor.spec`: バンドル設定を更新

### デュアル macOS アーキテクチャビルド

**要望**: Intel Mac ユーザーにも配布したい

**解決策**: GitHub Actions で両アーキテクチャを並行ビルド

| ランナー | アーキテクチャ | 出力ファイル |
|----------|---------------|-------------|
| macos-13 | Intel x86_64 | `*-macOS-Intel.dmg` |
| macos-latest | Apple Silicon arm64 | `*-macOS-AppleSilicon.dmg` |

**変更ファイル**: `.github/workflows/release.yml`

### YouTube ダウンロード改善

**AV1 コーデック除外**:
- macOS で AV1 のハードウェアデコードが非対応
- format 文字列を `bv[vcodec^=avc1]+ba/bv[vcodec!^=av01]+ba/b` に変更
- H.264 優先、AV1 除外

**一時プレイリスト対応**:
- TLP, RD, OL, UU, LL プレフィックスを検出
- 一時プレイリスト URL の場合、単一動画としてダウンロード
- URL からプレイリストパラメータを自動除去

**既存ファイル検出の修正**:
- yt-dlp の "has already been downloaded" メッセージを解析
- 正確なファイルパスを取得（mtime 検索ではなく）

**変更ファイル**:
- `workers.py`: format 文字列、ファイル検出ロジック
- `main_workspace.py`: `_is_playlist_url()`, `_clean_youtube_url()`

---

## 2026-01-06: チャプター移動・削除の改善 & 波形ハイライト

### チャプターリスト移動時の手動追加チャプター保持

**課題**: ソースファイルの順序を変更（ドラッグ移動）した際、手動で追加したチャプターが消えてしまう

**原因**: `_rebuild_chapters_after_source_move()` がファイルから再読み込みしていたため、テーブルに手動追加されたチャプターが失われていた

**解決策**:

1. **ヘルパー関数追加** (`_get_local_time_in_source`):
   - 仮想タイムラインの絶対時間をソース内ローカル時間に変換

2. **`_rebuild_chapters_after_source_move()` の書き換え**:
   - テーブルから現在のチャプター情報を収集（ファイル再読み込みではなく）
   - `old_offsets` パラメータで変更前のオフセットを受け取り、正確なローカル時間を計算
   - 移動モード: source_indexをマッピング（前→後、後→前の両方向対応）
   - 削除モード: `removed_indices` パラメータで削除されたインデックスを受け取り、残りをシフト

3. **呼び出し元の修正**:
   - `_handle_row_move_grouped()`: 変更前にオフセットを保存、移動後にインデックスとオフセットを渡す
   - `_remove_chapter_grouped()`: 削除前にオフセットを保存、削除後にremoved_indicesとオフセットを渡す

**関数シグネチャ**:

```python
def _rebuild_chapters_after_source_move(
    self,
    old_source_idx: int = -1,
    new_source_idx: int = -1,
    removed_indices: set = None,
    old_offsets: list = None
)
```

### 波形ウィジェットの選択ソースハイライト表示

**要望**: チャプターリストで行を選択した際、そのチャプターが属するソースファイルの範囲を波形上でハイライト表示

**実装**:

1. **WaveformWidget (`waveform.py`)**:
   - `_selected_range` プロパティ追加
   - `set_selected_source_range(start, end)` メソッド追加
   - `clear_selected_source_range()` メソッド追加
   - `_paint_overlays()` でハイライト描画

2. **MainWorkspace (`main_workspace.py`)**:
   - `_update_waveform_selected_range()` メソッド追加
   - `_on_selection_changed()` から呼び出し

**ハイライトのデザイン**:

| 要素 | 設定 |
|------|------|
| 背景 | 青系半透明 (100, 180, 255, alpha=40) |
| 斜線 | 幅1.5px、間隔15px、逆方向（除外区間と区別） |
| 縁取り | 四角形、幅1.5px、alpha=240 |

**除外区間との区別**:
- 除外区間: 赤系、斜線は `/` 方向
- 選択ソース: 青系、斜線は `\` 方向（逆）、四角縁取り付き

**変更ファイル**:
- `rehearsal_workflow/ui/widgets/waveform.py`
- `rehearsal_workflow/ui/main_workspace.py`

---

## 2026-01-05: UI改善

### Chaptersテーブルの行番号表示

**要望**: Chaptersリストに行番号（No.）を表示し、ヘッダーを黒背景にする

**実装**:
- 当初、新しいカラム「No.」を追加する方向で実装を進めたが、ユーザーの意図は自動で振られる行番号のヘッダー部分（コーナーウィジェット）に「No.」を表示することだった
- テーブルの垂直ヘッダー（行番号）を表示に設定
- コーナーウィジェット（左上隅）に「No.」ラベルを配置
- ヘッダー背景を黒（#000000）に設定

### チャプタースキップボタンの有効化条件

**要望**: チャプタースキップボタンは、チャプターリストを編集した場合にのみ有効になるよう変更

**実装**:
- `_chapters_edited` フラグを追加（初期値: False）
- チャプターを追加（Add）、削除（Remove）、編集、ペーストした時にフラグをTrueに設定
- `_update_chapter_buttons()` でフラグを確認し、編集されていない場合はスキップボタンを無効のままにする
- 新しいメディアを読み込んだ時はフラグをリセット

### 新規ソース読み込み時のリセット処理

**要望**: 動画再生中に新しいソース（MP3等）を読み込んだ場合、再生を停止してチャプター・再生画面をリセットする

**実装** (`_prepare_for_new_source()`):
- `self._media_player.stop()` - 再生中のメディアを停止
- `self._media_player.setSource(QUrl())` - ソースをクリアして再生画面をリセット（黒画面に戻る）
- `self._waveform_widget.clear()` - 波形データをクリア
- YouTube URLからのダウンロード開始時にも `_prepare_for_new_source()` を呼び出すよう修正

### 複数MP3読み込み時の仕様確認

| ケース | 再生 | 波形 | チャプター | スキップボタン |
|--------|------|------|------------|----------------|
| 動画ファイル | ○ | ○ | 埋め込み読込 | 編集後に有効 |
| 単一MP3 | ○ | ○ | なし | 編集後に有効 |
| 複数MP3 | × | × | 自動生成 | 無効（再生不可） |

**結論**:
- 複数MP3のチャプターは、エクスポート用のメタデータ設定のための表示
- 再生できないためスキップボタンは無効のまま

**変更ファイル**: `rehearsal_workflow/ui/main_workspace.py`

---

## 2025-12-29: UIスケルトン作成

### 新アーキテクチャ実装開始

`rehearsal_workflow/ui_next/` に次世代UIのスケルトンを作成。

**ファイル構成:**

```
ui_next/
├── __init__.py          # パッケージエクスポート
├── app.py               # メインウィンドウ (VideoChapterEditorNext)
├── main_workspace.py    # 単一画面ワークスペース
├── dialogs.py           # SourceSelectionDialog, CoverImageDialog
└── log_panel.py         # ログ表示パネル
```

**LogPanel機能:**

| 機能 | 説明 |
|------|------|
| ログレベル | DEBUG, INFO, WARNING, ERROR |
| フィルタリング | 表示レベル切替（コンボボックス） |
| コピー | Claude Code用フォーマットでクリップボードへ |
| 折りたたみ | パネルの表示/非表示切替 |

**コピー出力フォーマット:**

```log
# Log exported at 2025-12-29T15:30:00
# Level filter: INFO+

15:30:00 INFO  [ffmpeg] Export started
15:30:05 ERROR [ffmpeg] Encoding failed: ...
```

**MainWorkspace構成:**

```
┌─────────────────────────────────────────────┐
│ [ソース選択] [カバー画像]    ← ボタン行     │
│ ソース: audio.mp3 (14:20)   ← 情報表示     │
├─────────────────────────────────────────────┤
│ [波形表示]                  ← プレースホルダ │
├─────────────────────────────────────────────┤
│ [チャプターテーブル]        ← 編集可能      │
├─────────────────────────────────────────────┤
│ [書出設定] [書出ボタン]     ← 進捗表示含む  │
├─────────────────────────────────────────────┤
│ [ログパネル]                ← 折りたたみ可  │
└─────────────────────────────────────────────┘
```

**起動確認:**

```bash
python -c "from rehearsal_workflow.ui_next import VideoChapterEditorNext"
# Import successful
```

### 次のステップ

1. 既存WaveformWidgetの移植
2. ffprobe連携（duration取得）
3. ffmpegエクスポート処理の移植
4. 既存コード（video_chapter_editor.py）との共存

---

## 2025-12-29: ユースケース拡張

### ユースケース全体図

```mermaid
graph TD
    subgraph "UC1: 自分で撮影した動画"
        UC1[自分撮影MP4]
        UC1 --> UC1A[UC1-A: 編集済み]
        UC1 --> UC1B[UC1-B: 要編集/長尺]
    end

    subgraph "UC2: YouTube動画"
        UC2[YouTube]
        UC2 --> UC2A[UC2-A: 自分のチャンネル]
        UC2 --> UC2B[UC2-B: 他者の動画]
        UC2A --> UC2A1[UC2-A1: 編集済み]
        UC2A --> UC2A2[UC2-A2: 要編集]
    end

    subgraph "UC3: 音声のみ録音"
        UC3[音声録音]
        UC3 --> UC3A[UC3-A: 編集済み]
        UC3 --> UC3B[UC3-B: 要編集]
        UC3A --> UC3A1[UC3-A1: 複数MP3/曲別]
        UC3A --> UC3A2[UC3-A2: 単一MP3]
        UC3B --> UC3B1[UC3-B1: 単一MP3/長尺]
    end

    subgraph "UC4: 既存編集済み"
        UC4[既存MP4]
        UC4 --> UC4A[UC4-A: チャプターなし]
        UC4 --> UC4B[UC4-B: チャプター追加のみ]
    end

    style UC1 fill:#e3f2fd
    style UC2 fill:#fff3e0
    style UC3 fill:#f3e5f5
    style UC4 fill:#e8f5e9
```

### 処理フロー統合図

```mermaid
graph LR
    subgraph 入力ソース
        YT[YouTube URL]
        REC[iPhone/カメラ]
        MIC[マイク録音]
        LOC[ローカルファイル]
    end

    subgraph 前処理
        YT -->|ytdl-claude| DL[ダウンロード]
        DL --> MP4Y[MP4 + SRT]
        REC -->|転送| MP4R[生MP4]
        MIC -->|転送| MP3M[MP3]
        LOC --> MP4L[MP4/MP3]
    end

    subgraph "video-chapter-editor"
        MP4Y --> LOAD[ソース読込]
        MP4R --> LOAD
        MP3M --> LOAD
        MP4L --> LOAD

        LOAD --> EDIT{要編集?}
        EDIT -->|Yes| TRIM[トリム]
        EDIT -->|No| CHAP
        TRIM --> CHAP[チャプター設定]

        CHAP --> COV{MP3?}
        COV -->|Yes| COVER[カバー画像]
        COV -->|No| EXP
        COVER --> EXP[書出]
    end

    subgraph 出力
        EXP --> OUT1[配布用MP4]
        EXP --> OUT2[YouTube用MP4]
    end

    subgraph 後続処理
        OUT2 -->|アップロード| YTSUB[YouTube字幕取得]
        YTSUB --> SRT[SRT]
        SRT --> CLAUDE[Claude分析]
        CLAUDE --> REPORT[レポート生成]
    end

    style TRIM fill:#ffecb3
    style CHAP fill:#e3f2fd
    style EXP fill:#c8e6c9
    style REPORT fill:#f3e5f5
```

### ユースケース詳細マトリクス

| UC | パターン | 入力 | トリム | 結合 | カバー | 後続処理 |
|----|----------|------|--------|------|--------|----------|
| UC1-A | 自撮/編集済 | MP4 | - | - | - | 字幕取得→分析 |
| UC1-B | 自撮/長尺 | MP4 | 必要 | - | - | 字幕取得→分析 |
| UC2-A1 | YouTube/自/編集済 | MP4+SRT | - | - | - | 焼込+チャプタ |
| UC2-A2 | YouTube/自/要編集 | MP4+SRT | 必要 | - | - | 字幕取得→分析 |
| UC2-B | YouTube/他者 | MP4+SRT | - | - | - | 個人学習用 |
| UC3-A1 | 音声/曲別MP3 | 複数MP3 | - | 必要 | 必要 | 字幕取得→分析 |
| UC3-A2 | 音声/単一編集済 | MP3 | - | - | 必要 | 字幕取得→分析 |
| UC3-B1 | 音声/長尺未編集 | MP3 | 必要 | - | 必要 | 字幕取得→分析 |
| UC4-A | 既存/チャプタなし | MP4 | - | - | - | 焼込+チャプタ |
| UC4-B | 既存/チャプタ追加 | MP4 | - | - | - | 焼込+チャプタ |

### 配管/陶器 分界マトリクス

各処理ステップの担当を明確化。**境界線**はvideo-chapter-editorの入出力点。

```
凡例:
  🔧 配管（CLI/外部ツール）
  🏺 陶器（video-chapter-editor）
  ─── 境界線
```

| ステップ | ツール | ユーザー操作 | プラットフォーム提供 | 要実装 | 分類 |
|----------|--------|-------------|-------------------|--------|------|
| **入力取得** ||||||
| YouTube DL | ytdl | URLコピペ → コマンド実行 | - | ytdl (yt-dlpラッパー) | 🔧 |
| YouTube DL（統合） | rehearsal-download | URLコピペ → コマンド実行 | - | rehearsal-download + whisper-remote | 🔧 |
| 字幕のみ取得 | yt-srt | URLコピペ → コマンド実行 | - | yt-srt (yt-dlpラッパー) | 🔧 |
| ファイル転送 | Finder | iPhoneからAirDrop / D&D | macOS (AirDrop, Finder) | - | 🔧 |
| **─── 境界線（入力）───** ||||||
| **動画編集** ||||||
| ソース選択 | video-chapter-editor | ボタン押下 → ファイル選択 | QFileDialog | ダイアログ呼出ロジック | 🏺 |
| 波形生成 | video-chapter-editor | （自動） | numpy (FFT) | 波形描画Widget | 🏺 |
| 結合（MP3） | video-chapter-editor | 複数ファイル選択で自動実行 | ffmpeg (-c copy) | コマンド構築 + subprocess | 🏺 |
| トリム | video-chapter-editor | 波形クリック → `--`名前入力 | - | 除外区間ロジック + UI | 🏺 |
| カバー設定 | video-chapter-editor | ボタン押下 → 画像選択 → クロップ | QFileDialog, QImage | クロップUI + リサイズ処理 | 🏺 |
| チャプター編集 | video-chapter-editor | 波形クリック → 名前入力 | QTableWidget | テーブル⇔波形連携 | 🏺 |
| プレビュー | video-chapter-editor | 再生ボタン / シーク | QMediaPlayer | 波形⇔再生位置同期 | 🏺 |
| 書出 | video-chapter-editor | ボタン押下 → 進捗待機 | ffmpeg (drawtext, エンコード) | コマンド構築 + 進捗パース | 🏺 |
| **─── 境界線（出力）───** ||||||
| **後続処理** ||||||
| YouTubeアップロード | yt-upload (予定) | コマンド実行 → URL取得 | YouTube Data API v3 | yt-upload (APIラッパー) | 🔧 |
| 字幕取得 | yt-srt | 新URLコピペ → コマンド実行 | - | yt-srt (yt-dlpラッパー) | 🔧 |
| AI分析 | Claude Code | `/rehearsal` 入力 → 指示に従う | Claude API | skill定義 (.md) | 🔧 |
| PDF生成 | rehearsal-finalize | .texファイル指定 → コマンド実行 | - | luatex-pdf + rehearsal-finalize | 🔧 |
| チャプター抽出 | tex2chapters | （PDF生成に含まれる） | grep, sed, awk | 正規表現 + 出力整形 | 🔧 |

**コマンドリファレンス:**

```bash
# === 前処理（配管）===

# YouTube動画+字幕ダウンロード
ytdl "https://youtu.be/VIDEO_ID" -o "20251229_rehearsal"
# → 20251229_rehearsal.mp4, 20251229_rehearsal_yt.srt

# 統合ダウンロード（DL + Whisper起動）
rehearsal-download "https://youtu.be/VIDEO_ID"
# → MP4 + YouTube字幕 + Whisper字幕（非同期）

# 字幕のみ取得
yt-srt "https://youtu.be/VIDEO_ID"           # 字幕のみ
yt-srt "https://youtu.be/VIDEO_ID" -v        # 動画も
yt-srt "https://youtu.be/VIDEO_ID" -l en     # 英語字幕

# === 動画編集（陶器）===

# GUIを起動
video-chapter-editor ./work_dir

# === 後続処理（配管）===

# 字幕取得（YouTube処理後）
yt-srt "https://youtu.be/NEW_VIDEO_ID"

# AI分析 + LaTeX生成
claude code
/rehearsal

# PDF生成 + チャプター抽出
rehearsal-finalize "リハーサル記録.tex"
# → リハーサル記録.pdf
# → リハーサル記録_youtube.txt
# → リハーサル記録_movieviewer.txt

# チャプター抽出のみ
tex2chapters "リハーサル記録.tex"
```

**ユースケース別 責務分担:**

| UC | 配管（前） | 陶器 | 配管（後） |
|----|-----------|------|-----------|
| UC1-A | - | 編集→書出 | YT→SRT→分析 |
| UC1-B | - | トリム→編集→書出 | YT→SRT→分析 |
| UC2-A1 | ytdl | 編集→書出 | 配布のみ |
| UC2-A2 | ytdl | トリム→編集→書出 | YT→SRT→分析 |
| UC2-B | ytdl | 閲覧のみ | - |
| UC3-A1 | - | 結合→カバー→編集→書出 | YT→SRT→分析 |
| UC3-A2 | - | カバー→編集→書出 | YT→SRT→分析 |
| UC3-B1 | - | トリム→カバー→編集→書出 | YT→SRT→分析 |
| UC4-A | - | 編集→書出 | 配布のみ |
| UC4-B | - | 編集→書出 | 配布のみ |

**視覚化:**

```mermaid
graph LR
    subgraph "🔧 配管（前処理）"
        P1[ytdl-claude]
        P2[ファイル転送]
    end

    subgraph "🏺 陶器（video-chapter-editor）"
        E1[ソース選択]
        E2[結合/トリム]
        E3[カバー設定]
        E4[チャプター編集]
        E5[書出]
    end

    subgraph "🔧 配管（後処理）"
        P3[YouTube]
        P4[yt-srt]
        P5[Claude AI]
        P6[rehearsal-finalize]
    end

    P1 --> E1
    P2 --> E1
    E1 --> E2 --> E3 --> E4 --> E5
    E5 --> P3 --> P4 --> P5 --> P6

    style E1 fill:#e3f2fd
    style E2 fill:#e3f2fd
    style E3 fill:#e3f2fd
    style E4 fill:#e3f2fd
    style E5 fill:#e3f2fd
    style P1 fill:#fff3e0
    style P2 fill:#fff3e0
    style P3 fill:#fff3e0
    style P4 fill:#fff3e0
    style P5 fill:#fff3e0
    style P6 fill:#fff3e0
```

**設計上の意味:**

1. **video-chapter-editorの責務範囲が明確**: ソース選択〜書出まで
2. **入出力インターフェースが2箇所**: 入力（ファイル）と出力（MP4）
3. **後続処理は独立**: 字幕取得〜分析は別ワークフロー
4. **UC2-Bは例外**: 陶器を通過するが書出せず（閲覧用途）

### 処理パス分類

```mermaid
graph TD
    subgraph "パスA: フル処理（トリム→チャプタ→字幕→分析）"
        PA1[UC1-B] --> PA[トリム→書出→YouTube→SRT→分析]
        PA2[UC2-A2] --> PA
        PA3[UC3-B1] --> PA
    end

    subgraph "パスB: チャプタ追加のみ"
        PB1[UC2-A1] --> PB[焼込+チャプタ→配布]
        PB2[UC4-A] --> PB
        PB3[UC4-B] --> PB
    end

    subgraph "パスC: 結合→フル処理"
        PC1[UC3-A1] --> PC[結合→カバー→書出→YouTube→SRT→分析]
    end

    subgraph "パスD: カバー追加→フル処理"
        PD1[UC3-A2] --> PD[カバー→書出→YouTube→SRT→分析]
    end

    subgraph "パスE: 編集済→フル処理"
        PE1[UC1-A] --> PE[書出→YouTube→SRT→分析]
    end

    style PA fill:#ffecb3
    style PB fill:#c8e6c9
    style PC fill:#e1bee7
    style PD fill:#b2dfdb
    style PE fill:#e3f2fd
```

### 設計への影響

1. **トリム機能の重要性**: UC1-B, UC2-A2, UC3-B1 で必須 → video-chapter-editorに統合済み
2. **YouTube連携**: 字幕取得インフラとしての活用が複数パスで発生
3. **配布用 vs 字幕取得用**: 出力が2系統（ローカル配布、YouTube経由分析）
4. **カバー画像**: MP3入力時のみ必要、MP4では不要

---

## 2025-12-29: UI大改造計画

### 背景・課題

現状のワークフローでMP3からMP4を生成する際、2回のエンコードが発生：

```
現状（2回エンコード）:
  MP3 → [enc] → 中間MP4 → [enc] → 最終MP4
              ↑ここで劣化    ↑さらに劣化
```

### 設計目標

- エンコード1回のみで劣化最小化
- 処理オーバーヘッドの最小化
- タイトル焼込は必須要件として維持

### 検討過程

#### 1. 一筆書き問題の認識（グラフ理論的アプローチ）

ワークフロー設計を**グラフ理論**の観点から分析。

**問題の本質**: 入力パターン（起点）が3つ以上存在する場合、機能重複が発生しやすい。
これは**オイラー路（一筆書き）問題**に類似：奇数次数の頂点が2つより多いと一筆書き不可能。

**起点（入力パターン）:**
1. 複数のカット済みMP3
2. 単一の長尺未編集MP3
3. 既存のMP4

**終点:**
- チャプター付きMP4

**処理ノード:**

| ノード | 必要な起点 |
|--------|-----------|
| 結合 | 起点1のみ |
| カバー画像 | MP3入力時のみ |
| チャプター編集 | 全起点 |
| 書出 | 全起点 |

**一筆書きできない構造（初期設計）:**

```mermaid
graph LR
    A1[起点1: 複数MP3] --> B[結合]
    B --> C[カバー画像]
    A2[起点2: 単体MP3] --> C
    C --> D[チャプター編集]
    A3[起点3: MP4] --> D
    D --> E[書出]
    E --> F[最終MP4]

    style A1 fill:#e1f5fe
    style A2 fill:#e1f5fe
    style A3 fill:#e1f5fe
    style F fill:#c8e6c9
```

問題: 起点2→カバー画像、起点3→チャプター編集と、経路が分散している。

**解決策: 共通パスを1つにし、入口を分岐**

```mermaid
graph LR
    subgraph 入口分岐
        A1[起点1: 複数MP3] --> B[結合]
        A2[起点2: 単体MP3]
        A3[起点3: MP4]
    end

    subgraph 共通パス
        B --> C{MP3?}
        A2 --> C
        A3 --> D[チャプター編集]
        C -->|Yes| CV[カバー画像]
        C -->|No| D
        CV --> D
        D --> E[書出]
    end

    E --> F[最終MP4]

    style A1 fill:#e1f5fe
    style A2 fill:#e1f5fe
    style A3 fill:#e1f5fe
    style F fill:#c8e6c9
    style D fill:#fff9c4
    style E fill:#fff9c4
```

**洞察**: 機能重複は「起点が3つ以上ある」ことに起因。共通パスを明確にし、
入口のみを分岐させることで重複を排除できる。

#### 2. 制約条件による設計空間の縮小

制約を追加することで設計が明確化される逆説的な効果を確認。

**制約なし（最初の状態）:**

```mermaid
graph TD
    subgraph "設計空間: 8パターン"
        R[ルート] --> T{焼込?}
        T -->|あり| T1[焼込あり]
        T -->|なし| T2[焼込なし]
        T1 --> C{カット?}
        T2 --> C
        C -->|あり| C1[カットあり]
        C -->|なし| C2[カットなし]
        C1 --> I{入力?}
        C2 --> I
        I -->|MP3| I1[MP3]
        I -->|MP4| I2[MP4]
    end

    style R fill:#ffcdd2
```

**制約追加後（タイトル焼込必須）:**

```mermaid
graph TD
    subgraph "設計空間: 2パターンに縮小"
        R[ルート] --> T[焼込あり固定]
        T --> V[映像: 1回enc必須]
        V --> I{入力?}
        I -->|MP3| I1[MP3: 静止画+焼込]
        I -->|MP4| I2[MP4: 焼込のみ]
    end

    style R fill:#c8e6c9
    style T fill:#c8e6c9
```

**最適化されたエンコード戦略:**

| 入力 | 映像処理 | 音声処理 |
|------|----------|----------|
| MP3 | enc(静止画+焼込) 1回 | enc 1回 |
| MP4 | enc(焼込) 1回 | **copy（無劣化）** |

**洞察**: 制約は自由度を狭めるが、設計空間を明確にし、最適解を見つけやすくする。

#### 3. Tab構成の検討

**初期案**: 2タブ構成（入力準備 + 編集・書出）

**問題点**: Tab 1のMP3結合は無劣化（-c copy）で可能。中間ファイルが不要ならタブを分ける意味が薄い。

**議論の流れ:**
1. 「タブ1とタブ2を分けなくても良いのでは？」→ 陶器（UI）が巨大化する懸念
2. 「入力ソースも別画面では？」→ ダイアログパターンの発見
3. 「チャプター自動挿入、カバー画像も自動適用」→ 統一的なUXパターン

#### 4. 最終決定: 単一画面 + ダイアログ（モーダル分離パターン）

**アーキテクチャ:**

```mermaid
graph TB
    subgraph メイン画面
        M[MainWorkspace]
        M --> W[波形表示]
        M --> CT[チャプターテーブル]
        M --> EX[書出設定・実行]
    end

    subgraph ダイアログ
        SD[SourceSelectionDialog]
        CD[CoverImageDialog]
    end

    M -.->|ボタン| SD
    M -.->|ボタン| CD
    SD -->|自動反映| M
    CD -->|自動反映| M

    style M fill:#e3f2fd
    style SD fill:#fff3e0
    style CD fill:#fff3e0
```

**UI構成:**

```
┌─────────────────────────────────────────────┐
│ [ソース選択] [カバー画像]  ← ボタンで別画面 │
│                                             │
│ ソース: audio.mp3 (14:20)                   │
│ カバー: cover.jpg (1920x1080)               │
│                                             │
│ [波形表示]                                  │
│ ════════════════════════════════════════    │
│                                             │
│ [チャプターテーブル]                        │
│ │ 00:00 | 第1曲 ホルスト 木星              │
│ │ 05:23 | 第2曲 エルガー 威風堂々          │
│                                             │
│ [書出設定] [書出]                           │
└─────────────────────────────────────────────┘
```

### 決定事項

1. **単一画面構成**: タブを廃止、メイン画面1つに統合
2. **ダイアログパターン**:
   - ソース選択ダイアログ: MP3/MP4追加・並替 → 自動でチャプター挿入
   - カバー画像ダイアログ: 選択・クロップ → 自動適用
3. **エンコード最適化**:
   - MP3結合は無劣化（-c copy）
   - 最終書出で1回のみエンコード
   - MP4入力時の音声は無劣化copy

### 各ケースのフロー

```mermaid
flowchart LR
    subgraph "ケースA: 複数MP3"
        A1[ソース選択] --> A2[自動結合]
        A2 --> A3[カバー設定]
        A3 --> A4[チャプター編集]
        A4 --> A5[書出]
    end
```

```mermaid
flowchart LR
    subgraph "ケースB: 単体MP3"
        B1[ソース選択] --> B2[カバー設定]
        B2 --> B3[チャプター編集]
        B3 --> B4[書出]
    end
```

```mermaid
flowchart LR
    subgraph "ケースC: MP4"
        C1[ソース選択] --> C2[チャプター編集]
        C2 --> C3[書出]
    end

    style C1 fill:#e8f5e9
    style C2 fill:#e8f5e9
    style C3 fill:#e8f5e9
```

| ケース | カバー画像 | 結合 | エンコード |
|--------|-----------|------|-----------|
| A. 複数MP3 | 必要 | 必要 | 映像1回 + 音声1回 |
| B. 単体MP3 | 必要 | 不要 | 映像1回 + 音声1回 |
| C. MP4 | 不要 | 不要 | 映像1回 + 音声copy |

### メリット

- メイン画面はシンプル（表示と編集に集中）
- 各ダイアログは単一責務
- 明示的な「保存」「適用」ボタン不要
- タブ切替なし、迷わない
- エンコード1回のみ、劣化最小

### 設計原則（本議論から得られた知見）

1. **グラフ構造での問題分析**: ワークフローを有向グラフとして捉え、起点・終点・ノードを明確化
2. **共通パスの抽出**: 複数の起点が合流する「共通パス」を見つけ、そこを中心に設計
3. **制約による単純化**: 制約は選択肢を狭めるが、設計を明確にする効果がある
4. **モーダル分離パターン**: 複雑な入力はダイアログに分離し、メイン画面をシンプルに保つ
5. **自動適用の原則**: ダイアログを閉じると自動で反映、明示的な「保存」ボタン不要

### 次のステップ

- [ ] 現在の2タブ構成を単一画面に統合
- [ ] SourceSelectionDialog の実装
- [ ] CoverImageDialog の実装
- [ ] MainWorkspace の実装
- [ ] ffmpegコマンドの最適化（1パス処理）
- [ ] 実装完了後: PAD図による処理ロジックの文書化

### ダイアグラム方針

| フェーズ | 形式 | 用途 |
|----------|------|------|
| 設計 | Mermaid | グラフ構造、コンポーネント関係 |
| 実装記録 | PAD | 処理ロジック、条件分岐の詳細 |

PADは構造化プログラミング時代の産物であり、実装レベルの処理フローを階層的に記述するのに適している。

### 関連ファイル

- `docs/dev-log-ui-redesign-2025-12-29.md` - 詳細な議論ログ

---

**更新**: 2026-01-08
