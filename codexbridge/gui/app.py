from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tkinter import END, StringVar, Tk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk

from codexbridge.gui.config import (
    build_runtime_config,
    gui_home_dir,
    load_state,
    logs_dir,
    runtime_config_path,
    save_state,
)


class BotController:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, config_file: Path) -> None:
        if self.is_running():
            return

        if getattr(sys, "frozen", False):
            command = [sys.executable, "--run-service", str(config_file)]
        else:
            command = [sys.executable, "-m", "codexbridge.gui.entry", "--run-service", str(config_file)]

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        self.process = subprocess.Popen(
            command,
            cwd=str(Path.cwd()),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    def stop(self) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None


class LauncherApp:
    LOG_POLL_INTERVAL_MS = 1000
    PROCESS_POLL_INTERVAL_MS = 800

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("CodexBridge Launcher")
        self.root.geometry("760x520")
        self.root.minsize(760, 520)
        self.controller = BotController()

        saved = load_state()
        self.token_var = StringVar(value=saved.get("token", ""))
        self.user_id_var = StringVar(value=saved.get("user_id", ""))
        self.project_var = StringVar(value=saved.get("project_path", str(Path.cwd())))
        self.command_var = StringVar(value=saved.get("codex_command", "codex exec {prompt}"))
        self.status_var = StringVar(value="Stopped")
        self._state_save_job: str | None = None

        self.log_path = logs_dir() / "server.log"
        self.log_offset = 0
        self.log_text: ScrolledText

        self.start_button: ttk.Button
        self.stop_button: ttk.Button
        self._build_ui()
        self._bind_state_autosave()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(self.PROCESS_POLL_INTERVAL_MS, self._poll_process)
        self.root.after(self.LOG_POLL_INTERVAL_MS, self._poll_logs)

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True)

        launch_tab = ttk.Frame(notebook, padding=16)
        logs_tab = ttk.Frame(notebook, padding=12)
        notebook.add(launch_tab, text="Launcher")
        notebook.add(logs_tab, text="Logs")

        ttk.Label(launch_tab, text="Telegram Bot Token").grid(row=0, column=0, sticky="w")
        ttk.Entry(launch_tab, textvariable=self.token_var, width=70, show="*").grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )

        ttk.Label(launch_tab, text="Authorized Telegram User ID").grid(row=2, column=0, sticky="w")
        ttk.Entry(launch_tab, textvariable=self.user_id_var, width=35).grid(row=3, column=0, sticky="w", pady=(0, 10))

        ttk.Label(launch_tab, text="Default Project Path").grid(row=4, column=0, sticky="w")
        path_row = ttk.Frame(launch_tab)
        path_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        path_row.columnconfigure(0, weight=1)
        ttk.Entry(path_row, textvariable=self.project_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(path_row, text="Browse", command=self._choose_project).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(launch_tab, text="Codex Command (optional)").grid(row=6, column=0, sticky="w")
        ttk.Entry(launch_tab, textvariable=self.command_var, width=70).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(0, 12)
        )

        actions = ttk.Frame(launch_tab)
        actions.grid(row=8, column=0, columnspan=2, sticky="w")
        self.start_button = ttk.Button(actions, text="Start Bot", command=self._start_bot)
        self.start_button.grid(row=0, column=0)
        self.stop_button = ttk.Button(actions, text="Stop Bot", command=self._stop_bot, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=(8, 0))
        ttk.Button(actions, text="Open Logs Folder", command=self._open_logs).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(actions, text="Open Runtime Config", command=self._open_runtime_config).grid(row=0, column=3, padx=(8, 0))

        ttk.Label(launch_tab, text="Status").grid(row=9, column=0, sticky="w", pady=(14, 0))
        ttk.Label(launch_tab, textvariable=self.status_var).grid(row=10, column=0, sticky="w")

        hint = (
            "After startup, open Telegram and test: /help, /status, /threads, /attach 1.\n"
            "Input fields are auto-saved and restored at next launch."
        )
        ttk.Label(launch_tab, text=hint).grid(row=11, column=0, columnspan=2, sticky="w", pady=(14, 0))
        launch_tab.columnconfigure(0, weight=1)

        logs_actions = ttk.Frame(logs_tab)
        logs_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(logs_actions, text="Refresh Now", command=self._reload_logs).pack(side="left")
        ttk.Button(logs_actions, text="Clear View", command=self._clear_logs_view).pack(side="left", padx=(8, 0))
        ttk.Button(logs_actions, text="Open Logs Folder", command=self._open_logs).pack(side="left", padx=(8, 0))

        self.log_text = ScrolledText(logs_tab, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True)
        self._reload_logs()

    def _bind_state_autosave(self) -> None:
        for variable in (self.token_var, self.user_id_var, self.project_var, self.command_var):
            variable.trace_add("write", self._schedule_state_save)

    def _schedule_state_save(self, *_: object) -> None:
        if self._state_save_job is not None:
            self.root.after_cancel(self._state_save_job)
        self._state_save_job = self.root.after(250, self._persist_state)

    def _persist_state(self) -> None:
        self._state_save_job = None
        save_state(
            {
                "token": self.token_var.get().strip(),
                "user_id": self.user_id_var.get().strip(),
                "project_path": self.project_var.get().strip(),
                "codex_command": self.command_var.get().strip(),
            }
        )

    def _choose_project(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.project_var.get() or str(Path.cwd()))
        if selected:
            self.project_var.set(selected)

    def _start_bot(self) -> None:
        token = self.token_var.get().strip()
        user_id = self.user_id_var.get().strip()
        project_path = self.project_var.get().strip()
        codex_command = self.command_var.get().strip()

        if not token:
            messagebox.showerror("Missing token", "Please input Telegram bot token.")
            return
        if not user_id:
            messagebox.showerror("Missing user id", "Please input authorized Telegram user id.")
            return
        if not project_path:
            messagebox.showerror("Missing project path", "Please select a default project path.")
            return
        project = Path(project_path).expanduser()
        if not project.exists() or not project.is_dir():
            messagebox.showerror("Invalid path", f"Project path does not exist or is not a directory:\n{project}")
            return
        try:
            int(user_id)
        except ValueError:
            messagebox.showerror("Invalid user id", "User id must be an integer.")
            return

        self._persist_state()

        config_file = build_runtime_config(
            token=token,
            allowed_user_id=user_id,
            project_path=str(project),
            codex_command=codex_command,
        )
        try:
            self.controller.start(config_file)
        except Exception as exc:
            messagebox.showerror("Start failed", str(exc))
            self.status_var.set("Failed to start")
            return

        pid = self.controller.process.pid if self.controller.process else "-"
        self.status_var.set(f"Running (pid={pid})")
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self._reload_logs()

    def _stop_bot(self) -> None:
        self.controller.stop()
        self.status_var.set("Stopped")
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")

    def _open_logs(self) -> None:
        self._open_path(logs_dir())

    def _open_runtime_config(self) -> None:
        self._open_path(runtime_config_path())

    def _open_path(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        target = str(path)
        try:
            if os.name == "nt":
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

    def _append_logs(self, text: str) -> None:
        if not text:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert(END, text)
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def _set_logs(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", END)
        if text:
            self.log_text.insert(END, text)
            self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def _reload_logs(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_offset = 0
            self._set_logs("Log file not created yet. Start the bot to generate logs.\n")
            return

        text = self.log_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > 800:
            text = "\n".join(lines[-800:]) + "\n"
        elif text and not text.endswith("\n"):
            text += "\n"
        self._set_logs(text)
        self.log_offset = self.log_path.stat().st_size

    def _clear_logs_view(self) -> None:
        self._set_logs("")

    def _poll_logs(self) -> None:
        try:
            if not self.log_path.exists():
                self.root.after(self.LOG_POLL_INTERVAL_MS, self._poll_logs)
                return
            if self.log_offset == 0:
                self._reload_logs()
                self.root.after(self.LOG_POLL_INTERVAL_MS, self._poll_logs)
                return

            current_size = self.log_path.stat().st_size
            if current_size < self.log_offset:
                # Log rotated/truncated.
                self._reload_logs()
            elif current_size > self.log_offset:
                with self.log_path.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(self.log_offset)
                    chunk = handle.read()
                self.log_offset = current_size
                self._append_logs(chunk)
        except Exception:
            # Keep GUI resilient even if log file is temporarily unavailable.
            pass
        self.root.after(self.LOG_POLL_INTERVAL_MS, self._poll_logs)

    def _poll_process(self) -> None:
        if self.controller.process and self.controller.process.poll() is not None:
            code = self.controller.process.returncode
            self.controller.process = None
            self.status_var.set(f"Stopped (exit code {code})")
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self._reload_logs()
        self.root.after(self.PROCESS_POLL_INTERVAL_MS, self._poll_process)

    def _on_close(self) -> None:
        if self.controller.is_running():
            stop = messagebox.askyesno("Exit", "Bot is running. Stop it and exit?")
            if not stop:
                return
            self.controller.stop()
        self._persist_state()
        self.root.destroy()


def run_gui() -> None:
    gui_home_dir().mkdir(parents=True, exist_ok=True)
    root = Tk()
    LauncherApp(root)
    root.mainloop()
