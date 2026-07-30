# main.py
import os
import uuid
import shutil
import threading
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
from src.task_store import TaskStore
from src.model_validation import validate_simulation_payload

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

# 업로드 상한 (샘플 gbXML이 ~5MB 수준이므로 50MB면 충분)
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024

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
@limiter.limit("50/minute")
async def upload_gbxml(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    print(f"📥 gbXML 파일 업로드 수신: {file.filename}")
    
    if not file.filename.lower().endswith(('.xml', '.gbxml')):
        raise HTTPException(status_code=400, detail="gbXML(.xml 또는 .gbxml) 파일만 업로드 가능합니다.")

    # 💡 세션 격리 및 Path Traversal 방지
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TEMP_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    
    # 원본 파일명 대신 UUID를 사용하여 경로 이탈 완벽 차단
    safe_filename = f"{session_id}.xml"
    file_path = os.path.join(session_dir, safe_filename)
    
    # 파일 전체를 메모리에 올리지 않고 1MB 청크로 기록 + 크기 상한 검사
    written = 0
    with open(file_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                buffer.close()
                cleanup_workspace(session_dir)
                raise HTTPException(
                    status_code=413,
                    detail=f"파일이 너무 큽니다. 최대 {MAX_UPLOAD_BYTES // (1024*1024)}MB까지 업로드 가능합니다.",
                )
            buffer.write(chunk)

    # 응답 반환 후 즉시 임시 폴더 삭제 예약
    background_tasks.add_task(cleanup_workspace, session_dir)

    try:
        # gbXML 파싱 모듈 호출
        parsed_data = parse_gbxml_to_json(file_path)
        # 프리체크: XML은 맞지만 gbXML 구조가 아니면 존/면이 0개 — 뒤 단계에서
        # 알 수 없는 실패로 터지기 전에 원인을 명확히 알려준다
        n_zones = len(parsed_data.get("zones", []))
        n_surfs = len(parsed_data.get("surfaces", []))
        if n_zones == 0 or n_surfs == 0:
            raise HTTPException(
                status_code=400,
                detail=f"gbXML 구조를 찾지 못했습니다 (존 {n_zones}개 / 면 {n_surfs}개). "
                       "Revit 등에서 내보낸 gbXML 파일인지 확인해주세요.",
            )
        return {"status": "success", "data": parsed_data}
    except HTTPException:
        raise
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
    materials: Dict[str, Any] = {}
    constructionOverrides: Dict[str, Any] = {}
    # 업로드 원본(개선 전) 모델 {zones, surfaces} — 전/후 비교 시뮬레이션용
    baselineModel: Dict[str, Any] = {}

# 작업 저장소: SQLite 영속화 — 서버 재시작에도 완료 결과가 유지되고,
# 재시작으로 중단된 진행 중 작업은 기동 시 명시적으로 실패 처리된다.
TASK_TTL_SECONDS = 60 * 60      # 완료/실패 task 보관 시간 (1시간)
MAX_TASKS = 500                 # 저장소 최대 항목 수 (상한선)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
task_store = TaskStore(os.environ.get("TASK_DB_PATH", os.path.join(_BASE_DIR, "tasks.db")))
_orphans = task_store.recover_orphans()
if _orphans:
    print(f"♻️ 서버 재시작: 중단된 작업 {_orphans}건을 실패 처리했습니다.")

# 💡 EnergyPlus 동시 실행 제한: 1회 실행이 ~2.5분/수백MB라서 동시에 여러 개가 돌면
# 800MB 컨테이너가 OOM으로 죽는다. 초과분은 세마포어 앞에서 'queued' 상태로 대기.
# (세마포어는 프로세스 단위 — 멀티 워커로 띄우면 워커 수만큼 배수가 되니 주의)
MAX_CONCURRENT_SIMULATIONS = int(os.environ.get("MAX_CONCURRENT_SIMULATIONS", "1"))
MAX_PENDING_TASKS = int(os.environ.get("MAX_PENDING_TASKS", "10"))
_sim_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_SIMULATIONS)

def _run_simulation_task(task_id: str, payload_dict: Dict[str, Any], session_dir: str):
    """백그라운드에서 시뮬레이션을 실행하고 결과를 task_store에 저장"""
    try:
        with _sim_semaphore:
            task_store.mark_running(task_id)
            result = generate_idf_and_simulate(
                payload_dict, session_dir,
                on_stage=lambda s: task_store.set_stage(task_id, s),
            )
        task_store.finish(task_id, result=result)
    except Exception as e:
        print(f"❌ 시뮬레이션 에러: {str(e)}")
        task_store.finish(task_id, error=str(e))
    finally:
        # 시뮬레이션이 모두 끝난 뒤에 임시 폴더 삭제
        cleanup_workspace(session_dir)

@app.post("/api/simulate")
@limiter.limit("50/minute")
async def run_simulation(request: Request, background_tasks: BackgroundTasks, payload: SimulationPayload):
    print("🚀 시뮬레이션 비동기 요청 수신됨")

    # 업로드 화면의 차단은 클라이언트 UX 일 뿐이다. 다른 클라이언트나 변조된 요청은
    # 그 화면을 거치지 않으므로 여기서도 같은 기준으로 막는다.
    blocking, _warns = validate_simulation_payload(payload.zones, payload.surfaces)
    # baselineModel 도 같은 기준으로 본다 — 전/후 비교 시뮬레이션의 기준선이 되므로
    # 여기가 오염되면 절감량이 통째로 틀린다.
    _bm = payload.baselineModel or {}
    if _bm.get("zones") or _bm.get("surfaces"):
        _bb, _ = validate_simulation_payload(_bm.get("zones") or [], _bm.get("surfaces") or [])
        blocking += [dict(b, issue=f"baseline_{b['issue']}",
                          message="[개선 전 모델] " + b["message"]) for b in _bb]
    if blocking:
        detail = " / ".join(b["message"] for b in blocking)
        print(f"⛔ 무결성 검증 실패 — 시뮬레이션 거절: {detail}")
        raise HTTPException(status_code=422, detail=f"모델을 해석할 수 없습니다. {detail}")

    # 오래된 task 정리 후, 대기열이 꽉 찼으면 즉시 거절 (OOM 방지)
    task_store.prune(TASK_TTL_SECONDS, MAX_TASKS)
    if task_store.count_pending() >= MAX_PENDING_TASKS:
        raise HTTPException(status_code=429, detail="서버가 혼잡합니다. 잠시 후 다시 시도해주세요.")

    # 💡 시뮬레이션 환경 격리 및 Task ID 생성
    task_id = str(uuid.uuid4())
    session_dir = os.path.join(TEMP_DIR, task_id)
    os.makedirs(session_dir, exist_ok=True)

    task_store.create(task_id)

    # 백그라운드 작업으로 등록하고 즉시 응답 (100초 타임아웃 방지)
    background_tasks.add_task(_run_simulation_task, task_id, payload.model_dump(), session_dir)
    
    return {"status": "accepted", "task_id": task_id}

@app.get("/api/simulate/{task_id}")
async def get_simulation_status(task_id: str):
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)