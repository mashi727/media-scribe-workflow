# 文字起こしワークフロー設計ログ

**作成日**: 2025-01-03
**バージョン**: 1.0
**関連PAD**: `docs/pad/transcription-schema.spd`, `docs/pad/transcription-workflow.spd`

---

## PAD図

### スキーマ構造図

![スキーマ構造](../pad/transcription-schema.png)

### 処理フロー図

![処理フロー](../pad/transcription-workflow.png)

---

## 1. 設計の背景と目的

### 1.1 既存の課題

既存の `report_workflow.py` および `~/.claude/commands/` 配下のカスタムコマンド群には以下の課題があった：

- **モノリシック構造**: 1ファイルに設定・処理ロジック・出力テンプレートが混在（rehearsal.md: 302行、srt-meeting-report.md: 549行）
- **再利用性の欠如**: 類似のLuaTeX設定が複数ファイルで重複
- **拡張性の制限**: 新しいユースケース追加時に大幅な修正が必要

### 1.2 設計目標

1. **再現性**: 同じ設定で同じ結果を得られる
2. **再利用性**: テンプレートとして使い回せる
3. **スケーラビリティ**: CLIからも利用可能、バッチ処理対応
4. **分離の原則**: 設定・構造定義・処理ロジック・出力テンプレートの分離

---

## 2. 設計思想

### 2.1 TeX/LaTeX アナロジー

設計はTeX/LaTeXの構造に倣った：

| TeX/LaTeX | 本システム | 役割 |
|-----------|-----------|------|
| `.tex` ファイル | `transcription_workflow.yaml` | 具体的な値（インスタンス） |
| `.cls` / `.sty` | `profiles/*.yaml` | 構造定義（マクロ/クラス） |
| `\section{...}` | `fields.title: "..."` | 内容の記述 |
| マクロ展開 | プロンプト生成 | 変数展開と出力 |

### 2.2 分離の原則

```
設定ファイル（YAML）     → 「何を」処理するか（値）
プロファイル（YAML）     → 「どのような構造で」処理するか（型定義）
プロンプト（Markdown）   → 「AIに何を指示するか」（処理ロジック）
テンプレート（TeX）      → 「どのような形式で」出力するか（出力形式）
```

---

## 3. 入力状態の場合分け

### 3.1 問題の背景

YouTube経由の場合、`yt-dlp` で動画と字幕が同時に取得される。この自然な処理フローと、前処理/文字起こしワークフローの境界設計を整合させる必要がある。

### 3.2 入力状態の次元

```
入力の次元:
1. 動画ソース: YouTube URL | ローカルファイル | 処理済み動画
2. SRT状態: なし | YouTube字幕あり | Whisper字幕あり | 両方あり | 手動SRTあり
```

### 3.3 全状態の列挙

| # | 動画 | YT字幕 | Whisper | 手動SRT | 必要な処理 |
|---|------|--------|---------|---------|-----------|
| 1 | YouTube URL | - | - | - | ytdl（動画+YT字幕）、任意でWhisper |
| 2 | ローカル動画のみ | - | - | - | Whisperまたは手動SRT |
| 3 | ローカル動画 | ✓ | - | - | 任意でWhisper追加 |
| 4 | ローカル動画 | - | ✓ | - | 処理可能 |
| 5 | ローカル動画 | ✓ | ✓ | - | 処理可能（統合） |
| 6 | ローカル動画 | - | - | ✓ | 処理可能 |
| 7 | YouTube DL済み | - | - | - | yt-srt or Whisper |

### 3.4 前処理との関係

| 前処理の出力状態 | 文字起こしへの引き継ぎ |
|-----------------|---------------------|
| YouTube経由で完了 | 状態3 or 5（YT字幕あり） |
| ローカル動画をWhisper | 状態4（WP字幕あり） |
| ローカル動画のみ編集 | 状態2 or 7（字幕なし） |

### 3.5 ワークフロー境界の定義

```
前処理の責務:
  「SRTファイルが作業ディレクトリに存在する状態」を保証

文字起こしの責務:
  SRTファイルを読み込み、AI処理→出力
  （ただし単独起動時はSRT取得も可能）
```

ソースタイプ別の責務分担：

```
[YouTube経由]
前処理: ytdl → 動画 + SRT（両方取得）
文字起こし: method = "skip"（SRT既存）

[ローカル動画]
前処理: video-trim → チャプター → 最終動画
文字起こし: method = "whisper" or "manual"（SRT取得）

[YouTubeから直接（前処理スキップ）]
文字起こし単独起動: method = "youtube"（ytdl実行）
```

---

## 4. スキーマ設計

### 4.1 設定ファイル（transcription_workflow.yaml）

ユーザーが毎回編集するプロジェクト固有の設定：

```yaml
schema_version: "1.1"
profile: "orchestral_rehearsal"

source:
  type: "local"              # local | youtube
  path: "video.mp4"
  working_dir: "/path/to/project"

  # 入力状態を明示的に記述
  state:
    video: "ready"           # ready | url_only | missing
    youtube_srt: "exists"    # exists | missing | not_applicable
    whisper_srt: "missing"   # exists | missing
    manual_srt: "missing"    # exists | missing

  files:
    youtube_srt: "video_yt.srt"   # state.youtube_srt = exists の場合
    whisper_srt: null             # state.whisper_srt = missing の場合
    manual_srt: null

transcription:
  method: "auto"             # auto | youtube | whisper | manual | skip
  language: "ja"

  # method = "auto" の場合の優先順位
  auto_priority: ["whisper", "youtube"]

fields:
  title: "ブラームス交響曲第1番"
  date: "2025-01-03"
  key_person: "山田太郎"
  organization: "〇〇交響楽団"

output:
  basename: "rehearsal_record"
  format: "latex"            # markdown | latex | docx
```

