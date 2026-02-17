# VCE 機能マトリックス

> 本ドキュメントは [DESIGN_PRINCIPLES.md](./DESIGN_PRINCIPLES.md) の設計原則に基づく。

## 1. ユースケース × 機能マトリックス（現在の実装）

| ユースケース | 入力 | 仮想TL | 波形 | スペクトロ | 入替 | チャプター編集 | 除外カット | 焼込 | 埋込 | エンコーダ | YouTube DL |
|-------------|------|:------:|:----:|:---------:|:----:|:-------------:|:---------:|:----:|:----:|:---------:|:----------:|
| **編集済み分割（画角混在）** | 複数mp4 | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | - |
| └ YouTubeプレイリスト | URL→複数mp4 | ↑ | ↑ | ↑ | ↑ | ↑ | ↑ | ↑ | ↑ | ↑ | ○ |
| **編集済み分割（音声）** | 複数mp3 | ○ | ○ | ○ | ○ | ○ | ○ | - | ○ | ○ | - |
| **ダラダラ録画** | 単一mp4 | - | ○ | ○ | - | ○ | ○ | ○ | ○ | ○ | - |
| └ YouTube単一動画 | URL→単一mp4 | ↑ | ↑ | ↑ | ↑ | ↑ | ↑ | ↑ | ↑ | ↑ | ○ |
| **ダラダラ録音** | 単一mp3 | - | ○ | ○ | - | ○ | ○ | - | ○ | ○ | - |
| 混合ソース | mp4+mp3 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA |

**注**: YouTube系は入力取得手段の差異のみ。DL後は対応する基本パターンと同一処理。

---

## 2. 機能階層（What → How）

### レベル0: 目的（What）

| ID | 目的 | 説明 |
|----|------|------|
| W1 | ソース管理 | 複数メディアファイルを統合管理する |
| W2 | 内容確認 | メディアの内容を視覚的に確認する |
| W3 | 構造化 | 時間軸上に意味のある区切りを設定する |
| W4 | 出力生成 | 編集結果を配布可能な形式で出力する |
| W5 | 外部取得 | オンラインソースからメディアを取得する |

### レベル1: 手段（How）

| 目的ID | ID | 手段 | 実装クラス |
|--------|-----|------|-----------|
| W1 | H1.1 | ファイル読込 | SourceFileManager |
| W1 | H1.2 | メタデータ検出 | DurationDetectWorker |
| W1 | H1.3 | 仮想タイムライン構築 | PlaybackManager |
| W1 | H1.4 | ソース並べ替え | SourceFileManager.reorder_sources() |
| W2 | H2.1 | 動画プレビュー | QMediaPlayer + QVideoWidget |
| W2 | H2.2 | 波形抽出・表示 | WaveformWorker + WaveformWidget |
| W2 | H2.3 | スペクトログラム表示 | SpectrogramWorker + WaveformWidget |
| W2 | H2.4 | 再生制御 | PlaybackManager |
| W3 | H3.1 | チャプター追加/編集 | ChapterManager |
| W3 | H3.2 | 除外チャプター設定 | ChapterInfo.is_excluded |
| W3 | H3.3 | チャプターファイルI/O | ChapterManager.load/save |
| W4 | H4.1 | 除外区間カット | calculate_extraction_plan() |
| W4 | H4.2 | エンコード | ExportWorker |
| W4 | H4.3 | チャプター埋込 | FFMETADATA生成 |
| W4 | H4.4 | タイトル焼き込み | drawtext filter |
| W4 | H4.5 | チャプター分割出力 | SplitExportWorker |
| W5 | H5.1 | YouTube単一DL | YouTubeDownloadWorker |
| W5 | H5.2 | プレイリストDL | PlaylistDownloadWorker |

---

## 3. 因果関係（入力 → 処理 → 出力）

### W1: ソース管理

