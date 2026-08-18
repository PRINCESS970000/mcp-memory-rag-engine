# 1. Base Image - بيئة خفيفة ومستقرة لـ Python
FROM python:3.11-slim

# 2. Environment Variables - منع كتابة pyc وخزن المخرجات لتسجيل الأخطاء فوراً
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Work Directory
WORKDIR /app

# 4. Install System Dependencies (مهم لـ SQLite والـ build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    build-essential \
    && rm -rf /lib/apt/lists/*

# 5. Copy & Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy Application Code
COPY . .

# 7. Initialize Database (إنشاء السكيما وتغذيتها بالبيانات عند البناء)
RUN python db/init_db.py

# 8. Expose MCP HTTP Port
EXPOSE 8000

# 9. Startup Command - تشغيل سيرفر MCP عبر HTTP Streamable
CMD ["python", "mcp_server/server.py", "http"]