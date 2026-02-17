# Development Log (〜2025-12-29)

このファイルは2025-12-29までの開発履歴をアーカイブしたものです。
以降の開発ログは `DEVELOPMENT_LOG.md` を参照してください。

---

## プロジェクト概要

**rehearsal-workflow** - オーケストラ・吹奏楽のリハーサル動画から、AI分析による詳細レポートとチャプターリストを自動生成するワークフロー。

「Gitの陶器と配管」の思想に基づき、単一目的のツールを組み合わせてワークフローを構築。

---

## バージョン履歴

### v1.3.0 (2025-12-29)

**スマートビットレート検出と色空間保持**

- 元動画のビットレートを自動検出し、同等以上の品質で出力
- 色空間（BT.709等）を正確に保持
- GPUハードウェアエンコード対応（VideoToolbox/NVENC/QSV/AMF）

**UIモダン化**
- ダークテーマ（Theme class）の適用
- ボタン色ポリシーの確立（Primary: メインアクションのみ）
- 絵文字からテキストベースのボタンラベルへ変更
- チャプターテーブルの幅調整

### v1.2.0

**GPUハードウェアエンコーダー対応**

- macOS: VideoToolbox (h264_videotoolbox)
- Windows: NVENC (h264_nvenc), QSV (h264_qsv), AMF (h264_amf)
- 自動検出とフォールバック

### v1.1.1

**バイナリサイズ最適化**

- 不要なPySide6モジュールの除外
- opencv-python-headlessの使用
- PyInstaller specファイルの最適化

### v1.1.0

**自動リリースワークフロー**

- GitHub Actions による macOS/Windows バイナリ自動ビルド
- DMG/ZIP パッケージ作成
- リリースページへの自動アップロード

### v1.0.0 (初期リリース)

**GUIツール**
- video-chapter-editor: 動画チャプター編集・書出ツール
  - 動画プレビュー＋波形表示
  - チャプター編集（追加/削除/編集/ジャンプ）
  - 除外チャプター機能（`--`プレフィックス）
  - YouTubeチャプターのコピー＆ペースト
  - ffmpegによる動画書き出し

**CLIツール**
- yt-srt: YouTube字幕取得
- video-trim: 動画トリミング
- video-chapters: チャプター結合
- rehearsal-download: DL + Whisper起動
- rehearsal-finalize: PDF生成 + チャプター抽出
- tex2chapters: LaTeX → チャプターリスト

---

## 実装ドキュメント

### CLIワークフロー実装 (2025-11-05)

ハイブリッドアプローチ（Claude Code + Zshヘルパー関数）により、3ステップでリハーサル記録を生成：

```bash
# 1. ダウンロード + Whisper起動
rehearsal-download "https://youtu.be/VIDEO_ID"

# 2. AI分析 + LaTeX生成
claude code
/rehearsal

# 3. PDF生成 + チャプター抽出
rehearsal-finalize "リハーサル記録.tex"
```

**実装ファイル:**
- `~/.config/zsh/functions/rehearsal-download` (176行)
- `~/.config/zsh/functions/rehearsal-finalize` (183行)
- `~/.claude/commands/rehearsal.md` (321行)

### GUIリファクタリング (2025-11-06)

**元のGUI** (`video_analysis_gui.py`):
- 汎用動画分析ワークフロー
- 5カテゴリー、25フィールド
- 955行

**リファクタリング後** (`rehearsal_gui.py`→`video_chapter_editor.py`):
- リハーサル記録専用
- 15フィールド
- 3ステップワークフロー可視化
- ファイル自動検出、リアルタイムログ

**改善点:**
- メモリ使用量 約30%削減
- 起動時間 約33%短縮
- 明確なワークフロー

---

## Git コミット履歴

