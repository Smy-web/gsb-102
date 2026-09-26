import asyncio
from collections import namedtuple
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
import models
from routers import chat


class FakeConnection:
    """鸭子类型假连接：只实现 accept / send_json。"""

    def __init__(self):
        self.accepted = False
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        self.sent.append(data)


class FailingConnection(FakeConnection):
    """send_json 永远抛异常的坏连接。"""

    async def send_json(self, data):
        raise RuntimeError("connection broken")


Env = namedtuple("Env", ["client", "manager", "session_factory"])


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(chat.router)
    app.dependency_overrides[get_db] = override_get_db

    manager = chat.ConnectionManager()
    monkeypatch.setattr(chat, "manager", manager)

    with TestClient(app) as test_client:
        yield Env(test_client, manager, TestingSessionLocal)


def run(coro):
    return asyncio.run(coro)


def seed_meeting(session_factory, meeting_id=1):
    db = session_factory()
    try:
        designer = models.User(
            name="张造景", role="designer", email=f"designer{meeting_id}@example.com"
        )
        client_user = models.User(
            name="李先生", role="client", email=f"client{meeting_id}@example.com"
        )
        db.add_all([designer, client_user])
        db.commit()
        db.refresh(designer)
        db.refresh(client_user)
        meeting = models.Meeting(
            id=meeting_id,
            title=f"方案沟通会 {meeting_id}",
            designer_id=designer.id,
            client_id=client_user.id,
            scheduled_at=datetime(2026, 9, 27, 10, 0, 0),
        )
        db.add(meeting)
        db.commit()
        return designer.id, client_user.id
    finally:
        db.close()
