from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Dict
from datetime import datetime
import json

from database import get_db
from models import Message, Meeting, User
from schemas import MessageCreate, MessageResponse, ChatMessage

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, meeting_id: int):
        await websocket.accept()
        if meeting_id not in self.active_connections:
            self.active_connections[meeting_id] = []
        self.active_connections[meeting_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, meeting_id: int):
        if meeting_id in self.active_connections:
            if websocket in self.active_connections[meeting_id]:
                self.active_connections[meeting_id].remove(websocket)
            if not self.active_connections[meeting_id]:
                del self.active_connections[meeting_id]
    
    async def broadcast(self, message: dict, meeting_id: int):
        if meeting_id in self.active_connections:
            for connection in self.active_connections[meeting_id]:
                await connection.send_json(message)

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

@router.websocket("/ws/{meeting_id}")
async def websocket_endpoint(websocket: WebSocket, meeting_id: int, db: Session = Depends(get_db)):
    await manager.connect(websocket, meeting_id)
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
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, meeting_id)

@router.delete("/message/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db)):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    db.delete(message)
    db.commit()
    return {"message": "Message deleted successfully"}
