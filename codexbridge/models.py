from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ConversationMessage:
    role: str
    content: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class SessionRecord:
    chat_id: int
    telegram_user_id: int
    project_path: Path
    session_key: str
    codex_thread_id: str | None = None
    task_status: str = "idle"
    last_error: str | None = None
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class ExecutionEvent:
    kind: str
    text: str = ""
    returncode: int | None = None
    duration_seconds: float | None = None
    stderr: str = ""
    thread_id: str | None = None


@dataclass(slots=True)
class CodexThreadSummary:
    thread_id: str
    thread_name: str
    updated_at: datetime
