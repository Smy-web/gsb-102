from routers import chat
from tests.conftest import run, seed_meeting
from tests.test_broadcast import make_frame


def broadcast_n(manager, meeting_id, count):
    for i in range(1, count + 1):
        run(manager.broadcast(make_frame(i, meeting_id), meeting_id))


def test_replay_returns_ascending_sequences_without_duplicates(env):
    seed_meeting(env.session_factory, meeting_id=1)
    broadcast_n(env.manager, 1, 5)

    body = env.client.get("/api/chat/1/replay", params={"after_seq": 2}).json()
    seqs = [m["seq"] for m in body["messages"]]
    assert seqs == [3, 4, 5]
    assert len(seqs) == len(set(seqs))
    assert body["gap"] is False
    assert body["latest_seq"] == 5


def test_replay_buffer_evicts_oldest_when_full(env, monkeypatch):
    monkeypatch.setattr(chat, "REPLAY_BUFFER_SIZE", 3)
    seed_meeting(env.session_factory, meeting_id=1)
    broadcast_n(env.manager, 1, 5)

    body = env.client.get("/api/chat/1/replay", params={"after_seq": 0}).json()
    assert [m["seq"] for m in body["messages"]] == [3, 4, 5]
    assert body["gap"] is True
    assert body["latest_seq"] == 5


def test_replay_default_after_seq_returns_whole_window(env):
    seed_meeting(env.session_factory, meeting_id=1)
    broadcast_n(env.manager, 1, 3)

    body = env.client.get("/api/chat/1/replay").json()
    assert [m["seq"] for m in body["messages"]] == [1, 2, 3]
    assert body["gap"] is False


def test_replay_404_for_missing_meeting(env):
    response = env.client.get("/api/chat/999/replay")
    assert response.status_code == 404
    assert response.json()["detail"] == "Meeting not found"


def test_replay_frames_carry_existing_fields(env):
    seed_meeting(env.session_factory, meeting_id=1)
    broadcast_n(env.manager, 1, 2)

    body = env.client.get("/api/chat/1/replay", params={"after_seq": 0}).json()
    frame = body["messages"][0]
    for key in ("id", "meeting_id", "sender_id", "content",
                "message_type", "timestamp", "sender", "seq"):
        assert key in frame
