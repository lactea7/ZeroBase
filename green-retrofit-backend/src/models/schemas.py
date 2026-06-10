# src/models/schemas.py - Pydantic 데이터 모델
from pydantic import BaseModel
from typing import List, Dict, Any

class SimulationPayload(BaseModel):
    projectData: Dict[str, Any]
    zones: List[Dict[str, Any]]
    surfaces: List[Dict[str, Any]]
    materials: Dict[str, Any] = {}
    insulationOverrides: Dict[str, Any] = {}
