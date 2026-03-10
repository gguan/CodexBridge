from pathlib import Path

from codexbridge.storage.session_store import SessionStore


def test_session_store_round_trip(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.db")
    store.initialize()

    session = store.create_or_get_session(1, 42, tmp_path)
    assert session.chat_id == 1
    assert session.telegram_user_id == 42

    store.append_message(1, "user", "hello")
    store.append_message(1, "assistant", "world")

    messages = store.list_messages(1)
    assert [message.role for message in messages] == ["user", "assistant"]
    assert [message.content for message in messages] == ["hello", "world"]

    updated = store.set_project(1, tmp_path / "repo")
    assert updated.project_path == tmp_path / "repo"

    reset = store.reset_session(1, 42, tmp_path)
    assert reset.chat_id == 1
    assert store.count_messages(1) == 0
