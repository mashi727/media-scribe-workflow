# ワークフロー図

## 基本ワークフロー（単一動画 → SRT）

```mermaid
flowchart TD
    START([開始])
    INPUT[/"生の長時間動画<br>例: 13:30-17:00の練習録画"/]

    subgraph TRIM["1. 不要部分の削除 (video-trim)"]
        T1[休憩時間カット]
        T2[準備・片付けカット]
        T3[演奏部分のみ抽出]
        T1 --> T2 --> T3
    end

    subgraph CHAPTER["2. 構造化 (movie-viewer)"]
        C1[曲ごとに分割点決定]
        C2[チャプター名付与]
        C1 --> C2
    end

    subgraph CONCAT["3. 結合 (video-chapters)"]
        CO1[チャプター情報埋め込み]
        CO2[単一MP4出力]
        CO1 --> CO2
    end

    subgraph SRT["4. 字幕取得 (yt-srt)"]
        S1[YouTube字幕取得]
        S2[SRTファイル出力]
        S1 --> S2
    end

    OUTPUT[/"*.srt"/]
    END([終了])

    START --> INPUT
    INPUT --> TRIM
    TRIM --> CHAPTER
    CHAPTER --> CONCAT
    CONCAT --> SRT
    SRT --> OUTPUT
    OUTPUT --> END
```

## 拡張ワークフロー（複数ソース対応）

```mermaid
flowchart TD
    START([開始])

    subgraph INPUT["入力ソース"]
        I1[/"Wireless Pro<br>指揮者近くマイク"/]
        I2[/"iPhone<br>後方からの動画"/]
    end

    CHECK{複数ソースあり?}

    subgraph AUDIO["A. 音声処理"]
        A1[audio-normalize<br>音量正規化]
        A2[audio-extract-channel<br>指揮者チャンネル抽出]
        A3[文字起こし用音声]
        A1 --> A2 --> A3
    end

    subgraph VIDEO["B. 映像処理"]
        V1[video-trim<br>不要部分削除]
        V2[movie-viewer<br>チャプター付け]
        V1 --> V2
    end

    subgraph MERGE["C. 合成"]
        M1[video-replace-audio<br>動画+指揮者音声]
        M2[最終動画]
        M1 --> M2
    end

    subgraph SINGLE["単一ソース処理"]
        SG1[video-trim]
        SG2[movie-viewer]
        SG1 --> SG2
    end

    TRANS_METHOD{文字起こし方法}

    subgraph YT["YouTube字幕"]
        Y1[yt-srt]
    end

    subgraph WH["Whisper"]
        W1[whisper-remote]
    end

    OUTPUT[/"SRTファイル"/]
    END([終了])

    START --> INPUT
    INPUT --> CHECK
    CHECK -->|Yes| AUDIO
    CHECK -->|Yes| VIDEO
    AUDIO --> MERGE
    VIDEO --> MERGE
    CHECK -->|No| SINGLE
    MERGE --> TRANS_METHOD
    SINGLE --> TRANS_METHOD
    TRANS_METHOD -->|YouTube| YT
    TRANS_METHOD -->|Whisper| WH
    TRANS_METHOD -->|両方| YT
    TRANS_METHOD -->|両方| WH
    YT --> OUTPUT
    WH --> OUTPUT
    OUTPUT --> END
```

## 全体フロー

```mermaid
flowchart LR
    subgraph PHASE1["Phase 1: 前処理"]
        direction TB
        P1_IN{入力ソース}
        P1_YT[YouTube URL]
        P1_LOCAL[ローカル動画]
        P1_MULTI[複数ソース]

        P1_IN --> P1_YT
        P1_IN --> P1_LOCAL
        P1_IN --> P1_MULTI

        P1_YT --> P1_SRT1[yt-srt]
        P1_LOCAL --> P1_BASIC[基本パターン]
        P1_MULTI --> P1_ADV[拡張パターン]
    end

    subgraph PHASE2["Phase 2: 分析"]
        direction TB
        P2_SRT[/"SRTファイル"/]
        P2_LLM[LLMで分析<br>Claude/ChatGPT等]
        P2_PROMPT[プロンプト例参照]

        P2_SRT --> P2_LLM
        P2_PROMPT -.-> P2_LLM
    end

    subgraph PHASE3["Phase 3: 出力"]
        direction TB
        P3_CHECK{LaTeX?}
        P3_TEX[luatex-docker-remote<br>PDF生成]
        P3_MD[Markdown等]
        P3_OUT[/"最終出力"/]

        P3_CHECK -->|Yes| P3_TEX
        P3_CHECK -->|No| P3_MD
        P3_TEX --> P3_OUT
        P3_MD --> P3_OUT
    end

    PHASE1 --> PHASE2
    PHASE2 --> PHASE3
```

