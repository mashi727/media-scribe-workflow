# VCE アーキテクチャ設計書

> 本ドキュメントは [DESIGN_PRINCIPLES.md](./DESIGN_PRINCIPLES.md) の設計原則に基づく。

## 1. 設計手法

本設計は以下の手法を組み合わせて導出された：

| 手法 | 適用箇所 |
|------|----------|
| IPOモデル (IDEF0) | コンテンツフロー、入力→中間→出力の分類 |
| Goal-Oriented RE | 目的-手段の階層分解 (P1.x → M1.x.x) |
| 状態遷移モデル | ファイル状態の変化 (S0→S1→...→S5) |
| Responsibility-Driven Design | クラス境界と責務の決定 |

---

## 2. コンテンツフロー（IPOモデル）

### 2.1 入力コンテンツ (Input)

| コンテンツ | 形式 | 取得元 |
|-----------|------|--------|
| ソースメディア | MP4, MP3 | ローカルファイル |
| YouTube動画 | URL → MP4 | yt-dlp |
| 既存チャプター | .txt | ファイル読込 |
| 既存プロジェクト | .vce.json | ファイル読込 |
| YouTube字幕 | .vtt | yt-dlp |

### 2.2 中間生成物 (Intermediate)

#### 永続化（人間の判断結果）

| コンテンツ | 形式 | 説明 |
|-----------|------|------|
| プロジェクト | .vce.json | ソース・チャプター・設定を保持 |

#### 導出構造（Derived Structures）

| コンテンツ | 導出元 | 用途 |
|-----------|--------|------|
| VirtualTimeline | List[SourceFile] | 統一座標系、境界情報 |
| ExcludedRegions | List[ChapterData] | ハッチング描画、カット計画 |
| ExtractionPlan | Sources + Chapters + Exclusions | ffmpeg concat用セグメント計画 |

#### 分析結果（Analysis Results）

| コンテンツ | 生成元 | 消費先 |
|-----------|--------|--------|
| WaveformData | WaveformWorker | WaveformWidget |
| SpectrogramData | SpectrogramWorker | WaveformWidget |

#### 一時生成

| コンテンツ | 形式 | 備考 |
|-----------|------|------|
| FFMETADATA | テキスト | エンコード時生成 |
| トリムセグメント | 一時ファイル | concat用 |

### 2.3 最終出力 (Output)

| コンテンツ | 形式 | 生成元 |
|-----------|------|--------|
| エンコード済み動画 | MP4（チャプター埋込） | vce-encode |
| 分割ファイル群 | MP4/MP3 | vce-split |
| チャプターファイル | .txt | vce-chapters |

---

## 3. 状態遷移モデル

### 3.1 状態定義

| 状態 | 名称 | データ構造 | 説明 |
|------|------|-----------|------|
| S0 | 外部 | Path | ファイルシステム上の位置 |
| S1 | 読込済 | SourceFile | パス + メタデータ(duration) |
| S1' | 座標系構築 | VirtualTimeline | 統一座標系（導出） |
| S2 | 分析済 | WaveformData, SpectrogramData | 可視化用データ |
| S3 | 構造化 | ChapterData | 位置 + 名前 + 除外フラグ |
| S3' | 除外計算 | ExcludedRegions | 除外区間リスト（導出） |
| S4 | 永続化 | VCEProject | ソース群 + チャプター群 + 設定 |
| S4' | 計画立案 | ExtractionPlan | セグメント計画（導出） |
| S5 | 出力 | ExportResult | 出力パス + 成否 + メタデータ |

### 3.2 状態遷移図

```
[S0: 外部]
    │ ファイル取得
    ▼
[S1: 読込済] ──導出──→ [S1': VirtualTimeline]
    │                         │
    │ 波形/スペクトロ抽出      │ 座標系提供
    ▼                         ▼
[S2: 分析済] ←────────────────┘
    │
    │ 人間の判断（UIロック）
    ▼
[S3: 構造化] ──導出──→ [S3': ExcludedRegions]
    │                         │
    │ 保存                    │
    ▼                         ▼
[S4: 永続化] ──導出──→ [S4': ExtractionPlan]
    │                         │
    │ エンコード              │ セグメント情報提供
    ▼                         ▼
[S5: 出力済] ←────────────────┘
```

