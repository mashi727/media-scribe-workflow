# LuaTeX Docker リモート環境構築

リモートサーバー上のDockerコンテナでLuaLaTeXをコンパイルし、
macOSからHTTP経由で呼び出す環境の構築方法です。

## 概要

```
┌─────────────────┐          HTTP              ┌─────────────────┐
│  macOS          │  ───────────────────────>  │  Linux Server   │
│  luatex-pdf     │       .tex file            │  LuaTeX Docker  │
│  (クライアント)  │  <───────────────────────  │  TeX Live Full  │
└─────────────────┘       .pdf file            └─────────────────┘
```

## 関連リポジトリ

公式の詳細なセットアップは以下を参照：
- [luatex-docker-remote](https://github.com/mashi727/luatex-docker-remote)

## サーバー側セットアップ

### 1. Dockerfile

```dockerfile
# Dockerfile
FROM texlive/texlive:latest

# 必要なパッケージ
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Libertinus フォント
RUN mkdir -p /usr/local/share/fonts && \
    cd /tmp && \
    wget https://github.com/alerque/libertinus/releases/download/v7.040/Libertinus-7.040.tar.xz && \
    tar xf Libertinus-7.040.tar.xz && \
    cp Libertinus-7.040/static/OTF/*.otf /usr/local/share/fonts/ && \
    rm -rf /tmp/Libertinus*

# 原ノ味フォント
RUN cd /tmp && \
    wget https://github.com/trueroad/HaranoAjiFonts/releases/download/20231009/HaranoAjiFonts-20231009.tar.gz && \
    tar xf HaranoAjiFonts-20231009.tar.gz && \
    cp HaranoAjiFonts-20231009/*.otf /usr/local/share/fonts/ && \
    rm -rf /tmp/HaranoAji*

# フォントキャッシュ更新
RUN fc-cache -fv

# Webサーバー
RUN pip3 install flask gunicorn

WORKDIR /app
COPY server.py .

EXPOSE 8080

CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "2", "--timeout", "300", "server:app"]
```

### 2. サーバーアプリケーション

```python
# server.py
from flask import Flask, request, send_file, jsonify
import tempfile
import subprocess
import os

app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/compile", methods=["POST"])
def compile():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    tex_file = request.files["file"]

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "document.tex")
        pdf_path = os.path.join(tmpdir, "document.pdf")
        tex_file.save(tex_path)

        # LuaLaTeX コンパイル（2回実行で相互参照解決）
        for i in range(2):
            result = subprocess.run(
                ["lualatex", "-interaction=nonstopmode",
                 "-output-directory", tmpdir, tex_path],
                capture_output=True, text=True, timeout=120
            )

        if not os.path.exists(pdf_path):
            log_path = os.path.join(tmpdir, "document.log")
            log_content = ""
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    log_content = f.read()[-2000:]  # 最後の2000文字
            return jsonify({
                "error": "Compilation failed",
                "stdout": result.stdout[-1000:],
                "stderr": result.stderr[-1000:],
                "log": log_content
            }), 400

        return send_file(pdf_path, as_attachment=True,
                        download_name="document.pdf")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

### 3. Docker Compose

```yaml
# docker-compose.yml
version: "3.8"
services:
  luatex:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./fonts:/usr/local/share/fonts/custom:ro
    restart: unless-stopped
```

### 4. 起動

```bash
docker compose up -d
```

## クライアント側セットアップ（macOS）

### luatex-pdf 関数

```zsh
# ~/.config/zsh/functions/luatex-pdf

#!/usr/bin/env zsh
# luatex-pdf - リモートLuaTeXコンパイル

local tex_file="$1"

if [[ -z "$tex_file" || ! -f "$tex_file" ]]; then
    echo "Usage: luatex-pdf <tex_file>" >&2
    return 1
fi

local host="${LUATEX_HOST:-gpu-server.local}"
local port="${LUATEX_PORT:-8080}"
local basename="${tex_file:r}"
local pdf_file="${basename}.pdf"

echo "Compiling on remote server..."
echo "  Host: ${host}:${port}"
echo "  File: ${tex_file}"

local response
response=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -F "file=@${tex_file}" \
    "http://${host}:${port}/compile" \
    -o "$pdf_file")

local http_code=$(echo "$response" | tail -1)

if [[ "$http_code" != "200" ]]; then
    echo "Error: Compilation failed (HTTP $http_code)" >&2
    cat "$pdf_file"  # エラーメッセージが含まれている
    rm -f "$pdf_file"
    return 1
fi

echo "Output: ${pdf_file}"
ls -lh "$pdf_file"
```

### 使用方法

```bash
luatex-pdf document.tex
```

## フォント設定

### 必須フォント

| フォント | 用途 | ダウンロード |
|---------|------|-------------|
| Libertinus | 欧文本文・数式 | [GitHub](https://github.com/alerque/libertinus) |
| 原ノ味 | 日本語 | [GitHub](https://github.com/trueroad/HaranoAjiFonts) |

### LaTeX での指定

```latex
% フォント設定
\usepackage{luatexja-fontspec}
\usepackage{unicode-math}

% 欧文
\setmainfont{Libertinus Serif}
\setsansfont{Libertinus Sans}
\setmonofont{Libertinus Mono}
\setmathfont{Libertinus Math}

% 日本語
\setmainjfont{HaranoAjiMincho-Regular}[
    BoldFont = {HaranoAjiGothic-Medium}
]
\setsansjfont{HaranoAjiGothic-Regular}
```

## トラブルシューティング

### フォントが見つからない

```bash
# コンテナ内でフォント確認
docker exec luatex-container fc-list | grep -i libertinus
docker exec luatex-container fc-list | grep -i harano

# フォントキャッシュ更新
docker exec luatex-container fc-cache -fv
```

### コンパイルエラー

```bash
# ログ確認
docker logs luatex-container

# 詳細なエラーメッセージはレスポンスに含まれる
```

### タイムアウト

```bash
# 大きなドキュメントの場合はタイムアウトを延長
# docker-compose.yml の gunicorn --timeout を増加
```

## ローカル代替（macOS直接インストール）

リモート環境が利用できない場合：

```bash
# MacTeX インストール
brew install --cask mactex

# フォントインストール
brew install --cask font-libertinus
brew install --cask font-harano-aji

# 直接コンパイル
lualatex document.tex
```

## 関連

- [my-setup.md](my-setup.md) - 全体構成
- [luatex-docker-remote](https://github.com/mashi727/luatex-docker-remote) - 公式リポジトリ
