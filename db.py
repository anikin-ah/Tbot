"""
db.py — Turso (libSQL) storage layer for the bot's file index.

Replaces the hardcoded FILE_INDEX dict with rows in a `files` table:

    key      TEXT PRIMARY KEY   -- the short name used in /get <key> and callback_data
    label    TEXT               -- display label shown to users (with emoji etc.)
    file_id  TEXT               -- Telegram file_id to resend the document

Requires two env vars (from your Turso database):
    TURSO_DATABASE_URL   e.g. "libsql://your-db-name-yourorg.turso.io"
    TURSO_AUTH_TOKEN     the auth token for that database

Setup (one-time, using the Turso CLI):
    turso db create my-bot-files
    turso db show my-bot-files --url
    turso db tokens create my-bot-files
"""

import os
import libsql_client

TURSO_DATABASE_URL = os.environ["TURSO_DATABASE_URL"]
TURSO_AUTH_TOKEN = os.environ["TURSO_AUTH_TOKEN"]

_client = None


def get_client():
    """Lazily create (and reuse) the sync libSQL client."""
    global _client
    if _client is None:
        _client = libsql_client.create_client_sync(
            url=TURSO_DATABASE_URL,
            auth_token=TURSO_AUTH_TOKEN,
        )
    return _client


def init_db():
    """Create the files table if it doesn't exist yet. Call once at startup."""
    get_client().execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            file_id TEXT NOT NULL
        )
        """
    )


def get_file(key):
    """Return {"label": ..., "file_id": ...} for a key, or None if missing."""
    rs = get_client().execute(
        "SELECT label, file_id FROM files WHERE key = ?", [key]
    )
    if not rs.rows:
        return None
    row = rs.rows[0]
    return {"label": row[0], "file_id": row[1]}


def list_files():
    """Return {key: {"label": ..., "file_id": ...}, ...} for every stored file,
    ordered by insertion (rowid) so button order stays stable."""
    rs = get_client().execute(
        "SELECT key, label, file_id FROM files ORDER BY rowid"
    )
    return {
        row[0]: {"label": row[1], "file_id": row[2]}
        for row in rs.rows
    }


def add_file(key, label, file_id):
    """Insert or update a file entry. Returns True on success."""
    get_client().execute(
        """
        INSERT INTO files (key, label, file_id) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET label = excluded.label, file_id = excluded.file_id
        """,
        [key, label, file_id],
    )
    return True


def remove_file(key):
    """Delete a file entry. Returns True if a row was actually deleted."""
    rs = get_client().execute("DELETE FROM files WHERE key = ?", [key])
    return rs.rows_affected > 0