"""AFN 외피 균열의 면적 정규화 계약.

⚠️ 예전에는 모든 Outdoors 표면이 같은 `WallCrack`(계수 0.01)을 factor 1.0 으로
공유했다. 총 누기가 외피 기밀성이 아니라 **표면 개수**에 좌우돼, gbXML 이 벽
하나를 여러 폴리곤으로 내보내면 침기가 그만큼 늘었다.
실측(ASHRAE 140 케이스 600, 북벽만 분할): 1개 6.4972 → 8개 8.6720 MWh (+33.5%).
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.idf_builder import (  # noqa: E402
    WALL_CRACK_COEFFICIENT_PER_M2,
    WALL_CRACK_EXPONENT,
    WALL_CRACK_Q50_M3_H_M2,
    IdfBuilder,
)

AIR_DENSITY = 1.2


def test_coefficient_reproduces_the_stated_leakage_at_50pa():
    """계수의 근거를 되짚는다 — Q = C·ΔP^n 에 50 Pa 를 넣으면 q50 이 나와야 한다."""
    q50 = WALL_CRACK_COEFFICIENT_PER_M2 * (50.0 ** WALL_CRACK_EXPONENT) / AIR_DENSITY * 3600
    assert q50 == pytest.approx(WALL_CRACK_Q50_M3_H_M2, rel=1e-3)


def test_crack_coefficient_scales_with_area():
    idf = IdfBuilder()
    idf.add_surface_crack("S1", 10.0)
    idf.add_surface_crack("S2", 40.0)
    c1, c2 = idf.objects[-2].fields[1], idf.objects[-1].fields[1]
    assert c2 == pytest.approx(c1 * 4)


def test_splitting_a_surface_preserves_total_leakage():
    """⚠️ 이 시험이 결함의 본질이다 — 쪼개도 합이 같아야 한다."""
    whole = IdfBuilder()
    whole.add_surface_crack("W", 48.0)
    total_whole = whole.objects[-1].fields[1]

    split = IdfBuilder()
    for i in range(8):
        split.add_surface_crack(f"W{i}", 6.0)
    total_split = sum(o.fields[1] for o in split.objects[-8:])

    assert total_split == pytest.approx(total_whole, rel=1e-6)


def test_each_surface_gets_its_own_component():
    """이름이 겹치면 EnergyPlus 가 중복 정의로 죽는다."""
    idf = IdfBuilder()
    names = {idf.add_surface_crack(f"S{i}", 10.0) for i in range(5)}
    assert len(names) == 5


def test_zero_and_negative_area_do_not_produce_negative_leakage():
    """⚠️ 음수 계수는 공기가 거꾸로 새는 물리적으로 불가능한 모델이 된다."""
    idf = IdfBuilder()
    idf.add_surface_crack("S1", 0.0)
    idf.add_surface_crack("S2", -5.0)
    assert idf.objects[-2].fields[1] == 0
    assert idf.objects[-1].fields[1] == 0


def test_exponent_is_not_scaled():
    """유동지수는 면적과 무관한 균열 특성이다."""
    idf = IdfBuilder()
    idf.add_surface_crack("S1", 100.0)
    assert idf.objects[-1].fields[2] == WALL_CRACK_EXPONENT
