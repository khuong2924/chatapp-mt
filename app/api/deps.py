from app.services.chat_service import ChatService, get_chat_service
from app.services.llm_service import LLMService, llm_service_instance
from fastapi import Depends, HTTPException, status
import uuid
from typing import Optional

# Dependency để lấy ChatService instance
def get_chat_service_dependency() -> ChatService:
    return get_chat_service()

# Dependency để lấy LLMService instance (nếu cần truy cập trực tiếp từ API)
def get_llm_service_dependency() -> LLMService:
    return llm_service_instance

# --- Placeholder cho Authentication ---
async def get_current_user_id() -> str:
    """
    Placeholder: Hàm này trong thực tế sẽ xác thực token (ví dụ: JWT)
    và trả về user_id. Hiện tại trả về giá trị cố định để test.
    !!! Cần thay thế bằng logic xác thực thực tế !!!
    """
    # Ví dụ: giải mã token, lấy user_id từ payload
    # header = Depends(oauth2_scheme) # Giả sử dùng OAuth2
    # user = decode_token(header)
    # return user.id
    return "test_user_123" # <<<<< THAY THẾ SAU

# Có thể thêm dependency để kiểm tra quyền sở hữu conversation
async def get_conversation_owner(
    conversation_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id), # Lấy user_id từ auth
    chat_service: ChatService = Depends(get_chat_service_dependency),
    conv_type: Optional[str] = None # Thêm tham số này nếu cần kiểm tra type
) -> uuid.UUID:
    """
    Dependency kiểm tra xem user hiện tại có phải là chủ sở hữu conversation không.
    Trả về conversation_id nếu hợp lệ, nếu không raise HTTPException.
    """
    try:
        # Logic kiểm tra owner nằm trong service, gọi nó ra
        # Trong ví dụ này, chúng ta chưa có hàm riêng nên check trực tiếp (không tốt lắm)
        conv = await chat_service.get_conversation_if_owner(conversation_id, user_id, conv_type) # type: ignore
        if not conv:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return conversation_id # Trả về ID nếu hợp lệ
    except ValueError as e: # Bắt lỗi từ service
        if "Unauthorized access" in str(e):
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to access this conversation")
        elif "Incorrect conversation type" in str(e):
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        else:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found or invalid")