"""면별 외피 온도·일사와 창호 기류 추출 — 3D 뷰어 오버레이용.

`cost_analyzer._surface_outputs()` 에서 옮겼다. 순수 이동이며 동작을 바꾸지 않았다.

⚠️ **알려진 결함(이동 시점에 발견, 아직 안 고침)**:
`_MONTHS` 개의 값을 뽑을 때 **행 인덱스 0~11 을 그대로 쓴다.** 월별 CSV(12행)에서는
우연히 맞지만, 실제 운영에서 쓰는 **시간별 CSV(8,760행)에서는 1월 1일 1~12시**가
"월별" 값으로 나간다. 화면에는 12개월로 표시된다.
고치면 3D 뷰어의 값이 전부 바뀌므로 별도 커밋에서 다룬다 — 여기서는 이동만 한다.
`tests/test_surface_outputs.py` 의 xfail 시험이 이 결함을 고정하고 있다.
"""
from typing import Any, Dict, List, Tuple

_MONTHS = 12

# 해당 출력이 없을 때 쓰는 표시용 기본값. 실제 계산이 아니라 뷰어가 비지 않게 하는 값이다.
DEFAULT_SURFACE_TEMP_C = 20.0
DEFAULT_SOLAR_W_M2 = 100.0

M3_S_TO_L_S = 1000.0


def _find_columns(df, surface_id: str) -> Tuple[Any, Any, Any, Any]:
    """면 id 로 온도·일사 열과 창호 기류 열을 찾는다.

    ⚠️ **접두 정확 매칭**이어야 한다. 부분문자열이면 'WALL1' 이 'WALL10' 열까지 잡는다.
    `_MIRROR` 접미는 자기참조 인접면 처리에서 생기는 거울면이다.
    """
    s_id = surface_id.upper()
    win_id = f"WIN_{surface_id}".upper()
    temp_col = rad_col = flow1_col = flow2_col = None

    for col in df.columns:
        upper = col.upper()
        if upper.startswith(s_id + ":") or upper.startswith(s_id + "_MIRROR:"):
            if "SURFACE OUTSIDE FACE TEMPERATURE" in upper:
                temp_col = col
            elif "SURFACE OUTSIDE FACE INCIDENT SOLAR" in upper:
                rad_col = col
        elif upper.startswith(win_id + ":"):
            if "NODE 1 TO NODE 2 VOLUME FLOW RATE" in upper:
                flow1_col = col
            elif "NODE 2 TO NODE 1 VOLUME FLOW RATE" in upper:
                flow2_col = col

    return temp_col, rad_col, flow1_col, flow2_col


def extract_surface_outputs(df, surfaces: List[dict]) -> Tuple[Dict, Dict]:
    """(면별 온도·일사, 창호 기류) 두 dict."""
    thermal: Dict[str, Dict[str, List[float]]] = {}
    airflow: Dict[str, Dict[str, List[float]]] = {}

    for s in surfaces or []:
        temp_col, rad_col, flow1_col, flow2_col = _find_columns(df, s["id"])

        temps, rads, inflow, outflow = [], [], [], []
        for i in range(min(_MONTHS, len(df))):
            row = df.iloc[i]
            temps.append(round(float(row[temp_col]) if temp_col else DEFAULT_SURFACE_TEMP_C, 2))
            rads.append(round(float(row[rad_col]) if rad_col else DEFAULT_SOLAR_W_M2, 2))
            inflow.append(round((float(row[flow1_col]) if flow1_col else 0.0) * M3_S_TO_L_S, 2))
            outflow.append(round((float(row[flow2_col]) if flow2_col else 0.0) * M3_S_TO_L_S, 2))

        thermal[s["id"]] = {"temperature": temps, "radiation": rads}
        airflow[s["id"]] = {"inflow": inflow, "outflow": outflow}

    return thermal, airflow
