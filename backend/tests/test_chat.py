"""Test cases for the chat API.

The suite is organised around the things that can independently break:
  1. session lifecycle      - can a conversation be started, listed, and deleted?
  2. session titles         - are titles auto-set from the first message, and renameable?
  3. streaming contract     - does the wire format match what the client parses?
  4. persistence            - do both sides of the turn reach the database?
  5. conversational memory  - is prior history actually replayed to the model?

Provider-specific behaviour lives in test_groq_provider.py; the rate limiter
in test_rate_limit.py.
"""

import json

from fakes import FakeLLM
from src.dependencies import get_llm
from src.main import app


def use_llm(fake):
    """Swap in a differently-scripted model for one test.

    The `client` fixture clears overrides on teardown, so this is contained.
    """
    app.dependency_overrides[get_llm] = lambda: fake
    return fake


def sse_events(response):
    """Parse an SSE body into the list of JSON payloads the browser would see."""
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def start_session(client):
    return client.post("/sessions").json()["session_id"]


# --- 1. session lifecycle ----------------------------------------------------


def test_create_session_returns_id_and_persists_it(client, db):
    session_id = start_session(client)

    assert session_id
    assert [r["id"] for r in db.rows("sessions")] == [session_id]


def test_history_starts_empty(client):
    session_id = start_session(client)

    assert client.get(f"/sessions/{session_id}/messages").json() == []


def test_deleting_a_session_removes_it_and_its_messages(client, db):
    session_id = start_session(client)
    client.post("/chat/stream", json={"session_id": session_id, "message": "hi"})

    client.delete(f"/sessions/{session_id}")

    assert db.rows("sessions") == []
    assert db.rows("messages") == []


def test_deleting_one_session_leaves_the_other_intact(client):
    kept = start_session(client)
    dropped = start_session(client)
    for sid in (kept, dropped):
        client.post("/chat/stream", json={"session_id": sid, "message": "hi"})

    client.delete(f"/sessions/{dropped}")

    assert len(client.get(f"/sessions/{kept}/messages").json()) == 2
    assert [s["id"] for s in client.get("/sessions").json()] == [kept]


def test_deleted_session_cannot_be_chatted_with_again(client):
    session_id = start_session(client)
    client.delete(f"/sessions/{session_id}")

    response = client.post(
        "/chat/stream", json={"session_id": session_id, "message": "hi"}
    )

    assert response.status_code == 404


# --- session listing & renaming -----------------------------------------------


def test_new_session_has_no_title(client):
    session_id = start_session(client)

    sessions = client.get("/sessions").json()
    assert sessions == [{"id": session_id, "title": None, "created_at": sessions[0]["created_at"]}]


def test_first_message_sets_the_title(client):
    session_id = start_session(client)

    client.post(
        "/chat/stream", json={"session_id": session_id, "message": "tell me about maistorage"}
    )

    sessions = client.get("/sessions").json()
    assert sessions[0]["title"] == "tell me about maistorage"


def test_long_first_message_is_truncated_into_a_title(client):
    session_id = start_session(client)
    long_message = "x" * 80

    client.post("/chat/stream", json={"session_id": session_id, "message": long_message})

    title = client.get("/sessions").json()[0]["title"]
    assert len(title) == 50
    assert title.endswith("…")


def test_second_message_does_not_overwrite_the_title(client):
    session_id = start_session(client)
    client.post("/chat/stream", json={"session_id": session_id, "message": "first"})

    client.post("/chat/stream", json={"session_id": session_id, "message": "second"})

    assert client.get("/sessions").json()[0]["title"] == "first"


def test_sessions_are_listed_newest_first(client):
    older = start_session(client)
    newer = start_session(client)

    ids = [s["id"] for s in client.get("/sessions").json()]
    assert ids == [newer, older]


def test_rename_session(client):
    session_id = start_session(client)

    response = client.patch(f"/sessions/{session_id}", json={"title": "My renamed chat"})

    assert response.status_code == 200
    assert client.get("/sessions").json()[0]["title"] == "My renamed chat"


def test_renaming_unknown_session_is_rejected(client):
    response = client.patch(
        "/sessions/11111111-1111-1111-1111-111111111111", json={"title": "x"}
    )

    assert response.status_code == 404


def test_renaming_with_an_empty_title_is_rejected(client):
    session_id = start_session(client)

    response = client.patch(f"/sessions/{session_id}", json={"title": ""})

    assert response.status_code == 422


def test_unknown_session_is_rejected(client):
    response = client.post(
        "/chat/stream",
        json={"session_id": "11111111-1111-1111-1111-111111111111", "message": "hi"},
    )

    assert response.status_code == 404


# --- 2. streaming contract ---------------------------------------------------


