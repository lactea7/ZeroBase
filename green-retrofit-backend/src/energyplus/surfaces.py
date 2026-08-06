"""면별 외피 온도·일사와 창호 기류 추출 — 3D 뷰어 오버레이용.

`cost_analyzer._surface_outputs()` 에서 옮겼다. 순수 이동이며 동작을 바꾸지 않았다.

⚠️ **집계 규칙은 물리량에 따라 다르다.**
온도·일사율(W/㎡)·유량(m³/s)은 **상태량**이라 월평균이고, 에너지량이 추가되면
월합계여야 한다. 모든 열에 같은 집계를 적용하면 안 된다.

과거 결함(2026-08-06 수정): 행 인덱스 0~11 을 그대로 "월"로 썼다. 월별 CSV(12행)
에서는 우연히 맞았지만 실제 운영의 시간별 CSV(8,760행)에서는 **1월 1일 1~12시**가
월별 값으로 나갔다 — 3D 뷰어에 12개월로 표시됐다.
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


def _monthly_means(values: List[float], months: List[int], missing: float) -> List[float]:
    """월별 **평균**. 데이터가 없는 달은 `missing` 으로 채운다.

    온도·일사율·유량은 상태량이므로 합계가 아니라 평균이다.
    (에너지량 열이 추가되면 합계용 함수를 따로 둘 것)
    """
    sums = [0.0] * _MONTHS
    counts = [0] * _MONTHS
    for v, m in zip(values, months):
        if 1 <= m <= _MONTHS:
            sums[m - 1] += v
            counts[m - 1] += 1
    return [sums[i] / counts[i] if counts[i] else missing for i in range(_MONTHS)]


def extract_surface_outputs(df, surfaces: List[dict], months=None) -> Tuple[Dict, Dict]:
    """(면별 온도·일사, 창호 기류) 두 dict. 각 12개월.

    `months` 를 주지 않으면 DataFrame 에서 시간축을 직접 읽는다.
    """
    thermal: Dict[str, Dict[str, List[float]]] = {}
    airflow: Dict[str, Dict[str, List[float]]] = {}
    if not surfaces:
        return thermal, airflow

    if months is None:
        months = _months_of(df)
    months = list(months)

    index = _build_column_index(df)
    cache: Dict[str, List[float]] = {}

    def values(col):
        """열 값을 **한 번만** 배열로 뽑아 재사용한다.

        ⚠️ 예전엔 `df.iloc[i]` 로 행을 통째로 만들었다. 수천 열짜리 DataFrame 에서
        행 하나를 만드는 데 전 열을 순회하므로, 면 1,209개 × 12행이면 23초가 걸렸다.
        """
        if col not in cache:
            cache[col] = [float(v) for v in df[col].to_numpy()]
        return cache[col]

    def series(col, missing):
        if not col:
            return [missing] * _MONTHS
        return _monthly_means(values(col), months, missing)

    for s in surfaces:
        temp_col, rad_col, flow1_col, flow2_col = _find_columns(index, s["id"])
        thermal[s["id"]] = {
            "temperature": [round(v, 2) for v in series(temp_col, DEFAULT_SURFACE_TEMP_C)],
            "radiation": [round(v, 2) for v in series(rad_col, DEFAULT_SOLAR_W_M2)],
        }
        airflow[s["id"]] = {
            "inflow": [round(v * M3_S_TO_L_S, 2) for v in series(flow1_col, 0.0)],
            "outflow": [round(v * M3_S_TO_L_S, 2) for v in series(flow2_col, 0.0)],
        }

    return thermal, airflow


def _months_of(df) -> List[int]:
    """각 행의 월. 시간별이면 타임스탬프에서, 월별이면 순서대로."""
    from src.energyplus.outputs import TimeResolution, detect_resolution

    n = len(df)
    if detect_resolution(df) is TimeResolution.HOURLY:
        first = df.iloc[:, 0].astype(str)
        extracted = first.str.extract(r"(\d{1,2})/\d{1,2}")[0]
        if extracted.notna().any():
            return [int(v) if v == v else 1 for v in extracted.fillna(1).astype(int)]
    return [(i % _MONTHS) + 1 for i in range(n)]
