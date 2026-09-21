"""Tiny SQLite storage for shared files (Telegram file_ids)."""
import os
import secrets
import sqlite3
import threading


class Database:
    def __init__(self, path: str):
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    code      TEXT    NOT NULL,
                    position  INTEGER NOT NULL,
                    file_id   TEXT    NOT NULL,
                    file_type TEXT    NOT NULL,
                    caption   TEXT,
                    PRIMARY KEY (code, position)
                )
                """
            )
            self._conn.commit()

    def add_files(self, items):
        """Store a list of (file_type, file_id, caption) under one share code."""
        with self._lock:
            while True:
                code = secrets.token_urlsafe(9)  # 12 chars, safe for t.me links
                row = self._conn.execute(
                    "SELECT 1 FROM files WHERE code = ? LIMIT 1", (code,)
                ).fetchone()
                if row is None:
                    break
            self._conn.executemany(
                "INSERT INTO files (code, position, file_id, file_type, caption) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (code, i, file_id, file_type, caption)
                    for i, (file_type, file_id, caption) in enumerate(items)
                ],
            )
            self._conn.commit()
        return code

    def get_files(self, code: str):
        """Return a list of (file_type, file_id, caption) for a share code."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT file_type, file_id, caption FROM files "
                "WHERE code = ? ORDER BY position",
                (code,),
            ).fetchall()
        return rows

    def close(self):
        with self._lock:
            self._conn.close()
