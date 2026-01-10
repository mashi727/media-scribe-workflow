# Development Log

開発ログ - 新しい順

---

## 今後の予定

### video-chapter-editor

#### 短期（リファクタリング）
- ~~Phase 1: 重複コード抽出~~ ✅ 完了
- ~~Phase 2: ユーティリティクラス~~ ✅ 完了
- Phase 3: God Class分割（main_workspace.py: 5000行超）
  - ~~YouTubeDownloadMixin抽出~~ ✅ 完了
  - 残り候補: ChapterManager, MediaPlaybackController, ExportOrchestrator

#### 中期（アーキテクチャ改善）
- プロジェクトファイル（JSON）への移行 → 下記「設計検討事項」参照
- バッチエンコード機能
- 複数ソース時のチャプター操作改善

#### リポジトリ名変更 ✅ 完了

**決定**: `rehearsal-workflow` → `media-scribe-workflow`

**変更完了**:
- [x] リポジトリ名: `rehearsal-workflow` → `media-scribe-workflow`
- [x] パッケージ名: `rehearsal_workflow` → `media_scribe_workflow`
- [x] 関連ファイル: pyproject.toml, CLAUDE.md, README.md 等

#### 長期
- UI大改造: スケルトン完成 → 機能実装へ
- 単一エンコードパス実装

### report-workflow

- 配管のプロトタイプは完了
- 陶器（GUI）の設計は video-chapter-editor 完成後

---

## 2026-01-10: アーキテクチャドキュメント作成

### 概要

「配管と陶器（Plumbing & Porcelain）」の設計思想を明文化。
スケーラブルなユースケースのレベル分けを整理。

### 作成ドキュメント

`docs/architecture.md` を新規作成。

**主な内容**:

1. **設計思想: 配管と陶器**
   - Gitからの着想と本プロジェクトへの適用
   - 3層構造図（陶器 → 配管 → 外部ツール）

2. **配管ツール一覧**
   - 単一機能ツール（yt-srt, video-trim, tex2chapters等）
   - 複合ツール（rehearsal-download, rehearsal-finalize）
   - 設計原則（単一責任、stdin/stdout対応、冪等性）

3. **陶器ツール一覧**
   - GUIアプリケーション（video-chapter-editor, report-workflow）
   - Claude Codeスラッシュコマンド（/rehearsal, /aesa等）

4. **スケーラブルなユースケース**（レベル0〜4）
   - レベル0: 単一ツール使用
   - レベル1: パイプライン構築
   - レベル2: ワークフロー自動化
   - レベル3: AI統合ワークフロー
   - レベル4: GUI統合

5. **責務分離マトリクス**
   - 処理タイプ別の最適実行環境

6. **拡張パターン**
   - 新規配管ツール追加方法
   - 新規陶器（GUI）追加方法
   - Claude Codeコマンド追加方法

7. **依存関係グラフ**
   - Mermaid形式で視覚化

### 効果

- 新規開発者へのオンボーディング資料として機能
- ツール追加時の設計判断基準を明確化
- ユースケース別の推奨レベルを整理

---

## 2026-01-08: コードリファクタリング（Phase 1-3）

### 概要

main_workspace.py（5,000行超のGod Class）を中心としたコードベースの保守性向上。
機能変更なし、テスト可能な小さな変更を積み重ねるアプローチ。

### Phase 1: 重複コード抽出

#### styles.py 新規作成

色定数とボタンスタイルを集約。

```python
# media_scribe_workflow/ui/styles.py
class Colors:
    PRIMARY = "#3b82f6"
    DANGER = "#dc2626"
    BACKGROUND_DARK = "#1a1a1a"
    # ...

class ButtonStyles:
    @staticmethod
    def primary() -> str: ...
    @staticmethod
    def danger() -> str: ...
    @staticmethod
    def primary_compact() -> str: ...
    # ...
```

#### build_drawtext_filter() 追加

workers.py内の4箇所で重複していたdrawtextフィルター生成ロジックを関数化。

```python
def build_drawtext_filter(
    fontfile: str,
    textfile: str,
    fontsize_ratio: float = 0.04,
    fontcolor: str = "white",
    # ...
) -> str:
```

### Phase 2: Mixinパターン導入

#### TempFileManagerMixin

一時ファイルの作成・クリーンアップを管理。

```python
class TempFileManagerMixin:
    def _init_temp_manager(self) -> None
    def _create_temp_file(self, suffix: str, prefix: str = "vce_") -> str
    def _add_temp_file(self, path: str) -> None
    def _cleanup_temp_files(self) -> None
```

#### CancellableWorkerMixin

キャンセル可能なワーカーの共通機能。

