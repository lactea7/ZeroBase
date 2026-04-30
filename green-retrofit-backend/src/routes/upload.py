# src/routes/upload.py - gbXML 업로드 라우트
import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Request

from src.config.settings import TEMP_DIR
from src.helpers.cleanup import cleanup_workspace
from src.gbxml_parser import parse_gbxml_to_json

router = APIRouter()

@router.post("/api/upload-gbxml")
async def upload_gbxml(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    print(f"📥 gbXML 파일 업로드 수신: {file.filename}")
    
    if not file.filename.lower().endswith('.xml'):
        raise HTTPException(status_code=400, detail="gbXML(.xml) 파일만 업로드 가능합니다.")

    # 💡 세션 격리 및 Path Traversal 방지
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TEMP_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    
    # 원본 파일명 대신 UUID를 사용하여 경로 이탈 완벽 차단
    safe_filename = f"{session_id}.xml"
    file_path = os.path.join(session_dir, safe_filename)
    
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # 응답 반환 후 즉시 임시 폴더 삭제 예약
    background_tasks.add_task(cleanup_workspace, session_dir)

    try:
        # gbXML 파싱 모듈 호출
        parsed_data = parse_gbxml_to_json(file_path)
        return {"status": "success", "data": parsed_data}
    except Exception as e:
        print(f"❌ 파싱 에러: {str(e)}")
        raise HTTPException(status_code=500, detail=f"파싱 실패: {str(e)}")
