from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    role = Column(String(20))
    email = Column(String(100), unique=True, index=True)
    avatar = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    messages = relationship("Message", back_populates="sender")
    meetings_as_designer = relationship("Meeting", foreign_keys="Meeting.designer_id", back_populates="designer")
    meetings_as_client = relationship("Meeting", foreign_keys="Meeting.client_id", back_populates="client")

class Material(Base):
    __tablename__ = "materials"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    category = Column(String(50))
    description = Column(Text)
    image_url = Column(String(255))
    properties = Column(JSON)
    price = Column(String(50), nullable=True)
    origin = Column(String(100), nullable=True)

class CaseStudy(Base):
    __tablename__ = "case_studies"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    style = Column(String(50))
    description = Column(Text)
    thumbnail_url = Column(String(255))
    gallery_urls = Column(JSON)
    materials_used = Column(JSON)
    plants = Column(JSON)
    difficulty = Column(String(20))
    tank_size = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

class Meeting(Base):
    __tablename__ = "meetings"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    designer_id = Column(Integer, ForeignKey("users.id"))
    client_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String(20), default="pending")
    scheduled_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    designer = relationship("User", foreign_keys=[designer_id], back_populates="meetings_as_designer")
    client = relationship("User", foreign_keys=[client_id], back_populates="meetings_as_client")
    messages = relationship("Message", back_populates="meeting", cascade="all, delete-orphan")
    audio_records = relationship("AudioRecord", back_populates="meeting", cascade="all, delete-orphan")
    summaries = relationship("MeetingSummary", back_populates="meeting", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    sender_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text)
    message_type = Column(String(20), default="text")
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    sender = relationship("User", back_populates="messages")
    meeting = relationship("Meeting", back_populates="messages")

class AudioRecord(Base):
    __tablename__ = "audio_records"
    
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    original_file_path = Column(String(255))
    processed_file_path = Column(String(255), nullable=True)
    duration = Column(Integer)
    transcription = Column(Text, nullable=True)
    diarization_result = Column(JSON, nullable=True)
    status = Column(String(20), default="processing")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    meeting = relationship("Meeting", back_populates="audio_records")

class MeetingSummary(Base):
    __tablename__ = "meeting_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    landscape_theme = Column(String(200), nullable=True)
    plant_combinations = Column(JSON, nullable=True)
    construction_steps = Column(JSON, nullable=True)
    maintenance_guide = Column(Text, nullable=True)
    full_summary = Column(Text, nullable=True)
    certificate_markdown = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    meeting = relationship("Meeting", back_populates="summaries")
