# 私の環境構成（参考）

このドキュメントは、media-scribe-workflow を最大限に活用するための環境構成例です。
必須ではありませんが、同様の環境を構築することでフルワークフローが利用可能になります。

## 全体構成図

```
┌─────────────────────────────────────────────────────────────┐
│  macOS (作業マシン)                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ yt-dlp      │    │ Claude Code │    │ Movie Viewer│     │
│  │ (動画DL)    │    │ (AI分析)    │    │ (チャプター)│     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                  │                  │             │
│         └──────────┬───────┴──────────────────┘             │
│                    │                                        │
│  ┌─────────────────▼────────────────────────────────────┐   │
│  │  Zsh関数群                                            │   │
│  │  ├── rehearsal-download (統合DL+Whisper起動)         │   │
│  │  ├── rehearsal-finalize (PDF生成+チャプター抽出)     │   │
│  │  ├── yt-srt, video-trim, video-chapters              │   │
│  │  └── ytdl, whisper-remote, luatex-pdf               │   │
│  └──────────────────────────────────────────────────────┘   │
│                    │                                        │
└────────────────────┼────────────────────────────────────────┘
                     │ SSH/HTTP
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Linux サーバー (GPU搭載)                                   │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Whisper Docker  │    │ LuaTeX Docker   │                │
│  │ (文字起こし)    │    │ (PDF生成)       │                │
│  │ NVIDIA GPU      │    │ Libertinus/原ノ味│                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## 必要なコンポーネント

### 1. macOS側

| コンポーネント | 用途 | インストール |
|--------------|------|-------------|
| Zsh | シェル | 標準搭載 |
| yt-dlp | YouTube動画DL | `brew install yt-dlp` |
| ffmpeg | 動画処理 | `brew install ffmpeg` |
| Claude Code | AI分析 | [公式サイト](https://claude.com/claude-code) |
| Movie Viewer | チャプター編集 | [GitHub](https://github.com/mashi727/movie-viewer) |

### 2. リモートサーバー側（オプション）

| コンポーネント | 用途 | 備考 |
|--------------|------|------|
| Docker | コンテナ実行 | |
| NVIDIA GPU + CUDA | Whisper高速化 | |
| Whisper Docker | 文字起こし | [whisper-remote.md](whisper-remote.md) |
| LuaTeX Docker | PDF生成 | [luatex-docker.md](luatex-docker.md) |

## Zsh関数の配置

```bash
# ~/.config/zsh/functions/ に配置
~/.config/zsh/functions/
├── rehearsal-download
├── rehearsal-finalize
├── tex2chapters
├── yt-srt
├── video-trim
├── video-chapters
├── ytdl          # ytdl-claude ラッパー
├── whisper-remote
└── luatex-pdf
```

### fpath設定（~/.zshrc）

```zsh
# Zsh関数の読み込み
fpath=(~/.config/zsh/functions $fpath)
autoload -Uz rehearsal-download rehearsal-finalize tex2chapters
autoload -Uz yt-srt video-trim video-chapters
autoload -Uz ytdl whisper-remote luatex-pdf
```

## 環境変数

```zsh
# ~/.zshrc または ~/.zshenv

# リモートサーバー設定
export WHISPER_HOST="gpu-server.local"
export WHISPER_PORT="9000"

export LUATEX_HOST="gpu-server.local"
export LUATEX_PORT="8080"

# Claude Code設定
export CLAUDE_API_KEY="sk-ant-..."
```

## 動作確認

```bash
# 各コンポーネントの確認
which yt-dlp ffmpeg
claude --version

# Zsh関数の確認
type rehearsal-download
type whisper-remote
type luatex-pdf

# リモートサーバー接続確認
curl -s http://${WHISPER_HOST}:${WHISPER_PORT}/health
curl -s http://${LUATEX_HOST}:${LUATEX_PORT}/health
```

## ワークフロー例

```bash
# 1. 動画ダウンロード + Whisper起動
rehearsal-download "https://youtu.be/VIDEO_ID"

# 2. Whisper完了待ち（30分〜2時間）
# *_wp.srt ファイルが生成されるまで待機

# 3. Claude Code でAI分析
claude code
# プロンプト: /rehearsal

# 4. PDF生成 + チャプター抽出
rehearsal-finalize "リハーサル記録.tex"

# 5. 成果物確認
open "リハーサル記録.pdf"
cat "リハーサル記録_youtube.txt" | pbcopy
```

## トラブルシューティング

### Whisper接続エラー

```bash
# サーバー状態確認
ssh gpu-server "docker ps | grep whisper"

# ログ確認
ssh gpu-server "docker logs whisper-container"
```

### LuaTeX コンパイルエラー

```bash
# フォント確認
ssh gpu-server "docker exec luatex-container fc-list | grep -i libertinus"
ssh gpu-server "docker exec luatex-container fc-list | grep -i harano"
```

## 関連ドキュメント

- [whisper-remote.md](whisper-remote.md) - Whisperリモート環境の詳細
- [luatex-docker.md](luatex-docker.md) - LuaTeX Docker環境の詳細
- [claude-commands.md](claude-commands.md) - Claude Codeコマンドの詳細
