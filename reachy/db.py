"""SQLite storage with versioned migrations.

SQLite is used deliberately: the deployment target is a single VPS or laptop,
the dataset fits comfortably in SQLite, WAL mode supports a worker plus CLI
reads, and backup/restore is a single file operation.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path, timeout: float = 30.0):
        self.path = str(path)
        self.timeout = timeout
        self._local = threading.local()
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ conn
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=self.timeout,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        if self.path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -------------------------------------------------------------- queries
    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def executescript(self, script: str) -> None:
        self.conn.executescript(script)

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params).fetchall())

    def insert(self, sql: str, params: Sequence[Any] = ()) -> int:
        cur = self.conn.execute(sql, params)
        return int(cur.lastrowid)

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        try:
            yield conn
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")

    # ----------------------------------------------------------- migrations
    def migrate(self) -> list[int]:
        migrations_dir = Path(__file__).resolve().parent / "migrations"
        applied: list[int] = []
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version INTEGER PRIMARY KEY,
                   applied_at TEXT NOT NULL
               )"""
        )
        existing = {
            int(row["version"])
            for row in self.conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for path in sorted(migrations_dir.glob("*.sql")):
            try:
                version = int(path.name.split("_", 1)[0])
            except ValueError:
                continue
            if version in existing:
                continue
            script = path.read_text(encoding="utf-8")
            self.conn.executescript(script)
            self.conn.execute(
                "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, utcnow()),
            )
            applied.append(version)
        return applied

    def schema_version(self) -> int:
        row = self.fetchone("SELECT MAX(version) AS v FROM schema_migrations")
        return int(row["v"]) if row and row["v"] is not None else 0

    # --------------------------------------------------------------- utility
    def audit(
        self,
        actor: str,
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str | int] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        import json

        self.execute(
            """INSERT INTO audit_log(actor, action, entity_type, entity_id, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                actor,
                action,
                entity_type,
                str(entity_id) if entity_id is not None else None,
                json.dumps(detail, sort_keys=True) if detail else None,
                utcnow(),
            ),
        )

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, value, utcnow()),
        )

    def backup(self, destination: str | Path) -> Path:
        destination = Path(destination).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(destination) as dest:
            self.conn.backup(dest)
        try:
            os.chmod(destination, 0o600)
        except OSError:
            pass
        return destination

    @staticmethod
    def restore(source: str | Path, destination: str | Path) -> Path:
        """Restore a database file. The caller must stop the worker first."""
        import shutil

        src = Path(source).expanduser()
        dst = Path(destination).expanduser()
        if not src.exists():
            raise FileNotFoundError(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        try:
            os.chmod(dst, 0o600)
        except OSError:
            pass
        return dst

    def reset_interrupted_sends(self, actor: str = "system") -> int:
        """Move stale SENDING rows to UNCERTAIN after a crash.

        They are never blindly re-sent; reconciliation decides whether the
        provider accepted them.
        """
        rows = self.fetchall("SELECT id FROM messages WHERE state = 'SENDING'")
        if not rows:
            return 0
        with self.transaction(immediate=True) as conn:
            for row in rows:
                message_id = row["id"]
                conn.execute(
                    """UPDATE messages SET state='UNCERTAIN', last_error=?, updated_at=?
                       WHERE id=? AND state='SENDING'""",
                    ("Worker stopped after submission attempt", utcnow(), message_id),
                )
                conn.execute(
                    """INSERT INTO message_events(message_id, event_type, detail_json, created_at)
                       VALUES (?, 'RECOVERY_UNCERTAIN', ?, ?)""",
                    (message_id, '{"reason":"process restarted during send"}', utcnow()),
                )
        self.audit(actor, "recovery.reset_interrupted", "messages", ",".join(str(r["id"]) for r in rows))
        return len(rows)
