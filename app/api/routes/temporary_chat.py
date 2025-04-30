from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from app.schemas.chat import TemporaryChatRequest, TemporaryChatResponse
from app.schemas.message import MessageResponse
from app.services.chat_service import ChatService
from app.api.deps import get_chat_service_dependency, get_current_user_id, get_conversation_owner
import uuid
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/temporary-chat/messages",
    response_model=TemporaryChatResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message in a temporary chat session",
    tags=["Temporary Chat"],
)
async def send_temporary_chat_message(
    payload: TemporaryChatRequest,
    background_tasks: BackgroundTasks,
    chat_service: ChatService = Depends(get_chat_service_dependency),
):
    """
    Gửi tin nhắn trong một phiên trò chuyện tạm thời.
    - Nếu `conversation_id` không được cung cấp hoặc không hợp lệ, tạo một phiên mới.
    - Nếu `conversation_id` hợp lệ, gửi tin nhắn tiếp theo vào phiên đó.
    - Luôn trả về `conversation_id` (mới hoặc cũ) và phản hồi LLM.
    - Chạy nền tác vụ tóm tắt.
    """
    user_id_from_payload = payload.user_id
    conversation_id = payload.conversation_id

    try:
        if conversation_id:
            # --- Logic gửi tin nhắn tiếp theo vào phiên tạm đã có ---
            try:
                 # Kiểm tra xem conversation có tồn tại, thuộc user và là temporary không
                 conv = await chat_service.get_conversation_if_owner(conversation_id, user_id_from_payload, "temporary")
                 if not conv:
                      # Nếu không hợp lệ, coi như tạo mới bên dưới
                      logger.warning(f"Invalid temporary conversation ID {conversation_id} provided by user {user_id_from_payload}. Creating new one.")
                      conversation_id = None # Reset để đi vào nhánh tạo mới
                 else:
                      # Nếu hợp lệ, gửi tin nhắn tiếp theo
                      user_msg_db, llm_resp_db = await chat_service.add_message_and_get_response(
                            conversation_id=conversation_id,
                            user_id=user_id_from_payload,
                            new_message=payload.message
                      )
                      # Thêm tác vụ tóm tắt
                      background_tasks.add_task(chat_service.background_summarize, user_msg_db, llm_resp_db)

                      return TemporaryChatResponse(
                            conversation_id=conversation_id,
                            llm_response=MessageResponse.from_orm(llm_resp_db)
                      )

            except ValueError as e:
                 # Bắt lỗi từ get_conversation_if_owner hoặc add_message_and_get_response
                 if "Unauthorized access" in str(e) or "Incorrect conversation type" in str(e):
                      # Nếu không đúng user hoặc type, coi như tạo mới
                      logger.warning(f"Error accessing temporary conv {conversation_id}: {e}. Creating new one.")
                      conversation_id = None # Reset để tạo mới
                 else:
                     # Lỗi khác thì raise lại
                      raise e

        # --- Logic tạo phiên tạm mới (nếu conversation_id ban đầu là None hoặc bị reset) ---
        if not conversation_id:
            logger.info(f"Creating new temporary conversation for user {user_id_from_payload}")
            conversation, user_msg_db, llm_resp_db = await chat_service.create_new_conversation(
                user_id=user_id_from_payload,
                first_message=payload.message,
                conv_type="temporary"
            )
            # Thêm tác vụ tóm tắt
            background_tasks.add_task(chat_service.background_summarize, user_msg_db, llm_resp_db)

            return TemporaryChatResponse(
                conversation_id=conversation.id,
                llm_response=MessageResponse.from_orm(llm_resp_db)
            )

    except ValueError as e: # Bắt các lỗi chưa xử lý ở trên (ví dụ từ create_new_conversation)
         # Log lỗi và trả về lỗi server chung chung hơn
         logger.error(f"Value error processing temporary chat for user {user_id_from_payload}: {e}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request data")
    except ConnectionError as e:
        logger.error(f"LLM connection error during temporary chat: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"LLM service unavailable: {e}")
    except Exception as e:
        logger.error(f"Failed to process temporary chat message for user {user_id_from_payload}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process message")


@router.delete(
    "/temporary-chat/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a temporary conversation",
    tags=["Temporary Chat"],
)
async def delete_temporary_conversation(
    conversation_id: uuid.UUID,
    chat_service: ChatService = Depends(get_chat_service_dependency),
    user_id: str = Depends(get_current_user_id), # Lấy user_id từ auth
    # owner_check: uuid.UUID = Depends(lambda conv_id=conversation_id: get_conversation_owner(conv_id, conv_type="temporary")) # Kiểm tra quyền và type
):
    """
    Xóa một phiên trò chuyện 'temporary' khi người dùng rời khỏi nó.
    Yêu cầu xác thực người dùng là chủ sở hữu.
    """
    try:
        success = await chat_service.delete_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            conv_type="temporary"
        )
        if not success:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temporary conversation not found")
        return None
    except ValueError as e:
         if "Unauthorized access" in str(e):
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
         elif "Conversation is not of type 'temporary'" in str(e):
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This is not a temporary conversation")
         else:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete temporary conversation {conversation_id} for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete temporary conversation")