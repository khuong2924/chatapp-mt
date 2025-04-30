from beanie.odm.operators.update.general import Set
from app.db.models import Conversation, Message, ConversationSummary, ConversationType
from app.schemas.message import MessageCreate
from app.services.llm_service import LLMService
from typing import List, Optional, Tuple
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    async def _get_or_create_summary(self, conversation_id: uuid.UUID) -> ConversationSummary:
        """Lấy hoặc tạo mới bản ghi tóm tắt."""
        summary = await ConversationSummary.find_one(ConversationSummary.conversation_id == conversation_id)
        if not summary:
            summary = ConversationSummary(conversation_id=conversation_id, content="")
            await summary.insert()
            logger.info(f"Created new summary entry for conversation {conversation_id}")
        return summary

    async def create_new_conversation(
        self, user_id: str, first_message: MessageCreate, conv_type: ConversationType = "regular"
    ) -> Tuple[Conversation, Message, Message]:
        """
        Tạo cuộc trò chuyện mới, *tự động tạo tiêu đề*, lưu tin nhắn đầu tiên,
        gọi LLM lấy phản hồi, lưu phản hồi LLM.
        Trả về (conversation, user_message_db, llm_response_db).
        """
        now = datetime.utcnow()

        # 1. Tạo Conversation mới (chưa có title)
        conversation = Conversation(
            user_id=user_id,
            type=conv_type,
            title=None, # Title sẽ được cập nhật sau
            created_at=now,
            last_active_at=now
        )
        await conversation.insert()
        logger.info(f"Created new {conv_type} conversation {conversation.id} for user {user_id} (title pending).")

        # 2. Tạo và Lưu tin nhắn đầu tiên của người dùng (giờ đã có conversation.id)
        user_message_db = Message(
            conversation_id=conversation.id,
            order=1,
            role="user",
            content=first_message.content,
            sent_at=now
        )
        await user_message_db.insert()
        logger.debug(f"Saved first user message {user_message_db.id} for conversation {conversation.id}")


        # 3. Tạo Tiêu đề Tự động (dùng content từ user_message_db)
        generated_title: Optional[str] = None
        try:
            generated_title = await self.llm_service.generate_title(user_message_db.content)
            if generated_title:
                # Cập nhật title vào conversation trong DB
                await conversation.update(Set({Conversation.title: generated_title}))
                conversation.title = generated_title # Cập nhật cả object trong bộ nhớ
                logger.info(f"Automatically generated and saved title for conversation {conversation.id}: '{generated_title}'")
            else:
                logger.info(f"Could not automatically generate title for conversation {conversation.id}.")
        except Exception as e:
            logger.error(f"Error during automatic title generation for conv {conversation.id}: {e}", exc_info=True)

        # 4. Gọi LLM lấy phản hồi chat
        try:
            llm_content = await self.llm_service.generate_response(
                history=[], # Chỉ gửi tin nhắn đầu tiên
                new_user_message_content=user_message_db.content,
                summary=None
            )
        except Exception as e:
            logger.error(f"LLM response call failed for new conversation {conversation.id}: {e}")
            await user_message_db.delete()
            await conversation.delete() # Xóa cả conversation nếu LLM lỗi
            logger.warning(f"Rolled back creation of conversation {conversation.id} due to LLM error.")
            raise # Ném lại lỗi để API trả 500

        # 5. Lưu phản hồi của LLM
        llm_response_db = Message(
            conversation_id=conversation.id,
            order=2,
            role="model",
            content=llm_content,
            sent_at=datetime.utcnow() # Thời điểm LLM trả lời
        )
        await llm_response_db.insert()

        # 6. Cập nhật last_active_at lần nữa (không bắt buộc nhưng để chắc chắn)

        logger.info(f"Saved first LLM response for conversation {conversation.id}")
        return conversation, user_message_db, llm_response_db

    async def add_message_and_get_response(
        self, conversation_id: uuid.UUID, user_id: str, new_message: MessageCreate
    ) -> Tuple[Message, Message]:
        """
        Thêm tin nhắn mới, lấy lịch sử/tóm tắt, gọi LLM, lưu phản hồi.
        Trả về (user_message_db, llm_response_db).
        Kiểm tra quyền sở hữu conversation.
        """
        # 1. Tìm conversation và kiểm tra quyền sở hữu + loại (nếu cần)
        conversation = await Conversation.get(conversation_id)
        if not conversation:
            logger.warning(f"Conversation {conversation_id} not found.")
            raise ValueError("Conversation not found") # Hoặc trả về None/Exception cụ thể
        if conversation.user_id != user_id:
            logger.warning(f"User {user_id} attempted to access conversation {conversation_id} owned by {conversation.user_id}")
            raise ValueError("Unauthorized access to conversation") # Hoặc trả về None/Exception cụ thể

        # 2. Lấy số lượng tin nhắn hiện có và tin nhắn cuối cùng để xác định order tiếp theo
        last_message = await Message.find(Message.conversation_id == conversation_id).sort(-Message.order).limit(1).first_or_none()
        current_message_count = last_message.order if last_message else 0
        next_order = current_message_count + 1

        # 3. Lưu tin nhắn mới của người dùng
        user_message_db = Message(
            conversation_id=conversation_id,
            order=next_order,
            role="user",
            content=new_message.content
        )
        await user_message_db.insert()

        # 4. Lấy lịch sử và tóm tắt (nếu cần)
        history_messages: List[Message] = []
        summary_content: Optional[str] = None
        limit = 10 # Số lượng tin nhắn gần nhất cần lấy

        if current_message_count > limit -1: # Nếu tổng số tin nhắn TRƯỚC ĐÓ đã >= 10
            # Lấy tóm tắt
            summary_doc = await ConversationSummary.find_one(ConversationSummary.conversation_id == conversation_id)
            if summary_doc:
                summary_content = summary_doc.content
                logger.debug(f"Using summary for conversation {conversation_id}")
            else:
                 logger.warning(f"Conversation {conversation_id} has > 10 messages but no summary found.")
            # Lấy 10 tin nhắn gần nhất (bao gồm cả user message vừa thêm TẠM THỜI - HOẶC LẤY 9 + msg mới)
            # Lấy 10 message có order cao nhất TRƯỚC message hiện tại
            history_messages = await Message.find(
                Message.conversation_id == conversation_id,
                Message.order < next_order # Chỉ lấy những tin trước đó
            ).sort(-Message.order).limit(limit).to_list()
            history_messages.reverse() # Sắp xếp lại từ cũ -> mới

        else: # Nếu tổng số tin nhắn TRƯỚC ĐÓ < 10
            # Lấy TẤT CẢ tin nhắn TRƯỚC ĐÓ
             history_messages = await Message.find(
                 Message.conversation_id == conversation_id,
                 Message.order < next_order
            ).sort(+Message.order).to_list() # Sắp xếp từ cũ -> mới
             logger.debug(f"Using all {len(history_messages)} previous messages for conversation {conversation_id}")


        # 5. Gọi LLM
        try:
            llm_content = await self.llm_service.generate_response(
                history=history_messages,
                new_user_message_content=user_message_db.content,
                summary=summary_content
            )
        except Exception as e:
            # Xử lý lỗi gọi LLM
            logger.error(f"LLM call failed for conversation {conversation_id}, user message order {next_order}: {e}")
            # Có thể xóa user_message vừa lưu? Hoặc đánh dấu lỗi?
            await user_message_db.delete() # Xóa tin nhắn user nếu LLM lỗi
            raise # Ném lại lỗi

        # 6. Lưu phản hồi LLM
        llm_response_db = Message(
            conversation_id=conversation_id,
            order=next_order + 1,
            role="model",
            content=llm_content
        )
        await llm_response_db.insert()

        # 7. Cập nhật last_active_at
        await conversation.update(Set({Conversation.last_active_at: datetime.utcnow()}))

        logger.info(f"Added messages order {next_order}, {next_order+1} to conversation {conversation_id}")
        return user_message_db, llm_response_db

    async def background_summarize(self, user_message: Message, llm_response: Message):
        """
        Tác vụ nền: Gọi LLM để tóm tắt lượt trao đổi và cập nhật DB.
        """
        logger.info(f"Starting background summarization for conv {user_message.conversation_id}, orders {user_message.order}/{llm_response.order}")
        try:
            summary_addition = await self.llm_service.summarize_turn(user_message, llm_response)

            if summary_addition:
                summary_doc = await self._get_or_create_summary(user_message.conversation_id)
                new_summary_content = summary_doc.content + summary_addition # Nối vào cuối
                await summary_doc.update(Set({ConversationSummary.content: new_summary_content}))
                logger.info(f"Successfully updated summary for conversation {user_message.conversation_id}")
            else:
                logger.info(f"No summary needed or generated for turn in conv {user_message.conversation_id}, orders {user_message.order}/{llm_response.order}")

        except Exception as e:
            # Bắt các lỗi không mong muốn khác trong quá trình xử lý nền
            logger.error(f"Unhandled error in background_summarize for conv {user_message.conversation_id}: {e}", exc_info=True)


    async def delete_conversation(self, conversation_id: uuid.UUID, user_id: Optional[str] = None, conv_type: Optional[ConversationType] = None):
        """
        Xóa conversation, messages, và summary. Kiểm tra quyền sở hữu và loại (nếu được cung cấp).
        """
        conversation = await Conversation.get(conversation_id)
        if not conversation:
            logger.warning(f"Attempt to delete non-existent conversation {conversation_id}")
            return False # Hoặc raise NotFound

        if conv_type and conversation.type != conv_type:
             logger.warning(f"Attempt to delete conv {conversation_id} with wrong type (expected {conv_type}, found {conversation.type})")
             raise ValueError(f"Conversation is not of type '{conv_type}'")

        # Xóa dữ liệu liên quan
        deleted_messages_count = await Message.find(Message.conversation_id == conversation_id).delete()
        deleted_summary_count = await ConversationSummary.find(ConversationSummary.conversation_id == conversation_id).delete()
        await conversation.delete()

        logger.info(f"Deleted conversation {conversation_id} (type: {conversation.type}) for user {user_id}. "
                    f"Removed {deleted_messages_count} messages and {deleted_summary_count} summary entries.")
        return True

    async def get_conversation_if_owner(self, conversation_id: uuid.UUID, user_id: str, conv_type: Optional[ConversationType] = None) -> Optional[Conversation]:
        """Helper để lấy conversation nếu user là owner và đúng type."""
        conversation = await Conversation.get(conversation_id)
        if not conversation:
            return None

        if conv_type and conversation.type != conv_type:
             raise ValueError(f"Incorrect conversation type (expected {conv_type})") # Nên là HTTPException(400)
        return conversation
    
    async def get_user_conversations_info(self, user_id: str) -> List[Conversation]:
        """
        Lấy danh sách các cuộc trò chuyện (chỉ loại 'regular')
        thuộc về một người dùng, sắp xếp theo lần hoạt động gần nhất.
        Trả về các đối tượng Conversation đầy đủ (hoặc chỉ các trường cần thiết nếu muốn tối ưu).
        """
        # Tìm các conversation khớp user_id và type, sắp xếp
        # Không cần project nữa nếu trả về cả object hoặc các trường cần thiết
        conversations = await Conversation.find(
            Conversation.user_id == user_id,
            Conversation.type == "regular"
        ).sort("-last_active_at").to_list()

        # Trả về list các object Conversation đầy đủ
        # API layer sẽ map sang ConversationInfo dùng response_model
        return conversations
    
    async def get_all_messages_by_id(self, conversation_id: uuid.UUID) -> List[Message]:
        """
        Lấy tất cả tin nhắn của một cuộc trò chuyện chỉ dựa vào ID.
        Không kiểm tra quyền sở hữu.
        Trả về danh sách tin nhắn sắp xếp theo thứ tự tăng dần (order).
        """
        # 1. Kiểm tra xem conversation có tồn tại không (không cần check owner)
        conversation_exists = await Conversation.find_one(Conversation.id == conversation_id).exists() # type: ignore
        if not conversation_exists:
             raise ValueError("Conversation not found") # Raise lỗi nếu không tìm thấy

        # 2. Lấy tất cả tin nhắn thuộc conversation này
        messages = await Message.find(
            Message.conversation_id == conversation_id
        ).sort("+order").to_list()

        return messages

# --- Dependency Injection Setup ---
# Khởi tạo instance của LLMService trước
from app.services.llm_service import llm_service_instance

# Tạo instance ChatService với LLM service đã khởi tạo
chat_service_instance = ChatService(llm_service=llm_service_instance)

# Hàm dependency cho FastAPI
def get_chat_service() -> ChatService:
    return chat_service_instance