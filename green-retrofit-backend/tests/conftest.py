# 공통 픽스처: 실제 건물(ARK 샘플) 파싱 결과 + 월별 EnergyPlus 출력 CSV
# EnergyPlus 풀런(~2.5분) 없이 초 단위로 비용 산식 전체를 회귀 검증한다.
import json
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

FIXTURE_DIR = os.path.join(BACKEND_DIR, "tests", "fixtures")
CSV_PATH = os.path.join(FIXTURE_DIR, "eplusout_monthly.csv")
BUILDING_PATH = os.path.join(FIXTURE_DIR, "ark_building.json")
DB_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "_data")


@pytest.fixture(scope="session")
def building():
    with open(BUILDING_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def analyzer():
    from src.cost_analyzer import LCCAnalyzer
    return LCCAnalyzer(DB_DIR)


@pytest.fixture(scope="session")
def base_kwargs(building):
    """calculate()의 공통 인자. 개별 테스트는 dict(base_kwargs, ...)로 덮어쓴다."""
    from src.ep_simulator import calculate_surface_area

    zones = building["zones"]
    surfaces = building["surfaces"]

    total_area = total_window_area = total_wall_area = 0.0
    for s in surfaces:
        t = s.get("type", "").lower()
        a = calculate_surface_area(s.get("vertices", []))
        if "floor" in t or "slab" in t:
            total_area += a
        if "wall" in t:
            total_wall_area += a
            total_window_area += a * (s.get("wwr", 0) / 100.0)

    return dict(
        eplus_csv_path=CSV_PATH,
        zones=zones,
        surfaces=surfaces,
        materials=building.get("materials", {}),
        total_area=total_area,
        total_window_area=total_window_area,
        total_wall_area=total_wall_area,
        target_u=2.74,
        target_shgc=0.6,
        pv_capacity_kw=0.0,
        is_geothermal=False,
        act_main=1105,
        target_budget=0.0,
        led_fixture_count=0,
        led_reduction_active=False,
        heat_source=11,
    )