### 3.3 因果関係マトリックス

|                  | S0→S1 | S1→S1' | S1→S2 | S2→S3 | S3→S3' | S3→S4 | S4→S4' | S4→S5 |
|------------------|:-----:|:------:|:-----:|:-----:|:------:|:-----:|:------:|:-----:|
| ファイル取得     | ●     |        |       |       |        |       |        |       |
| 座標系構築       | 前提  | ●      |       |       |        |       |        |       |
| 波形抽出         | 前提  | 前提   | ●     |       |        |       |        |       |
| 人間判断         |       | 参照   | 参照  | ●     |        |       |        |       |
| 除外区間計算     |       |        |       | 前提  | ●      |       |        |       |
| 永続化           |       |        |       | 前提  |        | ●     |        |       |
| 計画立案         |       |        |       |       | 前提   | 前提  | ●      |       |
| エンコード       |       |        |       |       |        |       | 前提   | ●     |

凡例: ● 直接作用 / 前提 = 時系列的依存 / 参照 = 読み取り依存

---

## 4. 目的-手段階層（Goal Decomposition）

### 4.1 レベル0: 最上位目的

```
P0: 素材を構造化された再利用可能な形式に変換する
```

### 4.2 レベル1: 目的分解

| ID | 目的 | 説明 |
|----|------|------|
| P1.1 | 素材取得・統合 | 外部メディアをシステムに取り込む |
| P1.2 | 判断支援 | 人間が判断できる状態にする |
| P1.3 | 構造定義 | 時間軸上の構造を定義する |
| P1.4 | 永続化 | 判断結果を保存する |
| P1.5 | 成果物生成 | 最終出力を生成する |

### 4.3 レベル2: 手段

| 目的 | ID | 手段 |
|------|-----|------|
| P1.1 | M1.1.1 | ローカルファイル読込 |
| | M1.1.2 | YouTube DL（単一/プレイリスト） |
| | M1.1.3 | メタデータ検出（duration） |
| | M1.1.4 | 仮想タイムライン構築 |
| P1.2 | M1.2.1 | 動画プレビュー表示 |
| | M1.2.2 | 音声再生 |
| | M1.2.3 | 波形抽出・表示 |
| | M1.2.4 | スペクトログラム表示 |
| | M1.2.5 | 再生位置ナビゲーション |
| P1.3 | M1.3.1 | チャプター追加/編集 |
| | M1.3.2 | 除外区間設定 |
| | M1.3.3 | ソース順序変更 |
| | M1.3.4 | 除外ハッチング/境界表示 |
| P1.4 | M1.4.1 | .vce.json書出 |
| | M1.4.2 | チャプターファイル書出 |
| P1.5 | M1.5.1 | 除外区間カット計画 |
| | M1.5.2 | エンコード |
| | M1.5.3 | チャプター埋込 |
| | M1.5.4 | タイトル焼込 |
| | M1.5.5 | チャプター分割出力 |

---

## 5. データ構造

### 5.1 基本データ（入力由来）

```python
@dataclass
class SourceFile:
    path: Path
    duration_ms: int
    media_type: Literal["video", "audio"]
    metadata: MediaInfo

@dataclass
class MediaInfo:
    codec: str                           # "h264", "aac", etc.
    resolution: Optional[Tuple[int, int]]  # 動画のみ
    frame_rate: Optional[float]          # 動画のみ
    audio_channels: int
    audio_sample_rate: int
```

### 5.2 導出構造（Derived Structures）

```python
@dataclass
class VirtualTimeline:
    """複数ソースを統一座標系に射影"""
    total_duration_ms: int
    source_boundaries: List[int]    # 各ソースの開始位置（仮想座標）
    source_offsets: List[int]       # 累積オフセット

    def virtual_to_source(self, virtual_ms: int) -> Tuple[int, int]:
        """仮想座標 → (ソースindex, ソース内座標)"""
        ...

    def source_to_virtual(self, source_idx: int, source_ms: int) -> int:
        """(ソースindex, ソース内座標) → 仮想座標"""
        ...

@dataclass
class ExcludedRegion:
    """除外区間（仮想座標）"""
    start_ms: int
    end_ms: int

@dataclass
class SegmentInfo:
    """抽出セグメント（ソース座標）"""
    source_index: int
    start_ms: int
    end_ms: int

@dataclass
class ExtractionPlan:
    """エクスポート用セグメント計画"""
    segments: List[SegmentInfo]
    total_output_duration_ms: int
```

