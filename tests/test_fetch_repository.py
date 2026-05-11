from __future__ import annotations

import pytest

from app.db.repositories.fetch import FetchRepository
from tests.fakes import FakeDb


def test_fetch_repository_get_conversation() -> None:
    db = FakeDb()
    repo = FetchRepository(db.connection)
    conversation = repo.create_conversation(user_id=1, title="One")
    got = repo.get_conversation(1, conversation.conversation_id)
    assert got is not None
    assert got.title == "One"
    assert repo.get_conversation(1, "00000000-0000-0000-0000-000000000000") is None


def test_fetch_repository_creates_and_lists_conversations() -> None:
    db = FakeDb()
    repo = FetchRepository(db.connection)

    conversation = repo.create_conversation(user_id=1, title="  First   Fetch thread  ")
    conversations = repo.list_conversations(user_id=1)

    assert conversation.title == "First Fetch thread"
    assert conversations[0].conversation_id == conversation.conversation_id
    assert conversations[0].message_count == 0
    assert any("INSERT INTO fetch_conversations" in statement for statement, _ in db.statements)


def test_fetch_repository_renames_and_soft_deletes_conversation() -> None:
    db = FakeDb()
    repo = FetchRepository(db.connection)
    conversation = repo.create_conversation(user_id=1, title="Original")

    repo.rename_conversation(user_id=1, conversation_id=conversation.conversation_id, title="New name")
    renamed = repo.list_conversations(user_id=1)
    repo.soft_delete_conversation(user_id=1, conversation_id=conversation.conversation_id)

    assert renamed[0].title == "New name"
    assert repo.list_conversations(user_id=1) == []


def test_fetch_repository_appends_and_lists_messages() -> None:
    db = FakeDb()
    repo = FetchRepository(db.connection)
    conversation = repo.create_conversation(user_id=1, title="Messages")

    repo.append_message(
        user_id=1,
        conversation_id=conversation.conversation_id,
        role="user",
        content="What is invoice 123456 doing?",
        route_key="local",
    )
    repo.append_message(
        user_id=1,
        conversation_id=conversation.conversation_id,
        role="assistant",
        content="Fetch routing is still disabled.",
        route_key="disabled",
        model_label="model not connected",
        context_percent=0,
        context_state="ready",
        metadata={"source_cards": [{"kind": "docs", "title": "Switch Manual"}]},
    )

    messages = repo.list_messages(user_id=1, conversation_id=conversation.conversation_id)
    conversations = repo.list_conversations(user_id=1)

    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[1].route_key == "disabled"
    assert messages[1].model_label == "model not connected"
    assert messages[1].metadata == {"source_cards": [{"kind": "docs", "title": "Switch Manual"}]}
    assert conversations[0].message_count == 2
    assert conversations[0].route_state == "disabled"


def test_fetch_repository_rejects_unknown_message_role() -> None:
    db = FakeDb()
    repo = FetchRepository(db.connection)
    conversation = repo.create_conversation(user_id=1, title="Messages")

    with pytest.raises(ValueError, match="Invalid Fetch message role"):
        repo.append_message(
            user_id=1,
            conversation_id=conversation.conversation_id,
            role="tool",
            content="not allowed yet",
        )
