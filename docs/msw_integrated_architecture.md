# MSW 統合アーキテクチャ

## 概要

Media Scribe Workflow (MSW) は、動画からレポートを生成するエンドツーエンドのパイプラインです。VCE（Video Chapter Editor）はこのパイプラインの中核コンポーネントとして動作します。

## パイプライン全体像

```
[動画ファイル]
     │
     ▼
┌─────────────────────────────────────────────┐
│  VCE（Video Chapter Editor）                │
│  ├─ チャプター編集                          │
│  ├─ ソース管理                              │
│  └─ プロジェクト管理 (.vce.json)            │
└─────────────────────────────────────────────┘
     │
     ├─ vce-encode → [チャプター付き単一動画]
     │
     └─ vce-split → [チャプター別ファイル]
           │
           ▼
┌─────────────────────────────────────────────┐
│  字幕取得                                    │
│  ├─ yt-srt（YouTube字幕）                   │
│  └─ whisper（音声認識）                     │
└─────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────┐
│  MSW レポート生成                            │
│  ├─ テンプレート選択                        │
│  ├─ Claude/LLM による分析                   │
│  └─ LaTeX → PDF                             │
└─────────────────────────────────────────────┘
     │
     ▼
[レポート.pdf]
```

## 統合プロジェクトファイル

VCE と MSW は単一のプロジェクトファイル（`.vce.json`）を共有します。

### ファイル構造

```json
{
  "version": "1.0",

  // ===== VCE 管理領域 =====
  "sources": [
    {
      "path": "lesson_2026-01-15.mp4",
      "start": 0,
      "end": 3600000,
      "label": "メイン動画"
    }
  ],

  "chapters": [
    {
      "title": "導入",
      "start": 0,
      "end": 300000
    },
    {
      "title": "アンブシュア解説",
      "start": 300000,
      "end": 1200000
    }
  ],

  "export": {
    "encoder": "libx264",
    "quality": 1,
    "output_dir": "./output"
  },

  // ===== MSW 管理領域 =====
  "msw": {
    "template": "instrument_lesson",
    "metadata": {
      "date": "2026-01-15",
      "instructor": "濵地 宗",
      "instructor_title": "群馬交響楽団 首席ホルン奏者",
      "instrument": "ホルン",
      "lesson_topic": "アンブシュア"
    },
    "output": {
      "report": "lesson_report.tex"
    }
  }
}
```

### 領域の責務

| 領域 | 管理者 | 内容 |
|------|--------|------|
| `sources` | VCE | ソースメディア情報 |
| `chapters` | VCE | チャプター定義 |
| `export` | VCE | エンコード設定 |
| `msw` | MSW | レポート生成設定 |

## 設定ファイル階層

```
~/.config/msw/
├── defaults.yaml           # グローバルデフォルト
├── luatex-settings.yaml    # LaTeX共通設定
└── templates/
    ├── rehearsal.yaml      # リハーサル記録
    ├── instrument_lesson.yaml  # 楽器レッスン
    ├── lecture.yaml        # 学術講義
    ├── meeting.yaml        # 会議記録
    └── yoga.yaml           # ヨガレッスン

[プロジェクトディレクトリ]/
└── project.vce.json        # プロジェクト固有設定（msw含む）
```

### 設定マージ順序

```
defaults.yaml
    ↓ extends
templates/{template}.yaml
    ↓ override
project.vce.json["msw"]
    ↓
[最終設定]
```

## コンポーネント

### VCE（Video Chapter Editor）

GUI アプリケーション。以下を担当：

- ソースファイルの追加・管理
- タイムライン上でのチャプター編集
- プロジェクトファイルの保存・読み込み
- エクスポート設定の管理

**注**: VCE は `msw` セクションを無視します（透過的に保持）。

### vce-encode

チャプター付き単一動画を生成：

```bash
vce-encode project.vce.json
# → output/project_encoded.mp4（チャプター埋め込み済み）
```

### vce-split

チャプターごとに分割：

```bash
vce-split project.vce.json
# → output/01_導入.mp4
# → output/02_アンブシュア解説.mp4
```

### MSW レポート生成

プロジェクトファイルの `msw` セクションと字幕ファイルを入力として、テンプレートに従ってレポートを生成。

## 自動化パイプライン

### 基本フロー

```bash
# 1. VCE でチャプター編集（GUI）
# 2. エンコード
vce-encode project.vce.json

# 3. YouTube にアップロード → 字幕取得
yt-srt "https://youtube.com/watch?v=..."

# 4. レポート生成（将来実装）
msw-report project.vce.json --srt subtitles.srt
```

### 完全自動化（将来構想）

```bash
msw-pipeline project.vce.json
# 内部処理:
#   1. vce-split で分割
#   2. whisper で字幕生成
#   3. テンプレートに従ってレポート生成
#   4. luatex-pdf でPDF出力
```

## 設計原則

1. **単一ソース**: プロジェクト情報は `.vce.json` に集約
2. **関心の分離**: VCE は動画編集、MSW はレポート生成
3. **透過性**: 各ツールは自分に関係ない設定を無視
4. **拡張性**: テンプレートシステムによる柔軟なカスタマイズ
