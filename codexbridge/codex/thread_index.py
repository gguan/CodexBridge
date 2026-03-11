from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from codexbridge.models import CodexThreadSummary


class CodexThreadCatalog:
    def __init__(self, index_path: Path) -> None:
        self.index_path = Path(index_path)

    def list_threads(self, limit: int = 10) -> list[CodexThreadSummary]:
        if not self.index_path.exists():
            return []

        threads_by_id: dict[str, CodexThreadSummary] = {}
        with self.index_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                thread_id = str(payload.get("id") or "").strip()
                updated_at = str(payload.get("updated_at") or "").strip()
                if not thread_id or not updated_at:
                    continue
                try:
                    timestamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                except ValueError:
                    continue
                threads_by_id[thread_id] = CodexThreadSummary(
                    thread_id=thread_id,
                    thread_name=str(payload.get("thread_name") or "(untitled)"),
                    updated_at=timestamp,
                )

        threads = sorted(
            threads_by_id.values(),
            key=lambda thread: thread.updated_at,
            reverse=True,
        )
        return threads[:limit]

    def resolve_thread(self, spec: str, *, limit: int = 20) -> CodexThreadSummary | None:
        candidate = spec.strip()
        if not candidate:
            return None

        threads = self.list_threads(limit=limit)
        if candidate.isdigit():
            index = int(candidate) - 1
            if 0 <= index < len(threads):
                return threads[index]
            return None

        for thread in threads:
            if thread.thread_id == candidate:
                return thread
        for thread in threads:
            if thread.thread_id.startswith(candidate):
                return thread
        return None
