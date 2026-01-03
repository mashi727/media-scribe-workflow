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
    subgraph P1["Phase 1"]
        direction TB
        P1A["初期化"]
        P1B["設定読込/新規作成"]
    end

    subgraph P2["Phase 2"]
        direction TB
        P2A["プロファイル解決"]
        P2B["リソース読込"]
    end

    subgraph P3["Phase 3"]
        direction TB
        P3A["ソース処理"]
        P3B["SRT取得/読込"]
    end

    subgraph P4["Phase 4"]
        direction TB
        P4A["文字起こし"]
        P4B["SRT統合"]
    end

    subgraph P5["Phase 5"]
        direction TB
        P5A["プロンプト生成"]
        P5B["変数展開"]
    end

    subgraph P6["Phase 6"]
        direction TB
        P6A["AI処理"]
        P6B["(外部)"]
    end

    subgraph P7["Phase 7"]
        direction TB
        P7A["出力生成"]
        P7B["PDF/MD/DOCX"]
    end

    P1 --> P2 --> P3 --> P4 --> P5 --> P6 --> P7
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

## 文字起こしワークフロー アクティビティ図（UML）

### 全体フロー

```mermaid
stateDiagram-v2
    [*] --> 初期化

    state 初期化 {
        [*] --> 起動方法判定
        起動方法判定 --> 設定ファイル読込: 既存ファイル指定
        起動方法判定 --> 新規作成: 新規
        新規作成 --> プロファイル選択
        プロファイル選択 --> 設定ファイル生成
        設定ファイル生成 --> 設定ファイル読込
        設定ファイル読込 --> [*]
    }

    初期化 --> プロファイル解決

    state プロファイル解決 {
        [*] --> 検索開始
        検索開始 --> 作業ディレクトリ検索
        作業ディレクトリ検索 --> プロファイル読込: 発見
        作業ディレクトリ検索 --> ユーザー設定検索: なし
        ユーザー設定検索 --> プロファイル読込: 発見
        ユーザー設定検索 --> ビルトイン検索: なし
        ビルトイン検索 --> プロファイル読込: 発見
        ビルトイン検索 --> エラー: なし
        プロファイル読込 --> リソース読込
        リソース読込 --> [*]
    }

    プロファイル解決 --> ソース処理

    state ソース処理 {
        [*] --> ソースタイプ判定
        ソースタイプ判定 --> ローカルファイル処理: local
        ソースタイプ判定 --> YouTube処理: youtube
        ローカルファイル処理 --> SRT読込
        YouTube処理 --> yt_srt実行
        yt_srt実行 --> SRT保存
        SRT保存 --> SRT読込
        SRT読込 --> [*]
    }

    ソース処理 --> 文字起こし

    state 文字起こし {
        [*] --> 方式判定
        方式判定 --> YouTube字幕使用: youtube
        方式判定 --> Whisper実行: whisper
        方式判定 --> 既存SRT使用: manual
        方式判定 --> スキップ: skip
        Whisper実行 --> SRT生成
        YouTube字幕使用 --> 複数SRT判定
        SRT生成 --> 複数SRT判定
        既存SRT使用 --> 複数SRT判定
        スキップ --> 複数SRT判定
        複数SRT判定 --> SRT統合: 複数あり
        複数SRT判定 --> [*]: 単一
        SRT統合 --> [*]
    }

    文字起こし --> プロンプト生成

    state プロンプト生成 {
        [*] --> テンプレート読込
        テンプレート読込 --> 変数展開
        変数展開 --> 参加者情報展開
        参加者情報展開 --> 字幕データ埋込
        字幕データ埋込 --> プロンプト出力
        プロンプト出力 --> [*]
    }

    プロンプト生成 --> AI処理_外部

    state AI処理_外部 {
        [*] --> ユーザー操作待ち
        note right of ユーザー操作待ち
            Claude / ChatGPT / ローカルLLM
            でプロンプトを実行
        end note
        ユーザー操作待ち --> AI出力取得
        AI出力取得 --> [*]
    }

    AI処理_外部 --> 出力生成

    state 出力生成 {
        [*] --> 出力形式判定
        出力形式判定 --> Markdown生成: markdown
        出力形式判定 --> LaTeX生成: latex
        出力形式判定 --> Word生成: docx
        LaTeX生成 --> luatex_pdf実行
        luatex_pdf実行 --> PDF生成
        Markdown生成 --> 追加出力判定
        PDF生成 --> 追加出力判定
        Word生成 --> 追加出力判定
        追加出力判定 --> チャプターファイル生成: あり
        追加出力判定 --> 状態保存: なし
        チャプターファイル生成 --> 状態保存
        状態保存 --> [*]
    }

    出力生成 --> [*]
```

### 参加者構造別の処理分岐

```mermaid
stateDiagram-v2
    [*] --> 参加者構造判定

    state 参加者構造判定 {
        [*] --> タイプ確認
        タイプ確認 --> 階層型処理: hierarchical
        タイプ確認 --> フラット型処理: flat
    }

    state 階層型処理 {
        [*] --> 講師情報抽出
        講師情報抽出 --> 生徒情報抽出
        生徒情報抽出 --> 指導関係マッピング
        指導関係マッピング --> [*]
    }

    state フラット型処理 {
        [*] --> 参加者リスト取得
        参加者リスト取得 --> 発言者マクロ生成
        発言者マクロ生成 --> [*]
    }

    階層型処理 --> プロンプト変数設定
    フラット型処理 --> プロンプト変数設定

    プロンプト変数設定 --> [*]
```

### 文字起こし方式の詳細

```mermaid
stateDiagram-v2
    [*] --> 入力確認

    state fork_state <<fork>>
    state join_state <<join>>

    入力確認 --> fork_state: 両方実行

    fork_state --> YouTube字幕取得
    fork_state --> Whisper文字起こし

    state YouTube字幕取得 {
        [*] --> yt_srt_コマンド実行
        yt_srt_コマンド実行 --> 字幕ダウンロード
        字幕ダウンロード --> _yt.srt保存
        _yt.srt保存 --> [*]
    }

    state Whisper文字起こし {
        [*] --> whisper_remote実行
        whisper_remote実行 --> 音声解析
        音声解析 --> _wp.srt保存
        _wp.srt保存 --> [*]
    }

    YouTube字幕取得 --> join_state
    Whisper文字起こし --> join_state

    join_state --> SRT統合処理

    state SRT統合処理 {
        [*] --> タイムスタンプ照合
        タイムスタンプ照合 --> 相補的マージ
        note right of 相補的マージ
            YouTube: 時系列構造把握
            Whisper: 発話内容の精度
        end note
        相補的マージ --> 統合SRT出力
        統合SRT出力 --> [*]
    }

    SRT統合処理 --> [*]
```
