"""SQLite のジョブキュー

ワーカーは1台（自宅の WSL）を想定しているので、外部のキューは持たない。
claim は UPDATE ... RETURNING 1文で行い、同時に2つのワーカーが走っても
同じジョブを取らないようにしておく。lease が切れた running は再び取れる
（WSL ごと落ちた・Windows Update で再起動した、など）。
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    owner        TEXT NOT NULL,
    status       TEXT NOT NULL,          -- uploading / queued / running / done / failed
    stage        TEXT NOT NULL DEFAULT '',
    meta         TEXT NOT NULL,          -- JSON（フォームの前提情報・ファイル名・サイズ）
    error        TEXT NOT NULL DEFAULT '',
    attempts     INTEGER NOT NULL DEFAULT 0,
    lease_until  REAL NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(owner, created_at);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
"""

MAX_ATTEMPTS = 3


class JobStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
        if r is None:
            return None
        d = dict(r)
        d["meta"] = json.loads(d["meta"])
        return d

    def create(self, owner: str, meta: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        job_id = uuid.uuid4().hex
        with self._conn() as c:
            c.execute(
                "INSERT INTO jobs (id, owner, status, meta, created_at, updated_at)"
                " VALUES (?, ?, 'uploading', ?, ?, ?)",
                (job_id, owner, json.dumps(meta, ensure_ascii=False), now, now))
        return self.get(job_id)  # type: ignore[return-value]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            return self._row(c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def list_for(self, owner: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM jobs WHERE owner = ? ORDER BY created_at DESC LIMIT ?",
                (owner, limit)).fetchall()
        return [self._row(r) for r in rows]  # type: ignore[misc]

    def update(self, job_id: str, **fields: Any) -> None:
        if "meta" in fields:
            fields["meta"] = json.dumps(fields["meta"], ensure_ascii=False)
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as c:
            c.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))

    def delete(self, job_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def claim(self, lease_seconds: float) -> dict[str, Any] | None:
        """queued、または lease 切れの running を1件取る（古い順）"""
        now = time.time()
        with self._conn() as c:
            r = c.execute(
                """
                UPDATE jobs SET status = 'running', attempts = attempts + 1,
                                lease_until = ?, updated_at = ?
                WHERE id = (
                    SELECT id FROM jobs
                    WHERE (status = 'queued' OR (status = 'running' AND lease_until < ?))
                      AND attempts < ?
                    ORDER BY created_at LIMIT 1)
                RETURNING *
                """,
                (now + lease_seconds, now, now, MAX_ATTEMPTS)).fetchone()
            job = self._row(r)
            # 試行回数を使い切って放置された running は failed に落とす
            c.execute(
                "UPDATE jobs SET status = 'failed', error = 'ワーカーが応答しなくなりました',"
                " updated_at = ? WHERE status = 'running' AND lease_until < ? AND attempts >= ?",
                (now, now, MAX_ATTEMPTS))
        return job

    def renew(self, job_id: str, lease_seconds: float) -> None:
        self.update(job_id, lease_until=time.time() + lease_seconds)
