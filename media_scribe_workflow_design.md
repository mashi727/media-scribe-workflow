# Media Scribe Workflow 設計書

## 概要

この文書は、Media Scribe Workflow アプリケーションの状態設計・データモデル・アルゴリズムに関する設計議論をまとめたものです。

---

## 1. 背景と課題

### 1.1 現状の仮想タイムライン実装

既存の `chapter_manager.py` には仮想タイムラインの基本実装が含まれている：

- **ソースオフセット計算** (`get_source_offsets`)
- **ローカル時間 ↔ 絶対時間の変換** (`_local_to_absolute`, `_virtual_to_source`)
- **仮想タイムライン上でのチャプター追加** (`add_chapter_at_position`)

### 1.2 現状の問題点

```
【現状】ソースファイル = タイムライン上の単位
- シングルファイル: SourceFile 1つ → チャプターはlocal_time_msのみ
- マルチファイル: SourceFile複数 → チャプターはsource_index + local_time_ms

区間移動ができない:
[0:00 A][2:00 B][5:00 C] → Bを末尾に移動したい → 不可能
```

### 1.3 拡張要件

1. **任意区間の切り出し・移動** - タイムライン上で範囲選択して別位置にドラッグ
2. **シングル/マルチファイルの統一** - 同一クラスで両方を扱う

### 1.4 トリミングの現状実装

現状では、トリミングは編集時点では行わず、チャプターに識別子 `"--"` を付したチャプター区間をエンコード（出力時）に出力しないという実装になっている。

```python
def get_chapters_for_export(self, exclude_marked: bool = False) -> List[ChapterInfo]:
    """エクスポート用チャプターリストを取得
    Args:
        exclude_marked: "--"プレフィックスのチャプターを除外するか
    """
```

---

## 2. 提案: クリップベースモデル

### 2.1 基本概念

```
【新モデル】Clip = ソースの部分参照
Clip(source_index, in_point_ms, out_point_ms)

タイムライン = Clipの順序付きリスト

例: 単一ファイルでも内部的にはClipとして扱う
Source: video.mp4 (10分)

初期状態:
[Clip0: source=0, in=0, out=600000]  # 全体

区間選択して分割:
[Clip0: in=0, out=120000][Clip1: in=120000, out=300000][Clip2: in=300000, out=600000]
       (0-2分)                  (2-5分)                      (5-10分)

Clip1を末尾に移動:
[Clip0: 0-2分][Clip2: 5-10分][Clip1: 2-5分]
```

### 2.2 チャプターの紐づけ先

**採用案: チャプターはClipに紐づく（案B）**

理由：
- Clip移動がメイン操作 → チャプター自動追従が自然
- Clip分割は「意図的な編集点」→ チャプター再割当ては明示的で良い

### 2.3 Clip分割時の処理

```
【分割前】
Clip0: in=0, out=300000 (0:00-5:00)
  └── chapters: [
        {offset: 0,      title: "Intro"},
        {offset: 120000, title: "Main"},    # 2:00
        {offset: 240000, title: "Bridge"}   # 4:00
      ]

【3:00で分割】
                    ↓ split_at(180000)

Clip0: in=0, out=180000 (0:00-3:00)
  └── chapters: [
        {offset: 0,      title: "Intro"},
        {offset: 120000, title: "Main"}     # 2:00
      ]

Clip1: in=180000, out=300000 (3:00-5:00)
  └── chapters: [
        {offset: 60000,  title: "Bridge"}   # 元4:00 → Clip1内では1:00
      ]
```

---

## 3. 状態設計

### 3.1 現状の問題

```
【現状】各マネージャーが独立して状態を持つ
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ SourceManager   │  │ ChapterManager  │  │ PlaybackManager │
│  _sources[]     │  │  _chapters[]    │  │  _current_idx   │
│  _work_dir      │  │  _edited        │  │  _position      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         ↑                   ↑                    ↑
         └───────── 同期が必要 ─────────┘
                （シグナルで連携）

問題:
- 状態の整合性を各所で保証する必要がある
- ソース変更 → チャプター再計算 → 再生位置調整 → ...
- どこで何が起きるか追いにくい
```

