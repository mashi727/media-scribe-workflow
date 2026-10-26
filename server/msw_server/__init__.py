"""msw_server — media-scribe-workflow の Web 陶器（音声 → リハ記録 PDF）

配管（bin/ のツール群）はそのまま使い、ここではジョブ受付・認証・段階実行だけを持つ。

    app.py       FastAPI（Cloudflare Tunnel の内側、127.0.0.1 でだけ待つ）
    auth.py      Cloudflare Access の JWT 検証 ＋ 許可リスト
    db.py        SQLite のジョブキュー
    worker.py    ジョブを1件ずつ取り出して段階を回す常駐プロセス
    stages.py    normalize → transcribe → analyze → render
    analysis.py  文字起こしを章ごとの記録 JSON にする（既定は AI なしの発言録・差し替え可）
    tex.py       記録 JSON → .tex（\\section{曲名} と \\ts{HH:MM:SS} を界面として守る）
"""

__version__ = "0.1.0"
