"""SQLite storage layer."""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from . import constants as C

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS package_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dsm_uid TEXT NOT NULL UNIQUE,
  username TEXT NOT NULL,
  pin_hash BLOB,
  pin_salt BLOB,
  pin_iters INTEGER,
  pin_set_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id INTEGER NOT NULL REFERENCES users(id),
  issuer TEXT NOT NULL,
  account TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  algorithm TEXT NOT NULL,
  digits INTEGER NOT NULL,
  period INTEGER NOT NULL,
  secret_ct BLOB NOT NULL,
  secret_nonce BLOB NOT NULL,
  secret_tag BLOB NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS shares (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  grantee_id INTEGER NOT NULL REFERENCES users(id),
  shared_at INTEGER NOT NULL,
  UNIQUE(entry_id, grantee_id)
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  token_hash BLOB NOT NULL UNIQUE,
  dsm_sid TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL,
  absolute_expires_at INTEGER NOT NULL,
  idle_expires_at INTEGER NOT NULL,
  revoked_at INTEGER
);

CREATE TABLE IF NOT EXISTS pin_attempts (
  user_id INTEGER PRIMARY KEY REFERENCES users(id),
  failures INTEGER NOT NULL DEFAULT 0,
  cooldown_until INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS import_previews (
  token_hash BLOB PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  payload_ct BLOB NOT NULL,
  payload_nonce BLOB NOT NULL,
  payload_tag BLOB NOT NULL,
  digest TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entries_owner ON entries(owner_id);
CREATE INDEX IF NOT EXISTS idx_entries_search ON entries(owner_id, issuer, account, label);
CREATE INDEX IF NOT EXISTS idx_shares_grantee ON shares(grantee_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            os.chmod(self.path, 0o660)
        except OSError:
            pass
        return conn

    @contextmanager
    def txn(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(SCHEMA_SQL)
            row = conn.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (C.SCHEMA_VERSION, int(time.time())),
                )
        finally:
            conn.close()

    def backup_to(self, dest_path: str) -> None:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with self.connect() as src:
            dest = sqlite3.connect(dest_path)
            try:
                src.backup(dest)
            finally:
                dest.close()


def now() -> int:
    return int(time.time())


def get_user_by_uid(conn: sqlite3.Connection, dsm_uid: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM users WHERE dsm_uid = ?", (dsm_uid,)).fetchone()


def get_user_by_username(conn: sqlite3.Connection, username: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
        (username,),
    ).fetchone()


def ensure_user(conn: sqlite3.Connection, dsm_uid: str, username: str) -> sqlite3.Row:
    row = get_user_by_uid(conn, dsm_uid)
    ts = now()
    if row is None:
        conn.execute(
            "INSERT INTO users(dsm_uid, username, created_at, updated_at, status) VALUES (?, ?, ?, ?, 'active')",
            (dsm_uid, username, ts, ts),
        )
        return get_user_by_uid(conn, dsm_uid)
    if row["username"] != username:
        conn.execute(
            "UPDATE users SET username = ?, updated_at = ? WHERE id = ?",
            (username, ts, row["id"]),
        )
        return get_user_by_uid(conn, dsm_uid)
    return row