### 3.2 提案: 単一の状態ツリー + イミュータブル更新

```
【新設計】単一のAppState
┌─────────────────────────────────────────────┐
│ AppState (immutable)                        │
│  ├── sources: List[SourceFile]              │
│  ├── timeline: VirtualTimeline              │
│  │     ├── clips: List[Clip]                │
│  │     └── (各ClipがChapterを持つ)          │
│  ├── playback: PlaybackState                │
│  │     ├── position_ms: int                 │
│  │     ├── is_playing: bool                 │
│  │     └── current_clip_index: int          │
│  └── export: Optional[ExportSnapshot]       │
└─────────────────────────────────────────────┘

更新は常に新しいAppStateを生成
  → 整合性が自動的に保証される
  → Undo/Redoも容易
```

### 3.3 状態遷移の例

```python
# 現状: 複数箇所で状態変更
source_manager.add_source(path)
chapter_manager.recalculate_times()
playback_manager.reload()
ui.update_table()
ui.update_timeline()

# 新設計: 単一のアクション
new_state = app_state.with_source_added(path)
app.set_state(new_state)  # UIは自動的に反映
```

### 3.4 エンコード時のスナップショット

```python
class ExportOrchestrator:
    def start_export(self, ...):
        # エンコード開始時点でスナップショットを取得
        self._export_snapshot = ExportSnapshot(
            clips=deepcopy(timeline.clips),
            chapters=deepcopy(timeline.get_all_chapters()),
            sources=list(source_manager.sources)
        )
        
        # 以降はスナップショットを使ってエンコード
        # → 元のtimelineは編集可能
```

### 3.5 ファイル操作の整理

```
【このアプリがやること】
- ソースファイルの参照（読み取りのみ）
- エンコード出力ファイルの新規作成

【このアプリがやらないこと】
- ソースファイルの削除/移動/上書き
```

---

## 4. データモデル

### 4.1 基本データ型（イミュータブル）

```python
from dataclasses import dataclass, field
from typing import List, Optional, FrozenSet
from pathlib import Path
from enum import Enum, auto
import uuid


@dataclass(frozen=True)
class SourceFile:
    """ソースファイル（イミュータブル）"""
    id: str                    # UUID
    path: Path
    duration_ms: int
    file_type: str             # "mp4", "mov", "mp3", etc.
    
    @staticmethod
    def create(path: Path, duration_ms: int) -> "SourceFile":
        return SourceFile(
            id=str(uuid.uuid4()),
            path=path,
            duration_ms=duration_ms,
            file_type=path.suffix[1:].lower()
        )


@dataclass(frozen=True)
class ClipChapter:
    """Clip内のチャプター（イミュータブル）"""
    id: str
    offset_ms: int             # Clip先頭からの相対位置
    title: str
    is_excluded: bool = False  # "--"プレフィックス相当
    
    @staticmethod
    def create(offset_ms: int, title: str) -> "ClipChapter":
        return ClipChapter(
            id=str(uuid.uuid4()),
            offset_ms=offset_ms,
            title=title,
            is_excluded=title.startswith("--")
        )


@dataclass(frozen=True)
class Clip:
    """タイムライン上の基本単位（イミュータブル）"""
    id: str
    source_id: str             # SourceFile.id への参照
    in_point_ms: int           # ソース内IN点
    out_point_ms: int          # ソース内OUT点
    chapters: tuple[ClipChapter, ...] = field(default_factory=tuple)
    
    @property
    def duration_ms(self) -> int:
        return self.out_point_ms - self.in_point_ms
    
    @staticmethod
    def create(source_id: str, in_point_ms: int, out_point_ms: int,
               chapters: tuple[ClipChapter, ...] = ()) -> "Clip":
        return Clip(
            id=str(uuid.uuid4()),
            source_id=source_id,
            in_point_ms=in_point_ms,
            out_point_ms=out_point_ms,
            chapters=chapters
        )
    
    def with_chapters(self, chapters: tuple[ClipChapter, ...]) -> "Clip":
        """チャプターを更新した新しいClipを返す"""
        return Clip(
            id=self.id,
            source_id=self.source_id,
            in_point_ms=self.in_point_ms,
            out_point_ms=self.out_point_ms,
            chapters=chapters
        )
```