### 5.3 分析結果（Analysis Results）

```python
@dataclass
class WaveformData:
    """波形データ"""
    source_index: int
    samples: np.ndarray       # ピーク値配列
    sample_rate: int
    duration_ms: int

@dataclass
class SpectrogramData:
    """スペクトログラムデータ"""
    source_index: int
    image: np.ndarray         # 2D配列 (周波数×時間)
    freq_range: Tuple[int, int]
    duration_ms: int
```

### 5.4 人間の判断結果

```python
@dataclass
class ChapterData:
    """チャプター情報"""
    position_ms: int          # 仮想タイムライン上の位置
    title: str
    is_excluded: bool = False
```

### 5.5 永続化データ

```python
@dataclass
class ExportSettings:
    encoder: str              # "libx264", "h264_videotoolbox", etc.
    quality: int              # 0-5
    overlay_title: bool
    embed_chapters: bool

@dataclass
class VCEProject:
    version: str
    sources: List[SourceFile]
    chapters: List[ChapterData]
    export_settings: ExportSettings
    created_at: datetime
    modified_at: datetime
```

### 5.6 出力・状態

```python
@dataclass
class ExportResult:
    success: bool
    output_path: Path
    duration_ms: int
    error_message: Optional[str]

class ExportState(Enum):
    IDLE = "idle"
    EXTRACTING = "extracting"     # セグメント抽出中
    ENCODING = "encoding"         # エンコード中
    EMBEDDING = "embedding"       # メタデータ埋込中
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

@dataclass
class ProjectState:
    """プロジェクト変更状態（将来のUndo/Redo用）"""
    is_dirty: bool                # 未保存の変更あり
    last_saved_at: Optional[datetime]
```

---

## 6. クラス設計

### 6.1 目的からクラスへの写像

| 目的 | クラス | 責務 |
|------|--------|------|
| P1.1 | SourceFileManager | S0→S1 遷移管理 |
| P1.1 | PlaybackManager | S1→S1' VirtualTimeline構築 |
| P1.2 | WaveformWorker | S1→S2 波形抽出 |
| P1.2 | SpectrogramWorker | S1→S2 スペクトログラム抽出 |
| P1.2 | WaveformWidget | 波形・スペクトログラム表示 |
| P1.3 | ChapterManager | S2→S3 チャプター管理 |
| P1.4 | ProjectPersistence | S3↔S4 永続化 |
| P1.5 | ExportOrchestrator | S4→S5 エクスポート管理 |

### 6.2 クラス詳細

#### SourceFileManager

```
責務: S0 → S1 の遷移を管理

入力:
  - Path (ローカルファイル)
  - URL (YouTube)

出力:
  - List[SourceFile]
  - source_order_changed シグナル

インターフェース:
  + add_source(path: Path) -> SourceFile
  + add_from_url(url: str) -> SourceFile
  + remove_source(index: int) -> None
  + reorder_sources(new_order: List[int]) -> None
  + get_sources() -> List[SourceFile]

依存: なし（最上流）
```

#### PlaybackManager

```
責務:
  1. S1 → S1' VirtualTimeline構築・管理
  2. 再生制御
  3. 座標変換

保持するデータ:
  - VirtualTimeline

入力:
  - List[SourceFile] (from SourceFileManager)
  - seek_position: int (仮想座標)

出力:
  - position_changed(virtual_ms: int) シグナル
  - source_switched(index: int) シグナル

インターフェース:
  + set_sources(sources: List[SourceFile]) -> None
  + get_virtual_timeline() -> VirtualTimeline
  + play() -> None
  + pause() -> None
  + seek(virtual_ms: int) -> None
  + get_position() -> int
  + virtual_to_source(virtual_ms) -> Tuple[int, int]
  + source_to_virtual(index, source_ms) -> int
  + get_total_duration() -> int
  + get_source_boundaries() -> List[int]

依存: SourceFileManager (sources)
```

#### WaveformWorker / SpectrogramWorker

