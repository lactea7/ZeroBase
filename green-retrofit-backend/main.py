# main.py
import os
import uuid
import shutil
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.gbxml_parser import parse_gbxml_to_json
from src.ep_simulator import generate_idf_and_simulate

# Rate Limiter 설정
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Green Retrofit AI Backend - gbXML Version")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# React 프론트엔드 연동을 위한 CORS 설정
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "temp_workspace"
os.makedirs(TEMP_DIR, exist_ok=True)

def cleanup_workspace(path: str):
    """안전한 디렉토리 정리를 위한 헬퍼 함수"""
    if os.path.exists(path) and os.path.isdir(path):
        try:
            shutil.rmtree(path)
            print(f"🧹 임시 작업 공간 정리 완료: {path}")
        except Exception as e:
            print(f"⚠️ 임시 작업 공간 정리 실패: {e}")

# ---------------------------------------------------------
# API 1: gbXML 업로드 및 React용 3D 데이터 파싱
# ---------------------------------------------------------
@app.post("/api/upload-gbxml")
@limiter.limit("5/minute")
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

# ---------------------------------------------------------
# API 2: 시뮬레이션 실행 (비동기 폴링)
# ---------------------------------------------------------
class SimulationPayload(BaseModel):
    projectData: Dict[str, Any]
    zones: List[Dict[str, Any]]
    surfaces: List[Dict[str, Any]]

# 전역 작업 저장소 (간이 비동기 큐용)
simulation_tasks: Dict[str, Any] = {}

def _run_simulation_task(task_id: str, payload_dict: Dict[str, Any], session_dir: str):
    """백그라운드에서 시뮬레이션을 실행하고 결과를 simulation_tasks에 저장"""
    try:
        result = generate_idf_and_simulate(payload_dict, session_dir)
        simulation_tasks[task_id] = {"status": "success", "result": result}
    except Exception as e:
        print(f"❌ 시뮬레이션 에러: {str(e)}")
        simulation_tasks[task_id] = {"status": "failed", "error": str(e)}
    finally:
        # 시뮬레이션이 모두 끝난 뒤에 임시 폴더 삭제
        cleanup_workspace(session_dir)

@app.post("/api/simulate")
@limiter.limit("5/minute")
async def run_simulation(request: Request, background_tasks: BackgroundTasks, payload: SimulationPayload):
    print("🚀 시뮬레이션 비동기 요청 수신됨")
    
    # 💡 시뮬레이션 환경 격리 및 Task ID 생성
    task_id = str(uuid.uuid4())
    session_dir = os.path.join(TEMP_DIR, task_id)
    os.makedirs(session_dir, exist_ok=True)
    
    # 상태 초기화
    simulation_tasks[task_id] = {"status": "running"}
    
    # 백그라운드 작업으로 등록하고 즉시 응답 (100초 타임아웃 방지)
    background_tasks.add_task(_run_simulation_task, task_id, payload.dict(), session_dir)
    
    return {"status": "accepted", "task_id": task_id}

@app.get("/api/simulate/{task_id}")
async def get_simulation_status(task_id: str):
    task = simulation_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)