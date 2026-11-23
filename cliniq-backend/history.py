"""Chat history stored in SQLite, so it survives backend restarts.

The database file is HISTORY_DB (default ./chat_history.db). On Render, point it at the
persistent disk, e.g. HISTORY_DB=/data/chat_history.db."""

import json
import os
import sqlite3
import threading
import time
from typing import List, Optional


class ChatHistoryStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.getenv("HISTORY_DB", "./chat_history.db")
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_messages_doc ON messages (doc_id, id)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def add_exchange(self, doc_id: str, question: str, answer: str, citations: list):
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._lock, self._connect() as db:
            db.executemany(
                "INSERT INTO messages (doc_id, role, content, citations, created_at) VALUES (?, ?, ?, ?, ?)",
                [
                    (doc_id, "user", question, None, now),
                    (doc_id, "assistant", answer, json.dumps(citations), now),
                ],
            )

    def get(self, doc_id: str) -> List[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT role, content, citations FROM messages WHERE doc_id = ? ORDER BY id", (doc_id,)
            ).fetchall()
        return [
            {"role": role, "content": content, "citations": json.loads(citations) if citations else None}
            for role, content, citations in rows
        ]

    def counts(self) -> dict:
        """Number of questions asked per document."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT doc_id, COUNT(*) FROM messages WHERE role = 'user' GROUP BY doc_id"
            ).fetchall()
        return dict(rows)

    def delete(self, doc_id: str):
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM messages WHERE doc_id = ?", (doc_id,))
