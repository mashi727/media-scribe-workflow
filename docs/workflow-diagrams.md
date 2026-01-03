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

## 前処理ワークフロー ユーザー/UI/バックエンド インタラクション図

Video Chapter Editor における前処理フェーズのアクター間協調。

### 全体フロー

```mermaid
sequenceDiagram
    autonumber
    participant U as ユーザー
    participant UI as UI
    participant BE as バックエンド

    rect rgb(240, 248, 255)
        Note over U,BE: Phase 1: 動画読込
        U->>UI: 動画ファイルをドロップ
        UI->>BE: メディア情報解析要求
        BE-->>UI: duration, codec, resolution
        UI-->>U: サムネイル・タイムライン表示
    end

    rect rgb(255, 250, 240)
        Note over U,BE: Phase 2: 不要部分削除（video-trim）
        loop トリミング操作
            U->>UI: 再生位置をシーク
            UI-->>U: プレビュー表示
            U->>UI: 開始点/終了点を設定
            UI-->>U: 選択範囲ハイライト
            U->>UI: 区間を削除/復元
        end
        U->>UI: トリミング確定
        UI->>BE: ffmpeg トリミング実行
        loop 処理中
            BE-->>UI: 進捗通知
            UI-->>U: プログレスバー更新
        end
        BE-->>UI: 中間ファイル生成完了
    end

    rect rgb(240, 255, 240)
        Note over U,BE: Phase 3: チャプター作成（movie-viewer連携）
        UI-->>U: チャプターエディタ表示
        loop チャプター操作
            U->>UI: 再生位置をシーク
            U->>UI: チャプターマーカー追加
            UI-->>U: マーカー名入力ダイアログ
            U->>UI: チャプター名入力
            UI-->>U: タイムライン上にマーカー表示
        end
        U->>UI: チャプター編集完了
        UI->>BE: chapters.txt 保存
        BE-->>UI: 保存完了
    end

    rect rgb(255, 240, 245)
        Note over U,BE: Phase 4: 動画結合・チャプター埋込（video-chapters）
        alt 複数動画あり
            UI-->>U: 結合順序確認ダイアログ
            U->>UI: 順序確定
            UI->>BE: 動画結合実行
            BE-->>UI: 結合完了
        end
        UI->>BE: チャプター埋込実行
        BE->>BE: ffmpeg -map_metadata
        BE-->>UI: 最終動画出力完了
        UI-->>U: 完了通知・ファイル場所表示
    end

    rect rgb(245, 245, 255)
        Note over U,BE: Phase 5: 字幕取得準備
        UI-->>U: 字幕取得方式選択
        alt YouTube経由
            U->>UI: YouTube URL 入力
            UI-->>U: yt-srt 実行準備完了
        else ローカル Whisper
            UI->>BE: whisper-remote 接続確認
            BE-->>UI: 接続OK
            UI-->>U: Whisper 準備完了
        else 手動
            U->>UI: 既存SRTファイル指定
        end
        UI-->>U: 「次フェーズへ進む」ボタン有効化
    end
```

### トリミング操作の詳細

```mermaid
sequenceDiagram
    participant U as ユーザー
    participant UI as UI
    participant TL as タイムライン
    participant BE as バックエンド

    U->>TL: タイムラインをクリック/ドラッグ
    TL-->>UI: 位置変更通知
    UI->>BE: フレーム取得要求
    BE-->>UI: サムネイルフレーム
    UI-->>U: プレビュー表示

    U->>UI: [I] キー押下（開始点）
    UI->>TL: 開始マーカー設置
    TL-->>U: 緑マーカー表示

    U->>TL: 別位置へシーク
    U->>UI: [O] キー押下（終了点）
    UI->>TL: 終了マーカー設置
    TL-->>U: 赤マーカー表示・区間ハイライト

    U->>UI: [X] キー押下（区間削除）
    UI->>TL: 削除区間として記録
    TL-->>U: グレーアウト表示

    Note over U,BE: 複数区間の削除を繰り返し可能

    U->>UI: 「トリミング実行」ボタン
    UI->>BE: 削除区間リスト送信
    BE->>BE: ffmpeg で区間抽出・結合
    BE-->>UI: 処理完了
    UI-->>U: 新しい動画でタイムライン更新
```

### チャプター編集の詳細

