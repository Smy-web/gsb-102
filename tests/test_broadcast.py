from tests.conftest import FakeConnection, FailingConnection, run


def make_frame(message_id, meeting_id=1):
    return {
        "id": message_id,
        "meeting_id": meeting_id,
        "sender_id": 2,
        "content": f"消息 {message_id}",
        "message_type": "text",
        "timestamp": "2026-09-27T10:00:00",
        "sender": None,
    }


def test_sequence_starts_at_one_and_is_monotonic(env):
    conn = FakeConnection()
    run(env.manager.connect(conn, 1))
    run(env.manager.broadcast(make_frame(1), 1))
    run(env.manager.broadcast(make_frame(2), 1))
    run(env.manager.broadcast(make_frame(3), 1))
    assert [frame["seq"] for frame in conn.sent] == [1, 2, 3]


def test_sequence_counters_are_isolated_per_room(env):
    conn_a = FakeConnection()
    conn_b = FakeConnection()
    run(env.manager.connect(conn_a, 1))
    run(env.manager.connect(conn_b, 2))
    run(env.manager.broadcast(make_frame(1, 1), 1))
    run(env.manager.broadcast(make_frame(2, 1), 1))
    run(env.manager.broadcast(make_frame(3, 2), 2))
    assert [frame["seq"] for frame in conn_a.sent] == [1, 2]
    assert [frame["seq"] for frame in conn_b.sent] == [1]


def test_broadcast_does_not_leak_across_rooms(env):
    conn_a = FakeConnection()
    conn_b = FakeConnection()
    run(env.manager.connect(conn_a, 1))
    run(env.manager.connect(conn_b, 2))
    run(env.manager.broadcast(make_frame(1, 1), 1))
    assert len(conn_a.sent) == 1
    assert conn_b.sent == []


def test_broadcast_isolates_failing_connection(env):
    """负例钉住失败隔离：若 broadcast 里的异常处理被去掉、
    send_json 的异常直接冒泡，本测试必须变红。"""
    good = FakeConnection()
    bad = FailingConnection()
    run(env.manager.connect(good, 1))
    run(env.manager.connect(bad, 1))
    run(env.manager.broadcast(make_frame(1), 1))
    assert len(good.sent) == 1


def test_failing_connection_is_dropped_and_skipped_later(env):
    good = FakeConnection()
    bad = FailingConnection()
    run(env.manager.connect(good, 1))
    run(env.manager.connect(bad, 1))
    run(env.manager.broadcast(make_frame(1), 1))
    assert bad not in env.manager.active_connections.get(1, [])

    run(env.manager.broadcast(make_frame(2), 1))
    assert [frame["id"] for frame in good.sent] == [1, 2]
    assert bad not in env.manager.active_connections.get(1, [])


def test_disconnect_during_broadcast_does_not_raise(env):
    manager = env.manager
    other = FakeConnection()

    class DisconnectingConnection(FakeConnection):
        async def send_json(self, data):
            manager.disconnect(other, 1)
            await super().send_json(data)

    first = DisconnectingConnection()
    run(manager.connect(first, 1))
    run(manager.connect(other, 1))
    run(manager.broadcast(make_frame(1), 1))
    assert len(first.sent) == 1
    assert other not in manager.active_connections.get(1, [])


def test_broadcast_frame_keeps_seven_existing_fields_plus_seq(env):
    conn = FakeConnection()
    run(env.manager.connect(conn, 1))
    run(env.manager.broadcast(make_frame(1), 1))
    frame = conn.sent[0]
    for key in ("id", "meeting_id", "sender_id", "content",
                "message_type", "timestamp", "sender"):
        assert key in frame
    assert frame["sender"] is None
    assert frame["seq"] == 1
