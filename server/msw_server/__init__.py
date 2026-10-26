"""msw_server — media-scribe-workflow の Web 陶器（音声 → リハ記録 PDF）

配管（bin/ のツール群）はそのまま使い、ここではジョブ受付・認証・段階実行だけを持つ。

    app.py       FastAPI（Cloudflare Tunnel の内側、127.0.0.1 でだけ待つ）
    auth.py      Cloudflare Access の JWT 検証 ＋ 許可リスト
    db.py        SQLite のジョブキュー
    worker.py    ジョブを1件ずつ取り出して段階を回す常駐プロセス
    stages.py    normalize → transcribe → analyze → render
    analysis.py  SRT を章ごとに Claude で構造化（JSON）し、出典時刻を検証する
    tex.py       構造化 JSON → .tex（\\section{曲名} と \\ts{HH:MM:SS} を界面として守る）
"""

__version__ = "0.1.0"