### 4.2 タイムライン

```python
@dataclass(frozen=True)
class VirtualTimeline:
    """仮想タイムライン（イミュータブル）"""
    clips: tuple[Clip, ...] = field(default_factory=tuple)
    
    @property
    def duration_ms(self) -> int:
        return sum(clip.duration_ms for clip in self.clips)
    
    @property
    def clip_count(self) -> int:
        return len(self.clips)
    
    def get_clip_offsets(self) -> tuple[int, ...]:
        """各Clipの開始オフセット（累積）"""
        offsets = []
        cumulative = 0
        for clip in self.clips:
            offsets.append(cumulative)
            cumulative += clip.duration_ms
        return tuple(offsets)
    
    def timeline_to_clip(self, timeline_pos_ms: int) -> tuple[int, int]:
        """タイムライン位置 → (clip_index, offset_in_clip)"""
        cumulative = 0
        for idx, clip in enumerate(self.clips):
            if cumulative + clip.duration_ms > timeline_pos_ms:
                return (idx, timeline_pos_ms - cumulative)
            cumulative += clip.duration_ms
        # 末尾
        if self.clips:
            return (len(self.clips) - 1, self.clips[-1].duration_ms)
        return (0, 0)
    
    def clip_to_timeline(self, clip_index: int, offset_in_clip: int) -> int:
        """(clip_index, offset_in_clip) → タイムライン位置"""
        offsets = self.get_clip_offsets()
        if 0 <= clip_index < len(offsets):
            return offsets[clip_index] + offset_in_clip
        return 0
```

### 4.3 再生状態

```python
class PlaybackStatus(Enum):
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()


@dataclass(frozen=True)
class PlaybackState:
    """再生状態（イミュータブル）"""
    status: PlaybackStatus = PlaybackStatus.STOPPED
    position_ms: int = 0       # タイムライン上の位置
    
    @property
    def is_playing(self) -> bool:
        return self.status == PlaybackStatus.PLAYING
```

### 4.4 エクスポート設定

