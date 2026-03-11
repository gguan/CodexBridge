from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import PureWindowsPath

from loguru import logger

from codexbridge.models import ConversationMessage, ExecutionEvent, SessionRecord


class _SafeDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class CodexExecutor:
    def __init__(
        self,
        *,
        session_mode: str,
        start_command_template: list[str],
        resume_command_template: list[str],
        resume_last_command_template: list[str],
        timeout_seconds: int,
        history_message_limit: int,
        heartbeat_seconds: int,
    ) -> None:
        self.session_mode = session_mode
        self.start_command_template = start_command_template
        self.resume_command_template = resume_command_template
        self.resume_last_command_template = resume_last_command_template
        self.timeout_seconds = timeout_seconds
        self.history_message_limit = history_message_limit
        self.heartbeat_seconds = heartbeat_seconds

    def build_prompt(
        self,
        session: SessionRecord,
        history: list[ConversationMessage],
        user_message: str,
    ) -> str:
        if self.session_mode == "resume":
            return user_message.strip()
        transcript_parts: list[str] = []
        for message in history[-self.history_message_limit :]:
            role = "User" if message.role == "user" else "Assistant"
            transcript_parts.append(f"{role}: {message.content.strip()}")
        transcript = "\n\n".join(part for part in transcript_parts if part.strip()) or "(no previous messages)"
        return (
            "You are Codex operating behind a Telegram bridge.\n"
            f"Current project directory: {session.project_path}\n"
            "Maintain continuity with the earlier conversation.\n"
            "Be concise, but include concrete findings, edits, or command results when relevant.\n\n"
            "Conversation so far:\n"
            f"{transcript}\n\n"
            "New user request:\n"
            f"{user_message.strip()}"
        )

    def build_command(self, prompt: str, session: SessionRecord) -> list[str]:
        project_path = str(session.project_path)
        template = self._select_command_template(session)
        values = _SafeDict(
            prompt=prompt,
            project_path=project_path,
            project_path_wsl=self.to_wsl_path(project_path),
            session_key=session.session_key,
            thread_id=session.codex_thread_id or "",
            chat_id=str(session.chat_id),
        )
        return [item.format_map(values) for item in template]

    def _select_command_template(self, session: SessionRecord) -> list[str]:
        if self.session_mode != "resume":
            return self.start_command_template
        if session.codex_thread_id and self.resume_command_template:
            return self.resume_command_template
        if self.resume_last_command_template:
            return self.resume_last_command_template
        return self.start_command_template

    @staticmethod
    def to_wsl_path(project_path: str) -> str:
        pure = PureWindowsPath(project_path)
        if pure.drive:
            drive = pure.drive.rstrip(":").lower()
            parts = [part for part in pure.parts[1:] if part not in ("\\", "/")]
            suffix = "/".join(parts)
            return f"/mnt/{drive}/{suffix}" if suffix else f"/mnt/{drive}"
        return project_path.replace("\\", "/")

    async def stream_execute(
        self,
        session: SessionRecord,
        history: list[ConversationMessage],
        user_message: str,
    ) -> AsyncIterator[ExecutionEvent]:
        prompt = self.build_prompt(session, history, user_message)
        command = self.build_command(prompt, session)
        logger.info("Executing Codex command for chat_id={} cwd={} command={}", session.chat_id, session.project_path, command)

        start = time.monotonic()
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(session.project_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            yield ExecutionEvent(kind="error", text=f"Codex command not found: {command[0]}")
            return
        except PermissionError:
            yield ExecutionEvent(kind="error", text=f"Codex command is not executable: {command[0]}")
            return
        except OSError as exc:
            yield ExecutionEvent(kind="error", text=f"Codex failed to start: {exc}")
            return

        if self.session_mode == "resume":
            async for event in self._stream_json_process(process, start):
                yield event
            return

        queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()
        stream_tasks = [
            asyncio.create_task(self._pump_stream(process.stdout, "stdout", queue)),
            asyncio.create_task(self._pump_stream(process.stderr, "stderr", queue)),
        ]

        closed_streams = 0
        while closed_streams < len(stream_tasks):
            elapsed = time.monotonic() - start
            remaining = self.timeout_seconds - elapsed
            if remaining <= 0:
                await self._terminate_process(process)
                for task in stream_tasks:
                    task.cancel()
                yield ExecutionEvent(
                    kind="timed_out",
                    text="Task timeout",
                    duration_seconds=time.monotonic() - start,
                    stderr="".join(stderr_chunks),
                )
                return

            try:
                event_kind, payload = await asyncio.wait_for(
                    queue.get(),
                    timeout=min(self.heartbeat_seconds, remaining),
                )
            except asyncio.TimeoutError:
                yield ExecutionEvent(kind="heartbeat", duration_seconds=time.monotonic() - start)
                continue

            if event_kind == "closed":
                closed_streams += 1
                continue

            text = payload or ""
            if event_kind == "stdout":
                stdout_chunks.append(text)
                yield ExecutionEvent(kind="output", text=text)
            elif event_kind == "stderr":
                if not self._is_ignorable_stderr(text):
                    stderr_chunks.append(text)
                    yield ExecutionEvent(kind="stderr", text=text)

        returncode = await process.wait()
        duration = time.monotonic() - start
        yield ExecutionEvent(
            kind="completed",
            text="".join(stdout_chunks),
            returncode=returncode,
            duration_seconds=duration,
            stderr="".join(stderr_chunks),
        )

    async def _stream_json_process(
        self,
        process: asyncio.subprocess.Process,
        start: float,
    ) -> AsyncIterator[ExecutionEvent]:
        queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()
        stream_tasks = [
            asyncio.create_task(self._pump_lines(process.stdout, "stdout", queue)),
            asyncio.create_task(self._pump_stream(process.stderr, "stderr", queue)),
        ]

        thread_id: str | None = None
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        closed_streams = 0

        while closed_streams < len(stream_tasks):
            elapsed = time.monotonic() - start
            remaining = self.timeout_seconds - elapsed
            if remaining <= 0:
                await self._terminate_process(process)
                for task in stream_tasks:
                    task.cancel()
                yield ExecutionEvent(
                    kind="timed_out",
                    text="Task timeout",
                    duration_seconds=time.monotonic() - start,
                    stderr="".join(stderr_chunks),
                    thread_id=thread_id,
                )
                return

            try:
                event_kind, payload = await asyncio.wait_for(
                    queue.get(),
                    timeout=min(self.heartbeat_seconds, remaining),
                )
            except asyncio.TimeoutError:
                yield ExecutionEvent(kind="heartbeat", duration_seconds=time.monotonic() - start, thread_id=thread_id)
                continue

            if event_kind == "closed":
                closed_streams += 1
                continue

            text = (payload or "").strip()
            if not text:
                continue

            if event_kind == "stderr":
                if not self._is_ignorable_stderr(text):
                    stderr_chunks.append(text)
                    yield ExecutionEvent(kind="stderr", text=text, thread_id=thread_id)
                continue

            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                stdout_chunks.append(text)
                yield ExecutionEvent(kind="output", text=text, thread_id=thread_id)
                continue

            event_type = event.get("type")
            if event_type == "thread.started":
                thread_id = event.get("thread_id")
                continue
            if event_type == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    message_text = str(item.get("text", "")).strip()
                    if message_text:
                        stdout_chunks.append(message_text)
                        yield ExecutionEvent(kind="output", text=message_text, thread_id=thread_id)
                continue
            if event_type == "error":
                message = str(event.get("message") or "Codex execution failed")
                yield ExecutionEvent(kind="error", text=message, thread_id=thread_id)
                return

        returncode = await process.wait()
        duration = time.monotonic() - start
        yield ExecutionEvent(
            kind="completed",
            text="\n\n".join(chunk for chunk in stdout_chunks if chunk).strip(),
            returncode=returncode,
            duration_seconds=duration,
            stderr="\n".join(chunk for chunk in stderr_chunks if chunk).strip(),
            thread_id=thread_id,
        )

    async def _pump_stream(
        self,
        stream: asyncio.StreamReader | None,
        kind: str,
        queue: asyncio.Queue[tuple[str, str | None]],
    ) -> None:
        if stream is None:
            await queue.put(("closed", None))
            return
        try:
            while True:
                chunk = await stream.read(1024)
                if not chunk:
                    break
                await queue.put((kind, chunk.decode("utf-8", errors="replace")))
        finally:
            await queue.put(("closed", None))

    async def _pump_lines(
        self,
        stream: asyncio.StreamReader | None,
        kind: str,
        queue: asyncio.Queue[tuple[str, str | None]],
    ) -> None:
        if stream is None:
            await queue.put(("closed", None))
            return
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                await queue.put((kind, line.decode("utf-8", errors="replace")))
        finally:
            await queue.put(("closed", None))

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.kill()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            logger.warning("Timed out while waiting for subprocess shutdown")

    @staticmethod
    def _is_ignorable_stderr(text: str) -> bool:
        cleaned = text.replace("\x00", "").strip()
        if not cleaned:
            return True
        return "WSL" in cleaned and "localhost" in cleaned
