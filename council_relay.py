#!/usr/bin/env python3
"""NBC AI Agent Council — shared bot-to-bot relay.

Telegram never delivers one bot's messages to another bot, so council bots
cannot coordinate over Telegram alone. This module is a tiny shared mailbox
(SQLite) that any council bot can import to send/receive *inter-bot* asks.

Contract (every council bot follows the same 3 steps):
  1. init_db()                          -> once at startup
  2. post_message(sender, recipient,    -> when bot A wants bot B to act
                  chat_id, text, depth)
  3. claim_unread(recipient)            -> poll loop; returns asks addressed
                                           to this bot, atomically marked read

Identities are Telegram usernames WITHOUT the leading '@' (e.g. 'rey_tran_bot').
The DB lives at COUNCIL_RELAY_DB (env) so every bot process points at the SAME
file. Default: ~/.nbc_council/relay.db — all council bots on one host share it.

`depth` is a hop counter to stop infinite bot-to-bot loops: a bot acting on a
relayed ask must pass depth+1 when it relays onward, and stop at COUNCIL_MAX_HOPS.
"""
import os
import sqlite3
import datetime as dt
from pathlib import Path

DEFAULT_DB = Path.home() / ".nbc_council" / "relay.db"


def db_path() -> Path:
    return Path(os.environ.get("COUNCIL_RELAY_DB", str(DEFAULT_DB)))


def max_hops() -> int:
    try:
        return int(os.environ.get("COUNCIL_MAX_HOPS", "3"))
    except ValueError:
        return 3


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # WAL + busy timeout so multiple bot processes can read/write concurrently.
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db() -> None:
    """Create the relay table if it does not exist. Safe to call repeatedly."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT    NOT NULL,
                sender     TEXT    NOT NULL,
                recipient  TEXT    NOT NULL,
                chat_id    INTEGER,
                text       TEXT    NOT NULL,
                depth      INTEGER NOT NULL DEFAULT 0,
                status     TEXT    NOT NULL DEFAULT 'unread'
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recipient_status "
            "ON messages (recipient, status)"
        )


def post_message(sender: str, recipient: str, chat_id, text: str, depth: int = 0) -> int:
    """Queue an inter-bot ask. Returns the new message id."""
    sender = sender.lstrip("@").lower()
    recipient = recipient.lstrip("@").lower()
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (ts, sender, recipient, chat_id, text, depth, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'unread')",
            (ts, sender, recipient, chat_id, text, depth),
        )
        return cur.lastrowid


def claim_unread(recipient: str, limit: int = 10):
    """Atomically fetch + mark-as-read all unread asks for `recipient`.

    Returns a list of dicts. Because each recipient bot is the sole claimer of
    its own rows, this is race-free across bot processes.
    """
    recipient = recipient.lstrip("@").lower()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT * FROM messages WHERE recipient = ? AND status = 'unread' "
            "ORDER BY id ASC LIMIT ?",
            (recipient, limit),
        ).fetchall()
        if rows:
            ids = [r["id"] for r in rows]
            conn.execute(
                f"UPDATE messages SET status = 'read' "
                f"WHERE id IN ({','.join('?' for _ in ids)})",
                ids,
            )
        conn.commit()
        return [dict(r) for r in rows]


if __name__ == "__main__":
    # Tiny smoke test / CLI inspector.
    init_db()
    print(f"Relay DB: {db_path()}  (max hops: {max_hops()})")
    with _connect() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
        unread = c.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE status='unread'"
        ).fetchone()["n"]
    print(f"Total messages: {n}  |  Unread: {unread}")
