"""常駐ワーカー（systemd: msw-worker.service）

    python -m msw_server.worker            # 常駐
    python -m msw_server.worker --once     # 1件だけ処理して終わる（動作確認用）

GPU は1枚なので1件ずつ順に処理する。進捗を書くたびに lease を延ばし、
lease が切れたジョブ（WSL ごと落ちた等）は次の claim で取り直される。
"""
from __future__ import annotations

import argparse
import logging
import signal
import threading
import time
import traceback

from . import stages
from .config import get_settings
from .db import JobStore

LEASE_SECONDS = 30 * 60
log = logging.getLogger("msw.worker")


def process(store: JobStore, job: dict, cfg) -> None:
    job_id = job["id"]
    d = cfg.jobs_dir / job_id

    def progress(msg: str) -> None:
        log.info("%s %s", job_id[:8], msg)
        store.update(job_id, stage=msg, lease_until=time.time() + LEASE_SECONDS)

    # 文字起こしは1段で数十分かかり進捗が出ないので、別スレッドで lease を延ばし続ける
    done = threading.Event()

    def heartbeat() -> None:
        while not done.wait(LEASE_SECONDS / 3):
            store.renew(job_id, LEASE_SECONDS)

    threading.Thread(target=heartbeat, daemon=True).start()
    try:
        stages.run_all(d, cfg, job["meta"], progress)
    except Exception as e:  # noqa: BLE001 - 失敗はジョブに記録して次へ進む
        log.error("%s failed: %s\n%s", job_id[:8], e, traceback.format_exc())
        store.update(job_id, status="failed", stage="失敗", error=str(e)[:4000])
        return
    finally:
        done.set()
    store.update(job_id, status="done", stage="完了", error="")


def main() -> int:
    ap = argparse.ArgumentParser(prog="msw-worker")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = get_settings()
    store = JobStore(cfg.db_path)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True  # 処理中のジョブは最後まで回す（中断すると lease 切れ待ちになる）

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    while not stopping:
        job = store.claim(LEASE_SECONDS)
        if job is None:
            if args.once:
                return 0
            time.sleep(cfg.poll_seconds)
            continue
        process(store, job, cfg)
        if args.once:
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
