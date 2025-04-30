from beanie import Document
from pydantic import Field
from typing import Literal, Optional
from datetime import datetime
import uuid
import pymongo
from pymongo import IndexModel

# --- Enums ---
ConversationType = Literal["regular", "temporary"]
MessageRole = Literal["user", "model"]

# --- Models ---
class Conversation(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: str
    title: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active_at: datetime = Field(default_factory=datetime.utcnow)
    type: ConversationType = "regular"

    class Settings:
        name = "conversations"
        indexes = [
            IndexModel([("user_id", pymongo.ASCENDING)]),
            IndexModel([("user_id", pymongo.ASCENDING), ("type", pymongo.ASCENDING)])
        ]

class Message(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    conversation_id: uuid.UUID
    order: int
    role: MessageRole
    content: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "messages"
        indexes = [
            IndexModel([("conversation_id", pymongo.ASCENDING)]),
            IndexModel([("order", pymongo.DESCENDING)]),
            IndexModel([("conversation_id", pymongo.ASCENDING), ("order", pymongo.DESCENDING)]),
            IndexModel([("conversation_id", pymongo.ASCENDING), ("sent_at", pymongo.DESCENDING)]),
        ]

class ConversationSummary(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    conversation_id: uuid.UUID
    content: str = ""

    class Settings:
        name = "conversation_summaries"
        indexes = [
            IndexModel([("conversation_id", pymongo.ASCENDING)], unique=True),
        ]