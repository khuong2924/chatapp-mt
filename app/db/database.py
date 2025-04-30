from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings
from app.db.models import Conversation, Message, ConversationSummary

async def init_db():
    """
    Khởi tạo kết nối MongoDB và Beanie.
    """
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]

    await init_beanie(
        database=db,
        document_models=[
            Conversation,
            Message,
            ConversationSummary,
        ],
    )
    print(f"Connected to MongoDB: {settings.MONGODB_DB_NAME} and initialized Beanie.")