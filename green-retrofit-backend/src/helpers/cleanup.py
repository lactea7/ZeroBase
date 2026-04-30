# src/helpers/cleanup.py - 임시 파일 정리 유틸리티
import os
import shutil

def cleanup_workspace(path: str):
    """안전한 디렉토리 정리를 위한 헬퍼 함수"""
    if os.path.exists(path) and os.path.isdir(path):
        try:
            shutil.rmtree(path)
            print(f"🧹 임시 작업 공간 정리 완료: {path}")
        except Exception as e:
            print(f"⚠️ 임시 작업 공간 정리 실패: {e}")