```python
class EncoderType(Enum):
    """エンコーダー種別"""
    LIBX264 = "libx264"
    LIBX265 = "libx265"
    H264_VIDEOTOOLBOX = "h264_videotoolbox"  # macOS HW
    HEVC_VIDEOTOOLBOX = "hevc_videotoolbox"  # macOS HW
    H264_NVENC = "h264_nvenc"                # NVIDIA HW
    HEVC_NVENC = "hevc_nvenc"                # NVIDIA HW
    COPY = "copy"                            # 再エンコードなし


class QualityPreset(Enum):
    """品質プリセット"""
    HIGH = auto()      # 8Mbps / CRF 20
    MEDIUM = auto()    # 4Mbps / CRF 23
    LOW = auto()       # 2Mbps / CRF 26
    SOURCE = auto()    # ソースと同じビットレート


class OutputFormat(Enum):
    """出力形式"""
    MP4 = "mp4"
    MOV = "mov"
    MKV = "mkv"
    MP3 = "mp3"        # 音声のみ
    M4A = "m4a"        # 音声のみ


@dataclass(frozen=True)
class ColorspaceSettings:
    """色空間設定"""
    color_primaries: Optional[str] = None    # bt709, bt2020, etc.
    color_transfer: Optional[str] = None     # srgb, smpte2084 (HDR), etc.
    color_matrix: Optional[str] = None       # bt709, bt2020nc, etc.
    is_hdr: bool = False


@dataclass(frozen=True)
class OverlaySettings:
    """オーバーレイ設定"""
    enabled: bool = False
    font_name: str = "Helvetica"
    font_size: int = 48
    font_color: str = "white"
    background_color: Optional[str] = "black@0.5"  # 半透明背景
    position: str = "top"                    # top, bottom, center
    margin: int = 20
    duration_sec: float = 5.0                # 表示時間


@dataclass(frozen=True)
class ChapterExportSettings:
    """チャプターエクスポート設定"""
    embed_chapters: bool = True              # メタデータに埋め込み
    cut_excluded: bool = True                # "--"チャプター区間を除外
    split_by_chapter: bool = False           # チャプターごとにファイル分割


@dataclass(frozen=True)
class AudioSettings:
    """音声設定"""
    codec: str = "aac"
    bitrate_kbps: int = 192
    sample_rate: int = 48000
    channels: int = 2


@dataclass(frozen=True)
class VideoSettings:
    """映像設定"""
    encoder: EncoderType = EncoderType.LIBX264
    quality_preset: QualityPreset = QualityPreset.MEDIUM
    bitrate_kbps: Optional[int] = None       # None = プリセットに従う
    crf: Optional[int] = None                # None = プリセットに従う
    max_width: Optional[int] = None          # リサイズ上限
    max_height: Optional[int] = None
    frame_rate: Optional[float] = None       # None = ソースのまま
    colorspace: ColorspaceSettings = field(default_factory=ColorspaceSettings)


@dataclass(frozen=True)
class ExportSettings:
    """エクスポート設定（統合）"""
    output_format: OutputFormat = OutputFormat.MP4
    video: VideoSettings = field(default_factory=VideoSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    chapters: ChapterExportSettings = field(default_factory=ChapterExportSettings)
    overlay: OverlaySettings = field(default_factory=OverlaySettings)
    
    # 出力ファイル名テンプレート（チャプター分割時）
    filename_template: str = "{base}_{index:02d}_{title}"
    
    @property
    def is_audio_only(self) -> bool:
        return self.output_format in (OutputFormat.MP3, OutputFormat.M4A)
```

### 4.5 エクスポートスナップショット

```python
class ExportStatus(Enum):
    IDLE = auto()
    PREPARING = auto()
    ENCODING = auto()
    COMPLETED = auto()
    ERROR = auto()


@dataclass(frozen=True)
class ExportSnapshot:
    """エクスポート用スナップショット（イミュータブル）"""
    
    # スナップショット対象のデータ
    sources: tuple[SourceFile, ...]
    timeline: VirtualTimeline
    
    # 出力先
    output_dir: Path
    output_base_name: str
    
    # 設定
    settings: ExportSettings
    
    # カバー画像（音声ファイル用）
    cover_image_path: Optional[Path] = None
    
    # 状態
    status: ExportStatus = ExportStatus.IDLE
    progress_percent: int = 0
    current_phase: str = ""                  # "Extracting", "Encoding", "Merging", etc.
    error_message: Optional[str] = None
    
    # 結果
    output_files: tuple[Path, ...] = field(default_factory=tuple)
    
    @property
    def output_path(self) -> Path:
        """単一ファイル出力時のパス"""
        ext = self.settings.output_format.value
        return self.output_dir / f"{self.output_base_name}.{ext}"
    
    @property
    def is_split_export(self) -> bool:
        return self.settings.chapters.split_by_chapter
```

### 4.6 アプリケーション状態（ルート）