## ツール一覧

| ツール | 機能 | 必須/オプション |
|--------|------|----------------|
| yt-srt | YouTube字幕取得 | 必須 |
| video-trim | 不要部分削除 | 基本 |
| movie-viewer | チャプター作成 | 基本 |
| video-chapters | チャプター結合 | 基本 |
| audio-normalize | 音量正規化 | 拡張 |
| audio-extract-channel | チャンネル抽出 | 拡張 |
| video-replace-audio | 音声差し替え | 拡張 |
| whisper-remote | 高精度文字起こし | 拡張 |
| luatex-docker-remote | PDF生成 | 拡張 |

---

## 前処理ワークフロー アクティビティ図（スイムレーン）

Video Chapter Editor における前処理フェーズのアクター間協調。
処理の詳細はPAD（`docs/pad/preprocessing-workflow.png`）を参照。

### 全体フロー

```mermaid
flowchart TB
    subgraph YAML["📄 YAML（プロジェクトマニフェスト）"]
        direction LR
        Y1[("静的セクション<br>profile, source.path<br>fields, output")]
        Y2[("動的セクション<br>source.state<br>source.files")]
    end

    subgraph USER["👤 ユーザー"]
        direction TB
        U1([開始])
        U2[動画ファイルをドロップ]
        U3[再生位置をシーク]
        U4[開始点/終了点を設定]
        U5[トリミング確定]
        U6[チャプターマーカー追加]
        U7[チャプター名入力]
        U8[チャプター編集完了]
        U9{複数動画?}
        U10[結合順序確定]
        U11{字幕取得方式}
        U12[YouTube URL入力]
        U13[SRTファイル指定]
        U14([次フェーズへ])
    end

    subgraph UI_LAYER["🖥️ UI"]
        direction TB
        I1[サムネイル・タイムライン表示]
        I2[プレビュー表示]
        I3[選択範囲ハイライト]
        I4[プログレスバー更新]
        I5[チャプターエディタ表示]
        I6[マーカー名入力ダイアログ]
        I7[タイムライン上にマーカー表示]
        I8[結合順序確認ダイアログ]
        I9[完了通知]
        I10[字幕取得方式選択]
        I11[次フェーズボタン有効化]
    end

    subgraph BACKEND["⚙️ バックエンド"]
        direction TB
        B1[メディア情報解析]
        B2[ffmpeg トリミング実行]
        B3[中間ファイル生成]
        B4[chapters.txt 保存]
        B5[動画結合実行]
        B6[チャプター埋込]
        B7[最終動画出力]
        B8[whisper-remote 接続確認]
        B9[state更新]
    end

    %% Phase 0: YAML読込
    U1 --> Y1
    Y1 -->|source.path読込| B1

    %% Phase 1: 動画読込
    B1 --> I1
    B1 -->|video: ready| Y2

    %% Phase 2: トリミング
    I1 --> U3
    U3 --> I2
    I2 --> U4
    U4 --> I3
    I3 --> U5
    U5 --> B2
    B2 --> I4
    I4 --> B3

    %% Phase 3: チャプター
    B3 --> I5
    I5 --> U6
    U6 --> I6
    I6 --> U7
    U7 --> I7
    I7 --> U8
    U8 --> B4

    %% Phase 4: 結合・埋込
    B4 --> U9
    U9 -->|Yes| I8
    I8 --> U10
    U10 --> B5
    B5 --> B6
    U9 -->|No| B6
    B6 --> B7
    B7 --> I9

    %% Phase 5: 字幕準備・state更新
    I9 --> I10
    I10 --> U11
    U11 -->|YouTube| U12
    U11 -->|Whisper| B8
    U11 -->|手動| U13
    U12 --> B9
    B8 --> B9
    U13 --> B9
    B9 -->|youtube_srt/whisper_srt/manual_srt| Y2
    Y2 --> I11
    I11 --> U14
```

