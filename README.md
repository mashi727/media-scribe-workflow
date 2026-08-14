# Media Scribe Workflow

メディアファイル（動画・音声）から字幕・チャプター・**LaTeX レポート PDF** を生成する CLI ツール群とレポートパイプライン。

「Gitの陶器と配管」の思想に基づき、単一目的のツールを組み合わせてワークフローを構築します。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## このリポジトリの範囲

```
[コア]
├── bin/yt-srt              YouTube 字幕取得
├── bin/video-trim          動画トリミング
├── bin/video-chapters      チャプター結合
├── bin/ytdl                YouTube ダウンロード
└── bin/jsonl2md            JSONL → Markdown 変換

[レポートパイプライン (msw-*)]
├── bin/msw-config          VCE 設定マージ・検証
├── bin/msw-report          SRT + VCE 設定 → LaTeX
├── bin/msw-compile         LuaTeX → PDF
└── bin/msw-pipeline        SRT → LaTeX → PDF 完全自動化

[VCE プロジェクト処理]
├── bin/vce-encode          VCE → チャプター付き単一動画
└── bin/vce-split           VCE → チャプター分割動画

[文字起こし (bin/advanced)]
├── bin/advanced/audio-transcribe     Whisper 系 (faster-whisper, 既定 large-v3)
└── bin/advanced/audio-transcribe-dg  Deepgram Nova-3 (REST)

[統合ワークフロー]
├── bin/rehearsal-download  YouTube DL + Whisper 起動
└── bin/rehearsal-finalize  PDF 生成 + チャプター抽出

[ドキュメント・テンプレート]
├── profiles/               リハーサル/会議/レッスン用テンプレ (YAML)
├── examples/prompts/       Claude AI 用プロンプト例
├── docs/                   設計書 (Snakemake 移行計画ほか)
└── docs/pad/               PAD 図 (ワークフロー可視化)
```

## 関連プロジェクト（GUI）

動画チャプター編集の GUI アプリは **[Chaptr](https://github.com/mashi727/chaptr)** として独立リポジトリに分離されています。PySide6 ベース、macOS/Windows バイナリ配布、GPU ハードウェアエンコード対応。

```
[本リポジトリ media-scribe-workflow]               [chaptr リポジトリ]
CLI 配管ツール + レポートパイプライン      ⇆      動画チャプター編集 GUI
                                                   .vce.json (チャプター定義)
            ↓                                              ↓
       bin/msw-pipeline ← ─────── 連携 ─────── → Chaptr が出力する .vce.json
```

## Features

### CLI ツール

| コマンド | 説明 |
|---------|------|
| `yt-srt` | YouTube 動画から SRT 字幕を取得 |
| `video-trim` | 動画の不要部分をカット |
| `video-chapters` | 複数動画をチャプター付きで結合 |
| `ytdl` | YouTube 動画ダウンロード |
| `jsonl2md` | JSONL → Markdown 変換 |

### 文字起こし（2エンジン並走）

同一素材を2エンジンで転写し、突き合わせて精度を上げるための組。**出力契約は共通**で、
`<base>.srt`（可読層）/ `<base>.words.json`（機械忠実層・語ごと confidence）/
`<base>.meta.json`（来歴・入力の sha256）を出す。

| コマンド | 説明 |
|---------|------|
| `advanced/audio-transcribe` | Whisper 系（faster-whisper + stable-ts）。既定 `large-v3`。`--terms` で hotwords 注入 |
| `advanced/audio-transcribe-dg` | Deepgram Nova-3（REST・標準ライブラリのみ）。`--terms` で Keyterm Prompting、`--diarize` で話者分離 |

語彙ファイル（[examples/terms-orchestral.txt](examples/terms-orchestral.txt)）は両者で共用。
一次資料は **メディア + `.words.json` + `.meta.json`**、`.srt` はその派生（原本ではない）。
既存の出力があるときは停止する（上書きは `--force`）。

`audio-transcribe-dg` は音声を外部 API へ送信する。`DEEPGRAM_API_KEY` が必要。

### レポートパイプライン

| コマンド | 説明 |
|---------|------|
| `msw-config` | VCE 設定のマージ・検証（defaults.yaml + template + project の3層） |
| `msw-report` | SRT + VCE 設定 → LaTeX 出力 |
| `msw-compile` | LuaTeX → PDF コンパイル |
| `msw-pipeline` | SRT → LaTeX → PDF 完全自動化 |

### VCE プロジェクトツール

VCE (`.vce.json`) は Chaptr GUI が出力するチャプター定義フォーマット。これを CLI から処理:

| コマンド | 説明 |
|---------|------|
| `vce-encode` | VCE → チャプター付き単一動画。`--cover-image`, `--overlay-title`, `--dry-run` 等 |
| `vce-split` | VCE → チャプターごとの分割動画 |

### AI 統合

- **Whisper 高精度文字起こし** — リモート GPU サーバー経由
- **Claude AI 統合分析** — プロンプトテンプレート (`examples/prompts/`)
- **LuaTeX レポート生成** — 2段組、美麗なタイポグラフィ (`profiles/`)

## Installation

### pip

```bash
pip install -e .
```

### bin/ をパスに通す

CLI ツールは `bin/` 配下のスクリプトとして提供されます:

```bash
export PATH="$(pwd)/bin:$PATH"
```

または個別に呼び出し:

```bash
./bin/msw-pipeline project.vce.json --srt recording.srt -o report.pdf
```

## Usage

### 基本ワークフロー

```bash
# 1. YouTube から動画 + 字幕取得
yt-srt "https://youtu.be/xxxxxxxxxxx" --video --output-base rehearsal

# 2. Chaptr GUI で動画を読み込み、チャプター編集 → .vce.json 保存
#    （または既存の .vce.json を流用）

# 3. SRT + VCE → PDF レポート生成
msw-pipeline rehearsal.vce.json --srt rehearsal.srt -o report.pdf
```

### プロファイル切り替え

`profiles/` に用途別テンプレート:

- `orchestral_rehearsal.yaml` — オーケストラ・吹奏楽リハーサル
- `horn_lesson.yaml` — ホルンレッスン
- `meeting_report.yaml` — 会議議事録

プロファイルは `~/.config/msw/templates/` または作業ディレクトリに配置して `msw-config` から参照されます。

## Documentation

- [`docs/workflow-rehearsal-to-dashboard.md`](docs/workflow-rehearsal-to-dashboard.md) — **収録からダッシュボードまでの全手順**（L/R 32-bit float + 映像 → 同期 → 原本の凍結 → 転写 → 記録 PDF → 取り込み）
- [`docs/snakemake-design.md`](docs/snakemake-design.md) — ワークフロー全体の Snakemake 移行設計（実装予定）
- [`docs/workflow-diagrams.md`](docs/workflow-diagrams.md) — Mermaid ワークフロー図
- [`docs/pad/`](docs/pad/) — PAD 図（ソース `.spd` + PNG）
- [`docs/DESIGN_PRINCIPLES.md`](docs/DESIGN_PRINCIPLES.md) — 設計原則

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issue / PR 歓迎します。
