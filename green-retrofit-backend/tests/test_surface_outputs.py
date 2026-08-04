"""`energyplus/surfaces.py` 단위시험.

이 코드는 분리 전까지 **시험이 하나도 없었다.** 3D 뷰어 오버레이의 유일한 출처인데
열 매칭이 틀려도 화면에 그럴듯한 값이 나오므로 조용히 잘못될 수 있다.
"""
import os
import sys

import pandas as pd
import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.energyplus.surfaces import (  # noqa: E402
    DEFAULT_SOLAR_W_M2,
    DEFAULT_SURFACE_TEMP_C,
    extract_surface_outputs,
)

TEMP = "Surface Outside Face Temperature [C](Monthly)"
SOLAR = "Surface Outside Face Incident Solar Radiation Rate per Area [W/m2](Monthly)"
FLOW_IN = "AFN Linkage Node 1 to Node 2 Volume Flow Rate [m3/s](Monthly)"
FLOW_OUT = "AFN Linkage Node 2 to Node 1 Volume Flow Rate [m3/s](Monthly)"


def _df(**cols):
    n = max(len(v) for v in cols.values()) if cols else 12
    return pd.DataFrame({"Date/Time": [f"{i+1}월" for i in range(n)], **cols})


def test_temperature_and_solar_are_matched_by_surface_id():
    df = _df(**{f"WALL_S:{TEMP}": [1.5] * 12, f"WALL_S:{SOLAR}": [200.0] * 12})
    thermal, _ = extract_surface_outputs(df, [{"id": "WALL_S"}])
    assert thermal["WALL_S"]["temperature"] == [1.5] * 12
    assert thermal["WALL_S"]["radiation"] == [200.0] * 12


def test_mirror_surfaces_are_matched():
    """자기참조 인접면 처리에서 생기는 `_MIRROR` 면도 같은 면으로 본다."""
    df = _df(**{f"WALL_S_MIRROR:{TEMP}": [3.0] * 12})
    thermal, _ = extract_surface_outputs(df, [{"id": "WALL_S"}])
    assert thermal["WALL_S"]["temperature"] == [3.0] * 12


def test_prefix_matching_is_exact():
    """⚠️ 부분문자열이면 'WALL1' 이 'WALL10' 열을 잡아 엉뚱한 면의 값을 보여준다."""
    df = _df(**{f"WALL10:{TEMP}": [99.0] * 12, f"WALL1:{TEMP}": [1.0] * 12})
    thermal, _ = extract_surface_outputs(df, [{"id": "WALL1"}])
    assert thermal["WALL1"]["temperature"] == [1.0] * 12


def test_missing_columns_use_display_defaults():
    """출력이 없어도 뷰어가 비지 않도록 기본값을 채운다."""
    thermal, airflow = extract_surface_outputs(_df(**{f"OTHER:{TEMP}": [0.0] * 12}),
                                               [{"id": "WALL_S"}])
    assert thermal["WALL_S"]["temperature"] == [DEFAULT_SURFACE_TEMP_C] * 12
    assert thermal["WALL_S"]["radiation"] == [DEFAULT_SOLAR_W_M2] * 12
    assert airflow["WALL_S"]["inflow"] == [0.0] * 12


def test_window_airflow_uses_win_prefix_and_litres():
    """창 기류 열은 `WIN_{면id}` 로 붙고, m³/s → L/s 로 1000배 한다."""
    df = _df(**{f"WIN_WALL_S:{FLOW_IN}": [0.001] * 12,
                f"WIN_WALL_S:{FLOW_OUT}": [0.002] * 12})
    _, airflow = extract_surface_outputs(df, [{"id": "WALL_S"}])
    assert airflow["WALL_S"]["inflow"] == [1.0] * 12
    assert airflow["WALL_S"]["outflow"] == [2.0] * 12


def test_window_flow_is_not_confused_with_surface_columns():
    """면 열과 창 열이 섞이면 안 된다 — 접두가 다르다."""
    df = _df(**{f"WALL_S:{TEMP}": [5.0] * 12, f"WIN_WALL_S:{FLOW_IN}": [0.003] * 12})
    thermal, airflow = extract_surface_outputs(df, [{"id": "WALL_S"}])
    assert thermal["WALL_S"]["temperature"] == [5.0] * 12
    assert airflow["WALL_S"]["inflow"] == [3.0] * 12


def test_every_surface_gets_an_entry():
    df = _df(**{f"A:{TEMP}": [1.0] * 12})
    thermal, airflow = extract_surface_outputs(df, [{"id": "A"}, {"id": "B"}, {"id": "C"}])
    assert set(thermal) == {"A", "B", "C"} == set(airflow)


def test_short_data_yields_short_series():
    df = _df(**{f"A:{TEMP}": [1.0, 2.0, 3.0]})
    thermal, _ = extract_surface_outputs(df, [{"id": "A"}])
    assert thermal["A"]["temperature"] == [1.0, 2.0, 3.0]


def test_values_are_rounded_to_two_decimals():
    df = _df(**{f"A:{TEMP}": [1.23456] * 12})
    thermal, _ = extract_surface_outputs(df, [{"id": "A"}])
    assert thermal["A"]["temperature"] == [1.23] * 12


def test_no_surfaces_returns_empty():
    assert extract_surface_outputs(_df(**{f"A:{TEMP}": [1.0] * 12}), []) == ({}, {})


# ── 알려진 결함 ──────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason=(
    "행 인덱스 0~11 을 그대로 '월'로 쓴다. 월별 CSV(12행)에서는 우연히 맞지만 "
    "실제 운영에서 쓰는 시간별 CSV(8,760행)에서는 **1월 1일 1~12시**가 월별 값으로 "
    "나간다. 3D 뷰어에는 12개월로 표시된다. 고치면 뷰어 값이 전부 바뀌므로 "
    "별도 커밋에서 다룬다."))
def test_hourly_csv_should_aggregate_by_month_not_first_12_rows():
    hourly = pd.DataFrame({
        "Date/Time": [f" {m:02d}/01  {h:02d}:00:00"
                      for m in range(1, 13) for h in range(1, 25)],
        # 1월은 0℃, 2월은 1℃ … 12월은 11℃
        f"A:{TEMP.replace('Monthly', 'Hourly')}": [float(m - 1)
                                                   for m in range(1, 13) for _ in range(24)],
    })
    thermal, _ = extract_surface_outputs(hourly, [{"id": "A"}])
    # 월별로 집계했다면 0..11 이 나와야 한다. 실제로는 1월 1일 12시간이라 전부 0 이다.
    assert thermal["A"]["temperature"] == [float(m) for m in range(12)]
