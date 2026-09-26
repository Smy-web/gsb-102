from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class UserBase(BaseModel):
    name: str
    role: str
    email: str
    avatar: Optional[str] = None

class UserCreate(UserBase):
    pass

class UserResponse(UserBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class MaterialBase(BaseModel):
    name: str
    category: str
    description: str
    image_url: str
    properties: Dict[str, Any]
    price: Optional[str] = None
    origin: Optional[str] = None

class MaterialCreate(MaterialBase):
    pass

class MaterialResponse(MaterialBase):
    id: int
    
    class Config:
        from_attributes = True

class CaseStudyBase(BaseModel):
    title: str
    style: str
    description: str
    thumbnail_url: str
    gallery_urls: List[str]
    materials_used: List[str]
    plants: List[str]
    difficulty: str
    tank_size: str

class CaseStudyCreate(CaseStudyBase):
    pass

class CaseStudyResponse(CaseStudyBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class MessageBase(BaseModel):
    meeting_id: int
    sender_id: int
    content: str
    message_type: str = "text"

class MessageCreate(MessageBase):
    pass

class MessageResponse(MessageBase):
    id: int
    timestamp: datetime
    sender: Optional[UserResponse]
    
    class Config:
        from_attributes = True

class MeetingBase(BaseModel):
    title: str
    designer_id: int
    client_id: int
    scheduled_at: datetime
    status: str = "pending"

class MeetingCreate(MeetingBase):
    pass

class MeetingResponse(MeetingBase):
    id: int
    created_at: datetime
    designer: Optional[UserResponse] = None
    client: Optional[UserResponse] = None
    messages: List[MessageResponse] = []
    
    class Config:
        from_attributes = True

class AudioRecordBase(BaseModel):
    meeting_id: int
    original_file_path: str
    duration: int
    status: str = "processing"

class AudioRecordCreate(AudioRecordBase):
    pass

class AudioRecordResponse(AudioRecordBase):
    id: int
    processed_file_path: Optional[str] = None
    transcription: Optional[str] = None
    diarization_result: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class MeetingSummaryBase(BaseModel):
    meeting_id: int
    landscape_theme: Optional[str] = None
    plant_combinations: Optional[List[str]] = None
    construction_steps: Optional[List[str]] = None
    maintenance_guide: Optional[str] = None
    full_summary: Optional[str] = None
    certificate_markdown: Optional[str] = None

class MeetingSummaryCreate(MeetingSummaryBase):
    pass

class MeetingSummaryResponse(MeetingSummaryBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class TranscriptionSegment(BaseModel):
    start: float
    end: float
    text: str
    speaker: Optional[str] = None

class AudioProcessRequest(BaseModel):
    meeting_id: int
    audio_url: Optional[str] = None

class SummaryGenerateRequest(BaseModel):
    meeting_id: int
    transcription_text: str
    diarization_result: Optional[Dict[str, Any]] = None

class ChatMessage(BaseModel):
    meeting_id: int
    user_id: int
    content: str
    sender_role: str
