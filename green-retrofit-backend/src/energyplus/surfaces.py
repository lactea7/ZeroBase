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


# 열 이름을 (키, 종류)로 분해하기 위한 조각들
_KINDS = (
    ("SURFACE OUTSIDE FACE TEMPERATURE", "temp"),
    ("SURFACE OUTSIDE FACE INCIDENT SOLAR", "rad"),
    ("NODE 1 TO NODE 2 VOLUME FLOW RATE", "flow_in"),
    ("NODE 2 TO NODE 1 VOLUME FLOW RATE", "flow_out"),
)


def _build_column_index(df) -> Dict[str, Dict[str, str]]:
    """`{접두(대문자): {종류: 열이름}}` 색인을 **한 번만** 만든다.

    ⚠️ 예전엔 면마다 전체 열을 훑었다. 면 1,209개 × 열 수천 개면 그 자체로 수 초다.
    """
    index: Dict[str, Dict[str, str]] = {}
    for col in df.columns:
        upper = str(col).upper()
        head, sep, _ = upper.partition(":")
        if not sep:
            continue
        for needle, kind in _KINDS:
            if needle in upper:
                index.setdefault(head, {})[kind] = col
                break
    return index


def _find_columns(df_or_index, surface_id: str) -> Tuple[Any, Any, Any, Any]:
    """면 id 로 온도·일사 열과 창호 기류 열을 찾는다.

    ⚠️ **접두 정확 매칭**이어야 한다. 부분문자열이면 'WALL1' 이 'WALL10' 열까지 잡는다.
    `_MIRROR` 접미는 자기참조 인접면 처리에서 생기는 거울면이다.
    """
    index = (df_or_index if isinstance(df_or_index, dict)
             else _build_column_index(df_or_index))
    s_id = surface_id.upper()
    win_id = f"WIN_{surface_id}".upper()

    surf = index.get(s_id) or index.get(s_id + "_MIRROR") or {}
    win = index.get(win_id, {})
    return (surf.get("temp"), surf.get("rad"),
            win.get("flow_in"), win.get("flow_out"))


def extract_surface_outputs(df, surfaces: List[dict]) -> Tuple[Dict, Dict]:
    """(면별 온도·일사, 창호 기류) 두 dict."""
    thermal: Dict[str, Dict[str, List[float]]] = {}
    airflow: Dict[str, Dict[str, List[float]]] = {}
    if not surfaces:
        return thermal, airflow

    index = _build_column_index(df)
    rows = min(_MONTHS, len(df))
    cache: Dict[str, List[float]] = {}

    def values(col):
        """열 값을 **한 번만** 배열로 뽑아 재사용한다.

        ⚠️ 예전엔 `df.iloc[i]` 로 행을 통째로 만들었다. 수천 열짜리 DataFrame 에서
        행 하나를 만드는 데 전 열을 순회하므로, 면 1,209개 × 12행이면 23초가 걸렸다.
        """
        if col not in cache:
            cache[col] = [float(v) for v in df[col].to_numpy()[:rows]]
        return cache[col]

    for s in surfaces:
        temp_col, rad_col, flow1_col, flow2_col = _find_columns(index, s["id"])
        temp_vals = values(temp_col) if temp_col else None
        rad_vals = values(rad_col) if rad_col else None
        in_vals = values(flow1_col) if flow1_col else None
        out_vals = values(flow2_col) if flow2_col else None

        thermal[s["id"]] = {
            "temperature": [round(temp_vals[i] if temp_vals else DEFAULT_SURFACE_TEMP_C, 2)
                            for i in range(rows)],
            "radiation": [round(rad_vals[i] if rad_vals else DEFAULT_SOLAR_W_M2, 2)
                          for i in range(rows)],
        }
        airflow[s["id"]] = {
            "inflow": [round((in_vals[i] if in_vals else 0.0) * M3_S_TO_L_S, 2)
                       for i in range(rows)],
            "outflow": [round((out_vals[i] if out_vals else 0.0) * M3_S_TO_L_S, 2)
                        for i in range(rows)],
        }

    return thermal, airflow
