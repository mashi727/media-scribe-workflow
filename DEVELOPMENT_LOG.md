# Development Log

開発ログ（2025-12-29〜）- 新しい順

過去のログは `DEVELOPMENT_LOG_as_of_2025-12-29.md` を参照。

---

## 今後の予定

### video-chapter-editor

- UI大改造（下記参照）
- 単一エンコードパス実装

### report-workflow

- 配管のプロトタイプは完了
- 陶器（GUI）の設計は video-chapter-editor 完成後

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

| ステップ | ツール | 分類 | 備考 |
|----------|--------|------|------|
| **入力取得** |||
| YouTube DL | ytdl-claude | 🔧 | URL → MP4 + SRT |
| ファイル転送 | Finder/手動 | 🔧 | iPhone → Mac |
| **─── 境界線 ───** |||
| **動画編集** |||
| ソース選択 | video-chapter-editor | 🏺 | ダイアログ |
| 結合（MP3） | video-chapter-editor | 🏺 | -c copy無劣化 |
| トリム | video-chapter-editor | 🏺 | 波形+プレビュー |
| カバー設定 | video-chapter-editor | 🏺 | ダイアログ |
| チャプター編集 | video-chapter-editor | 🏺 | メイン機能 |
| 書出 | video-chapter-editor | 🏺 | 焼込+エンコード |
| **─── 境界線 ───** |||
| **後続処理** |||
| YouTubeアップロード | ブラウザ/手動 | 🔧 | 字幕生成待ち |
| 字幕取得 | yt-srt | 🔧 | SRT出力 |
| AI分析 | Claude Code | 🔧 | /rehearsal skill |
| レポート生成 | rehearsal-finalize | 🔧 | PDF + chapters |

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

**更新**: 2025-12-29
