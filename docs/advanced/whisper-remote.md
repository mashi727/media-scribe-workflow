# Whisper リモート環境構築

GPUを搭載したリモートサーバーでWhisperを実行し、macOSから呼び出す環境の構築方法です。

## 概要

```
┌─────────────────┐          HTTP/SSH          ┌─────────────────┐
│  macOS          │  ───────────────────────>  │  Linux Server   │
│  whisper-remote │                            │  Whisper Docker │
│  (クライアント)  │  <───────────────────────  │  NVIDIA GPU     │
└─────────────────┘          SRT file          └─────────────────┘
```

## サーバー側セットアップ

### 前提条件

- Linux（Ubuntu 22.04推奨）
- NVIDIA GPU（VRAM 8GB以上推奨）
- Docker + NVIDIA Container Toolkit
- 十分なストレージ（音声ファイル一時保存用）

### 1. NVIDIA Container Toolkit インストール

```bash
# リポジトリ追加
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# インストール
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### 2. Whisper Docker イメージ

```dockerfile
# Dockerfile
FROM nvidia/cuda:12.1-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install openai-whisper demucs flask gunicorn

WORKDIR /app
COPY server.py .

EXPOSE 9000

CMD ["gunicorn", "-b", "0.0.0.0:9000", "-w", "1", "--timeout", "3600", "server:app"]
```

### 3. サーバーアプリケーション

```python
# server.py
from flask import Flask, request, send_file, jsonify
import whisper
import tempfile
import os

app = Flask(__name__)
model = whisper.load_model("large-v3")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    use_demucs = request.form.get("demucs", "false").lower() == "true"

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.mp4")
        output_path = os.path.join(tmpdir, "output.srt")
        file.save(input_path)

        # Demucs音声分離（オプション）
        if use_demucs:
            os.system(f"demucs --two-stems=vocals -o {tmpdir} {input_path}")
            input_path = os.path.join(tmpdir, "htdemucs/input/vocals.wav")

        # Whisper文字起こし
        result = model.transcribe(input_path, language="ja")

        # SRT形式で出力
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(result["segments"], 1):
                start = format_timestamp(segment["start"])
                end = format_timestamp(segment["end"])
                text = segment["text"].strip()
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

        return send_file(output_path, as_attachment=True,
                        download_name="transcription.srt")

def format_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000)
```

### 4. Docker Compose

```yaml
# docker-compose.yml
version: "3.8"
services:
  whisper:
    build: .
    ports:
      - "9000:9000"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    volumes:
      - ./data:/data
    restart: unless-stopped
```

### 5. 起動

```bash
docker compose up -d
```

## クライアント側セットアップ（macOS）

### whisper-remote 関数

```zsh
# ~/.config/zsh/functions/whisper-remote

#!/usr/bin/env zsh
# whisper-remote - リモートWhisper文字起こし

local input_file="$1"
local use_demucs=false

# オプション解析
while [[ $# -gt 0 ]]; do
    case "$1" in
        --demucs) use_demucs=true; shift ;;
        *) input_file="$1"; shift ;;
    esac
done

if [[ -z "$input_file" || ! -f "$input_file" ]]; then
    echo "Usage: whisper-remote [--demucs] <input_file>" >&2
    return 1
fi

local host="${WHISPER_HOST:-gpu-server.local}"
local port="${WHISPER_PORT:-9000}"
local basename="${input_file:r}"
local output_file="${basename}_wp.srt"

echo "Uploading to Whisper server..."
echo "  Host: ${host}:${port}"
echo "  File: ${input_file}"
echo "  Demucs: ${use_demucs}"

local demucs_param=""
[[ "$use_demucs" == true ]] && demucs_param="-F demucs=true"

if ! curl -s -X POST \
    -F "file=@${input_file}" \
    ${demucs_param} \
    "http://${host}:${port}/transcribe" \
    -o "$output_file"; then
    echo "Error: Whisper transcription failed" >&2
    return 1
fi

echo "Output: ${output_file}"
```

### 使用方法

```bash
# 基本的な使用
whisper-remote video.mp4

# Demucs音声分離付き（ボーカル抽出で精度向上）
whisper-remote --demucs video.mp4
```

## パフォーマンスの目安

| GPU | 1時間動画の処理時間 |
|-----|-------------------|
| RTX 3090 | 約10-15分 |
| RTX 4090 | 約5-10分 |
| A100 | 約3-5分 |

※ Demucs使用時は追加で5-10分

## トラブルシューティング

### GPU認識エラー

```bash
# GPU確認
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.1-base-ubuntu22.04 nvidia-smi
```

### メモリ不足

```bash
# モデルサイズを下げる
# server.py で "large-v3" → "medium" に変更
```

### タイムアウト

```bash
# gunicorn タイムアウトを延長
# Dockerfile: --timeout 7200
```

## 関連

- [my-setup.md](my-setup.md) - 全体構成
- [OpenAI Whisper](https://github.com/openai/whisper)
- [Demucs](https://github.com/facebookresearch/demucs)