### トリミング操作の詳細

```mermaid
flowchart LR
    subgraph USER["👤 ユーザー"]
        U1[タイムラインをクリック]
        U2["[I] 開始点設定"]
        U3[別位置へシーク]
        U4["[O] 終了点設定"]
        U5["[X] 区間削除"]
        U6[トリミング実行ボタン]
    end

    subgraph UI_LAYER["🖥️ UI/タイムライン"]
        I1[プレビュー表示]
        I2[緑マーカー表示]
        I3[赤マーカー表示]
        I4[区間ハイライト]
        I5[グレーアウト表示]
        I6[タイムライン更新]
    end

    subgraph BACKEND["⚙️ バックエンド"]
        B1[フレーム取得]
        B2[ffmpeg 区間抽出・結合]
    end

    U1 --> B1 --> I1
    U2 --> I2
    U3 --> U4 --> I3 --> I4
    U5 --> I5
    U6 --> B2 --> I6

    %% ループを示す注釈
    I5 -.->|繰り返し| U1
```

### チャプター編集の詳細

```mermaid
flowchart LR
    subgraph USER["👤 ユーザー"]
        U1[再生位置をシーク]
        U2["[M] マーカー追加"]
        U3[チャプター名入力]
        U4[マーカーをダブルクリック]
        U5[名前変更入力]
        U6[マーカーをドラッグ]
    end

    subgraph UI_LAYER["🖥️ UI/タイムライン"]
        I1[現在時刻表示]
        I2[名前入力ダイアログ]
        I3[マーカー表示]
        I4[編集ダイアログ]
        I5[ラベル更新]
        I6[マーカー位置更新]
    end

    subgraph BACKEND["⚙️ バックエンド"]
        B1[chapters.txt 保存]
    end

    U1 --> I1
    U2 --> I2 --> U3 --> I3
    U4 --> I4 --> U5 --> I5
    U6 --> I6
    I3 --> B1
    I5 --> B1
    I6 --> B1
```

### 状態遷移（UI視点）

```mermaid
stateDiagram-v2
    [*] --> 待機中

    待機中 --> 動画読込中: ファイルドロップ
    動画読込中 --> トリミングモード: 読込完了

    トリミングモード --> トリミングモード: 区間操作
    トリミングモード --> トリミング処理中: 実行確定
    トリミング処理中 --> チャプターモード: 処理完了
    トリミングモード --> チャプターモード: スキップ

    チャプターモード --> チャプターモード: マーカー操作
    チャプターモード --> 結合処理中: チャプター確定

    結合処理中 --> 字幕準備: 出力完了

    字幕準備 --> YouTube入力: YouTube選択
    字幕準備 --> Whisper待機: Whisper選択
    字幕準備 --> SRT指定: 手動選択

    YouTube入力 --> 次フェーズ準備: URL入力完了
    Whisper待機 --> 次フェーズ準備: 接続確認完了
    SRT指定 --> 次フェーズ準備: ファイル指定完了

    次フェーズ準備 --> [*]: 次フェーズへ

    トリミング処理中 --> エラー: 処理失敗
    結合処理中 --> エラー: 処理失敗
    エラー --> トリミングモード: リトライ
```

---

## 前処理ワークフロー PAD図

### 処理フロー

![前処理ワークフロー](pad/preprocessing-workflow.png)

---

## 入力状態の場合分けと遷移

### 入力状態の列挙

| # | 動画 | YT字幕 | Whisper | 手動SRT | 必要な処理 |
|---|------|--------|---------|---------|-----------|
| 1 | YouTube URL | - | - | - | ytdl（動画+YT字幕）、任意でWhisper |
| 2 | ローカル動画のみ | - | - | - | Whisperまたは手動SRT |
| 3 | ローカル動画 | ✓ | - | - | 任意でWhisper追加 |
| 4 | ローカル動画 | - | ✓ | - | 処理可能 |
| 5 | ローカル動画 | ✓ | ✓ | - | 処理可能（統合） |
| 6 | ローカル動画 | - | - | ✓ | 処理可能 |
| 7 | YouTube DL済み | - | - | - | yt-srt or Whisper |

