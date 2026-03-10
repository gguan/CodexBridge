from __future__ import annotations

from pathlib import Path

from codexbridge.models import ConversationMessage, SessionRecord
from codexbridge.storage import SessionStore


class SessionManager:
    def __init__(
        self,
        store: SessionStore,
        *,
        default_project_path: Path,
        projects: dict[str, Path],
        history_message_limit: int,
    ) -> None:
        self.store = store
        self.default_project_path = default_project_path.resolve()
        self.projects = {name: path.resolve() for name, path in projects.items()}
        self.history_message_limit = history_message_limit

    def get_or_create_session(self, chat_id: int, telegram_user_id: int) -> SessionRecord:
        return self.store.create_or_get_session(chat_id, telegram_user_id, self.default_project_path)

    def get_session(self, chat_id: int, telegram_user_id: int) -> SessionRecord:
        existing = self.store.get_session(chat_id)
        if existing is not None:
            return existing
        return self.get_or_create_session(chat_id, telegram_user_id)

    def get_history(self, chat_id: int) -> list[ConversationMessage]:
        return self.store.list_messages(chat_id, limit=self.history_message_limit)

    def append_turn(self, chat_id: int, user_message: str, assistant_message: str) -> None:
        self.store.append_message(chat_id, "user", user_message)
        self.store.append_message(chat_id, "assistant", assistant_message)

    def set_status(self, chat_id: int, status: str, last_error: str | None = None) -> SessionRecord:
        return self.store.set_status(chat_id, status, last_error=last_error)

    def reset(self, chat_id: int, telegram_user_id: int) -> SessionRecord:
        session = self.get_session(chat_id, telegram_user_id)
        return self.store.reset_session(chat_id, telegram_user_id, session.project_path)

    def list_project_aliases(self) -> dict[str, Path]:
        return dict(sorted(self.projects.items()))

    def message_count(self, chat_id: int) -> int:
        return self.store.count_messages(chat_id)

    def switch_project(self, chat_id: int, telegram_user_id: int, spec: str) -> SessionRecord:
        self.get_session(chat_id, telegram_user_id)
        resolved = self.resolve_project(spec)
        return self.store.set_project(chat_id, resolved)

    def resolve_project(self, spec: str) -> Path:
        candidate = spec.strip()
        if not candidate:
            raise ValueError("Project value cannot be empty")

        if candidate in self.projects:
            resolved = self.projects[candidate]
        else:
            raw_path = Path(candidate).expanduser()
            if not raw_path.is_absolute():
                raw_path = self.default_project_path / raw_path
            resolved = raw_path.resolve()

        if not resolved.exists():
            raise ValueError(f"Project path does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"Project path is not a directory: {resolved}")
        if not self._is_allowed_project(resolved):
            raise ValueError(f"Project path is outside the allowed roots: {resolved}")
        return resolved

    def _is_allowed_project(self, project_path: Path) -> bool:
        roots = {self.default_project_path, *self.projects.values()}
        return any(self._is_relative_to(project_path, root) for root in roots)

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
