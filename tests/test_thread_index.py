import json
from pathlib import Path

from codexbridge.codex.thread_index import CodexThreadCatalog


def test_thread_catalog_lists_and_resolves_threads(tmp_path: Path) -> None:
    index_path = tmp_path / "session_index.jsonl"
    index_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "thread-1",
                        "thread_name": "First thread",
                        "updated_at": "2026-03-10T19:36:26.1063439Z",
                    }
                ),
                json.dumps(
                    {
                        "id": "thread-2",
                        "thread_name": "Second thread",
                        "updated_at": "2026-03-10T19:45:21.6632649Z",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    catalog = CodexThreadCatalog(index_path)
    threads = catalog.list_threads()

    assert [thread.thread_id for thread in threads] == ["thread-2", "thread-1"]
    assert catalog.resolve_thread("1").thread_id == "thread-2"
    assert catalog.resolve_thread("thread-1").thread_name == "First thread"
    assert catalog.resolve_thread("thread").thread_id == "thread-2"
