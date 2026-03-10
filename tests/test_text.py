from codexbridge.utils.text import chunk_text


def test_chunk_text_keeps_short_message() -> None:
    assert chunk_text("hello world", limit=50) == ["hello world"]


def test_chunk_text_splits_long_message() -> None:
    text = "A" * 30 + "\n\n" + "B" * 30 + "\n\n" + "C" * 30
    chunks = chunk_text(text, limit=40)
    assert len(chunks) == 3
    assert chunks[0] == "A" * 30
    assert chunks[1] == "B" * 30
    assert chunks[2] == "C" * 30
