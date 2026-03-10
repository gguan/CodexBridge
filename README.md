# CodexBridge

CodexBridge lets you talk to a local Codex CLI from Telegram. It keeps a per-chat conversation history, forwards tasks to Codex, and streams the result back in chunks that fit Telegram limits.

## What is included

- Telegram bot with authorization checks
- Per-chat persistent sessions stored in SQLite
- Project switching with `/project`
- Task status with `/status`
- Session reset with `/reset`
- Codex subprocess execution with timeout handling
- Chunked replies and lightweight progress updates
- File logging with `loguru`

## How session continuity works

This MVP persists the transcript for each Telegram chat and replays the recent conversation into each Codex request. That means you get follow-up continuity even if the underlying Codex CLI on your machine does not expose a stable native session ID.

If your local Codex install supports a different command shape, update `codex_command_template` in `config.yaml`.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

2. Copy the example config:

```bash
copy config.example.yaml config.yaml
```

3. Fill in:

- `telegram_bot_token`
- `allowed_users`
- `default_project_path`
- `projects` aliases if you want `/project qtrade`
- `codex_command_template` if your Codex CLI command differs

4. Start the service:

```bash
python main.py
```

## Commands

- `/status` show current project, session status, and message count
- `/reset` clear the current chat history
- `/project` show current project and configured aliases
- `/project <alias-or-path>` switch the working directory for this chat

## Config reference

```yaml
telegram_bot_token: "..."
allowed_users:
  - 12345678
default_project_path: "."
session_db_path: "./data/sessions.db"
logs_dir: "./logs"
log_level: "INFO"
codex_command_template:
  - "codex"
  - "exec"
  - "{prompt}"
codex_timeout_seconds: 1800
history_message_limit: 24
telegram_reply_chunk_size: 3500
status_update_interval_seconds: 15
projects:
  qtrade: "D:/Projects/qtrade"
```

## Notes on Codex CLI integration

Codex CLI packaging varies by environment. On this machine, `codex` resolved to a Windows App package resource and direct execution returned a permission error. Because of that, the bridge keeps the execution command fully configurable through `codex_command_template` rather than hard-coding one interface.

Recommended first check on your host machine:

```bash
where codex
codex --help
```

Then update the template accordingly. Examples:

```yaml
codex_command_template:
  - "codex"
  - "exec"
  - "--skip-git-repo-check"
  - "{prompt}"
```

```yaml
codex_command_template:
  - "python"
  - "-m"
  - "codex_cli"
  - "{prompt}"
```

## Development checks

```bash
pytest
python -m compileall codexbridge main.py
```
