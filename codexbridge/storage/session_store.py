from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from codexbridge.models import ConversationMessage, SessionRecord


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


class SessionStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL;")
            self._connection.execute("PRAGMA foreign_keys=ON;")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    chat_id INTEGER PRIMARY KEY,
                    telegram_user_id INTEGER NOT NULL,
                    project_path TEXT NOT NULL,
                    session_key TEXT NOT NULL,
                    codex_thread_id TEXT,
                    task_status TEXT NOT NULL DEFAULT 'idle',
                    last_error TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "codex_thread_id" not in columns:
                self._connection.execute("ALTER TABLE sessions ADD COLUMN codex_thread_id TEXT")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES sessions(chat_id) ON DELETE CASCADE
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_chat_id_id
                ON messages(chat_id, id)
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def create_or_get_session(self, chat_id: int, telegram_user_id: int, project_path: Path) -> SessionRecord:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if row:
                return self._row_to_session(row)
            session = SessionRecord(
                chat_id=chat_id,
                telegram_user_id=telegram_user_id,
                project_path=Path(project_path),
                session_key=str(uuid.uuid4()),
                codex_thread_id=None,
            )
            self._connection.execute(
                """
                INSERT INTO sessions (chat_id, telegram_user_id, project_path, session_key, codex_thread_id, task_status, last_error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.chat_id,
                    session.telegram_user_id,
                    str(session.project_path),
                    session.session_key,
                    session.codex_thread_id,
                    session.task_status,
                    session.last_error,
                    session.updated_at.isoformat(),
                ),
            )
            return session

    def get_session(self, chat_id: int) -> SessionRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def set_status(self, chat_id: int, status: str, last_error: str | None = None) -> SessionRecord:
        updated_at = _utc_now_iso()
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE sessions
                SET task_status = ?, last_error = ?, updated_at = ?
                WHERE chat_id = ?
                """,
                (status, last_error, updated_at, chat_id),
            )
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Session not found for chat_id={chat_id}")
        return self._row_to_session(row)

    def set_project(self, chat_id: int, project_path: Path) -> SessionRecord:
        updated_at = _utc_now_iso()
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE sessions
                SET project_path = ?, codex_thread_id = NULL, updated_at = ?
                WHERE chat_id = ?
                """,
                (str(project_path), updated_at, chat_id),
            )
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Session not found for chat_id={chat_id}")
        return self._row_to_session(row)

    def set_codex_thread_id(self, chat_id: int, codex_thread_id: str | None) -> SessionRecord:
        updated_at = _utc_now_iso()
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE sessions
                SET codex_thread_id = ?, updated_at = ?
                WHERE chat_id = ?
                """,
                (codex_thread_id, updated_at, chat_id),
            )
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Session not found for chat_id={chat_id}")
        return self._row_to_session(row)

    def reset_session(self, chat_id: int, telegram_user_id: int, project_path: Path) -> SessionRecord:
        updated_at = _utc_now_iso()
        session_key = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            self._connection.execute(
                """
                INSERT INTO sessions (chat_id, telegram_user_id, project_path, session_key, codex_thread_id, task_status, last_error, updated_at)
                VALUES (?, ?, ?, ?, NULL, 'idle', NULL, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    telegram_user_id = excluded.telegram_user_id,
                    project_path = excluded.project_path,
                    session_key = excluded.session_key,
                    codex_thread_id = NULL,
                    task_status = 'idle',
                    last_error = NULL,
                    updated_at = excluded.updated_at
                """,
                (chat_id, telegram_user_id, str(project_path), session_key, updated_at),
            )
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Session not found for chat_id={chat_id}")
        return self._row_to_session(row)

    def append_message(self, chat_id: int, role: str, content: str) -> None:
        now = _utc_now_iso()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO messages (chat_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, role, content, now),
            )
            self._connection.execute(
                """
                UPDATE sessions
                SET updated_at = ?
                WHERE chat_id = ?
                """,
                (now, chat_id),
            )

    def list_messages(self, chat_id: int, limit: int = 24) -> list[ConversationMessage]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [
            ConversationMessage(
                role=row["role"],
                content=row["content"],
                created_at=_parse_datetime(row["created_at"]),
            )
            for row in reversed(rows)
        ]

    def count_messages(self, chat_id: int) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return int(row["count"])

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            chat_id=int(row["chat_id"]),
            telegram_user_id=int(row["telegram_user_id"]),
            project_path=Path(row["project_path"]),
            session_key=row["session_key"],
            codex_thread_id=row["codex_thread_id"],
            task_status=row["task_status"],
            last_error=row["last_error"],
            updated_at=_parse_datetime(row["updated_at"]),
        )