```
責務: S1 → S2 分析データ生成

入力:
  - SourceFile

出力:
  - WaveformData / SpectrogramData
  - progress(percent: int) シグナル
  - finished(data) シグナル

インターフェース:
  + start(source: SourceFile) -> None
  + cancel() -> None

依存: SourceFile
```

#### ChapterManager

```
責務:
  1. S2 → S3 チャプター管理
  2. S3 → S3' ExcludedRegions導出

保持するデータ:
  - List[ChapterData]

入力:
  - position: int (仮想座標)
  - title: str
  - is_excluded: bool

出力:
  - List[ChapterData]
  - chapters_changed シグナル

インターフェース:
  + add_chapter(position_ms: int, title: str) -> ChapterData
  + remove_chapter(index: int) -> None
  + update_chapter(index: int, **kwargs) -> None
  + set_excluded(index: int, excluded: bool) -> None
  + get_chapters() -> List[ChapterData]
  + get_excluded_regions() -> List[ExcludedRegion]

依存: PlaybackManager (VirtualTimeline参照)
```

#### ProjectPersistence

```
責務: S3 ↔ S4 の遷移（永続化/読込）

入力:
  - List[SourceFile]
  - List[ChapterData]
  - ExportSettings

出力:
  - VCEProject (.vce.json)
  - ChapterFile (.txt)

インターフェース:
  + save_project(path: Path, project: VCEProject) -> None
  + load_project(path: Path) -> VCEProject
  + export_chapters(path: Path, chapters: List[ChapterData]) -> None
  + import_chapters(path: Path) -> List[ChapterData]

依存: なし（データ変換のみ）
```

#### ExportOrchestrator

```
責務:
  1. S4 → S4' ExtractionPlan導出
  2. S4' → S5 エクスポート実行

保持するデータ:
  - ExportState
  - ExtractionPlan

入力:
  - VCEProject
  - ExportSettings

出力:
  - ExportResult
  - progress_updated(percent: int) シグナル
  - state_changed(state: ExportState) シグナル
  - export_completed(result: ExportResult) シグナル

インターフェース:
  + calculate_extraction_plan(project: VCEProject) -> ExtractionPlan
  + start_export(project: VCEProject, settings: ExportSettings) -> None
  + start_split(project: VCEProject, settings: SplitSettings) -> None
  + cancel() -> None
  + get_state() -> ExportState

依存: VCEProject, ExcludedRegions
```

### 6.3 依存関係図

```
                    ┌─────────────────┐
                    │SourceFileManager│
                    │    (S0→S1)      │
                    └────────┬────────┘
                             │ List[SourceFile]
                             ▼
                    ┌─────────────────┐
                    │ PlaybackManager │
                    │  (S1→S1')       │
                    │  VirtualTimeline│
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ WaveformWorker  │ │SpectrogramWorker│ │  (座標系参照)   │
│   (S1→S2)       │ │   (S1→S2)       │ │                 │
└────────┬────────┘ └────────┬────────┘ │                 │
         │ WaveformData      │ SpectrogramData   │
         ▼                   ▼                   ▼
┌─────────────────────────────────────┐ ┌─────────────────┐
│          WaveformWidget             │ │ ChapterManager  │
│           (判断支援)                │ │   (S2→S3)       │
│  - 波形描画                         │ │   (S3→S3')      │
│  - スペクトログラム描画              │ │ ExcludedRegions │
│  - ハッチング（ExcludedRegions参照） │◄┤                 │
│  - 境界線（VirtualTimeline参照）     │ │                 │
└─────────────────────────────────────┘ └────────┬────────┘
                                                 │ List[ChapterData]
                                                 │ List[ExcludedRegion]
                                                 ▼
                                       ┌─────────────────┐
                                       │ProjectPersistence│
                                       │   (S3↔S4)        │
                                       └────────┬────────┘
                                                │ VCEProject
                                                ▼
                                       ┌─────────────────┐
                                       │ExportOrchestrator│
                                       │   (S4→S4'→S5)    │
                                       │ ExtractionPlan   │
                                       │ ExportState      │
                                       └────────┬────────┘
                                                │
                         ┌──────────────────────┼──────────────────────┐
                         ▼                      ▼                      ▼
                  ┌──────────┐           ┌──────────┐           ┌──────────┐
                  │vce-encode│           │vce-split │           │vce-chapt │
                  │  (CLI)   │           │  (CLI)   │           │  (CLI)   │
                  └──────────┘           └──────────┘           └──────────┘
```

