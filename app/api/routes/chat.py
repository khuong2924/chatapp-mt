from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from app.schemas.chat import (
    ConversationCreate,
    ConversationResponse,
    NewMessageRequest,
    NewMessageResponse,
    ConversationInfo,
)
from app.schemas.message import MessageResponse
from app.services.chat_service import ChatService
from typing import List, Optional
from app.api.deps import get_chat_service_dependency, get_current_user_id # Bỏ get_conversation_owner nếu không dùng
import uuid
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new regular conversation",
    tags=["Conversations"],
)
async def create_new_regular_conversation(
    payload: ConversationCreate,
    background_tasks: BackgroundTasks,
    chat_service: ChatService = Depends(get_chat_service_dependency),
):
    """
    Khởi tạo một phiên trò chuyện 'regular' mới.
    - Lưu tin nhắn đầu tiên.
    - Gọi LLM để có phản hồi đầu tiên.
    - Lưu phản hồi LLM.
    - Chạy nền tác vụ tóm tắt cho lượt đầu tiên.
    """
    user_id_from_payload = payload.user_id

    try:
        conversation, user_msg_db, llm_resp_db = await chat_service.create_new_conversation(
            user_id=user_id_from_payload,
            first_message=payload.first_message,
            conv_type="regular"
        )

        background_tasks.add_task(
            chat_service.background_summarize,
            user_message=user_msg_db,
            llm_response=llm_resp_db
        )

        return ConversationResponse(
            id=conversation.id,
            user_id=conversation.user_id,
            title=conversation.title,
            created_at=conversation.created_at,
            last_active_at=conversation.last_active_at,
            type=conversation.type,
            first_llm_response=MessageResponse.from_orm(llm_resp_db)
        )
    except ConnectionError as e:
        logger.error(f"LLM connection error during conversation creation: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"LLM service unavailable: {e}")
    except Exception as e:
        logger.error(f"Failed to create conversation for user {user_id_from_payload}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create conversation")


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=NewMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message to a regular conversation",
    tags=["Conversations"],
)
async def send_message_to_regular_conversation(
    conversation_id: uuid.UUID,
    payload: NewMessageRequest,
    background_tasks: BackgroundTasks,
    chat_service: ChatService = Depends(get_chat_service_dependency),
):
    """
    Gửi một tin nhắn mới vào phiên trò chuyện 'regular' đã có.
    - Xác thực người dùng và `conversation_id`.
    - Lấy lịch sử/tóm tắt phù hợp.
    - Gọi LLM.
    - Lưu tin nhắn người dùng và phản hồi LLM.
    - Chạy nền tác vụ tóm tắt.
    """
    user_id_from_payload = payload.user_id

    try:
        conv = await chat_service.get_conversation_if_owner(conversation_id, user_id_from_payload, "regular")
        if not conv:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found or not accessible")

        user_msg_db, llm_resp_db = await chat_service.add_message_and_get_response(
            conversation_id=conversation_id,
            user_id=user_id_from_payload,
            new_message=payload.message
        )

        background_tasks.add_task(
            chat_service.background_summarize,
            user_message=user_msg_db,
            llm_response=llm_resp_db
        )

        return NewMessageResponse(
            llm_response=MessageResponse.from_orm(llm_resp_db)
        )
    except ValueError as e:
         if "Unauthorized access" in str(e):
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
         elif "Conversation is not of type" in str(e):
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
         else:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConnectionError as e:
        logger.error(f"LLM connection error during message sending for conv {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"LLM service unavailable: {e}")
    except Exception as e:
        logger.error(f"Failed to add message to conversation {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process message")


@router.get(
    "/conversations",
    response_model=List[ConversationInfo],
    summary="Get list of conversation info by User ID (NO AUTH)",
    tags=["Conversations"],
)
async def get_user_conversations_list_by_id(
    user_id: str = Query(..., description="User ID to filter conversations for"),
    chat_service: ChatService = Depends(get_chat_service_dependency),
):
    """
    Lấy danh sách thông tin (ID, Title, Last Active At) của các cuộc trò chuyện
    (loại 'regular') thuộc về `user_id` được cung cấp trong query parameter,
    sắp xếp theo thời gian hoạt động gần nhất.
    !!! CẢNH BÁO: Endpoint này KHÔNG yêu cầu xác thực người gọi. !!!
    """
    if not user_id:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id query parameter is required")
    try:
        conversations = await chat_service.get_user_conversations_info(user_id)
        return conversations
    except Exception as e:
        logger.error(f"Failed to retrieve conversation list for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve conversation list")


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[MessageResponse],
    summary="Get all messages for a specific conversation (NO AUTH)", # <<< Cập nhật summary
    tags=["Conversations"],
)
async def get_all_conversation_messages_no_auth(
    conversation_id: uuid.UUID,
    chat_service: ChatService = Depends(get_chat_service_dependency),
):
    """
    Lấy toàn bộ lịch sử tin nhắn của một cuộc trò chuyện cụ thể chỉ dựa vào ID.
    !!! CẢNH BÁO: Endpoint này KHÔNG kiểm tra quyền sở hữu cuộc trò chuyện. !!!
    Tin nhắn được trả về theo thứ tự (order).
    """
    try:
        messages = await chat_service.get_all_messages_by_id(conversation_id)
        return messages
    except ValueError as e:
        if "Conversation not found" in str(e):
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        else:
             logger.warning(f"ValueError when fetching messages for conv {conversation_id} (no auth): {e}")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to retrieve messages for conversation {conversation_id} (no auth): {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve messages")


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a regular conversation",
    tags=["Conversations"],
)
async def delete_regular_conversation(
    conversation_id: uuid.UUID,
    chat_service: ChatService = Depends(get_chat_service_dependency),
    user_id: str = Depends(get_current_user_id),
):
    """
    Xóa một phiên trò chuyện 'regular' và tất cả dữ liệu liên quan (messages, summary).
    Yêu cầu xác thực người dùng là chủ sở hữu (dựa trên dependency get_current_user_id).
    """
    try:
        success = await chat_service.delete_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            conv_type="regular"
        )
        if not success:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        return None
    except HTTPException as http_exc:
        raise http_exc
    except ValueError as e:
         if "Unauthorized access" in str(e):
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
         elif "Conversation is not of type" in str(e):
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
         else:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete conversation {conversation_id} for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete conversation")