```python
@dataclass(frozen=True)
class AppState:
    """アプリケーション全体の状態（イミュータブル）"""
    
    # ソースプール
    sources: tuple[SourceFile, ...] = field(default_factory=tuple)
    
    # タイムライン
    timeline: VirtualTimeline = field(default_factory=VirtualTimeline)
    
    # 再生状態
    playback: PlaybackState = field(default_factory=PlaybackState)
    
    # エクスポート（実行中のみ）
    export: Optional[ExportSnapshot] = None
    
    # 作業ディレクトリ
    work_dir: Optional[Path] = None
    
    # 編集フラグ
    is_modified: bool = False
    
    # ==== ヘルパーメソッド ====
    
    def get_source_by_id(self, source_id: str) -> Optional[SourceFile]:
        """IDでソースを検索"""
        for source in self.sources:
            if source.id == source_id:
                return source
        return None
    
    def get_all_chapters(self) -> list[tuple[int, ClipChapter]]:
        """全チャプターを (timeline_position_ms, chapter) のリストで取得"""
        result = []
        offsets = self.timeline.get_clip_offsets()
        for idx, clip in enumerate(self.timeline.clips):
            clip_offset = offsets[idx] if idx < len(offsets) else 0
            for chapter in clip.chapters:
                result.append((clip_offset + chapter.offset_ms, chapter))
        return result
    
    @property
    def is_empty(self) -> bool:
        return len(self.sources) == 0
    
    @property  
    def is_exporting(self) -> bool:
        return self.export is not None and self.export.status == ExportStatus.ENCODING
```

---

## 5. システム全体像

### 5.1 アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Media Scribe Workflow                            │
├─────────────────────────────────────────────────────────────────────┤
│  GUI (陶器)                                                         │
│  ├── Editor GUI - タイムライン編集、プレビュー                        │
│  └── Report GUI - レポート設定、プレビュー                           │
├─────────────────────────────────────────────────────────────────────┤
│  CLI (陶器)                                                         │
│  └── msw <subcommand> [options]                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Subcommands (実処理)                                               │
│  ├── msw encode     - 動画/音声エンコード                            │
│  ├── msw split      - チャプター分割出力                             │
│  ├── msw chapters   - チャプターリスト出力                           │
│  ├── msw upload     - YouTube アップロード                          │
│  ├── msw fetch-srt  - YouTube SRT取得                               │
│  ├── msw whisper    - Whisper文字起こし                             │
│  ├── msw structure  - SRT構造化（Claude）                           │
│  ├── msw report     - LuaTeXレポート生成                            │
│  └── msw pdf        - PDF出力                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 入出力

**入力:**
- メディアファイル: `.mp4`, `.mov`, `.mp3`, `.m4a`, ...（複数可）
- チャプターファイル: `.txt`, `.chapters`（任意）
- プロジェクトファイル: `.vce.json`（任意）

**出力:**
- プロジェクトファイル: `.vce.json`
- チャプターリスト: `.txt`（YouTube用）, `.json`
- エンコード済み動画/音声: `.mp4`, `.mp3`（単一/分割）
- SRTファイル: `.srt`（YouTube/Whisper）
- LuaTeXファイル: `.tex`
- PDFファイル: `.pdf`

---

## 6. 状態の定義

### 6.1 プロジェクト状態 (ProjectState)

| 状態 | 説明 |
|------|------|
| Empty | プロジェクト未作成/未読み込み |
| Creating | 新規作成中（ソース選択待ち） |
| Loaded | 読み込み済み（変更なし） |
| Modified | 編集済み（未保存） |
| Saving | 保存中 |

### 6.2 タイムライン状態 (TimelineState)

| 状態 | 説明 |
|------|------|
| Empty | クリップなし |
| Ready | 編集可能 |
| Editing | 編集操作中（ドラッグ中など） |

### 6.3 再生状態 (PlaybackState)

| 状態 | 説明 |
|------|------|
| Stopped | 停止 |
| Playing | 再生中 |
| Paused | 一時停止 |
| Seeking | シーク中 |
| Buffering | バッファリング中 |

### 6.4 エンコード状態 (EncodeState)

| 状態 | 説明 |
|------|------|
| Idle | 待機 |
| Preparing | 準備中（スナップショット作成） |
| Encoding | エンコード中 |
| Splitting | 分割出力中 |
| Completed | 完了 |
| Error | エラー |
| Cancelled | キャンセル |

### 6.5 文字起こし状態 (TranscriptionState)

| 状態 | 説明 |
|------|------|
| Idle | 待機 |
| Uploading | YouTube アップロード中 |
| FetchingSrt | SRT取得待ち/取得中 |
| Whisper | Whisper実行中 |
| Completed | 完了 |
| Error | エラー |

### 6.6 レポート状態 (ReportState)

