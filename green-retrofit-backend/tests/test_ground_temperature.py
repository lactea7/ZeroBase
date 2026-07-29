# 지중온도 및 지면 승격.
#
# Site:GroundTemperature:BuildingSurface 가 없으면 EnergyPlus 는 연중 18℃ 를 가정하고
# 경고만 남긴다. Ground 경계면의 열손실이 전적으로 이 값에 좌우되므로 명시해야
# 민감도 비교를 해석할 수 있다.
import pytest

from src.activity_schedules import monthly_ground_temperatures
from src.idf_builder import IdfBuilder


def test_twelve_monthly_values():
    assert len(monthly_ground_temperatures()) == 12


def test_offset_below_indoor_setpoint():
    """EnergyPlus 지침대로 실내온도보다 2K 낮은 값을 쓴다."""
    g = monthly_ground_temperatures(heat_setpoint=20.0, cool_setpoint=26.0)
    assert g[0] == 18.0    # 1월 — 난방기
    assert g[6] == 24.0    # 7월 — 냉방기


def test_follows_zone_setpoints():
    """존 설정온도가 다르면 지중온도도 따라간다 (의료시설 22/25 등)."""
    g = monthly_ground_temperatures(heat_setpoint=22.0, cool_setpoint=25.0)
    assert g[0] == 20.0
    assert g[6] == 23.0


def test_not_undisturbed_soil_temperature():
    """EPW 비교란 토양온도를 그대로 쓰지 않는다.

    서울 EPW 2m 깊이 2월은 3.4℃ 다. 난방 건물 하부는 실내온도로 damping 되므로
    비교란 값을 넣으면 겨울 바닥 열손실이 비현실적으로 커진다.
    """
    g = monthly_ground_temperatures()
    assert min(g) > 10.0, f"겨울 지중온도가 비교란 토양온도 수준으로 낮다: {min(g)}"


def test_idf_emits_ground_temperature_object():
    idf = IdfBuilder()
    idf.add_ground_temperatures(monthly_ground_temperatures())
    text = "\n".join(o.to_idf() for o in idf.objects)
    assert "Site:GroundTemperature:BuildingSurface" in text


def test_idf_rejects_wrong_length():
    idf = IdfBuilder()
    with pytest.raises(ValueError):
        idf.add_ground_temperatures([18.0] * 11)