```python
class CancellableWorkerMixin:
    def _init_cancellable(self) -> None
    def cancel(self) -> None
    def _is_cancelled(self) -> bool
    def _set_process(self, process) -> None
```

#### 適用クラス

- `ExportWorker`
- `SplitExportWorker`
- `YouTubeDownloadWorker`

**効果**: 約51行の重複コード削除

### Phase 3: YouTubeDownloadMixin抽出

main_workspace.pyからYouTube関連メソッド18個（約380行）を分離。

```python
# media_scribe_workflow/ui/youtube_mixin.py
class YouTubeDownloadMixin:
    def _youtube_btn_style_normal(self) -> str
    def _youtube_btn_style_processing(self) -> str
    def _clean_youtube_url(self, url: str) -> str
    def _is_playlist_url(self, url: str) -> bool
    def _start_youtube_download(self)
    def _on_youtube_progress(self, message: str)
    def _on_youtube_completed(self, video_path: str, srt_path: str)
    # ... 他11メソッド
```

**継承構造**:

```python
class MainWorkspace(QWidget, YouTubeDownloadMixin):
    ...
```

### ユニットテスト追加

GUIに依存しない純粋関数部分のテストを作成。

| ファイル | テスト対象 | テスト数 |
|---------|-----------|---------|
| test_mixins.py | TempFileManagerMixin, CancellableWorkerMixin | 11 |
| test_youtube_mixin.py | URL処理、プレイリスト判定 | 17 |
| test_workers_utils.py | build_drawtext_filter | 12 |
| test_styles.py | Colors, ButtonStyles | 16 |
| **合計** | | **56** |

実行: `pytest tests/ -v`

### 変更ファイル一覧

| ファイル | 操作 | 内容 |
|---------|------|------|
| `styles.py` | 新規 | Colors, ButtonStyles |
| `youtube_mixin.py` | 新規 | YouTubeDownloadMixin |
| `workers.py` | 編集 | build_drawtext_filter, Mixins追加 |
| `dialogs.py` | 編集 | styles.pyインポート |
| `main_workspace.py` | 編集 | Mixin継承、YouTube関連削除（-377行） |
| `tests/` | 新規 | ユニットテスト56件 |

---

## 2026-01-08: 設計決定事項の確定

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

### 基本原則: 同名規則

**制約**: ソースファイルとチャプターファイルは同名とする

```
working_directory/
├── rehearsal_2026-01-06.mp4
├── rehearsal_2026-01-06.txt      ← 自動的に対応
├── rehearsal_2026-01-07.mp3
├── rehearsal_2026-01-07.txt      ← 自動的に対応
└── rehearsal_2026-01-08.mp4      ← チャプターなし（.txtがない）
```

### 決定済み: プロジェクトファイル

| 項目 | 決定 |
|------|------|
| 拡張子 | `.vce.json` |
| 自動保存 | あり（チャプターリスト変更時） |
| エンコード設定 | 明示的Saveで保存（自動保存しない） |
| 既存.txt読み込み | 対応（ペースト機能と同様の実装） |

---

## 2026-01-06: v2.1.27 リリース

### ffmpeg/ffprobe のバンドル

**課題**: `imageio-ffmpeg` は ffmpeg のみを同梱し、ffprobe が含まれない。

**解決策**: `static-ffmpeg` パッケージに移行

| パッケージ | ffmpeg | ffprobe |
|-----------|--------|---------|
| imageio-ffmpeg | ✅ | ❌ |
| static-ffmpeg | ✅ | ✅ |

### デュアル macOS アーキテクチャビルド

| ランナー | アーキテクチャ | 出力ファイル |
|----------|---------------|-------------|
| macos-13 | Intel x86_64 | `*-macOS-Intel.dmg` |
| macos-latest | Apple Silicon arm64 | `*-macOS-AppleSilicon.dmg` |

---

## 2026-01-05: UI改善

### Chaptersテーブルの行番号表示

- テーブルの垂直ヘッダー（行番号）を表示に設定
- コーナーウィジェット（左上隅）に「No.」ラベルを配置
- ヘッダー背景を黒（#000000）に設定

### チャプタースキップボタンの有効化条件

- `_chapters_edited` フラグを追加（初期値: False）
- チャプターを追加・削除・編集・ペーストした時にフラグをTrueに設定
- 新しいメディアを読み込んだ時はフラグをリセット

---

## 2025-12-29: UIスケルトン作成

### 新アーキテクチャ実装開始

`media_scribe_workflow/ui_next/` に次世代UIのスケルトンを作成。

**ファイル構成:**

```
ui_next/
├── __init__.py          # パッケージエクスポート
├── app.py               # メインウィンドウ (VideoChapterEditorNext)
├── main_workspace.py    # 単一画面ワークスペース
├── dialogs.py           # SourceSelectionDialog, CoverImageDialog
└── log_panel.py         # ログ表示パネル
```

