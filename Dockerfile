# Sử dụng base image Python chính thức
FROM python:3.10-slim

# Đặt thư mục làm việc trong container
WORKDIR /app

# Cài đặt các dependencies hệ thống nếu cần (ví dụ: build tools)
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Sao chép file requirements và cài đặt thư viện Python
# Làm riêng bước này để tận dụng Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ mã nguồn ứng dụng vào thư mục làm việc
COPY ./app /app/app

# Expose port mà ứng dụng FastAPI sẽ chạy
EXPOSE 8000

# Lệnh để chạy ứng dụng khi container khởi động
# Sử dụng uvicorn để chạy ASGI app trong main.py
# --host 0.0.0.0 để lắng nghe trên tất cả các network interfaces
# --port 8000 khớp với port đã EXPOSE
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
# Bỏ --reload trong môi trường production
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]