| 状態 | 説明 |
|------|------|
| Idle | 待機 |
| Structuring | SRT構造化中（Claude） |
| Generating | LuaTeX生成中 |
| Compiling | PDF コンパイル中 |
| Completed | 完了 |
| Error | エラー |

---

## 7. 状態遷移表

### 7.1 プロジェクト状態遷移

| 現在 \ アクション | NewProject | LoadProject | LoadSources | Edit* | Save | SaveAs | Close |
|---|---|---|---|---|---|---|---|
| **Empty** | → Creating | → Loaded | → Modified | - | - | - | - |
| **Creating** | - | - | → Modified | - | - | - | → Empty |
| **Loaded** | → Creating¹ | → Loaded¹ | → Modified | → Modified | → Loaded | → Loaded | → Empty¹ |
| **Modified** | → Creating¹ | → Loaded¹ | → Modified | → Modified | → Loaded | → Loaded | → Empty¹ |
| **Saving** | - | - | - | - | - | - | - |

> ¹ 未保存確認ダイアログを表示  
> \* Edit = SplitClip, MoveClip, AddChapter, EditChapter, DeleteChapter, ToggleExcluded, etc.

### 7.2 タイムライン状態遷移

| 現在 \ アクション | AddClip | RemoveClip | SplitClip | MoveClip | MergeClips | ClearAll |
|---|---|---|---|---|---|---|
| **Empty** | → Ready | - | - | - | - | - |
| **Ready** | → Ready | → Ready/Empty² | → Ready | → Ready | → Ready | → Empty |
| **Editing** | - | - | - | - | - | - |

> ² 最後のClip削除時はEmptyに遷移

### 7.3 再生状態遷移

| 現在 \ アクション | Play | Pause | Stop | Seek | SeekComplete | MediaEnd | Error |
|---|---|---|---|---|---|---|---|
| **Stopped** | → Playing | - | - | → Seeking | - | - | → Stopped |
| **Playing** | - | → Paused | → Stopped | → Seeking | - | → Stopped | → Stopped |
| **Paused** | → Playing | - | → Stopped | → Seeking | - | - | → Stopped |
| **Seeking** | - | - | → Stopped | → Seeking | → Playing/Paused³ | - | → Stopped |
| **Buffering** | - | → Paused | → Stopped | → Seeking | → Playing | - | → Stopped |

> ³ シーク前の状態を復元

### 7.4 エンコード状態遷移

| 現在 \ アクション | StartEncode | StartSplit | Cancel | Progress | Complete | Error |
|---|---|---|---|---|---|---|
| **Idle** | → Preparing | → Preparing | - | - | - | - |
| **Preparing** | - | - | → Cancelled | → Encoding/Splitting | - | → Error |
| **Encoding** | - | - | → Cancelled | → Encoding | → Completed | → Error |
| **Splitting** | - | - | → Cancelled | → Splitting | → Completed | → Error |
| **Completed** | → Preparing | → Preparing | - | - | - | - |
| **Error** | → Preparing | → Preparing | - | - | - | - |
| **Cancelled** | → Preparing | → Preparing | - | - | - | - |

### 7.5 文字起こし状態遷移

| 現在 \ アクション | Upload | FetchSrt | RunWhisper | Cancel | Complete | Error |
|---|---|---|---|---|---|---|
| **Idle** | → Uploading | → FetchingSrt | → Whisper | - | - | - |
| **Uploading** | - | - | - | → Idle | → FetchingSrt⁴ | → Error |
| **FetchingSrt** | - | - | - | → Idle | → Completed | → Error |
| **Whisper** | - | - | - | → Idle | → Completed | → Error |
| **Completed** | → Uploading | → FetchingSrt | → Whisper | - | - | - |
| **Error** | → Uploading | → FetchingSrt | → Whisper | - | - | - |

> ⁴ アップロード完了後、自動的にSRT取得待ちへ遷移

### 7.6 レポート状態遷移

