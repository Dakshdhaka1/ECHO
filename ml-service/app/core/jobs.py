"""Retraining job state, shared by all uvicorn worker processes (SQLite next to the monitoring log)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path


class RetrainJobStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS retrain_jobs (id TEXT PRIMARY KEY, model TEXT, status TEXT, "
                        "created_at REAL, doc TEXT)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10, isolation_level=None)

    def create(self, model: str, promote: bool) -> dict | None:
        """Atomically create a QUEUED job; None if this model already has an active job (in any process)."""
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            active = con.execute("SELECT 1 FROM retrain_jobs WHERE model = ? AND status IN ('QUEUED', 'RUNNING')",
                                 (model,)).fetchone()
            if active:
                con.execute("ROLLBACK")
                return None
            job = {"id": uuid.uuid4().hex[:12], "model": model, "status": "QUEUED", "promote": promote,
                   "created_at": time.time()}
            con.execute("INSERT INTO retrain_jobs VALUES (?, ?, ?, ?, ?)",
                        (job["id"], model, "QUEUED", job["created_at"], json.dumps(job)))
            con.execute("COMMIT")
            return job
        finally:
            con.close()

    def update(self, job_id: str, **fields) -> None:
        with self._connect() as con:
            row = con.execute("SELECT doc FROM retrain_jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return
            doc = {**json.loads(row[0]), **fields}
            con.execute("UPDATE retrain_jobs SET status = ?, doc = ? WHERE id = ?", (doc["status"], json.dumps(doc), job_id))

    def recent(self, limit: int = 50) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("SELECT doc FROM retrain_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]

    def fail_interrupted(self) -> None:
        """Jobs left QUEUED/RUNNING by a restarted process can never finish."""
        with self._connect() as con:
            for (job_id,) in con.execute("SELECT id FROM retrain_jobs WHERE status IN ('QUEUED', 'RUNNING')").fetchall():
                self.update(job_id, status="FAILED", log_tail="interrupted by a service restart")
