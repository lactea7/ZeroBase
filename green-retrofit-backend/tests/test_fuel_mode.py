# 연료 실기기 모드(가스/등유/지역난방 = UnitHeater+WindowAC) 회귀 테스트
# 픽스처: 단일 존 가스보일러 연간 시뮬 출력 (gzip — pandas가 확장자로 자동 해제)
import os

import pytest

from conftest import FIXTURE_DIR

FUEL_CSV = os.path.join(FIXTURE_DIR, "eplusout_fuel_hourly.csv.gz")


@pytest.fixture(scope="module")
def fuel_result(analyzer, base_kwargs):
    return analyzer.calculate(**dict(
        base_kwargs, eplus_csv_path=FUEL_CSV,
        heat_source=1, hvac_mode="fuel",
        heating_fuel="NaturalGas", heating_fuel_eff=0.87,
    ))


def test_fuel_heating_from_gas_meter(fuel_result):
    """난방 소비는 Heating:NaturalGas 미터(연료 kWh)에서 와야 한다."""
    m = fuel_result["matrix"]
    assert m["heating"]["con"] == pytest.approx(1.5, abs=0.1)
    # 연소효율(0.87) 반영 → 연료 소비 > 현열 요구량
    assert m["heating"]["con"] > m["heating"]["req"]


def test_fuel_cooling_is_real_dx(fuel_result):
    """냉방은 WindowAC DX 실소비(전기) — COP>1이므로 소비 < 요구량."""
    m = fuel_result["matrix"]
    assert m["cooling"]["con"] > 0
    assert m["cooling"]["con"] < m["cooling"]["req"]


def test_fuel_billing_split(fuel_result):
    """난방 연료 → 열요금(가스 단가), 냉방·팬 → 전기요금."""
    fin = fuel_result["financial"]
    assert fin["heat_source"] == "가스보일러"
    assert fin["annual_heat_bill"] == 134_841       # 골든 (가스 78.12원/kWh)
    assert fin["annual_elec_bill"] == 3_728_001     # 골든 (냉방+조명+기기+팬)


def test_heat_source_db_has_all_fuels(analyzer):
    """열원 DB에 가스(1)/전기(2)/등유(4)/지역난방(11) 모두 있어야 폴백 오적용이 없다."""
    for hs in (1, 2, 4, 11):
        assert hs in analyzer.HEAT_SOURCE_DB
    assert analyzer.HEAT_SOURCE_DB[1]["label"] == "가스보일러"