### 入力状態遷移図

```mermaid
stateDiagram-v2
    [*] --> 入力確認

    state 入力確認 {
        [*] --> 状態判定
        状態判定 --> S1_YouTube_URL: URLのみ
        状態判定 --> S2_ローカル動画のみ: 動画ファイルのみ
        状態判定 --> S3_動画_YT字幕あり: 動画 + *_yt.srt
        状態判定 --> S4_動画_WP字幕あり: 動画 + *_wp.srt
        状態判定 --> S5_動画_両方あり: 動画 + 両SRT
        状態判定 --> S6_動画_手動SRTあり: 動画 + 手動.srt
        状態判定 --> S7_YouTube_DL済み_字幕なし: DL済み動画のみ
    }

    S1_YouTube_URL --> S3_動画_YT字幕あり: ytdl実行
    S2_ローカル動画のみ --> S4_動画_WP字幕あり: Whisper実行
    S2_ローカル動画のみ --> S6_動画_手動SRTあり: 手動指定
    S3_動画_YT字幕あり --> S5_動画_両方あり: Whisper追加
    S7_YouTube_DL済み_字幕なし --> S3_動画_YT字幕あり: yt-srt実行
    S7_YouTube_DL済み_字幕なし --> S4_動画_WP字幕あり: Whisper実行

    S3_動画_YT字幕あり --> 処理可能
    S4_動画_WP字幕あり --> 処理可能
    S5_動画_両方あり --> 処理可能
    S6_動画_手動SRTあり --> 処理可能

    処理可能 --> [*]
```

### 前処理出力と文字起こし入力の対応

```mermaid
flowchart LR
    subgraph PREPROCESS["前処理の出力"]
        direction TB
        P1["YouTube経由で完了"]
        P2["ローカル動画をWhisper"]
        P3["ローカル動画のみ編集"]
    end

    subgraph STATE["入力状態"]
        direction TB
        S3["状態3: 動画+YT字幕"]
        S5["状態5: 動画+両方"]
        S4["状態4: 動画+WP字幕"]
        S2["状態2: 動画のみ"]
        S7["状態7: DL済み字幕なし"]
    end

    subgraph TRANSCRIPTION["文字起こしmethod"]
        direction TB
        M_SKIP["skip"]
        M_WHISPER["whisper"]
        M_YOUTUBE["youtube"]
        M_MANUAL["manual"]
    end

    P1 --> S3
    P1 --> S5
    P2 --> S4
    P3 --> S2
    P3 --> S7

    S3 --> M_SKIP
    S4 --> M_SKIP
    S5 --> M_SKIP
    S2 --> M_WHISPER
    S2 --> M_MANUAL
    S7 --> M_YOUTUBE
    S7 --> M_WHISPER
```

### YAMLライフサイクル

YAMLファイルは**プロジェクトマニフェスト**として、全ワークフローの開始前に作成する。

```mermaid
flowchart TB
    subgraph YAML_STRUCTURE["YAMLの構成"]
        direction TB
        STATIC["静的セクション<br>（ユーザーが最初に記入）"]
        DYNAMIC["動的セクション<br>（処理中に自動更新）"]
    end

    subgraph STATIC_DETAIL["静的セクション"]
        direction LR
        S1["schema_version, profile"]
        S2["source.type, path, working_dir"]
        S3["fields（title, date...）"]
        S4["transcription.method"]
        S5["output（basename, format）"]
    end

    subgraph DYNAMIC_DETAIL["動的セクション"]
        direction LR
        D1["source.state"]
        D2["source.files"]
    end

    STATIC --> STATIC_DETAIL
    DYNAMIC --> DYNAMIC_DETAIL
```

### ワークフロー順序（YAML中心）

