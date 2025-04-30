from pydantic import BaseModel, Field, ConfigDict
from app.db.models import MessageRole
import uuid
from datetime import datetime

class MessageBase(BaseModel):
    content: str = Field(..., min_length=1)

class MessageCreate(MessageBase):
    pass

class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    order: int
    role: MessageRole
    content: str
    sent_at: datetime
    model_config = ConfigDict(from_attributes=True)