"""API 응답 조립 — **계산하지 않는다.**

계층별 결과를 받아 프런트가 아는 JSON 모양으로 맞추는 것만 한다.
여기에 산식이 들어가면 "응답을 고치려다 계산이 바뀌는" 일이 생긴다.

⚠️ 키 이름은 **프런트와의 계약**이다. 바꾸면 화면이 깨진다.
`tests/test_response_contract.py` 가 스키마를 고정한다.
"""
from typing import Any, Dict, List

# ⚠️ 응답이 같은 내용을 **두 번** 싣는다 — 최상위에도, `result` 아래에도.
# 프런트가 두 경로를 섞어 쓰고 있어(`res.data.summary` 와 `res.data.result.summary`)
# 한쪽만 없애면 화면이 깨진다. 프런트를 한 경로로 모은 뒤에 제거할 것.
LEGACY_NESTED_KEY = "result"

# 응답 최상위 키. 순서를 고정해 snapshot diff 를 읽기 쉽게 한다.
TOP_LEVEL_KEYS = ("summary", "monthly", "matrix", "financial",
                  "surfaceThermal", "surfaceAirflow")


def assemble_response(*, summary: Dict[str, Any], monthly: List[Dict[str, Any]],
                      matrix: Dict[str, Dict[str, float]],
                      financial: Dict[str, Any],
                      surface_thermal: Dict[str, Any],
                      surface_airflow: Dict[str, Any]) -> Dict[str, Any]:
    """계층별 결과 → API 응답 dict."""
    body = {
        "summary": summary,
        "monthly": monthly,
        "matrix": matrix,
        "financial": financial,
        "surfaceThermal": surface_thermal,
        "surfaceAirflow": surface_airflow,
    }
    return {**body, LEGACY_NESTED_KEY: body}
