# main.py
import os
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any

from src.gbxml_parser import parse_gbxml_to_json
from src.ep_simulator import generate_idf_and_simulate

app = FastAPI(title="Green Retrofit AI Backend - gbXML Version")

# React 프론트엔드 연동을 위한 CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "temp_workspace"
os.makedirs(TEMP_DIR, exist_ok=True)

# ---------------------------------------------------------
# API 1: gbXML 업로드 및 React용 3D 데이터 파싱
# ---------------------------------------------------------
@app.post("/api/upload-gbxml")
async def upload_gbxml(file: UploadFile = File(...)):
    print(f"📥 gbXML 파일 업로드 수신: {file.filename}")
    
    if not file.filename.lower().endswith('.xml'):
        raise HTTPException(status_code=400, detail="gbXML(.xml) 파일만 업로드 가능합니다.")

    file_path = os.path.join(TEMP_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    try:
        # gbXML 파싱 모듈 호출
        parsed_data = parse_gbxml_to_json(file_path)
        return {"status": "success", "data": parsed_data}
    except Exception as e:
        print(f"❌ 파싱 에러: {str(e)}")
        raise HTTPException(status_code=500, detail=f"파싱 실패: {str(e)}")

# ---------------------------------------------------------
# API 2: 시뮬레이션 실행 (React에서 편집된 데이터 수신)
# ---------------------------------------------------------
class SimulationPayload(BaseModel):
    projectData: Dict[str, Any]
    zones: List[Dict[str, Any]]
    surfaces: List[Dict[str, Any]]

@app.post("/api/simulate")
async def run_simulation(payload: SimulationPayload):
    print("🚀 시뮬레이션 요청 수신됨")
    try:
        # 시뮬레이터 모듈 호출
        result = generate_idf_and_simulate(payload.dict(), TEMP_DIR)
        return {"status": "success", "result": result}
    except Exception as e:
        print(f"❌ 시뮬레이션 에러: {str(e)}")
        raise HTTPException(status_code=500, detail=f"시뮬레이션 실패: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)