```mermaid
sequenceDiagram
    autonumber
    participant U as ユーザー
    participant YAML as YAML
    participant PRE as 前処理
    participant TRANS as 文字起こし

    rect rgb(240, 248, 255)
        Note over U,YAML: Phase 0: YAML作成
        U->>YAML: プロファイル選択
        U->>YAML: ソース情報入力
        U->>YAML: フィールド入力
        Note over YAML: 静的セクション確定
    end

    rect rgb(255, 250, 240)
        Note over PRE,YAML: 前処理フェーズ
        PRE->>YAML: source.path 読込
        PRE->>PRE: トリミング・チャプター
        PRE->>YAML: source.state 更新
    end

    rect rgb(240, 255, 240)
        Note over TRANS,YAML: 文字起こしフェーズ
        TRANS->>YAML: source.state 確認
        TRANS->>TRANS: SRT取得（必要に応じて）
        TRANS->>TRANS: AI処理 → 出力
    end
```

### ワークフロー境界の定義

```mermaid
flowchart TB
    subgraph PHASE0["Phase 0: YAML作成（ユーザー）"]
        YAML_CREATE["YAML作成"]
        YAML_EDIT["静的セクション入力"]
        YAML_CREATE --> YAML_EDIT
    end

    subgraph BOUNDARY["ワークフロー境界"]
        direction LR
        PRE["前処理<br>Video Chapter Editor"]
        INTERFACE[/"YAML<br>source.state で状態共有"/]
        TRANS["文字起こし<br>Transcription Workflow"]

        PRE -->|"責務: YAML読込→編集→state更新"| INTERFACE
        INTERFACE -->|"責務: state確認→SRT取得→AI→出力"| TRANS
    end

    subgraph STANDALONE["単独起動時"]
        TRANS2["文字起こし単独起動"]
        SRT_ACQ["SRT取得も実行可能"]
        TRANS2 --> SRT_ACQ
    end

    PHASE0 --> BOUNDARY
```

---

## 文字起こしワークフロー スキーマ構造

### ファイル参照関係

```mermaid
graph TD
    subgraph WD["作業ディレクトリ"]
        YAML["transcription_workflow.yaml<br>(設定ファイル)"]
        SRT1["*_yt.srt"]
        SRT2["*_wp.srt"]
        OUTPUT["output/*.tex"]
    end

    subgraph CONFIG["~/.config/rehearsal-workflow/"]
        subgraph PROFILES["profiles/"]
            P1["orchestral_rehearsal.yaml"]
            P2["horn_lesson.yaml"]
            P3["meeting_report.yaml"]
        end

        subgraph PROMPTS["prompts/"]
            PR1["orchestral_rehearsal.md"]
            PR2["horn_lesson.md"]
            PR3["meeting_report.md"]
        end

        subgraph TEMPLATES["templates/"]
            T1["luatex_twocolumn.tex"]
        end

        subgraph MACROS["macros/"]
            M1["common.tex"]
            M2["meeting_speakers.tex"]
        end

        subgraph GLOSSARIES["glossaries/"]
            G1["music_terms.yaml"]
            G2["horn_techniques.yaml"]
            G3["defense_acronyms.yaml"]
        end
    end

    YAML -->|"profile:"| PROFILES
    P1 -->|"prompt_template:"| PR1
    P2 -->|"prompt_template:"| PR2
    P3 -->|"prompt_template:"| PR3
    P1 -->|"base_template:"| T1
    P2 -->|"base_template:"| T1
    P3 -->|"base_template:"| T1
    P1 -->|"macros:"| M1
    P3 -->|"macros:"| M2
    P1 -->|"glossary:"| G1
    P2 -->|"glossary:"| G2
    P3 -->|"glossary:"| G3

    YAML -->|"source.files:"| SRT1
    YAML -->|"source.files:"| SRT2
    YAML -->|"output:"| OUTPUT
```

### スキーマ階層（TeX/LaTeXアナロジー）

```mermaid
graph TB
    subgraph ANALOGY["設計思想: TeX/LaTeX アナロジー"]
        direction LR
        TEX[".tex ファイル<br>(内容)"] --> CLS[".cls / .sty<br>(構造定義)"]
        CLS --> MACRO["マクロ展開<br>(処理)"]
    end

    subgraph SYSTEM["本システム"]
        direction LR
        YAML2["設定ファイル<br>(値)"] --> PROFILE["プロファイル<br>(型定義)"]
        PROFILE --> PROMPT["プロンプト生成<br>(処理)"]
    end

    ANALOGY -.->|"対応"| SYSTEM
```

### 参加者構造の類型

