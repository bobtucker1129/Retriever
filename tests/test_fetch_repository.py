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


def test_fetch_repository_adopts_same_email_legacy_conversations() -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Current User", "active")
    db.add_user("legacy-row", "Legacy User", "active")
    current_id = db.users["fetcher@boonegraphics.net"]["id"]
    legacy_id = db.users["legacy-row"]["id"]
    db.users["legacy-row"]["cloudflare_email"] = "fetcher@boonegraphics.net"
    db.users["legacy-row"]["email"] = "fetcher@boonegraphics.net"
    db.users["legacy-row"]["username"] = "fetcher@boonegraphics.net"

    repo = FetchRepository(db.connection)
    conversation = repo.create_conversation(user_id=legacy_id, title="Legacy thread")
    repo.append_message(
        user_id=legacy_id,
        conversation_id=conversation.conversation_id,
        role="user",
        content="Where did my history go?",
    )

    adopted = repo.adopt_conversations_for_identity(
        user_id=current_id,
        email="FETCHER@boonegraphics.net",
    )

    assert adopted == 1
    assert repo.list_conversations(current_id)[0].title == "Legacy thread"
    assert repo.list_messages(current_id, conversation.conversation_id)[0].content == (
        "Where did my history go?"
    )
    assert repo.list_conversations(legacy_id) == []


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
