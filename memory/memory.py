from __future__ import annotations

import sqlite3
from pathlib import Path


class MemoryError(RuntimeError):
    pass


class Memory:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.conn = sqlite3.connect(self.path)
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, "
                "content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_id ON messages(id)")
            self.conn.commit()
        except sqlite3.Error as exc:
            raise MemoryError(f"could not open memory database: {exc}") from exc

    def save_message(self, role: str, content: str) -> None:
        try:
            self.conn.execute("INSERT INTO messages (role, content) VALUES (?, ?)", (role, str(content)))
            self.conn.commit()
        except sqlite3.Error as exc:
            raise MemoryError(f"could not save memory: {exc}") from exc

    def recent_messages(self, limit: int = 20) -> list[dict[str, str]]:
        limit = max(1, min(int(limit), 1000))
        try:
            rows = self.conn.execute(
                "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        except sqlite3.Error as exc:
            raise MemoryError(f"could not read memory: {exc}") from exc
        rows.reverse()
        return [{"role": role, "content": content} for role, content in rows]

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass
