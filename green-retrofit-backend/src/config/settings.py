# src/config/settings.py - 앱 설정 및 미들웨어 구성
import os

# CORS 허용 출처
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS]

# 임시 작업 디렉토리
TEMP_DIR = "temp_workspace"
os.makedirs(TEMP_DIR, exist_ok=True)