---

## 2025-12-29: UI大改造計画

### 設計目標

- エンコード1回のみで劣化最小化
- 処理オーバーヘッドの最小化
- タイトル焼込は必須要件として維持

### 最終決定: 単一画面 + ダイアログ（モーダル分離パターン）

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

---

# アーカイブ（〜2025-12-29）

## プロジェクト概要

**media-scribe-workflow** - メディアファイルから、AI分析による詳細レポートとチャプターリストを自動生成するワークフロー。

「Gitの陶器と配管」の思想に基づき、単一目的のツールを組み合わせてワークフローを構築。

---

## バージョン履歴

### v1.3.0 (2025-12-29)

**スマートビットレート検出と色空間保持**

- 元動画のビットレートを自動検出し、同等以上の品質で出力
- 色空間（BT.709等）を正確に保持
- GPUハードウェアエンコード対応（VideoToolbox/NVENC/QSV/AMF）

**UIモダン化**
- ダークテーマ（Theme class）の適用
- ボタン色ポリシーの確立（Primary: メインアクションのみ）
- 絵文字からテキストベースのボタンラベルへ変更
- チャプターテーブルの幅調整

### v1.2.0

**GPUハードウェアエンコーダー対応**

- macOS: VideoToolbox (h264_videotoolbox)
- Windows: NVENC (h264_nvenc), QSV (h264_qsv), AMF (h264_amf)
- 自動検出とフォールバック

### v1.1.1

**バイナリサイズ最適化**

- 不要なPySide6モジュールの除外
- opencv-python-headlessの使用
- PyInstaller specファイルの最適化

### v1.1.0

**自動リリースワークフロー**

- GitHub Actions による macOS/Windows バイナリ自動ビルド
- DMG/ZIP パッケージ作成
- リリースページへの自動アップロード

### v1.0.0 (初期リリース)

**GUIツール**
- video-chapter-editor: 動画チャプター編集・書出ツール
  - 動画プレビュー＋波形表示
  - チャプター編集（追加/削除/編集/ジャンプ）
  - 除外チャプター機能（`--`プレフィックス）
  - YouTubeチャプターのコピー＆ペースト
  - ffmpegによる動画書き出し

**CLIツール**
- yt-srt: YouTube字幕取得
- video-trim: 動画トリミング
- video-chapters: チャプター結合
- rehearsal-download: DL + Whisper起動
- rehearsal-finalize: PDF生成 + チャプター抽出
- tex2chapters: LaTeX → チャプターリスト

---

## アーキテクチャ

### ディレクトリ構成

```
media-scribe-workflow/
├── media_scribe_workflow/   # Pythonパッケージ
│   ├── __init__.py
│   └── ui/                  # GUI
│
├── bin/                     # CLIツール
│   ├── yt-srt
│   ├── video-trim
│   ├── video-chapters
│   └── ...
│
├── examples/prompts/        # プロンプト例
│
├── docs/                    # ドキュメント
│   └── advanced/            # 環境構築ガイド
│
└── .github/workflows/       # GitHub Actions
    └── release.yml          # 自動リリース
```

### ハイブリッドアプローチ

- **Python GUI**: 動画編集、チャプター管理
- **Zsh関数**: 機械的処理（ダウンロード、コンパイル、抽出）
- **Claude AI**: 分析・文書生成（SRT統合分析、LaTeX生成）

---

## 技術スタック

### GUIツール
- Python 3.10+
- PySide6 (Qt6)
- numpy
- opencv-python
- ffmpeg（システム）

### CLIワークフロー
- Zsh 5.0+
- Claude Code
- ytdl-claude
- whisper-remote
- luatex-pdf

### フォント（LaTeX出力）
- Libertinus (欧文)
- 原ノ味 (日本語)

---

## 設計思想

### 「配管と陶器」

Unix哲学に基づく設計：
- **配管 (Plumbing)**: 単一目的のCLIツール
- **陶器 (Porcelain)**: ユーザーフレンドリーなGUI

各ツールは独立して動作し、組み合わせることで複雑なワークフローを実現。

### 責務分離

| 処理タイプ | 担当 |
|-----------|------|
| 機械的処理 | Zsh関数 |
| AI判断処理 | Claude Code |
| ユーザー操作 | Python GUI |

---

## 参考ドキュメント

- `docs/gui-refactoring.md` - GUIリファクタリング詳細
- `docs/implementation.md` - CLIワークフロー実装詳細
- `docs/workflow-diagrams.md` - Mermaid形式フロー図
- `docs/advanced/` - 環境構築ガイド

---

**最終更新**: 2026-01-10
