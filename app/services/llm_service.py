import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from app.core.config import settings
from app.db.models import Message as DBMessage
from typing import List, Optional, Tuple
import logging
import re

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        try:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            self.model = genai.GenerativeModel(settings.GEMINI_MODEL_NAME)
            logger.info(f"Google Generative AI configured with model: {settings.GEMINI_MODEL_NAME}")
        except Exception as e:
            logger.error(f"Failed to configure Google Generative AI: {e}")
            raise ConnectionError("Could not configure Google Generative AI") from e

    def _format_history_for_gemini(self, history: List[DBMessage]) -> List[dict]:
        """Chuyển đổi lịch sử tin nhắn từ DB format sang Gemini format."""
        gemini_history = []
        for msg in history:
            role = msg.role # 'user' hoặc 'model' đã khớp với Gemini
            gemini_history.append({"role": role, "parts": [{"text": msg.content}]})
        return gemini_history

    async def generate_response(
        self,
        history: List[DBMessage],
        new_user_message_content: str,
        summary: Optional[str] = None
    ) -> str:
        """
        Tạo phản hồi từ LLM dựa trên lịch sử, tin nhắn mới và tóm tắt (nếu có).
        """
        try:
            # Bắt đầu với tóm tắt nếu có
            prompt_parts = []
            if summary:
                 prompt_parts.append(f"[Conversation Summary Start]\n{summary}\n[Conversation Summary End]\n\n")


            # Format lịch sử gần đây cho Gemini API
            gemini_history = self._format_history_for_gemini(history)

            # Nếu có lịch sử, thêm tin nhắn mới vào cuối
            if prompt_parts and gemini_history:
                 first_message_role = gemini_history[0]['role']
                 first_message_content = gemini_history[0]['parts'][0]['text']
                 # Ghép tóm tắt vào trước nội dung tin nhắn đầu tiên
                 gemini_history[0]['parts'][0]['text'] = "".join(prompt_parts) + first_message_content
            elif prompt_parts and not gemini_history:
                 pass


            # Tạo đối tượng ChatSession hoặc gọi generate_content trực tiếp
            # Sử dụng generate_content cho phép truyền history mỗi lần gọi
            chat_session = self.model.start_chat(history=gemini_history)

            # Ghép summary vào message mới nếu không có history để ghép vào
            final_user_prompt = new_user_message_content
            if prompt_parts and not gemini_history:
                 final_user_prompt = "".join(prompt_parts) + new_user_message_content


            logger.debug(f"Sending to Gemini. History length: {len(gemini_history)}. Summary included: {bool(summary)}. User prompt: {final_user_prompt[:100]}...") # Log phần đầu prompt

            response = await chat_session.send_message_async(final_user_prompt) # Sử dụng async

            logger.debug(f"Received response from Gemini: {response.text[:100]}...")
            return response.text

        except google_exceptions.GoogleAPIError as e:
            logger.error(f"Gemini API Error: {e}")
            raise ConnectionError(f"LLM API error: {e}") from e
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            raise RuntimeError(f"Failed to generate response: {e}") from e

    async def summarize_turn(self, user_message: DBMessage, llm_response: DBMessage) -> Optional[str]:
        """
        Sử dụng LLM để tóm tắt một lượt trao đổi (user + llm) theo định dạng yêu cầu.
        Trả về chuỗi tóm tắt đã định dạng hoặc None nếu không có gì để tóm tắt.
        """
        try:
            prompt = settings.SUMMARIZATION_PROMPT_TEMPLATE.format(
                user_msg_order=user_message.order,
                user_msg_content=user_message.content,
                llm_msg_order=llm_response.order,
                llm_msg_content=llm_response.content
            )

            logger.debug(f"Sending summarization prompt to Gemini for conv {user_message.conversation_id}, orders {user_message.order}/{llm_response.order}")

            # Sử dụng generate_content vì đây là tác vụ một lần, không cần session
            response = await self.model.generate_content_async(prompt)

            summary_text = response.text.strip()
            logger.debug(f"Received summarization result: '{summary_text}'")

            if summary_text.upper() == "NONE":
                return None
            elif not summary_text: # Nếu LLM trả về rỗng
                 logger.warning(f"Summarization LLM returned empty string for conv {user_message.conversation_id}, orders {user_message.order}/{llm_response.order}")
                 return None
            else:
                # Đảm bảo có dấu xuống dòng ở cuối nếu có nội dung
                return summary_text + "\n" if summary_text else None

        except google_exceptions.GoogleAPIError as e:
            logger.error(f"Gemini API Error during summarization: {e}")
            return None
        except Exception as e:
            logger.error(f"Error summarizing turn: {e}")
            return None # Bỏ qua tóm tắt nếu có lỗi
        
    
    async def generate_title(self, user_message_content: str) -> Optional[str]:
        """
        Sử dụng LLM để tạo tiêu đề ngắn gọn dựa trên tin nhắn đầu tiên.
        Trả về chuỗi tiêu đề hoặc None nếu có lỗi hoặc không tạo được.
        """
        if not user_message_content:
            return None # Không tạo tiêu đề nếu tin nhắn rỗng

        try:
            prompt = settings.TITLE_GENERATION_PROMPT_TEMPLATE.format(
                user_message_content=user_message_content
            )

            logger.debug(f"Sending title generation prompt to Gemini...")

            # Sử dụng generate_content vì đây là tác vụ một lần
            response = await self.model.generate_content_async(prompt)
            generated_title = response.text.strip()

            # Xử lý hậu kỳ đơn giản: bỏ dấu ngoặc kép nếu LLM trả về dạng "Title"
            generated_title = re.sub(r'^"|"$', '', generated_title)

            if 2 < len(generated_title.split()) < 10 and len(generated_title) < 100:
                logger.debug(f"Generated title: '{generated_title}'")
                return generated_title
            else:
                logger.warning(f"Generated title rejected (too long/short or empty): '{generated_title}'")
                return None # Trả về None nếu tiêu đề không phù hợp

        except google_exceptions.GoogleAPIError as e:
            logger.error(f"Gemini API Error during title generation: {e}")
            return None # Không tạo tiêu đề nếu API lỗi
        except Exception as e:
            logger.error(f"Error generating title: {e}")
            return None # Không tạo tiêu đề nếu có lỗi khác

# Khởi tạo instance để sử dụng trong dependency injection
llm_service_instance = LLMService()