```mermaid
graph LR
    subgraph HIER["hierarchical (階層型)"]
        direction TB
        I1["講師/指揮者"]
        S1["生徒/奏者"]
        I1 -->|"指導"| S1
    end

    subgraph FLAT["flat (フラット型)"]
        direction TB
        P1["参加者A"]
        P2["参加者B"]
        P3["参加者C"]
        P1 <-->|"対等"| P2
        P2 <-->|"対等"| P3
    end

    HIER --- EXAMPLES1["レッスン, 講義, リハーサル"]
    FLAT --- EXAMPLES2["会議, 座談会"]
```

### 処理フェーズ

```mermaid
flowchart LR
    subgraph P0["Phase 0"]
        direction TB
        P0A["YAML作成"]
        P0B["ユーザー入力"]
    end

    subgraph PRE["前処理"]
        direction TB
        PRE_A["トリミング"]
        PRE_B["チャプター"]
        PRE_C["state更新"]
    end

    subgraph P1["Phase 1"]
        direction TB
        P1A["初期化"]
        P1B["YAML読込"]
    end

    subgraph P2["Phase 2"]
        direction TB
        P2A["プロファイル解決"]
        P2B["リソース読込"]
    end

    subgraph P3["Phase 3"]
        direction TB
        P3A["入力状態判定"]
        P3B["7状態のいずれか"]
    end

    subgraph P4["Phase 4"]
        direction TB
        P4A["ソース処理"]
        P4B["url_only→ytdl"]
    end

    subgraph P5["Phase 5"]
        direction TB
        P5A["文字起こし"]
        P5B["SRT統合"]
    end

    subgraph P6["Phase 6"]
        direction TB
        P6A["プロンプト生成"]
        P6B["変数展開"]
    end

    subgraph P7["Phase 7"]
        direction TB
        P7A["AI処理"]
        P7B["(外部)"]
    end

    subgraph P8["Phase 8"]
        direction TB
        P8A["出力生成"]
        P8B["PDF/MD/DOCX"]
    end

    P0 --> PRE --> P1 --> P2 --> P3 --> P4 --> P5 --> P6 --> P7 --> P8
```

### プロファイル検索順序

```mermaid
flowchart TD
    START["profile: 'xxx' を解決"]

    CHECK1{"作業ディレクトリ内<br>./profiles/xxx.yaml"}
    CHECK2{"ユーザー設定<br>~/.config/.../profiles/xxx.yaml"}
    CHECK3{"ビルトイン<br>パッケージ内蔵"}

    FOUND["プロファイル読込"]
    ERROR["エラー: 見つからない"]

    START --> CHECK1
    CHECK1 -->|"存在"| FOUND
    CHECK1 -->|"なし"| CHECK2
    CHECK2 -->|"存在"| FOUND
    CHECK2 -->|"なし"| CHECK3
    CHECK3 -->|"存在"| FOUND
    CHECK3 -->|"なし"| ERROR
```

---

## 文字起こしワークフロー アクティビティ図（スイムレーン）

ユーザー、UI、バックエンド間の協調を示す。処理の詳細はPAD（`docs/pad/transcription-workflow.png`）を参照。

### 全体フロー

