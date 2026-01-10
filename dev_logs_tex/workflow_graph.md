# Video Chapter Editor ワークフローグラフ

## 処理フロー（一筆書き問題としての分析）

入力ソース、中間生成物、最終成果物をノードとし、処理の流れをエッジとしたグラフ。

```mermaid
flowchart TB
    subgraph inputs["入力ソース"]
        I1["YouTube URL"]
        I2["ローカルMP4"]
        I3["MP3 + カバー画像"]
    end

    subgraph preprocessing["前処理"]
        P1["yt-dlp<br/>ダウンロード"]
        P2["video-trim<br/>トリミング"]
        P3["ffmpeg<br/>静止画動画生成"]
        P4["Whisper<br/>文字起こし"]
    end

    subgraph intermediate["中間成果物"]
        M1["編集可能MP4"]
        M2["SRTファイル"]
    end

    subgraph vce["Video Chapter Editor"]
        V1["チャプター編集"]
        V2["エクスポート"]
    end

    subgraph outputs["最終成果物"]
        O1["チャプター付きMP4"]
        O2["YouTubeチャプターリスト"]
        O3["分割動画"]
    end

    subgraph report["レポート生成"]
        R1["Claude AI分析"]
    end

    subgraph docs["文書成果物"]
        D1["スクリプトPDF"]
        D2["サマリーPDF"]
    end

    %% 入力から前処理
    I1 --> P1
    I2 --> P2
    I3 --> P3

    %% 前処理から中間成果物（共通パスへの集約）
    P1 --> M1
    P1 -.->|"字幕あり"| M2
    P2 --> M1
    P3 --> M1

    %% Whisperによる文字起こし
    M1 -.->|"字幕なし"| P4
    P4 --> M2

    %% 共通パス: VCEでの編集
    M1 --> V1
    V1 --> V2

    %% 最終成果物への出力
    V2 --> O1
    V2 --> O2
    V2 --> O3

    %% レポート生成フロー
    M2 --> R1
    R1 --> D1
    R1 --> D2

    %% スタイル
    classDef input fill:#e1f5fe,stroke:#01579b
    classDef process fill:#fff3e0,stroke:#e65100
    classDef intermediate fill:#f3e5f5,stroke:#7b1fa2
    classDef vce fill:#e8f5e9,stroke:#2e7d32
    classDef output fill:#ffebee,stroke:#c62828
    classDef doc fill:#fce4ec,stroke:#880e4f

    class I1,I2,I3 input
    class P1,P2,P3,P4 process
    class M1,M2 intermediate
    class V1,V2 vce
    class O1,O2,O3 output
    class D1,D2 doc
```

## グラフ理論的分析

### ノード次数の確認

| ノード | 入次数 | 出次数 | 合計次数 | 種別 |
|--------|--------|--------|----------|------|
| YouTube URL | 0 | 1 | 1 | 始点（奇点） |
| ローカルMP4 | 0 | 1 | 1 | 始点（奇点） |
| MP3+カバー | 0 | 1 | 1 | 始点（奇点） |
| 編集可能MP4 | 3 | 1 | 4 | 中間（偶点） |
| SRTファイル | 2 | 1 | 3 | 中間（奇点）※ |
| チャプター付きMP4 | 1 | 0 | 1 | 終点（奇点） |

※ SRTファイルは中間ノードでありながら奇点となっている。これはSRT取得（入力2本：yt-dlp、Whisper）とレポート生成（出力1本）で次数が3となるため。

### 設計上の対応

共通パス「編集可能MP4 → VCE → チャプター付きMP4」に集約することで、
入力側の分岐を吸収し、処理の重複を最小化している。

SRTファイルについては、VCEのスコープ外（レポート生成ワークフロー）への
接続点として機能しており、ワークフロー間の境界として許容される。
