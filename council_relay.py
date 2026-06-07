#!/usr/bin/env python3
"""NBC AI Agent Council — shared bot-to-bot relay (direct + open broadcast).

Telegram never delivers one bot's messages to another bot, so council bots
cannot coordinate over Telegram alone. This module is a tiny shared mailbox
(SQLite) that any council bot can import to talk to each other.

Two modes:
  • DIRECT  — post_message(to=bob) ... claim_unread('bob')  (point-to-point ask)
  • OPEN    — post_broadcast() ... fetch_new_broadcasts('bob')  (group discussion:
              EVERY bot sees EVERY broadcast it didn't send, grouped by thread_id)

Contract (every council bot follows the same calls against the SAME db file):
  init_db()                               # once at startup
  post_message(sender, to, chat, text)    # direct ask
  claim_unread(me)                        # poll: my direct asks (atomic)
  post_broadcast(sender, chat, text, ...) # open the floor / contribute to a thread
  fetch_new_broadcasts(me)                # poll: new open messages I haven't seen
  thread_recent / thread_count / thread_sender_count   # discussion context + caps

Identities are Telegram usernames WITHOUT the leading '@' (e.g. 'rey_tran_bot'),
or 'human:<id>' for a person who opened a topic.

The DB lives at COUNCIL_RELAY_DB (env) so every bot process points at the SAME
file. Default: ~/.nbc_council/relay.db.

`depth` is a hop counter to stop infinite bot-to-bot loops: a bot contributing to
a relayed/broadcast message must pass depth+1; stop at COUNCIL_MAX_HOPS.
"""
import os
import uuid
import sqlite3
import datetime as dt
from pathlib import Path

DEFAULT_DB = Path.home() / ".nbc_council" / "relay.db"
BROADCAST = "*"  # recipient sentinel for open-discussion messages


def db_path() -> Path:
    return Path(os.environ.get("COUNCIL_RELAY_DB", str(DEFAULT_DB)))


def max_hops() -> int:
    try:
        return int(os.environ.get("COUNCIL_MAX_HOPS", "4"))
    except ValueError:
        return 4


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _norm(name: str) -> str:
    return (name or "").lstrip("@").lower()


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db() -> None:
    """Create/upgrade the relay schema. Safe to call repeatedly."""
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
                thread_id  TEXT,
                status     TEXT    NOT NULL DEFAULT 'unread'
            )
            """
        )
        # Migrate older DBs that predate thread_id.
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(messages)")]
        if "thread_id" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN thread_id TEXT")
        # Per-bot read cursor for broadcast fan-out.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cursors ("
            "bot TEXT PRIMARY KEY, last_id INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recipient_status "
            "ON messages (recipient, status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_thread ON messages (thread_id)"
        )


# ── Direct (point-to-point) ───────────────────────────────────────────────────
def post_message(sender: str, recipient: str, chat_id, text: str, depth: int = 0) -> int:
    """Queue a direct inter-bot ask. Returns the new message id."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (ts, sender, recipient, chat_id, text, depth, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'unread')",
            (_now(), _norm(sender), _norm(recipient), chat_id, text, depth),
        )
        return cur.lastrowid


def claim_unread(recipient: str, limit: int = 10):
    """Atomically fetch + mark-read all unread DIRECT asks for `recipient`."""
    recipient = _norm(recipient)
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
                f"UPDATE messages SET status='read' "
                f"WHERE id IN ({','.join('?' for _ in ids)})",
                ids,
            )
        conn.commit()
        return [dict(r) for r in rows]


# ── Open broadcast (group discussion) ─────────────────────────────────────────
def post_broadcast(sender: str, chat_id, text: str, depth: int = 0, thread_id: str = None):
    """Open the floor (or contribute) to an open council thread.

    Returns (message_id, thread_id). A new thread_id is minted if none given.
    """
    thread_id = thread_id or uuid.uuid4().hex
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (ts, sender, recipient, chat_id, text, depth, thread_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'open')",
            (_now(), _norm(sender), BROADCAST, chat_id, text, depth, thread_id),
        )
        return cur.lastrowid, thread_id


def fetch_new_broadcasts(bot_name: str, limit: int = 20):
    """Return broadcast messages this bot hasn't seen yet (excluding its own).

    Advances the bot's cursor past everything scanned so each broadcast is
    delivered to each bot exactly once.
    """
    bot = _norm(bot_name)
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT last_id FROM cursors WHERE bot = ?", (bot,)
        ).fetchone()
        last = row["last_id"] if row else 0
        rows = conn.execute(
            "SELECT * FROM messages WHERE recipient = ? AND id > ? "
            "ORDER BY id ASC LIMIT ?",
            (BROADCAST, last, limit),
        ).fetchall()
        if rows:
            newlast = rows[-1]["id"]
            conn.execute(
                "INSERT INTO cursors (bot, last_id) VALUES (?, ?) "
                "ON CONFLICT(bot) DO UPDATE SET last_id = excluded.last_id",
                (bot, newlast),
            )
        conn.commit()
        # Deliver only what this bot did not author.
        return [dict(r) for r in rows if r["sender"] != bot]


# ── Thread helpers (discussion context + loop caps) ───────────────────────────
def thread_recent(thread_id: str, limit: int = 12):
    """Most-recent messages in a thread, oldest-first, for LLM context."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT sender, text, ts FROM messages WHERE thread_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (thread_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def thread_count(thread_id: str) -> int:
    with _connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE thread_id = ?", (thread_id,)
        ).fetchone()["n"]


def thread_sender_count(thread_id: str, sender: str) -> int:
    with _connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE thread_id = ? AND sender = ?",
            (thread_id, _norm(sender)),
        ).fetchone()["n"]


if __name__ == "__main__":
    init_db()
    print(f"Relay DB: {db_path()}  (max hops: {max_hops()})")
    with _connect() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
        unread = c.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE status='unread'"
        ).fetchone()["n"]
        threads = c.execute(
            "SELECT COUNT(DISTINCT thread_id) AS n FROM messages WHERE thread_id IS NOT NULL"
        ).fetchone()["n"]
    print(f"Messages: {n} | Unread direct: {unread} | Open threads: {threads}")