| 現在 \ アクション | Structure | Generate | Compile | Cancel | Complete | Error |
|---|---|---|---|---|---|---|
| **Idle** | → Structuring | → Generating⁵ | → Compiling⁵ | - | - | - |
| **Structuring** | - | - | - | → Idle | → Generating | → Error |
| **Generating** | - | - | - | → Idle | → Compiling | → Error |
| **Compiling** | - | - | - | → Idle | → Completed | → Error |
| **Completed** | → Structuring | → Generating | → Compiling | - | - | - |
| **Error** | → Structuring | → Generating | → Compiling | - | - | - |

> ⁵ 前段階の出力ファイルが存在する場合のみ実行可能

---

## 8. クロス状態制約表

プロジェクト状態と他の状態の許可/禁止の組み合わせ:

| 状態 | Empty | Creating | Loaded | Modified | Saving |
|------|-------|----------|--------|----------|--------|
| Timeline.Ready | ✗ | ✓ | ✓ | ✓ | ✓ |
| Playback.Playing | ✗ | ✗ | ✓ | ✓ | ✓ |
| Encode.Encoding | ✗ | ✗ | ✓ | ✓ | ✗ |
| Transcription.* | ✗ | ✗ | ✓ | ✓ | ✓ |
| Report.* | ✗ | ✗ | ✓ | ✓ | ✓ |

---

## 9. イベントドリブン: サブコマンド呼び出しマトリクス

| GUIアクション | トリガー条件 | サブコマンド | 入力 | 出力 |
|---|---|---|---|---|
| Export開始 | EncodeState → Preparing | `msw encode` | project.json | .mp4/.mp3 |
| 分割出力 | split_by_chapter=true | `msw split` | project.json | .mp4 × N |
| チャプター出力 | Export完了 or 手動 | `msw chapters` | project.json | .txt/.json |
| YouTubeアップ | 手動 or 自動パイプライン | `msw upload` | .mp4, metadata | video_id |
| SRT取得 | アップロード完了 | `msw fetch-srt` | video_id | .srt |
| Whisper実行 | 手動 or 自動パイプライン | `msw whisper` | .mp4/.mp3 | .srt |
| 構造化 | SRT取得完了 | `msw structure` | .srt, project.json | structured.json |
| レポート生成 | 構造化完了 | `msw report` | structured.json, project.json | .tex |
| PDF出力 | レポート生成完了 | `msw pdf` | .tex | .pdf |

---

## 10. 処理パイプライン

### 10.1 標準パイプライン

```
encode → chapters → whisper/upload → fetch-srt → structure → report → pdf
```

### 10.2 プロジェクトファイルでのパイプライン定義

```json
{
  "pipeline": {
    "auto_run": true,
    "steps": [
      { "command": "encode", "on_complete": "chapters" },
      { "command": "chapters", "on_complete": "whisper" },
      { "command": "whisper", "on_complete": "structure" },
      { "command": "structure", "on_complete": "report" },
      { "command": "report", "on_complete": "pdf" }
    ],
    "on_error": "stop"
  }
}
```

---

## 11. プロジェクトファイル構造（完全版）