```
[入力]                    [処理]                      [出力]
ファイルパス ──────────→ DurationDetectWorker ────→ duration_ms
                              │
複数SourceFile ─────────→ PlaybackManager ─────────→ file_boundaries
                              │                         source_offsets
                              ↓
                        仮想タイムライン構築
```

### W2: 内容確認

```
[入力]                    [処理]                      [出力]
音声データ ────────────→ WaveformWorker ───────────→ numpy.ndarray (波形)
                              │
                              ↓
                        WaveformWidget ────────────→ 画面描画
                              ↑
再生位置(ms) ──────────→ set_position() ───────────→ インジケータ表示
チャプターリスト ──────→ _paint_overlays() ────────→ マーカー/ハッチング
```

### W3: 構造化

```
[入力]                    [処理]                      [出力]
再生位置 + タイトル ───→ ChapterManager.add() ────→ ChapterData
                              │
                              ↓
                        chapters_changed シグナル
                              │
                              ↓
                        UI更新 (テーブル + 波形)
```

### W4: 出力生成

```
[入力]                    [処理]                      [出力]
SourceFiles ─────────┐
                     ├──→ calculate_extraction_plan() ──→ SegmentInfo[]
ChapterInfos ────────┘            │
                                  ↓
                           ExportWorker
                                  │
                     ┌────────────┼────────────┐
                     ↓            ↓            ↓
              trim+concat    FFMETADATA    drawtext
                     │            │            │
                     └────────────┴────────────┘
                                  │
                                  ↓
                           出力MP4ファイル
```

### W5: 外部取得

```
[入力]                    [処理]                      [出力]
YouTube URL ───────────→ YouTubeDownloadWorker ───→ MP4ファイル
                              │                       VTT字幕
                              ↓
                        yt-dlp (外部コマンド)
                              │
                              ↓
                        SourceFileManager.add()
```

---

## 4. 未実装機能

| 機能 | 優先度 | 備考 |
|------|--------|------|
| カバー画像設定 | 低 | サムネイル指定 |
| 音量正規化 | 中 | ffmpeg loudnorm filter |
| プロジェクト保存(.vce.json) | 高 | 作業状態の永続化 |
| Undo/Redo | 中 | 操作履歴管理 |

---

## 5. リファクタリング候補

| 項目 | 現状 | 改善案 | 期待効果 |
|------|------|--------|---------|
| TL/仮想TL分離 | 仮想TLが単一/複数両方を処理 | TL（共通処理）と仮想TL（複数専用）を分離 | 責任明確化、単一ソース時の処理簡素化 |
| MainWorkspace分割 | 7,000行超のGod Class | Manager層への委譲（既存計画） | 保守性・テスタビリティ向上 |

### TL/仮想TL分離の詳細

```
【現状】
仮想TL（PlaybackManager）
├── 単一ソース: 境界なし仮想TLとして処理
└── 複数ソース: 境界付き仮想TLとして処理

【改善案】
TL（共通）        ← 時間軸操作、シーク、再生制御
    ↑
仮想TL（複数専用） ← ソース連結、境界管理、座標変換
                    単一ソースの場合はTLを直接使用
```

---

## 6. クラス責任マッピング

| 因果連鎖 | 責任クラス | 入力 | 出力 |
|---------|-----------|------|------|
| ファイル→メタデータ | SourceFileManager | Path | SourceFile |
| ソース群→仮想TL | PlaybackManager | List[SourceFile] | boundaries, offsets |
| 音声→波形 | WaveformWorker | Path | ndarray |
| 波形→描画 | WaveformWidget | ndarray | QPixmap |
| 操作→チャプター | ChapterManager | (time, title) | ChapterData |
| 設定→出力 | ExportOrchestrator | ExportSettings | MP4 |
| URL→ファイル | YouTubeDownloadWorker | URL | Path |

---

## 参照ドキュメント

- [DESIGN_PRINCIPLES.md](./DESIGN_PRINCIPLES.md) - 設計原則（上流）
- [vce_architecture.md](./vce_architecture.md) - アーキテクチャ設計書（状態遷移・クラス設計）