```
e0e3e33 UI modernization: apply dark theme and document redesign plan
2267a42 v1.3.0: Add smart bitrate detection and colorspace preservation
6dae870 Fix CI build: use full PySide6 for QtMultimedia support
a265440 Update README for v1.2.0 with GPU encoding feature
5b84a6d Add GPU hardware encoder support for faster video export
6cef802 Update README download links to v1.1.1
42245f2 Reduce binary size: exclude unused PySide6 modules, use headless opencv
3eebc20 Add direct download links to README
95b96ef Fix PyInstaller spec: use onedir mode for macOS app bundle
1fb19f7 Add debug step to release workflow
391b4ce Add GUI tools, pip install support, and automated releases
fc26e17 Revert to original PADtools output
9933a01 Improve PAD renderer with column-aligned layout
2568bd8 Revert PAD diagrams to original PADtools output
0eb9b44 Update PAD diagrams with simplified renderer output
813f973 Simplify PadAlignedRenderer: remove text wrapping
596038c Add horizontal separator lines between each case in Switch/If
73e8a58 Add top and bottom border lines for Switch/If blocks
586462a Remove horizontal separator lines between Switch/If cases
fe10cad Improve Switch/If rendering: vertically connected pennants
8c60a11 Fix condition branch layout: vertical line connects pennants
4636c96 Change condition branch shape to pennant
8fc8051 Fix vertical connecting lines to match original PADtools style
5dc1e95 Restore original PADtools visual style with column alignment
e0c0383 Add column-aligned PAD renderer with text wrapping
a6d01cc Add PADtools CLI wrapper and generate PAD diagram PNGs
f4ddd6b Add plumbing tools and documentation
d738a8c Add GUI frontend and improve workflow robustness
c01656e Add installation files documentation
579c45d Add luatex-docker-remote documentation
640bb7d Initial commit: Rehearsal workflow v1.0.0
```

---

## アーキテクチャ

### ディレクトリ構成

```
rehearsal-workflow/
├── rehearsal_workflow/      # Pythonパッケージ
│   ├── __init__.py
│   ├── video_chapter_editor.py   # 動画チャプター編集GUI
│   └── report_workflow.py        # レポート生成ワークフロー
│
├── bin/                     # CLIツール（Zsh関数）
│   ├── yt-srt
│   ├── video-trim
│   ├── video-chapters
│   ├── rehearsal-download
│   ├── rehearsal-finalize
│   └── tex2chapters
│
├── examples/prompts/        # プロンプト例
│
├── docs/                    # ドキュメント
│   └── advanced/            # 環境構築ガイド
│
└── .github/workflows/       # GitHub Actions
    └── release.yml          # 自動リリース
```

### ハイブリッドアプローチ

- **Python GUI**: 動画編集、チャプター管理
- **Zsh関数**: 機械的処理（ダウンロード、コンパイル、抽出）
- **Claude AI**: 分析・文書生成（SRT統合分析、LaTeX生成）

---

## 技術スタック

### GUIツール
- Python 3.10+
- PySide6 (Qt6)
- numpy
- opencv-python
- ffmpeg（システム）

### CLIワークフロー
- Zsh 5.0+
- Claude Code
- ytdl-claude
- whisper-remote
- luatex-pdf

### フォント（LaTeX出力）
- Libertinus (欧文)
- 原ノ味 (日本語)

---

## 設計思想

### 「配管と陶器」

Unix哲学に基づく設計：
- **配管 (Plumbing)**: 単一目的のCLIツール
- **陶器 (Porcelain)**: ユーザーフレンドリーなGUI

各ツールは独立して動作し、組み合わせることで複雑なワークフローを実現。

### 責務分離

| 処理タイプ | 担当 |
|-----------|------|
| 機械的処理 | Zsh関数 |
| AI判断処理 | Claude Code |
| ユーザー操作 | Python GUI |

---

## 参考ドキュメント

- `docs/gui-refactoring.md` - GUIリファクタリング詳細
- `docs/implementation.md` - CLIワークフロー実装詳細
- `docs/workflow-diagrams.md` - Mermaid形式フロー図
- `docs/advanced/` - 環境構築ガイド

---

**アーカイブ日**: 2025-12-29
**次の開発ログ**: `DEVELOPMENT_LOG.md`
