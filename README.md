# CodexBridge

CodexBridge lets you control a local Codex workflow from Telegram. It includes both a CLI service mode and a simple desktop GUI launcher.

## Features

- Telegram bot bridge with per-chat session memory
- Optional `resume` mode to attach to real Codex threads
- Thread management commands: `/threads` and `/attach`
- Simple GUI launcher: input `token` + `authorized user id`, then start/stop bot
- GUI auto-saves input fields and restores them on next launch
- GUI logs tab with real-time `server.log` tail view
- Cross-platform packaging workflow for Windows and macOS

## Quick Start (CLI)

1. Create environment and install dependencies:

```bash
python -m venv .venv
pip install -e .[dev]
```

2. Configure:

```bash
copy config.example.yaml config.yaml
```

3. Run:

```bash
python main.py
```

## Quick Start (GUI)

Run the desktop launcher:

```bash
codexbridge-gui
```

or:

```bash
python codexbridge_gui.py
```

Then in the UI:

- Input `Telegram Bot Token`
- Input `Authorized Telegram User ID`
- Choose default project folder
- Click `Start Bot`
- Open `Logs` tab to watch runtime logs in real time

Runtime files created by GUI:

- `~/.codexbridge-gui/config.yaml`
- `~/.codexbridge-gui/data/sessions.db`
- `~/.codexbridge-gui/logs/`

## Telegram Commands

- `/help`
- `/status`
- `/reset`
- `/project`
- `/project <alias-or-path>`
- `/threads`
- `/attach <number-or-thread-id>`

## End-to-End Test (Telegram -> Codex)

1. Start bot service (GUI or CLI).
2. In Telegram, send `/status` and confirm the bot replies.
3. If using `resume` mode, send `/threads`, then `/attach <number>`.
4. Send a natural-language task, for example:
   - `帮我总结当前仓库改动`
   - `运行测试并告诉我失败原因`
5. Confirm staged feedback appears (`Starting analysis...`, `Task still running...`, `Task completed.`).

## Session Modes

- `replay`: replays recent Telegram history into each `codex exec`
- `resume`: stores Codex `thread_id` and continues it with `codex exec resume`

## Build Packaged App

You must build on each target OS separately.

### Windows

```powershell
.\scripts\build_windows.ps1
```

Output:

- `dist/CodexBridgeGUI/CodexBridgeGUI.exe`

### macOS

```bash
chmod +x ./scripts/build_macos.sh
./scripts/build_macos.sh
```

Output:

- `dist/CodexBridgeGUI.app`

## Troubleshooting

### Error: `Conflict: terminated by other getUpdates request`

This means more than one process is polling the same Telegram bot token.

- Stop old bot processes (`python`, `CodexBridgeGUI.exe`, tmux/systemd jobs).
- Keep only one active instance per bot token.
- Restart CodexBridge and test with `/status`.

## Config Reference

```yaml
telegram_bot_token: "..."
allowed_users:
  - 12345678
default_project_path: "."
session_db_path: "./data/sessions.db"
codex_session_index_path: "~/.codex/session_index.jsonl"
logs_dir: "./logs"
log_level: "INFO"
codex_session_mode: "replay"
codex_command_template:
  - "codex"
  - "exec"
  - "{prompt}"
```

## Development Checks

```bash
pytest
python -m compileall codexbridge main.py codexbridge_gui.py
```