---

## 7. トレーサビリティマトリックス

| 目的(Why) | 手段(How) | クラス(Who) | データ構造(What) |
|-----------|-----------|-------------|------------------|
| P1.1 取得 | M1.1.1 読込 | SourceFileManager | SourceFile |
| | M1.1.2 DL | | |
| | M1.1.3 検出 | | MediaInfo |
| | M1.1.4 仮想TL | PlaybackManager | VirtualTimeline |
| P1.2 支援 | M1.2.1 映像 | PlaybackManager | |
| | M1.2.2 音声 | | |
| | M1.2.3 波形 | WaveformWorker | WaveformData |
| | M1.2.4 スペクトロ | SpectrogramWorker | SpectrogramData |
| | M1.2.5 ナビ | PlaybackManager | |
| P1.3 構造 | M1.3.1 追加 | ChapterManager | ChapterData |
| | M1.3.2 除外 | | ExcludedRegion |
| | M1.3.3 順序 | SourceFileManager | |
| | M1.3.4 表示 | WaveformWidget | |
| P1.4 永続 | M1.4.1 JSON | ProjectPersistence | VCEProject |
| | M1.4.2 TXT | | |
| P1.5 出力 | M1.5.1 計画 | ExportOrchestrator | ExtractionPlan |
| | M1.5.2 エンコード | | ExportState |
| | M1.5.3 埋込 | | |
| | M1.5.4 焼込 | | |
| | M1.5.5 分割 | | ExportResult |

---

## 8. 作用の分類

### 8.1 直接作用（状態遷移）

| 作用 | 遷移 | 責任クラス | 生成データ |
|------|------|-----------|-----------|
| ファイル取得 | S0→S1 | SourceFileManager | SourceFile |
| 座標系構築 | S1→S1' | PlaybackManager | VirtualTimeline |
| 波形抽出 | S1→S2 | WaveformWorker | WaveformData |
| スペクトロ抽出 | S1→S2 | SpectrogramWorker | SpectrogramData |
| チャプター定義 | S2→S3 | ChapterManager | ChapterData |
| 除外区間計算 | S3→S3' | ChapterManager | ExcludedRegion |
| 永続化 | S3→S4 | ProjectPersistence | VCEProject |
| 計画立案 | S4→S4' | ExportOrchestrator | ExtractionPlan |
| エンコード | S4'→S5 | ExportOrchestrator | ExportResult |

### 8.2 間接作用（支援）

| 作用 | 支援対象 | 責任クラス |
|------|----------|-----------|
| 波形表示 | 人間判断 → チャプター定義 | WaveformWidget |
| スペクトログラム表示 | 人間判断 → チャプター定義 | WaveformWidget |
| プレビュー再生 | 人間判断 → チャプター定義 | PlaybackManager |
| ハッチング表示 | 人間判断 → 除外区間確認 | WaveformWidget |
| 境界線表示 | 人間判断 → ソース確認 | WaveformWidget |

### 8.3 制約作用（前提条件）

| 制約 | 内容 |
|------|------|
| S1必須 | VirtualTimeline構築にはS1が前提 |
| S1'必須 | 波形抽出は座標系確定後 |
| S2必須 | 人間判断には分析データが必要 |
| S3必須 | 永続化には構造化が前提 |
| S3'必須 | 計画立案には除外区間計算が前提 |
| S4'必須 | エンコードには計画が前提 |

---

## 9. 変更履歴

| 日付 | 変更内容 |
|------|---------|
| 2026-01-12 | 初版作成 |
| 2026-01-12 | VirtualTimeline、ExcludedRegions、ExtractionPlan等の導出構造を追加 |
| 2026-01-12 | WaveformData、SpectrogramData、ExportState等を追加 |

---

## 参照ドキュメント

- [DESIGN_PRINCIPLES.md](./DESIGN_PRINCIPLES.md) - 設計原則
- [vce_feature_matrix.md](./vce_feature_matrix.md) - 機能マトリックス
