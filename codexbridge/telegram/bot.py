from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from loguru import logger
from telegram import BotCommand, Update
from telegram.error import Conflict, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from codexbridge.codex import CodexExecutor, CodexThreadCatalog, SessionManager
from codexbridge.config import AppSettings
from codexbridge.models import CodexThreadSummary, ExecutionEvent
from codexbridge.utils import chunk_display_text, normalize_display_text


class CodexBridgeBot:
    def __init__(
        self,
        *,
        settings: AppSettings,
        session_manager: SessionManager,
        executor: CodexExecutor,
        thread_catalog: CodexThreadCatalog,
    ) -> None:
        self.settings = settings
        self.session_manager = session_manager
        self.executor = executor
        self.thread_catalog = thread_catalog
        self._chat_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._fatal_error: str | None = None

    def build_application(self) -> Application:
        application = (
            Application.builder()
            .token(self.settings.telegram_bot_token)
            .post_init(self.on_startup)
            .build()
        )
        application.add_handler(CommandHandler("help", self.handle_help))
        application.add_handler(CommandHandler("status", self.handle_status))
        application.add_handler(CommandHandler("reset", self.handle_reset))
        application.add_handler(CommandHandler("project", self.handle_project))
        application.add_handler(CommandHandler("threads", self.handle_threads))
        application.add_handler(CommandHandler("attach", self.handle_attach))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        application.add_handler(MessageHandler(filters.COMMAND, self.handle_unknown_command))
        application.add_error_handler(self.handle_error)
        return application

    def run(self) -> None:
        application = self.build_application()
        logger.info("Starting Telegram polling")
        try:
            application.run_polling(drop_pending_updates=False)
            if self._fatal_error:
                raise SystemExit(self._fatal_error)
        except Conflict as exc:
            message = (
                "Telegram polling conflict: another process is already calling getUpdates for this bot token. "
                "Stop the other bot instance and restart CodexBridge."
            )
            logger.error("{} ({})", message, exc)
            raise SystemExit(message) from exc

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        assert update.effective_chat is not None
        assert update.effective_user is not None
        assert update.effective_message is not None
        session = self.session_manager.get_session(update.effective_chat.id, update.effective_user.id)
        aliases = ", ".join(self.session_manager.list_project_aliases().keys()) or "(none)"
        message = (
            f"Status: {session.task_status}\n"
            f"Project: {session.project_path}\n"
            f"Codex thread: {session.codex_thread_id or '(not attached)'}\n"
            f"Messages: {self.session_manager.message_count(session.chat_id)}\n"
            f"Aliases: {aliases}"
        )
        if session.last_error:
            message += f"\nLast error: {session.last_error}"
        if self.settings.codex_session_mode == "resume" and not session.codex_thread_id:
            message += "\nTip: use /threads to list recent Codex threads, or send a message to auto-attach the latest thread."
        await update.effective_message.reply_text(message)

    async def on_startup(self, application: Application) -> None:
        commands = [
            BotCommand("help", "Show quick usage"),
            BotCommand("status", "Show bot status"),
            BotCommand("reset", "Reset current chat session"),
            BotCommand("project", "Show or switch project"),
            BotCommand("threads", "List recent Codex threads"),
            BotCommand("attach", "Attach to a Codex thread"),
        ]
        try:
            await application.bot.set_my_commands(commands)
        except TelegramError as exc:
            logger.warning("Failed to set Telegram commands: {}", exc)

        startup_text = "\n".join(
            [
                "CodexBridge is connected.",
                "Quick commands: /help /status /project /threads /attach",
                "You can now send natural-language tasks directly.",
            ]
        )
        for user_id in self.settings.allowed_users:
            try:
                await application.bot.send_message(chat_id=user_id, text=startup_text)
            except TelegramError as exc:
                logger.warning("Failed to send startup notification to user_id={}: {}", user_id, exc)

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        assert update.effective_message is not None
        message = "\n".join(
            [
                "CodexBridge commands:",
                "/status - show task status and current project",
                "/reset - clear this chat session state",
                "/project - show current project and aliases",
                "/project <alias-or-path> - switch project",
                "/threads - list recent Codex app threads",
                "/attach <number|thread_id> - bind current Telegram chat to a thread",
                "",
                "Quick test flow:",
                "1) Send /status",
                "2) (resume mode) Send /threads and /attach 1",
                "3) Send a normal task message like: run tests and summarize failures",
            ]
        )
        await update.effective_message.reply_text(message)

    async def handle_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        assert update.effective_chat is not None
        assert update.effective_user is not None
        assert update.effective_message is not None
        session = self.session_manager.reset(update.effective_chat.id, update.effective_user.id)
        lines = [
            "Session reset.",
            f"Project remains: {session.project_path}",
        ]
        if self.settings.codex_session_mode == "resume":
            lines.append("The next message will attach to the latest Codex App session again.")
        await update.effective_message.reply_text("\n".join(lines))

    async def handle_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        assert update.effective_chat is not None
        assert update.effective_user is not None
        assert update.effective_message is not None
        if not context.args:
            session = self.session_manager.get_session(update.effective_chat.id, update.effective_user.id)
            aliases = self.session_manager.list_project_aliases()
            alias_lines = [f"{name}: {path}" for name, path in aliases.items()] or ["(no aliases configured)"]
            message = "\n".join(
                [
                    f"Current project: {session.project_path}",
                    "Configured aliases:",
                    *alias_lines,
                ]
            )
            await update.effective_message.reply_text(message)
            return

        raw_spec = " ".join(context.args)
        try:
            session = self.session_manager.switch_project(
                update.effective_chat.id,
                update.effective_user.id,
                raw_spec,
            )
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
            return

        reply_lines = [f"Project switched to: {session.project_path}"]
        if self.settings.codex_session_mode == "resume":
            reply_lines.append("Codex thread mapping cleared for this chat.")
        await update.effective_message.reply_text("\n".join(reply_lines))

    async def handle_threads(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        assert update.effective_message is not None
        threads = self.thread_catalog.list_threads(limit=10)
        if not threads:
            await update.effective_message.reply_text("No Codex threads found in the local session index.")
            return

        lines = ["Recent Codex threads:"]
        for index, thread in enumerate(threads, start=1):
            lines.append(self._format_thread_line(index, thread))
        lines.append("Use /attach <number> or /attach <thread_id> to bind this Telegram chat.")
        await update.effective_message.reply_text("\n".join(lines))

    async def handle_attach(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        assert update.effective_chat is not None
        assert update.effective_user is not None
        assert update.effective_message is not None

        if not context.args:
            await update.effective_message.reply_text("Usage: /attach <number|thread_id>\nUse /threads to see available threads.")
            return

        spec = " ".join(context.args)
        thread = self.thread_catalog.resolve_thread(spec)
        if thread is None:
            await update.effective_message.reply_text("Thread not found. Use /threads to see available threads.")
            return

        session = self.session_manager.get_session(update.effective_chat.id, update.effective_user.id)
        session = self.session_manager.set_codex_thread_id(session.chat_id, thread.thread_id)
        await update.effective_message.reply_text(
            "\n".join(
                [
                    f"Attached to Codex thread: {thread.thread_id}",
                    f"Name: {thread.thread_name}",
                    f"Updated: {thread.updated_at.isoformat()}",
                ]
            )
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        assert update.effective_chat is not None
        assert update.effective_user is not None
        assert update.effective_message is not None

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        user_text = (update.effective_message.text or "").strip()
        if not user_text:
            return

        chat_lock = self._chat_locks[chat_id]
        if chat_lock.locked():
            await update.effective_message.reply_text("A task is already running in this chat. Use /status to check progress.")
            return

        async with chat_lock:
            session = self.session_manager.get_session(chat_id, user_id)
            self.session_manager.set_status(chat_id, "running", last_error=None)
            logger.info("Telegram message chat_id={} user_id={} text={}", chat_id, user_id, user_text)

            if self.settings.codex_session_mode == "resume" and not session.codex_thread_id:
                latest_threads = self.thread_catalog.list_threads(limit=1)
                if latest_threads:
                    latest_thread = latest_threads[0]
                    session = self.session_manager.set_codex_thread_id(chat_id, latest_thread.thread_id)
                    await update.effective_message.reply_text(
                        "\n".join(
                            [
                                "No Codex thread was attached for this chat.",
                                f"Auto-attached latest app thread: {latest_thread.thread_id}",
                                f"Name: {latest_thread.thread_name}",
                                "Use /threads if you want to switch to a different thread first.",
                            ]
                        )
                    )
                else:
                    await update.effective_message.reply_text(
                        "No Codex thread attached yet, and no app threads were found in the local index. I will fall back to the latest available Codex session."
                    )
            else:
                await update.effective_message.reply_text("Working on your request...")

            streamed_output: list[str] = []
            stderr_output: list[str] = []
            pending_buffer = ""
            last_stream_send = time.monotonic()
            last_heartbeat_notice = 0.0
            assistant_text = ""

            try:
                history = self.session_manager.get_history(chat_id)
                async for event in self.executor.stream_execute(session, history, user_text):
                    if event.kind == "output":
                        pending_buffer += event.text
                        streamed_output.append(event.text)
                        if self._should_flush(pending_buffer, last_stream_send):
                            await self._flush_buffer(update, pending_buffer)
                            pending_buffer = ""
                            last_stream_send = time.monotonic()
                    elif event.kind == "stderr":
                        stderr_output.append(event.text)
                        logger.warning("Codex stderr chat_id={} chunk={}", chat_id, event.text.strip())
                    elif event.kind == "heartbeat":
                        now = time.monotonic()
                        if now - last_heartbeat_notice >= 60:
                            await update.effective_message.reply_text("Still running, I will send updates shortly.")
                            last_heartbeat_notice = now
                    elif event.kind == "error":
                        if pending_buffer:
                            await self._flush_buffer(update, pending_buffer)
                            pending_buffer = ""
                        assistant_text = event.text
                        await self._flush_buffer(update, assistant_text)
                        self.session_manager.set_status(chat_id, "failed", last_error=event.text)
                        break
                    elif event.kind == "timed_out":
                        if pending_buffer:
                            await self._flush_buffer(update, pending_buffer)
                            pending_buffer = ""
                        assistant_text = "Task timeout"
                        await self._flush_buffer(update, assistant_text)
                        self.session_manager.set_status(chat_id, "failed", last_error="Task timeout")
                        break
                    elif event.kind == "completed":
                        if pending_buffer:
                            await self._flush_buffer(update, pending_buffer)
                            pending_buffer = ""
                        previous_thread_id = session.codex_thread_id
                        if event.thread_id and event.thread_id != session.codex_thread_id:
                            session = self.session_manager.set_codex_thread_id(chat_id, event.thread_id)
                        assistant_text = self._finalize_output(event, stderr_output)
                        if event.returncode == 0:
                            self.session_manager.set_status(chat_id, "idle", last_error=None)
                            if self.settings.codex_session_mode == "resume" and event.thread_id and not previous_thread_id:
                                await update.effective_message.reply_text(
                                    f"Attached to Codex thread: {event.thread_id}"
                                )
                            if assistant_text == "Task completed, but Codex returned no stdout output.":
                                await self._flush_buffer(update, assistant_text)
                            elif not streamed_output:
                                await self._flush_buffer(update, assistant_text)
                        else:
                            failure_text = "Codex execution failed"
                            self.session_manager.set_status(chat_id, "failed", last_error=failure_text)
                            await update.effective_message.reply_text(failure_text)
                            if not streamed_output and assistant_text != failure_text:
                                await self._flush_buffer(update, assistant_text)
                        break
            except Exception as exc:
                logger.exception("Unhandled bot error for chat_id={}", chat_id)
                assistant_text = f"Codex execution failed: {exc}"
                self.session_manager.set_status(chat_id, "failed", last_error=str(exc))
                await update.effective_message.reply_text("Codex execution failed")

            if not assistant_text:
                assistant_text = "".join(streamed_output).strip()

            if assistant_text:
                self.session_manager.append_turn(chat_id, user_text, normalize_display_text(assistant_text))

    async def handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        if isinstance(context.error, Conflict):
            message = (
                "Telegram polling conflict: another process is already calling getUpdates for this bot token. "
                "Stop the other bot instance and restart CodexBridge."
            )
            self._fatal_error = message
            logger.error("{} ({})", message, context.error)
            context.application.stop_running()
            return
        logger.exception("Telegram application error: {}", context.error)

    async def handle_unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        assert update.effective_message is not None
        await update.effective_message.reply_text("Unknown command. Send /help to see available commands.")

    async def _authorize(self, update: Update) -> bool:
        if update.effective_user is None or update.effective_message is None:
            return False
        if update.effective_user.id not in self.settings.allowed_users:
            logger.warning("Unauthorized Telegram user: {}", update.effective_user.id)
            await update.effective_message.reply_text("Access denied")
            return False
        return True

    async def _flush_buffer(self, update: Update, buffer: str) -> None:
        assert update.effective_message is not None
        for chunk in chunk_display_text(buffer, limit=self.settings.telegram_reply_chunk_size):
            await update.effective_message.reply_text(chunk)

    def _should_flush(self, buffer: str, last_stream_send: float) -> bool:
        return (
            len(buffer) >= self.settings.telegram_reply_chunk_size
            or (len(buffer) >= 800 and time.monotonic() - last_stream_send >= 2)
        )

    @staticmethod
    def _finalize_output(event: ExecutionEvent, stderr_output: list[str]) -> str:
        stdout_text = event.text.strip()
        stderr_text = "".join(stderr_output).strip() or event.stderr.strip()
        if event.returncode == 0:
            return stdout_text or "Task completed, but Codex returned no stdout output."
        parts = [part for part in (stdout_text, stderr_text) if part]
        return "\n\n".join(parts) if parts else "Codex execution failed"

    @staticmethod
    def _format_thread_line(index: int, thread: CodexThreadSummary) -> str:
        updated = thread.updated_at.strftime("%Y-%m-%d %H:%M")
        return f"{index}. {thread.thread_id} | {thread.thread_name} | {updated}"