```json
{
  "version": "2.0",
  "created": "2025-01-20T12:00:00",
  "modified": "2025-01-20T14:30:00",

  "sources": [
    { "id": "src-001", "path": "video1.mp4", "duration_ms": 600000 },
    { "id": "src-002", "path": "video2.mp4", "duration_ms": 300000 }
  ],

  "timeline": {
    "clips": [
      {
        "id": "clip-001",
        "source_id": "src-001",
        "in_point_ms": 0,
        "out_point_ms": 300000,
        "chapters": [
          { "id": "ch-001", "offset_ms": 0, "title": "Intro", "is_excluded": false },
          { "id": "ch-002", "offset_ms": 120000, "title": "--カット", "is_excluded": true }
        ]
      },
      {
        "id": "clip-002",
        "source_id": "src-001",
        "in_point_ms": 300000,
        "out_point_ms": 600000,
        "chapters": [
          { "id": "ch-003", "offset_ms": 0, "title": "Main", "is_excluded": false }
        ]
      }
    ]
  },

  "export_settings": {
    "output_format": "mp4",
    "video": {
      "encoder": "libx264",
      "quality_preset": "medium",
      "bitrate_kbps": 4000,
      "crf": 23
    },
    "audio": {
      "codec": "aac",
      "bitrate_kbps": 192
    },
    "chapters": {
      "embed": true,
      "cut_excluded": true,
      "split_by_chapter": false
    },
    "overlay": {
      "enabled": true,
      "font_name": "Helvetica",
      "font_size": 48,
      "position": "top",
      "duration_sec": 5.0
    }
  },

  "transcription": {
    "method": "whisper",
    "language": "ja",
    "model": "large-v3"
  },

  "report": {
    "claude_command": "rehearsal-report",
    "template": "orchestra_rehearsal",
    "metadata": {
      "title": "第九 リハーサル",
      "conductor": "山田太郎",
      "organization": "〇〇交響楽団",
      "date": "2025-01-20"
    }
  },

  "pipeline": {
    "auto_run": false,
    "steps": [
      { "command": "encode", "on_complete": "chapters" },
      { "command": "chapters", "on_complete": "whisper" },
      { "command": "whisper", "on_complete": "structure" },
      { "command": "structure", "on_complete": "report" },
      { "command": "report", "on_complete": "pdf" }
    ],
    "on_error": "stop"
  },

  "outputs": {
    "encoded_video": "output/rehearsal_encoded.mp4",
    "chapters_txt": "output/rehearsal.chapters.txt",
    "srt_file": "output/rehearsal.srt",
    "structured_json": "output/rehearsal_structured.json",
    "tex_file": "output/rehearsal.tex",
    "pdf_file": "output/rehearsal.pdf"
  }
}
```

---

## 12. 主要操作のアルゴリズム

### 12.1 Clip分割

```python
def split_clip(self, clip_index: int, split_offset_ms: int) -> Tuple[Clip, Clip]:
    """Clipを分割"""
    clip = self.clips[clip_index]
    split_point_in_source = clip.in_point_ms + split_offset_ms
    
    # 前半Clip
    clip_a = Clip(
        source_id=clip.source_id,
        in_point_ms=clip.in_point_ms,
        out_point_ms=split_point_in_source,
        chapters=tuple(ch for ch in clip.chapters if ch.offset_ms < split_offset_ms)
    )
    
    # 後半Clip（チャプターのoffsetを再計算）
    clip_b = Clip(
        source_id=clip.source_id,
        in_point_ms=split_point_in_source,
        out_point_ms=clip.out_point_ms,
        chapters=tuple(
            ClipChapter(offset_ms=ch.offset_ms - split_offset_ms, title=ch.title)
            for ch in clip.chapters if ch.offset_ms >= split_offset_ms
        )
    )
    
    return clip_a, clip_b
```

### 12.2 Clip移動（再生位置追従）

```python
class VirtualTimeline:
    def move_clip(self, from_index: int, to_index: int):
        """Clipを移動（再生位置も追従）"""
        
        # 現在再生中のClipか？
        current_clip_index = self._get_playing_clip_index()
        current_offset_in_clip = self._get_offset_in_current_clip()
        
        # Clip移動
        clip = self.clips.pop(from_index)
        self.clips.insert(to_index, clip)
        
        # 再生位置を再計算
        if current_clip_index == from_index:
            # 移動したClipを再生中だった → 新しいタイムライン位置を計算
            new_timeline_pos = self._clip_to_timeline(to_index, current_offset_in_clip)
            self.playback_manager.seek_virtual(new_timeline_pos)
```

---

## 13. 次のステップ

1. **アクション（状態遷移）の列挙** - 各アクションの詳細仕様
2. **UIへの反映方法（リアクティブ）** - 状態変更時のUI更新パターン
3. **コードのスケルトン生成** - AppState, VirtualTimeline等のPythonコード実装

---

## 付録: 関連ファイル

- `state_transition_table.html` - 状態遷移表のHTML版（視覚化）