### 4.2 プロファイル（profiles/*.yaml）

マクロ定義。稀に編集：

```yaml
name: "オーケストラリハーサル"
icon: "🎼"
base_template: "luatex_twocolumn.tex"
macros: ["common.tex"]

participants:
  type: "hierarchical"       # hierarchical | flat
  instructor:
    label: "指揮者"
  students:
    label: "奏者"

field_schema:
  title:
    label: "曲目"
    required: true
  date:
    label: "練習日"
    type: "date"
  key_person:
    label: "指揮者"
  organization:
    label: "団体名"

source_schema:
  multi_srt: true
  files:
    youtube_srt: { pattern: "*_yt.srt" }
    whisper_srt: { pattern: "*_wp.srt" }

prompt_template: "orchestral_rehearsal.md"
glossary: "music_terms.yaml"
```

### 4.3 参加者構造の類型

| パターン | 構造 | 例 |
|----------|------|-----|
| **hierarchical** | 講師 → 生徒 | レッスン、講義、リハーサル |
| **flat** | 参加者A = 参加者B | 会議、座談会 |

---

## 5. ファイル構成

```
~/.config/rehearsal-workflow/          # ユーザー設定（グローバル）
├── profiles/
│   ├── orchestral_rehearsal.yaml      # オーケストラリハーサル
│   ├── horn_lesson.yaml               # ホルンレッスン
│   ├── meeting_report.yaml            # 会議レポート
│   └── ...
│
├── prompts/
│   ├── orchestral_rehearsal.md
│   ├── horn_lesson.md
│   ├── meeting_report.md
│   └── ...
│
├── templates/
│   └── luatex_twocolumn.tex           # 共通LuaTeX設定
│
├── macros/
│   ├── common.tex                     # JST日時、リンク色
│   └── meeting_speakers.tex           # 発言者マクロ
│
├── glossaries/
│   ├── music_terms.yaml
│   ├── horn_techniques.yaml
│   └── defense_acronyms.yaml
│
└── config.yaml                        # グローバルデフォルト


作業ディレクトリ/                       # プロジェクト単位
├── transcription_workflow.yaml        # 設定ファイル
├── video.mp4
├── video_yt.srt
├── video_wp.srt
└── output/
    └── rehearsal_record.tex
```

---

## 6. 適用対象の分析

### 6.1 既存カスタムコマンドの分析

| コマンド | 行数 | 対象 | 特殊処理 |
|----------|------|------|----------|
| `rehearsal.md` | 302 | オケリハ | 音楽用語校正、パート別抽出 |
| `horn_hamaji.md` | 127 | ホルンレッスン | 初心者向け補足 |
| `srt-meeting-report.md` | 549 | 国際会議 | 発言者識別、footnote、チャプター生成 |

### 6.2 共通要素（templates/luatex_twocolumn.tex として共有）

- LuaTeX 2段組設定
- フォント設定（Libertinus + 原ノ味）
- JST日時表示
- ハイパーリンク色設定
- 表スタイル（縦線なし、booktabs）

### 6.3 差分要素（プロファイル/プロンプトで差別化）

- field_schema（フィールド定義）
- participants（参加者構造）
- prompt_template（AI指示）
- glossary（用語集）
- output.additional_files（追加出力）

---

## 7. 処理フロー

### Phase 1: 初期化
- 設定ファイル読込 or 新規作成

### Phase 2: プロファイル解決
- 検索順序: 作業ディレクトリ → ユーザー設定 → ビルトイン
- リソース読込: template, macros, prompt, glossary

### Phase 3: ソース処理
- local: ファイル存在確認、SRT読込
- youtube: yt-srt実行、SRT保存

### Phase 4: 文字起こし
- youtube / whisper / manual / skip
- 複数SRTの統合（相補的マージ）

### Phase 5: プロンプト生成
- テンプレート変数展開
- 参加者情報展開（hierarchical/flat）
- 字幕データ埋め込み

### Phase 6: AI処理（外部）
- Claude / ChatGPT / ローカルLLM

### Phase 7: 出力生成
- markdown / latex / docx
- 追加ファイル（チャプター等）
- 状態保存

---

## 8. 可視化手法の選択

| 対象 | 手法 | 理由 |
|------|------|------|
| スキーマ構造 | **Mermaid グラフ** | エンティティ間の参照関係を表現 |
| 処理フロー | **PAD** | 手続き・分岐・順序を表現 |

---

## 9. 今後の実装タスク

1. [ ] dataclass実装
2. [ ] 設定ファイル読み書きモジュール作成
3. [ ] UIの基本構造設計
4. [ ] 文字起こし処理ワーカーの実装
5. [ ] プロファイル/テンプレートの整備

---

## 10. 参考資料

- 既存カスタムコマンド: `~/.claude/commands/`
- PAD図: `docs/pad/transcription-*.spd`
- Video Chapter Editor: `rehearsal_workflow/ui/main_workspace.py`
