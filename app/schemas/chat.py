from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
import uuid
from datetime import datetime
from app.schemas.message import MessageCreate, MessageResponse
from app.db.models import ConversationType

class ConversationCreate(BaseModel):
    user_id: str = Field(..., description="ID của người dùng (placeholder)")
    first_message: MessageCreate

class ConversationResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    title: Optional[str] = None
    created_at: datetime
    last_active_at: datetime
    type: ConversationType
    first_llm_response: MessageResponse

    class Config:
        orm_mode = True

class NewMessageRequest(BaseModel):
    user_id: str = Field(..., description="ID của người dùng (placeholder - nên lấy từ auth)")
    message: MessageCreate

class NewMessageResponse(BaseModel):
    llm_response: MessageResponse

    class Config:
        orm_mode = True

class TemporaryChatRequest(BaseModel):
    user_id: str = Field(..., description="ID của người dùng (placeholder - nên lấy từ auth)")
    message: MessageCreate
    conversation_id: Optional[uuid.UUID] = None

class TemporaryChatResponse(BaseModel):
    conversation_id: uuid.UUID
    llm_response: MessageResponse

    class Config:
        orm_mode = True

class ConversationInfo(BaseModel):
    """Schema rút gọn chứa thông tin cần thiết cho danh sách conversations."""
    id: uuid.UUID
    title: Optional[str] = None
    last_active_at: datetime

    model_config = ConfigDict(from_attributes=True)