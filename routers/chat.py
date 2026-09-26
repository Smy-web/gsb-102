from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from datetime import datetime
from collections import deque
import json
import logging
import os

from database import get_db
from models import Message, Meeting, User
from schemas import MessageCreate, MessageResponse, ChatMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 每个房间在服务端保留的最近消息条数（用于掉线补发），可用环境变量覆盖。
REPLAY_BUFFER_SIZE = int(os.getenv("CHAT_REPLAY_BUFFER_SIZE", "50"))

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.connection_identities: Dict[int, Dict[WebSocket, int]] = {}
        self.sequence_counters: Dict[int, int] = {}
        self.replay_buffers: Dict[int, deque] = {}

    async def connect(self, websocket: WebSocket, meeting_id: int, user_id: Optional[int] = None):
        await websocket.accept()
        if meeting_id not in self.active_connections:
            self.active_connections[meeting_id] = []
        self.active_connections[meeting_id].append(websocket)
        if user_id is not None:
            self.connection_identities.setdefault(meeting_id, {})[websocket] = user_id

    def disconnect(self, websocket: WebSocket, meeting_id: int):
        if meeting_id in self.active_connections:
            if websocket in self.active_connections[meeting_id]:
                self.active_connections[meeting_id].remove(websocket)
            if not self.active_connections[meeting_id]:
                del self.active_connections[meeting_id]
        identities = self.connection_identities.get(meeting_id)
        if identities is not None:
            identities.pop(websocket, None)
            if not identities:
                del self.connection_identities[meeting_id]

    def presence(self, meeting_id: int) -> dict:
        connections = self.active_connections.get(meeting_id, [])
        identities = self.connection_identities.get(meeting_id, {})
        identified = [c for c in connections if c in identities]
        return {
            "meeting_id": meeting_id,
            "connection_count": len(connections),
            "online_users": sorted({identities[c] for c in identified}),
            "anonymous_count": len(connections) - len(identified),
        }

    def _next_sequence(self, meeting_id: int) -> int:
        self.sequence_counters[meeting_id] = self.sequence_counters.get(meeting_id, 0) + 1
        return self.sequence_counters[meeting_id]

    def _replay_buffer(self, meeting_id: int) -> deque:
        if meeting_id not in self.replay_buffers:
            self.replay_buffers[meeting_id] = deque(maxlen=REPLAY_BUFFER_SIZE)
        return self.replay_buffers[meeting_id]

    async def broadcast(self, message: dict, meeting_id: int):
        seq = self._next_sequence(meeting_id)
        frame = dict(message)
        frame["seq"] = seq
        self._replay_buffer(meeting_id).append(frame)
        # 遍历快照，广播途中有人 disconnect 也不会改到正在遍历的列表。
        connections = list(self.active_connections.get(meeting_id, []))
        stale = []
        for connection in connections:
            try:
                await connection.send_json(frame)
            except Exception:
                logger.warning(
                    "send_json failed for a connection in meeting %s; dropping it",
                    meeting_id,
                    exc_info=True,
                )
                stale.append(connection)
        for connection in stale:
            self.disconnect(connection, meeting_id)

    def replay(self, meeting_id: int, after_seq: int) -> dict:
        buffer = self._replay_buffer(meeting_id)
        latest_seq = self.sequence_counters.get(meeting_id, 0)
        seen = set()
        messages = []
        for frame in buffer:
            seq = frame["seq"]
            if seq > after_seq and seq not in seen:
                seen.add(seq)
                messages.append(frame)
        messages.sort(key=lambda frame: frame["seq"])
        oldest_seq = buffer[0]["seq"] if buffer else None
        if oldest_seq is None:
            gap = after_seq < latest_seq
        else:
            gap = after_seq < oldest_seq - 1
        return {
            "meeting_id": meeting_id,
            "messages": messages,
            "gap": gap,
            "latest_seq": latest_seq,
        }

manager = ConnectionManager()

@router.get("/{meeting_id}/messages", response_model=List[MessageResponse])
def get_meeting_messages(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    messages = db.query(Message).filter(
        Message.meeting_id == meeting_id
    ).order_by(Message.timestamp.asc()).all()
    
    if not messages:
        return [
            {
                "id": 1,
                "meeting_id": meeting_id,
                "sender_id": 1,
                "content": "您好！欢迎来到生态缸造景设计咨询。请问您有什么具体的需求吗？",
                "message_type": "text",
                "timestamp": datetime.now().isoformat(),
                "sender": {"id": 1, "name": "张造景", "role": "designer", "email": "designer@example.com", "avatar": None}
            },
            {
                "id": 2,
                "meeting_id": meeting_id,
                "sender_id": 2,
                "content": "我想做一个60cm的生态缸，喜欢ADA自然风格，希望能营造森林的感觉。",
                "message_type": "text",
                "timestamp": datetime.now().isoformat(),
                "sender": {"id": 2, "name": "李先生", "role": "client", "email": "client@example.com", "avatar": None}
            }
        ]
    
    return messages

@router.post("/message", response_model=MessageResponse)
def send_message(message: MessageCreate, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == message.meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    db_message = Message(**message.model_dump())
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    
    sender = db.query(User).filter(User.id == message.sender_id).first()
    
    return {
        "id": db_message.id,
        "meeting_id": db_message.meeting_id,
        "sender_id": db_message.sender_id,
        "content": db_message.content,
        "message_type": db_message.message_type,
        "timestamp": db_message.timestamp,
        "sender": sender
    }

@router.get("/{meeting_id}/presence")
def get_meeting_presence(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return manager.presence(meeting_id)

@router.get("/{meeting_id}/replay")
def replay_meeting_messages(meeting_id: int, after_seq: int = 0, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return manager.replay(meeting_id, after_seq)

@router.websocket("/ws/{meeting_id}")
async def websocket_endpoint(websocket: WebSocket, meeting_id: int, db: Session = Depends(get_db)):
    raw_user_id = websocket.query_params.get("user_id")
    try:
        user_id = int(raw_user_id) if raw_user_id is not None else None
    except ValueError:
        user_id = None
    await manager.connect(websocket, meeting_id, user_id=user_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            db_message = Message(
                meeting_id=meeting_id,
                sender_id=message_data.get("user_id"),
                content=message_data.get("content"),
                message_type=message_data.get("message_type", "text")
            )
            db.add(db_message)
            db.commit()
            db.refresh(db_message)
            
            sender = db.query(User).filter(User.id == message_data.get("user_id")).first()
            
            response = {
                "id": db_message.id,
                "meeting_id": meeting_id,
                "sender_id": message_data.get("user_id"),
                "content": message_data.get("content"),
                "message_type": message_data.get("message_type", "text"),
                "timestamp": db_message.timestamp.isoformat(),
                "sender": {
                    "id": sender.id,
                    "name": sender.name,
                    "role": sender.role,
                    "avatar": sender.avatar
                } if sender else None
            }
            
            await manager.broadcast(response, meeting_id)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, meeting_id)
    except Exception:
        logger.exception("WebSocket error in meeting %s", meeting_id)
        manager.disconnect(websocket, meeting_id)

@router.delete("/message/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db)):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    db.delete(message)
    db.commit()
    return {"message": "Message deleted successfully"}
