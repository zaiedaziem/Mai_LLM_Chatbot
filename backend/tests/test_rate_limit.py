"""Rate limiter tests. The limit is patched low so they run in milliseconds."""
from src import config


def send(client, session_id):
    return client.post("/chat/stream", json={"session_id": session_id, "message": "hi"})


def test_requests_under_the_limit_succeed(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_REQUESTS", 3)
    session_id = client.post("/sessions").json()["session_id"]

    assert all(send(client, session_id).status_code == 200 for _ in range(3))


def test_request_over_the_limit_gets_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_REQUESTS", 2)
    session_id = client.post("/sessions").json()["session_id"]
    send(client, session_id)
    send(client, session_id)

    response = send(client, session_id)

    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_rejected_request_is_not_persisted(client, monkeypatch):
    # The limiter runs before the handler, so a blocked message must never
    # reach the database -- otherwise a reload would show a turn with no reply.
    monkeypatch.setattr(config, "RATE_LIMIT_REQUESTS", 1)
    session_id = client.post("/sessions").json()["session_id"]
    send(client, session_id)

    send(client, session_id)  # blocked

    assert len(client.get(f"/sessions/{session_id}/messages").json()) == 2


def test_limit_does_not_apply_to_cheap_endpoints(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_REQUESTS", 1)
    session_id = client.post("/sessions").json()["session_id"]
    send(client, session_id)  # uses up the one allowed

    assert client.get("/sessions").status_code == 200
    assert client.get(f"/sessions/{session_id}/messages").status_code == 200
    assert client.post("/sessions").status_code == 200
