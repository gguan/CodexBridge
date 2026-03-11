from codexbridge.utils.text import chunk_display_text, chunk_text, normalize_display_text
from codexbridge.codex.executor import CodexExecutor


def test_chunk_text_keeps_short_message() -> None:
    assert chunk_text("hello world", limit=50) == ["hello world"]


def test_chunk_text_splits_long_message() -> None:
    text = "A" * 30 + "\n\n" + "B" * 30 + "\n\n" + "C" * 30
    chunks = chunk_text(text, limit=40)
    assert len(chunks) == 3
    assert chunks[0] == "A" * 30
    assert chunks[1] == "B" * 30
    assert chunks[2] == "C" * 30


def test_windows_path_converts_to_wsl() -> None:
    assert CodexExecutor.to_wsl_path(r"D:\Projects\CodexBridge") == "/mnt/d/Projects/CodexBridge"


def test_normalize_display_text_removes_ansi_and_extra_spacing() -> None:
    raw = "line1\x1b[31m\n\n\nline2  \n"
    assert normalize_display_text(raw) == "line1\n\nline2"


def test_chunk_display_text_adds_part_labels_for_multi_chunk() -> None:
    text = "A" * 80 + "\n\n" + "B" * 80
    chunks = chunk_display_text(text, limit=90)
    assert len(chunks) > 1
    assert chunks[0].startswith(f"[Part 1/{len(chunks)}]")
    assert chunks[-1].startswith(f"[Part {len(chunks)}/{len(chunks)}]")
