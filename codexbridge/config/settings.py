from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _parse_int_list(raw: Any) -> set[int]:
    if raw is None:
        return set()
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",") if item.strip()]
        return {int(item) for item in values}
    if isinstance(raw, (list, tuple, set)):
        return {int(item) for item in raw}
    raise ValueError("allowed_users must be a list or comma-separated string")


def _parse_command_template(raw: Any) -> list[str]:
    if raw is None:
        return ["codex", "exec", "{prompt}"]
    if isinstance(raw, str):
        command = shlex.split(raw)
    elif isinstance(raw, (list, tuple)):
        command = [str(item) for item in raw]
    else:
        raise ValueError("codex_command_template must be a string or list")
    if not command:
        raise ValueError("codex_command_template cannot be empty")
    if not any("{prompt}" in item for item in command):
        command.append("{prompt}")
    return command


def _resolve_path(value: Any, *, base_dir: Path) -> Path:
    path = Path(str(value or ".")).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    else:
        path = path.resolve()
    return path


@dataclass(slots=True)
class AppSettings:
    telegram_bot_token: str
    allowed_users: set[int]
    default_project_path: Path
    session_db_path: Path
    logs_dir: Path
    log_level: str = "INFO"
    codex_command_template: list[str] = field(default_factory=lambda: ["codex", "exec", "{prompt}"])
    codex_timeout_seconds: int = 1800
    history_message_limit: int = 24
    telegram_reply_chunk_size: int = 3500
    status_update_interval_seconds: int = 15
    projects: dict[str, Path] = field(default_factory=dict)

    def ensure_directories(self) -> None:
        self.default_project_path.mkdir(parents=True, exist_ok=True)
        self.session_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any], *, base_dir: Path) -> "AppSettings":
        token = str(raw.get("telegram_bot_token") or "").strip()
        allowed_users = _parse_int_list(raw.get("allowed_users"))
        if not token:
            raise ValueError("telegram_bot_token is required")
        if not allowed_users:
            raise ValueError("allowed_users must contain at least one Telegram user id")

        projects = {
            str(name): _resolve_path(path, base_dir=base_dir)
            for name, path in (raw.get("projects") or {}).items()
        }

        settings = cls(
            telegram_bot_token=token,
            allowed_users=allowed_users,
            default_project_path=_resolve_path(raw.get("default_project_path", "."), base_dir=base_dir),
            session_db_path=_resolve_path(raw.get("session_db_path", "./data/sessions.db"), base_dir=base_dir),
            logs_dir=_resolve_path(raw.get("logs_dir", "./logs"), base_dir=base_dir),
            log_level=str(raw.get("log_level", "INFO")).upper(),
            codex_command_template=_parse_command_template(raw.get("codex_command_template")),
            codex_timeout_seconds=int(raw.get("codex_timeout_seconds", 1800)),
            history_message_limit=max(1, int(raw.get("history_message_limit", 24))),
            telegram_reply_chunk_size=max(500, int(raw.get("telegram_reply_chunk_size", 3500))),
            status_update_interval_seconds=max(5, int(raw.get("status_update_interval_seconds", 15))),
            projects=projects,
        )
        settings.ensure_directories()
        return settings


def _deep_update(target: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
    return target


def _env_overrides() -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if token := os.getenv("CODEXBRIDGE_TELEGRAM_BOT_TOKEN"):
        overrides["telegram_bot_token"] = token
    if allowed_users := os.getenv("CODEXBRIDGE_ALLOWED_USERS"):
        overrides["allowed_users"] = allowed_users
    if default_project_path := os.getenv("CODEXBRIDGE_DEFAULT_PROJECT_PATH"):
        overrides["default_project_path"] = default_project_path
    if session_db_path := os.getenv("CODEXBRIDGE_SESSION_DB_PATH"):
        overrides["session_db_path"] = session_db_path
    if logs_dir := os.getenv("CODEXBRIDGE_LOGS_DIR"):
        overrides["logs_dir"] = logs_dir
    if log_level := os.getenv("CODEXBRIDGE_LOG_LEVEL"):
        overrides["log_level"] = log_level
    if command_template := os.getenv("CODEXBRIDGE_CODEX_COMMAND_TEMPLATE"):
        overrides["codex_command_template"] = command_template
    if timeout_seconds := os.getenv("CODEXBRIDGE_CODEX_TIMEOUT_SECONDS"):
        overrides["codex_timeout_seconds"] = timeout_seconds
    if history_limit := os.getenv("CODEXBRIDGE_HISTORY_MESSAGE_LIMIT"):
        overrides["history_message_limit"] = history_limit
    if chunk_size := os.getenv("CODEXBRIDGE_TELEGRAM_REPLY_CHUNK_SIZE"):
        overrides["telegram_reply_chunk_size"] = chunk_size
    if status_interval := os.getenv("CODEXBRIDGE_STATUS_UPDATE_INTERVAL_SECONDS"):
        overrides["status_update_interval_seconds"] = status_interval
    return overrides


def load_settings(config_path: str | Path | None = None) -> AppSettings:
    explicit_path = Path(config_path) if config_path is not None else None
    file_path = Path(os.getenv("CODEXBRIDGE_CONFIG", explicit_path or "config.yaml")).expanduser()
    raw: dict[str, Any] = {}
    if file_path.exists():
        with file_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    elif explicit_path is not None:
        raise FileNotFoundError(f"Config file not found: {file_path}")

    base_dir = file_path.parent.resolve()
    raw = _deep_update(raw, _env_overrides())
    return AppSettings.from_mapping(raw, base_dir=base_dir)