```mermaid
flowchart TB
    subgraph YAML["📄 YAML（プロジェクトマニフェスト）"]
        direction LR
        Y1[("静的セクション<br>profile, fields<br>transcription.method<br>output")]
        Y2[("動的セクション<br>source.state<br>source.files")]
    end

    subgraph USER["👤 ユーザー"]
        direction TB
        U1([開始])
        U2{既存設定?}
        U3[ファイル選択]
        U4[プロファイル選択]
        U5[フィールド入力]
        U6[ファイル指定]
        U7{文字起こし方式}
        U8[方式選択]
        U9[クリップボードコピー]
        U10[AI実行<br>Claude/ChatGPT]
        U11[AI出力をペースト]
        U12{出力形式}
        U13[ファイルを開く]
        U14([完了])
    end

    subgraph UI_LAYER["🖥️ UI"]
        direction TB
        I1[選択ダイアログ表示]
        I2[プロファイル選択画面]
        I3[設定フォーム表示]
        I4[エラー表示]
        I5[文字起こし方式確認]
        I6[プログレスバー更新]
        I7[プロンプトプレビュー表示]
        I8[「AIで実行してください」]
        I9[出力形式確認]
        I10[結果表示・ファイル場所通知]
    end

    subgraph BACKEND["⚙️ バックエンド"]
        direction TB
        B1[設定ファイル検索]
        B2[YAML読込/生成]
        B3[プロファイル解決]
        B4[リソース読込]
        B5[ソースファイル確認]
        B6{ファイル不足?}
        B7[SRT読込]
        B8[文字起こし実行]
        B9[SRT生成]
        B10[プロンプト生成]
        B11[AI出力保存]
        B12{LaTeX?}
        B13[luatex-pdf実行]
        B14[出力生成]
    end

    %% Phase 1: 初期化・YAML読込
    U1 --> B1
    B1 --> U2
    U2 -->|Yes| I1 --> U3
    U2 -->|No| I2 --> U4
    U3 --> Y1
    U4 --> I3 --> U5
    U5 -->|静的セクション保存| Y1
    Y1 --> B2

    %% Phase 2-3: プロファイル解決・ソース処理
    B2 -->|profile読込| B3
    B3 --> B4
    Y2 -->|source.state確認| B5
    B4 --> B5
    B5 --> B6
    B6 -->|Yes| I4 --> U6 --> B5
    B6 -->|No| B7

    %% Phase 4-5: 文字起こし
    B7 --> I5 --> U7
    U7 --> U8 --> B8
    B8 --> I6 --> B9
    B9 -->|SRT状態更新| Y2

    %% Phase 6: プロンプト生成
    B9 --> B10
    Y1 -->|fields展開| B10
    B10 --> I7 --> U9

    %% Phase 7: AI処理（外部）
    U9 --> I8 --> U10 --> U11 --> B11

    %% Phase 8: 出力生成
    B11 --> I9 --> U12
    U12 --> B12
    B12 -->|Yes| B13 --> B14
    B12 -->|No| B14
    B14 --> I10 --> U13 --> U14
```

### エラー処理フロー

```mermaid
flowchart TB
    subgraph USER["👤 ユーザー"]
        U1[修正入力]
        U2[代替手段選択]
        U3[中止]
    end

    subgraph UI_LAYER["🖥️ UI"]
        I1[完了通知]
        I2[エラー箇所ハイライト]
        I3[エラー詳細表示]
        I4[代替手段提案]
        I5[エラーログ表示]
        I6[「再開可能」通知]
    end

    subgraph BACKEND["⚙️ バックエンド"]
        B1[処理要求]
        B2{結果}
        B3[成功レスポンス]
        B4[バリデーションエラー]
        B5[外部ツールエラー]
        B6[致命的エラー]
        B7[再処理]
        B8[状態保存]
    end

    B1 --> B2
    B2 -->|正常| B3 --> I1
    B2 -->|バリデーション| B4 --> I2 --> U1 --> B7 --> B1
    B2 -->|外部ツール| B5 --> I3 --> I4 --> U2 --> B1
    I4 --> U3
    B2 -->|致命的| B6 --> I5 --> B8 --> I6
```

### 状態遷移（UI視点）

```mermaid
stateDiagram-v2
    [*] --> 初期画面

    初期画面 --> 設定選択: 既存ファイル選択
    初期画面 --> プロファイル選択: 新規作成

    プロファイル選択 --> 設定編集: プロファイル決定
    設定選択 --> 設定編集: ファイル読込完了

    設定編集 --> ソース確認: 設定保存
    ソース確認 --> 設定編集: ファイル不足

    ソース確認 --> 文字起こし中: 処理開始
    文字起こし中 --> プロンプト確認: 完了

    プロンプト確認 --> AI待機: プロンプト出力
    AI待機 --> 出力生成中: AI結果入力

    出力生成中 --> 完了: 生成成功
    出力生成中 --> エラー: 生成失敗

    エラー --> 設定編集: 修正
    エラー --> 完了: スキップ

    完了 --> [*]
    完了 --> 設定編集: 別の設定で再実行
```

---

## 文字起こしワークフロー PAD図

### スキーマ構造

![スキーマ構造](pad/transcription-schema.png)

### 処理フロー

![処理フロー](pad/transcription-workflow.png)
