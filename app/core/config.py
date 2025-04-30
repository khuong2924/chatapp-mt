import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load biến môi trường từ file .env
load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Chatbot Backend"
    API_V1_STR: str = "/api/v1"

    # Google Gemini API Key
    # Đọc từ biến môi trường GOOGLE_API_KEY
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

    # MongoDB Connection String
    # Đọc từ biến môi trường MONGODB_URI
    # Ví dụ: "mongodb://user:password@host:port"
    # Hoặc cho Docker Compose: "mongodb://mongo:27017"
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "chatbot_db")

    # Cấu hình LLM
    GEMINI_MODEL_NAME: str = "gemini-2.0-flash"

    # Prompt đặc biệt để yêu cầu tóm tắt theo định dạng mong muốn
    SUMMARIZATION_PROMPT_TEMPLATE: str = """
Bạn là một trợ lý có nhiệm vụ tóm tắt và chọn lọc thông tin quan trọng từ một lượt trao đổi trong cuộc trò chuyện.
Dưới đây là tin nhắn của người dùng và phản hồi của trợ lý ảo (LLM) trong lượt trao đổi gần nhất:

User message (index {user_msg_order}): {user_msg_content}
LLM response (index {llm_msg_order}): {llm_msg_content}

Hãy xem xét nội dung của cả hai tin nhắn. Chỉ chọn những tin nhắn chứa thông tin cốt lõi, yêu cầu mới, quyết định hoặc kết quả quan trọng cần lưu lại cho ngữ cảnh dài hạn. Bỏ qua các câu chào hỏi, câu hỏi làm rõ đơn thuần mà đã được trả lời ngay sau đó, hoặc các câu không thêm giá trị thông tin mới.

Với mỗi tin nhắn bạn chọn giữ lại, hãy tóm tắt nội dung của nó một cách ngắn gọn nhất có thể, loại bỏ từ ngữ dư thừa nhưng vẫn giữ ý chính. Bắt đầu nội dung tóm tắt bằng "- ".

Nếu bạn chọn giữ lại tin nhắn người dùng, trả về dưới dạng:
[{user_msg_order}][user]: - [Nội dung tóm tắt của bạn]

Nếu bạn chọn giữ lại phản hồi LLM, trả về dưới dạng:
[{llm_msg_order}][llm]: - [Nội dung tóm tắt của bạn]

Nếu cả hai tin nhắn đều quan trọng, trả về cả hai tóm tắt, mỗi tóm tắt trên một dòng riêng.
Nếu không có tin nhắn nào trong cặp này cần được đưa vào tóm tắt dài hạn, hãy trả về chính xác từ "NONE".

Kết quả tóm tắt của bạn:
"""

    # Prompt đặc biệt để yêu cầu tạo tiêu đề cho một cuộc trò chuyện
    TITLE_GENERATION_PROMPT_TEMPLATE: str = """
Dựa trên nội dung tin nhắn đầu tiên của người dùng dưới đây, hãy tạo một tiêu đề NGẮN GỌN (tối đa khoảng 5-7 từ) và mô tả được chủ đề chính hoặc ý định của cuộc trò chuyện. Chỉ trả về nội dung tiêu đề, không thêm bất kỳ lời giải thích nào khác.

Tin nhắn người dùng:
"{user_message_content}"

Tiêu đề được đề xuất:
"""

    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()