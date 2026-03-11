from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

import yaml


def gui_home_dir() -> Path:
    return Path.home() / ".codexbridge-gui"


def state_path() -> Path:
    return gui_home_dir() / "gui-state.yaml"


def runtime_config_path() -> Path:
    return gui_home_dir() / "config.yaml"


def logs_dir() -> Path:
    return gui_home_dir() / "logs"


def load_state() -> dict[str, str]:
    path = state_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return {str(key): str(value) for key, value in data.items()}


def save_state(values: dict[str, str]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(values, handle, allow_unicode=True, sort_keys=True)


def parse_command_template(command_text: str) -> list[str]:
    raw = command_text.strip()
    if not raw:
        return ["codex", "exec", "{prompt}"]

    parsed = shlex.split(raw, posix=(os.name != "nt"))
    if not parsed:
        return ["codex", "exec", "{prompt}"]
    if not any("{prompt}" in item for item in parsed):
        parsed.append("{prompt}")
    return parsed


def build_runtime_config(*, token: str, allowed_user_id: str, project_path: str, codex_command: str) -> Path:
    user_id = int(allowed_user_id.strip())
    project = Path(project_path).expanduser().resolve()
    home = gui_home_dir()
    config_path = runtime_config_path()
    home.mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)
    (home / "data").mkdir(parents=True, exist_ok=True)

    config: dict[str, Any] = {
        "telegram_bot_token": token.strip(),
        "allowed_users": [user_id],
        "default_project_path": str(project),
        "session_db_path": str((home / "data" / "sessions.db").resolve()),
        "logs_dir": str(logs_dir().resolve()),
        "log_level": "INFO",
        "codex_session_mode": "replay",
        "codex_command_template": parse_command_template(codex_command),
        "history_message_limit": 24,
        "telegram_reply_chunk_size": 3500,
        "status_update_interval_seconds": 15,
    }

    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
    return config_path