```mermaid
sequenceDiagram
    participant U as ユーザー
    participant UI as UI
    participant TL as タイムライン
    participant BE as バックエンド

    U->>TL: 再生位置をシーク
    TL-->>UI: 現在位置通知
    UI-->>U: 現在時刻表示

    U->>UI: [M] キー押下（マーカー追加）
    UI-->>U: チャプター名入力ダイアログ
    U->>UI: 「第1楽章」と入力
    UI->>TL: チャプターマーカー追加
    TL-->>U: マーカー表示（旗アイコン）

    U->>TL: マーカーをダブルクリック
    UI-->>U: 編集ダイアログ
    U->>UI: 名前変更「第1楽章 Allegro」
    UI->>TL: マーカー更新
    TL-->>U: ラベル更新表示

    U->>TL: マーカーをドラッグ
    TL-->>UI: 位置変更通知
    UI->>TL: マーカー位置更新
    TL-->>U: 新位置にマーカー表示

    U->>UI: 「保存」ボタン
    UI->>BE: chapters.txt 形式で保存要求
    BE-->>UI: 保存完了
    UI-->>U: 「保存しました」通知
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

## ユーザー/UI/バックエンド インタラクション図

ユーザー、UI、バックエンド間の協調を示す。バックエンド内部の処理詳細はPAD参照。

### 全体フロー

```mermaid
sequenceDiagram
    autonumber
    participant U as ユーザー
    participant UI as UI
    participant BE as バックエンド

    rect rgb(240, 248, 255)
        Note over U,BE: Phase 1: 初期化
        U->>UI: アプリ起動
        UI->>BE: 設定ファイル検索
        alt 既存設定あり
            BE-->>UI: 設定ファイル一覧
            UI-->>U: 選択ダイアログ表示
            U->>UI: ファイル選択
        else 新規作成
            UI-->>U: プロファイル選択画面
            U->>UI: プロファイル選択
            UI-->>U: 設定フォーム表示
            U->>UI: 各フィールド入力
        end
        UI->>BE: 設定読込/生成
        BE-->>UI: 設定オブジェクト
    end

    rect rgb(255, 250, 240)
        Note over U,BE: Phase 2-3: プロファイル解決・ソース処理
        UI->>BE: プロファイル解決要求
        BE-->>UI: リソース読込完了
        UI->>BE: ソースファイル確認
        alt ファイル不足
            BE-->>UI: 不足ファイル通知
            UI-->>U: エラー表示
            U->>UI: ファイル指定
        end
        BE-->>UI: SRT読込完了
    end

    rect rgb(240, 255, 240)
        Note over U,BE: Phase 4: 文字起こし
        UI-->>U: 文字起こし方式確認
        U->>UI: 方式選択（youtube/whisper/manual/skip）
        UI->>BE: 文字起こし実行
        loop 処理中
            BE-->>UI: 進捗通知
            UI-->>U: プログレスバー更新
        end
        BE-->>UI: SRT生成完了
    end

    rect rgb(255, 240, 245)
        Note over U,BE: Phase 5: プロンプト生成
        UI->>BE: プロンプト生成要求
        BE-->>UI: プロンプト生成完了
        UI-->>U: プロンプトプレビュー表示
        U->>UI: クリップボードコピー or ファイル保存
    end

    rect rgb(245, 245, 255)
        Note over U,BE: Phase 6: AI処理（外部）
        UI-->>U: 「AIでプロンプトを実行してください」
        Note right of U: Claude / ChatGPT 等で実行
        U->>UI: AI出力をペースト or ファイル指定
        UI->>BE: AI出力保存
    end

    rect rgb(255, 255, 240)
        Note over U,BE: Phase 7: 出力生成
        UI-->>U: 出力形式確認
        U->>UI: 形式選択（latex/markdown/docx）
        UI->>BE: 出力生成要求
        alt LaTeX選択
            BE->>BE: luatex-pdf実行
        end
        BE-->>UI: 出力完了
        UI-->>U: 結果表示・ファイル場所通知
        U->>UI: ファイルを開く
    end
```

### エラー処理フロー

```mermaid
sequenceDiagram
    participant U as ユーザー
    participant UI as UI
    participant BE as バックエンド

    UI->>BE: 処理要求

    alt 正常終了
        BE-->>UI: 成功レスポンス
        UI-->>U: 完了通知
    else バリデーションエラー
        BE-->>UI: エラー（修正可能）
        UI-->>U: エラー箇所ハイライト
        U->>UI: 修正入力
        UI->>BE: 再処理要求
    else 外部ツールエラー
        BE-->>UI: エラー（yt-srt/whisper/luatex失敗）
        UI-->>U: エラー詳細表示
        UI-->>U: 代替手段提案
        U->>UI: 代替手段選択 or 中止
    else 致命的エラー
        BE-->>UI: エラー（回復不可）
        UI-->>U: エラーログ表示
        UI->>BE: 状態保存（途中経過）
        BE-->>UI: 保存完了
        UI-->>U: 「再開可能」通知
    end
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
