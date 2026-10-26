# msw_server — 音声 → リハ記録 PDF の Web 陶器

`differance-lab.tokyo` の固定ページから音声を受け取り、自宅 WSL（Ubuntu）で
文字起こし → 構造化（Claude）→ LuaLaTeX 組版までを行う。配管（`bin/`）はそのまま使う。

```
[ブラウザ] differance-lab.tokyo/msw/ （WordPress dlab: page-msw.php + msw.js）
     │  fetch(credentials: 'include')
     ▼
[Cloudflare Access]  Google ログイン・許可メールのみ通す（CORS もここ）
     │
[Cloudflare Tunnel]  外向き接続のみ（自宅のポート開放なし）
     ▼
[WSL Ubuntu]
  cloudflared ──▶ msw-api (uvicorn, 127.0.0.1:8787) ──▶ SQLite キュー
                                                         │
                  msw-worker ◀───────────────────────────┘
                    normalize   ffmpeg → 片ch 16kHz FLAC
                    transcribe  bin/advanced/audio-transcribe（GPU）
                    analyze     章ごとに Claude → report.json（出典時刻を検証）
                    render      report.json → report.tex → lualatex → report.pdf
```

設計上の決めごと:

- **API は 127.0.0.1 でだけ待つ。** 外からは Tunnel 経由でしか届かない。さらにアプリ側でも Access の JWT（署名・aud・iss）と許可リストを検証する（多層防御・許可リストが空なら全拒否）。
- **アップロードは 32MB ずつ**、offset 付き PUT で送る。Cloudflare のリクエスト本体上限（Free/Pro は 100MB）を避けるためで、途中で切れても受信済みの位置から再開できる。
- **LLM には TeX を書かせない。** スキーマ固定の JSON を返させ、`tex.py` がエスケープしてから組む。`\section{曲名}` と `\ts{HH:MM:SS}` は下流（`tex-link-timestamps`・ダッシュボードの `build_<slug>.py`）との界面なので変えない。
- **出典時刻は機械で検証する。** 区間外の時刻や、近くに発話の無い時刻は PDF 上で「要確認」と表示する。
- **各段は冪等。** 出力ファイルがあれば飛ばすので、WSL が落ちても次の claim で続きから処理する。
- 原本音声は処理後に削除する（`MSW_DELETE_INPUT=0` で残せる）。一次資料として残るのは `transcript.{srt,words.json,meta.json}` と成果物。

## セットアップ

### 0. 前提

- `differance-lab.tokyo` の DNS が Cloudflare で管理されていること（ネームサーバを Cloudflare に向ける）。WordPress の A レコードはそのまま残してよい。
- WSL 側: NVIDIA ドライバ（Windows 側のみ）、`ffmpeg`、TeX Live（LuaLaTeX と `luatexja`）、Noto Serif CJK JP。

### 1. WSL（Ubuntu）

```bash
sudo cp server/deploy/wsl.conf /etc/wsl.conf      # systemd を有効化 → Windows で wsl --shutdown
cd ~/media-scribe-workflow
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[server]' stable-ts faster-whisper

sudo mkdir -p /etc/msw && sudo cp server/deploy/msw.env.example /etc/msw/msw.env
sudo chmod 600 /etc/msw/msw.env && sudoedit /etc/msw/msw.env   # 値を埋める（下の AUD など）

# ユニット内のユーザー名（mashi）とパスを実環境に合わせてから
sudo cp server/deploy/msw-api.service server/deploy/msw-worker.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now msw-api msw-worker

# 初回の組版はフォントキャッシュ生成で約1分かかる。先に1回温めておく
luaotfload-tool --update
```

Windows 側では、`.wslconfig` に `vmIdleTimeout=-1` を設定し、タスクスケジューラのログオン時タスクで `wsl.exe -d Ubuntu --exec /bin/true` を実行する（`deploy/wsl.conf` に記載）。スリープも無効にしておく。

### 2. Cloudflare Tunnel

```bash
# https://pkg.cloudflare.com/ から cloudflared を入れてから
cloudflared tunnel login
cloudflared tunnel create msw
cloudflared tunnel route dns msw api.differance-lab.tokyo
sudo mkdir -p /etc/cloudflared && sudo cp server/deploy/cloudflared-config.yml /etc/cloudflared/config.yml
sudoedit /etc/cloudflared/config.yml          # TUNNEL-UUID と credentials-file を埋める
sudo cloudflared service install
```

### 3. Cloudflare Access（Google ログイン）

Zero Trust ダッシュボードで設定する。

1. **Settings → Authentication → Login methods** に Google を追加する（Google Cloud Console で OAuth クライアントを作り、リダイレクト URI に `https://<team>.cloudflareaccess.com/cdn-cgi/access/callback` を登録）。
2. **Access → Applications → Add → Self-hosted** でアプリを作る。
   - Domain: `api.differance-lab.tokyo`
   - Policy: Allow ／ Include: Emails（利用者のアドレス）。Login method は Google のみ
   - **Settings → CORS**:
     - Access-Control-Allow-Origin: `https://differance-lab.tokyo`
     - Allow credentials: ON
     - Allowed methods: GET, POST, PUT, DELETE
     - Allowed headers: `Content-Type`
     - **Bypass OPTIONS requests to origin: ON**（プリフライトは FastAPI 側の CORS で返す）
   - Cookie settings: SameSite は Lax のまま（`api.` と本体は同一サイト）
3. Overview の **Application Audience (AUD) Tag** を `/etc/msw/msw.env` の `MSW_CF_AUD` に設定し、`sudo systemctl restart msw-api` する。

### 4. WordPress（dlab テーマ）

- `server/wordpress/page-msw.php` をテーマ直下に、`server/wordpress/msw.js` を `assets/js/msw.js` に置く。
- 固定ページ（例: `/msw/`）を作り、テンプレート「リハ記録 PDF 作成」を選ぶ。

ページには秘密情報を置かない。初回アクセス時は「Google でログイン」から API の `/login` へ遷移し、Access で認証してからページへ戻る。

## 動作確認

```bash
curl -s http://127.0.0.1:8787/api/health                  # WSL 内から
python -m msw_server.worker --once                         # 1件だけ処理（ワーカーを止めた状態で）
journalctl -u msw-worker -f                                # 進捗ログ
python -m pytest tests/test_server.py                      # 外部に触れないテスト
```

Access を通さずに手元で UI を試す場合は、`MSW_DEV_EMAIL=you@example.com` を設定し、`MSW_CF_AUD` を空にして uvicorn を起動する。この変数は認証を飛ばすが、`MSW_CF_AUD` が設定されている（＝本番の）ときは無視される。

## 未実装（次の一手）

- 構造化 JSON の編集画面（PDF 前の人手校正。原本 SRT/words.json には書き戻さない）
- 見積もり表示（尺 × ASR ＋ LLM トークン）と、利用者ごとのクォータ
- 完了通知（メール等）
- 語彙ファイル（`--terms`）を楽団ごとに切り替える
