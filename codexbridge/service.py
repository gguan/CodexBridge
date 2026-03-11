from __future__ import annotations

from pathlib import Path

from codexbridge.codex import CodexExecutor, CodexThreadCatalog, SessionManager
from codexbridge.config import load_settings
from codexbridge.storage import SessionStore
from codexbridge.telegram import CodexBridgeBot
from codexbridge.utils import SingleInstanceError, SingleInstanceLock, configure_logging


def _single_instance_lock_path(bot_token: str) -> Path:
    # Use bot id (prefix before ':') so GUI mode and CLI mode cannot poll the same bot in parallel.
    bot_id = bot_token.split(":", 1)[0].strip() or "default"
    safe_bot_id = "".join(ch for ch in bot_id if ch.isalnum()) or "default"
    return Path.home() / ".codexbridge" / "locks" / f"{safe_bot_id}.lock"


def run_service(config_path: str | Path | None = None) -> None:
    settings = load_settings(config_path)
    configure_logging(settings)
    instance_lock = SingleInstanceLock(_single_instance_lock_path(settings.telegram_bot_token))
    try:
        instance_lock.acquire()
    except SingleInstanceError as exc:
        raise SystemExit(str(exc)) from exc

    store = SessionStore(settings.session_db_path)
    store.initialize()

    session_manager = SessionManager(
        store,
        default_project_path=settings.default_project_path,
        projects=settings.projects,
        history_message_limit=settings.history_message_limit,
    )
    thread_catalog = CodexThreadCatalog(settings.codex_session_index_path)
    executor = CodexExecutor(
        session_mode=settings.codex_session_mode,
        start_command_template=settings.codex_start_command_template,
        resume_command_template=settings.codex_resume_command_template,
        resume_last_command_template=settings.codex_resume_last_command_template,
        timeout_seconds=settings.codex_timeout_seconds,
        history_message_limit=settings.history_message_limit,
        heartbeat_seconds=settings.status_update_interval_seconds,
    )

    bot = CodexBridgeBot(
        settings=settings,
        session_manager=session_manager,
        executor=executor,
        thread_catalog=thread_catalog,
    )
    try:
        bot.run()
    finally:
        instance_lock.release()
