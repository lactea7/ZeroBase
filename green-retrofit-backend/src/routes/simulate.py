# src/routes/simulate.py - 시뮬레이션 실행 라우트
import os
import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request

from src.config.settings import TEMP_DIR
from src.helpers.cleanup import cleanup_workspace
from src.models.schemas import SimulationPayload
from src.ep_simulator import generate_idf_and_simulate

router = APIRouter()

@router.post("/api/simulate")
async def run_simulation(request: Request, background_tasks: BackgroundTasks, payload: SimulationPayload):
    print("🚀 시뮬레이션 요청 수신됨")
    
    # 💡 시뮬레이션 환경 격리
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TEMP_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    
    # 시뮬레이션 완료 후 임시 폴더 삭제 예약
    background_tasks.add_task(cleanup_workspace, session_dir)
    
    try:
        # 시뮬레이터 모듈 호출 (격리된 session_dir 전달)
        result = generate_idf_and_simulate(payload.dict(), session_dir)
        return {"status": "success", "result": result}
    except Exception as e:
        print(f"❌ 시뮬레이션 에러: {str(e)}")
        raise HTTPException(status_code=500, detail=f"시뮬레이션 실패: {str(e)}")
