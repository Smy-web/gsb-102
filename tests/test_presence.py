import json

from tests.conftest import FakeConnection, run, seed_meeting


def test_presence_reports_connections_and_users(env):
    seed_meeting(env.session_factory, meeting_id=1)
    alice = FakeConnection()
    bob = FakeConnection()
    run(env.manager.connect(alice, 1, user_id=7))
    run(env.manager.connect(bob, 1, user_id=9))

    body = env.client.get("/api/chat/1/presence").json()
    assert body["connection_count"] == 2
    assert body["online_users"] == [7, 9]
    assert body["anonymous_count"] == 0


def test_presence_counts_anonymous_connections(env):
    seed_meeting(env.session_factory, meeting_id=1)
    identified = FakeConnection()
    anon_a = FakeConnection()
    anon_b = FakeConnection()
    run(env.manager.connect(identified, 1, user_id=7))
    run(env.manager.connect(anon_a, 1))
    run(env.manager.connect(anon_b, 1))

    body = env.client.get("/api/chat/1/presence").json()
    assert body["connection_count"] == 3
    assert body["online_users"] == [7]
    assert body["anonymous_count"] == 2


def test_presence_drops_disconnected_connection_immediately(env):
    seed_meeting(env.session_factory, meeting_id=1)
    alice = FakeConnection()
    bob = FakeConnection()
    run(env.manager.connect(alice, 1, user_id=7))
    run(env.manager.connect(bob, 1, user_id=9))
    env.manager.disconnect(alice, 1)

    body = env.client.get("/api/chat/1/presence").json()
    assert body["connection_count"] == 1
    assert body["online_users"] == [9]
    assert body["anonymous_count"] == 0


def test_presence_404_for_missing_meeting(env):
    response = env.client.get("/api/chat/999/presence")
    assert response.status_code == 404
    assert response.json()["detail"] == "Meeting not found"


def test_websocket_connects_without_identity(env):
    _, client_id = seed_meeting(env.session_factory, meeting_id=1)
    with env.client.websocket_connect("/api/chat/ws/1") as ws:
        ws.send_text(json.dumps({
            "user_id": client_id,
            "content": "不带身份参数也能正常聊天",
            "message_type": "text",
        }))
        frame = ws.receive_json()
    assert frame["content"] == "不带身份参数也能正常聊天"
    assert frame["sender_id"] == client_id


def test_presence_reflects_live_websocket_identity(env):
    seed_meeting(env.session_factory, meeting_id=1)
    with env.client.websocket_connect("/api/chat/ws/1?user_id=5"):
        body = env.client.get("/api/chat/1/presence").json()
        assert body["connection_count"] == 1
        assert body["online_users"] == [5]
        assert body["anonymous_count"] == 0
    body = env.client.get("/api/chat/1/presence").json()
    assert body["connection_count"] == 0
    assert body["online_users"] == []
