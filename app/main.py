from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.db.database import init_db #, close_db
from app.api.routes import chat, temporary_chat
import logging

# Cấu hình logging cơ bản
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Context manager cho lifespan events (thay thế on_startup/on_shutdown cũ)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup...")
    try:
        await init_db()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        raise RuntimeError("Could not connect to database") from e
    yield
    logger.info("Application shutdown...")

# Khởi tạo FastAPI app với lifespan
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Include routers
api_prefix = settings.API_V1_STR
app.include_router(chat.router, prefix=api_prefix, tags=["Conversations"])
app.include_router(temporary_chat.router, prefix=api_prefix, tags=["Temporary Chat"])

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}