import json

from tests.conftest import seed_meeting


def test_websocket_broadcast_frame_has_all_fields(env):
    _, client_id = seed_meeting(env.session_factory, meeting_id=1)
    with env.client.websocket_connect(f"/api/chat/ws/1?user_id={client_id}") as ws:
        ws.send_text(json.dumps({
            "user_id": client_id,
            "content": "我想做一个60cm的生态缸",
            "message_type": "text",
        }))
        frame = ws.receive_json()

    for key in ("id", "meeting_id", "sender_id", "content",
                "message_type", "timestamp", "sender", "seq"):
        assert key in frame
    assert frame["seq"] == 1
    assert frame["sender"]["name"] == "李先生"


def test_websocket_sender_is_null_when_user_not_found(env):
    seed_meeting(env.session_factory, meeting_id=1)
    with env.client.websocket_connect("/api/chat/ws/1") as ws:
        ws.send_text(json.dumps({
            "user_id": 424242,
            "content": "查无此人",
            "message_type": "text",
        }))
        frame = ws.receive_json()
    assert "sender" in frame
    assert frame["sender"] is None


def test_existing_rest_endpoints_still_work(env):
    designer_id, client_id = seed_meeting(env.session_factory, meeting_id=1)

    response = env.client.post("/api/chat/message", json={
        "meeting_id": 1,
        "sender_id": client_id,
        "content": "第一条",
        "message_type": "text",
    })
    assert response.status_code == 200
    message_id = response.json()["id"]

    response = env.client.post("/api/chat/message", json={
        "meeting_id": 1,
        "sender_id": designer_id,
        "content": "第二条",
        "message_type": "text",
    })
    assert response.status_code == 200

    messages = env.client.get("/api/chat/1/messages").json()
    assert [m["content"] for m in messages] == ["第一条", "第二条"]

    response = env.client.get("/api/chat/999/messages")
    assert response.status_code == 404
    assert response.json()["detail"] == "Meeting not found"

    response = env.client.delete(f"/api/chat/message/{message_id}")
    assert response.status_code == 200
    response = env.client.delete("/api/chat/message/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Message not found"
