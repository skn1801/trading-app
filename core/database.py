"""
Local SQLite storage.

Everything lives in a single file under the user's home directory:
    ~/.trading_dashboard/app.db

Nothing here ever leaves the machine - there is no network call in this
module. Broker credentials are stored as opaque encrypted blobs (see
core/security.py); this module never sees plaintext secrets.
"""

import sqlite3
import datetime
from pathlib import Path
from contextlib import contextmanager

APP_DIR = Path.home() / ".trading_dashboard"
DB_PATH = APP_DIR / "app.db"


def _ensure_app_dir():
    APP_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    _ensure_app_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                kdf_salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS broker_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                broker TEXT NOT NULL,           -- 'angel_one' or 'kite'
                nickname TEXT NOT NULL,
                encrypted_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """
        )


def any_user_exists() -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None


def create_user(username: str, password_hash: str, kdf_salt: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, kdf_salt, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, kdf_salt, datetime.datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def get_user_by_username(username: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


def list_users():
    with get_conn() as conn:
        rows = conn.execute("SELECT id, username FROM users ORDER BY username").fetchall()
        return [dict(r) for r in rows]


# --- Broker accounts -------------------------------------------------------

def add_broker_account(user_id: int, broker: str, nickname: str, encrypted_payload: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO broker_accounts (user_id, broker, nickname, encrypted_payload, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, broker, nickname, encrypted_payload, datetime.datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def update_broker_account_payload(account_id: int, encrypted_payload: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE broker_accounts SET encrypted_payload = ? WHERE id = ?",
            (encrypted_payload, account_id),
        )


def rename_broker_account(account_id: int, nickname: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE broker_accounts SET nickname = ? WHERE id = ?",
            (nickname, account_id),
        )


def delete_broker_account(account_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM broker_accounts WHERE id = ?", (account_id,))


def list_broker_accounts(user_id: int, broker: str = None):
    with get_conn() as conn:
        if broker:
            rows = conn.execute(
                "SELECT * FROM broker_accounts WHERE user_id = ? AND broker = ? ORDER BY nickname",
                (user_id, broker),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM broker_accounts WHERE user_id = ? ORDER BY broker, nickname",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_broker_account(account_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM broker_accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row) if row else None