def test_response_is_sent_as_an_event_stream(client):
    session_id = start_session(client)

    response = client.post(
        "/chat/stream", json={"session_id": session_id, "message": "hi"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


def test_tokens_arrive_individually_and_end_with_done(client):
    session_id = start_session(client)

    response = client.post(
        "/chat/stream", json={"session_id": session_id, "message": "hi"}
    )

    events = sse_events(response)
    # One frame per token proves we are not buffering the whole reply and
    # flushing it in a single chunk, which would defeat the point of streaming.
    assert [e["content"] for e in events[:-1]] == ["Hello", " there", "!"]
    assert events[-1] == {"done": True}


def test_provider_failure_is_reported_as_an_error_frame(client):
    use_llm(FakeLLM(error=RuntimeError("rate limited")))
    session_id = start_session(client)

    response = client.post(
        "/chat/stream", json={"session_id": session_id, "message": "hi"}
    )

    events = sse_events(response)
    # The stream has already returned 200 by the time the provider fails, so the
    # failure has to travel in-band rather than as an HTTP status.
    assert response.status_code == 200
    assert "rate limited" in events[-1]["error"]


def test_failed_turn_does_not_persist_a_partial_reply(client):
    use_llm(FakeLLM(error=RuntimeError("boom")))
    session_id = start_session(client)

    client.post("/chat/stream", json={"session_id": session_id, "message": "hi"})

    roles = [m["role"] for m in client.get(f"/sessions/{session_id}/messages").json()]
    assert roles == ["user"]


# --- 3. persistence ----------------------------------------------------------


def test_both_sides_of_a_turn_are_stored_in_order(client):
    session_id = start_session(client)

    client.post("/chat/stream", json={"session_id": session_id, "message": "hi"})

    stored = client.get(f"/sessions/{session_id}/messages").json()
    assert [(m["role"], m["content"]) for m in stored] == [
        ("user", "hi"),
        ("assistant", "Hello there!"),
    ]


def test_assistant_message_is_the_full_concatenated_stream(client):
    session_id = start_session(client)

    response = client.post(
        "/chat/stream", json={"session_id": session_id, "message": "hi"}
    )

    streamed = "".join(e["content"] for e in sse_events(response)[:-1])
    stored = client.get(f"/sessions/{session_id}/messages").json()[-1]["content"]
    # What the user watched appear must equal what a page reload replays.
    assert stored == streamed


def test_messages_from_other_sessions_are_not_returned(client):
    first = start_session(client)
    second = start_session(client)
    client.post("/chat/stream", json={"session_id": first, "message": "first"})

    assert client.get(f"/sessions/{second}/messages").json() == []


# --- 4. conversational memory ------------------------------------------------


def test_first_turn_sends_only_the_new_message(client, llm):
    session_id = start_session(client)

    client.post("/chat/stream", json={"session_id": session_id, "message": "hi"})

    assert llm.last_messages == [{"role": "user", "content": "hi"}]


def test_later_turns_replay_the_whole_conversation(client, llm):
    session_id = start_session(client)

    client.post(
        "/chat/stream", json={"session_id": session_id, "message": "my name is Zaied"}
    )
    client.post(
        "/chat/stream", json={"session_id": session_id, "message": "what is my name?"}
    )

    # This is the test that actually pins down "the LLM remembers": the second
    # call must carry turn one's question *and* answer, not just the new prompt.
    assert llm.last_messages == [
        {"role": "user", "content": "my name is Zaied"},
        {"role": "assistant", "content": "Hello there!"},
        {"role": "user", "content": "what is my name?"},
    ]


def test_each_session_has_its_own_memory(client, llm):
    first = start_session(client)
    second = start_session(client)
    client.post("/chat/stream", json={"session_id": first, "message": "remember this"})

    client.post("/chat/stream", json={"session_id": second, "message": "fresh start"})

    assert llm.last_messages == [{"role": "user", "content": "fresh start"}]


def test_new_session_after_a_delete_starts_with_no_memory(client, llm):
    old_session = start_session(client)
    client.post("/chat/stream", json={"session_id": old_session, "message": "old"})
    client.delete(f"/sessions/{old_session}")

    new_session = start_session(client)
    client.post("/chat/stream", json={"session_id": new_session, "message": "new"})

    assert llm.last_messages == [{"role": "user", "content": "new"}]


def test_system_prompt_goes_to_the_provider_not_into_the_history(client, llm):
    session_id = start_session(client)

    client.post("/chat/stream", json={"session_id": session_id, "message": "hi"})

    # The provider decides how to attach the system prompt; the stored
    # conversation must stay clean so a reload shows only real turns.
    assert llm.last_system_prompt == "You are a test assistant."
    assert llm.last_messages == [{"role": "user", "content": "hi"}]
