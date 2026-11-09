"""SQLite job state. One row per distinct audio (by SHA-256); one row per observed inbox path."""
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY,
  size INTEGER NOT NULL,
  mtime REAL NOT NULL,
  last_change REAL NOT NULL,
  handled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  sha256 TEXT UNIQUE NOT NULL,
  source_name TEXT NOT NULL,
  archive_path TEXT NOT NULL,
  duration_sec REAL,
  status TEXT NOT NULL,
  stage TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  warnings TEXT,
  output_path TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
"""

ACTIVE = ("queued", "failed_retryable")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def observe(con, path: str, size: int, mtime: float, now: float) -> sqlite3.Row:
    """Record the latest size/mtime of an inbox file; last_change moves only when they change."""
    row = con.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()
    if row is None:
        con.execute("INSERT INTO files(path,size,mtime,last_change) VALUES(?,?,?,?)", (path, size, mtime, now))
    elif row["size"] != size or row["mtime"] != mtime:
        con.execute("UPDATE files SET size=?, mtime=?, last_change=?, handled=0 WHERE path=?", (size, mtime, now, path))
    con.commit()
    return con.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()


def mark_handled(con, path: str) -> None:
    con.execute("UPDATE files SET handled=1 WHERE path=?", (path,))
    con.commit()


def job_by_sha(con, sha: str):
    return con.execute("SELECT * FROM jobs WHERE sha256=?", (sha,)).fetchone()


def add_job(con, job_id, sha, source_name, archive_path, duration, status, error=None):
    now = time.time()
    con.execute(
        "INSERT INTO jobs(job_id,sha256,source_name,archive_path,duration_sec,status,error,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (job_id, sha, source_name, archive_path, duration, status, error, now, now),
    )
    con.commit()


def update(con, job_id: str, **fields) -> None:
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    con.execute(f"UPDATE jobs SET {cols} WHERE job_id=?", (*fields.values(), job_id))
    con.commit()


def next_job(con, now: float, max_attempts: int, backoff: float):
    rows = con.execute(
        "SELECT * FROM jobs WHERE status IN ('queued','failed_retryable') AND attempts < ? ORDER BY created_at",
        (max_attempts,),
    ).fetchall()
    for r in rows:
        if r["status"] == "queued" or now - r["updated_at"] >= backoff * r["attempts"]:
            return r
    return None


def counts(con) -> dict:
    return {r["status"]: r["n"] for r in con.execute("SELECT status, COUNT(*) n FROM jobs GROUP BY status")}
