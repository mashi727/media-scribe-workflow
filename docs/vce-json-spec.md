# VCE Project File Specification (.vce.json)

## 概要

`.vce.json` は Video Chapter Editor プロジェクトファイルの形式。
UIとCLI（vce-encode）の両方で同じ形式を使用する。

## フォーマット

```json
{
  "version": "1.0",
  "created": "2026-01-14T12:00:00",
  "sources": [
    "/absolute/path/to/file1.mp3",
    "/absolute/path/to/file2.mp3",
    "/absolute/path/to/file3.mp3"
  ],
  "chapters": [
    {"local_time_ms": 0, "source_index": 0, "title": "Chapter 1"},
    {"local_time_ms": 0, "source_index": 1, "title": "Chapter 2"},
    {"local_time_ms": 0, "source_index": 2, "title": "Chapter 3"}
  ],
  "encode_settings": {
    "encoder": "h264_videotoolbox",
    "quality_index": 1,
    "embed_chapters": true,
    "cut_excluded": true,
    "embed_cover": true
  },
  "cover_image": "project_cover.png",
  "output_dir": "/path/to/output"
}
```

## フィールド説明

### sources (必須)
- 型: `string[]`
- ソースファイルの絶対パスリスト
- 相対パスの場合、プロジェクトファイルのディレクトリからの相対

### chapters (必須)
- 型: `object[]`
- チャプター情報のリスト

各チャプターオブジェクト:
| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `local_time_ms` | `int` | Yes | ソースファイル内のローカル時間（ミリ秒） |
| `source_index` | `int` | Yes | ソースファイルのインデックス（0始まり） |
| `title` | `string` | Yes | チャプタータイトル |

**重要**: `source_index` は各ソースを正しく識別するために必須。
省略または不正な値の場合、チャプターが正しく埋め込まれない。

### version (推奨)
- 型: `string`
- プロジェクトファイルのバージョン
- 現在: `"1.0"`

### encode_settings (任意)
- 型: `object`
- エンコード設定

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `encoder` | `string` | `"libx264"` | エンコーダID |
| `quality_index` | `int` | `1` | 品質 (0=最高, 3=低) |
| `embed_chapters` | `bool` | `true` | チャプター埋め込み |
| `cut_excluded` | `bool` | `true` | 除外区間をカット |
| `embed_cover` | `bool` | `false` | カバー画像埋め込み（音声のみモード時） |

### cover_image (任意)
- 型: `string`
- カバー画像ファイルパス（相対パスの場合、プロジェクトファイルのディレクトリからの相対）
- プロジェクト保存時に自動的にプロジェクト名と同名のPNGファイルとして保存される
- 音声ファイルのみの場合に動画として出力する際の背景画像

### output_dir (任意)
- 型: `string`
- 出力ディレクトリの絶対パス

## チャプターの時間計算

### ローカル時間 vs 絶対時間

- **ローカル時間** (`local_time_ms`): 各ソースファイル内での相対時間
- **絶対時間**: 全ソースを結合した後の累積時間

```
Source 0: 15分 → local_time_ms=0 → absolute=0:00
Source 1: 18分 → local_time_ms=0 → absolute=15:00
Source 2: 12分 → local_time_ms=0 → absolute=33:00
```

### vce-encodeでの処理

1. ソースごとにチャプターを `source_index` でグループ化
2. 各ソースのセグメントを抽出
3. チャプターの絶対時間を計算（出力オフセット + ローカル時間）
4. 結合後のファイルにチャプターを埋め込み

## 使用例

### 複数MP3をチャプター付き動画に結合

```bash
# プロジェクトファイル作成
cat > project.vce.json << 'EOF'
{
  "version": "1.0",
  "sources": [
    "01.Opening.mp3",
    "02.Main.mp3",
    "03.Ending.mp3"
  ],
  "chapters": [
    {"local_time_ms": 0, "source_index": 0, "title": "Opening"},
    {"local_time_ms": 0, "source_index": 1, "title": "Main"},
    {"local_time_ms": 0, "source_index": 2, "title": "Ending"}
  ]
}
EOF

# ドライラン（計画確認）
vce-encode project.vce.json --dry-run

# エンコード実行
vce-encode project.vce.json -e h264_videotoolbox --auto
```

### 単一動画にチャプターを追加

```json
{
  "version": "1.0",
  "sources": ["video.mp4"],
  "chapters": [
    {"local_time_ms": 0, "source_index": 0, "title": "Introduction"},
    {"local_time_ms": 300000, "source_index": 0, "title": "Part 1"},
    {"local_time_ms": 900000, "source_index": 0, "title": "Part 2"},
    {"local_time_ms": 1800000, "source_index": 0, "title": "Conclusion"}
  ]
}
```

## 除外チャプター

タイトルが `--` で始まるチャプターは除外区間として扱われる:

```json
{
  "chapters": [
    {"local_time_ms": 0, "source_index": 0, "title": "Introduction"},
    {"local_time_ms": 300000, "source_index": 0, "title": "--休憩"},
    {"local_time_ms": 600000, "source_index": 0, "title": "Part 2"}
  ]
}
```

`--no-cut` オプションを付けない限り、`--休憩` の区間（5:00〜10:00）はカットされる。
