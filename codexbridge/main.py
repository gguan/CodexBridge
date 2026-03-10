from __future__ import annotations

from codexbridge.codex import CodexExecutor, SessionManager
from codexbridge.config import load_settings
from codexbridge.storage import SessionStore
from codexbridge.telegram import CodexBridgeBot
from codexbridge.utils import configure_logging


def main() -> None:
    settings = load_settings()
    configure_logging(settings)

    store = SessionStore(settings.session_db_path)
    store.initialize()

    session_manager = SessionManager(
        store,
        default_project_path=settings.default_project_path,
        projects=settings.projects,
        history_message_limit=settings.history_message_limit,
    )
    executor = CodexExecutor(
        command_template=settings.codex_command_template,
        timeout_seconds=settings.codex_timeout_seconds,
        history_message_limit=settings.history_message_limit,
        heartbeat_seconds=settings.status_update_interval_seconds,
    )

    bot = CodexBridgeBot(
        settings=settings,
        session_manager=session_manager,
        executor=executor,
    )
    bot.run()
