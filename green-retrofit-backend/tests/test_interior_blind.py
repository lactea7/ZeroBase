"""내부 블라인드(일사 제어) 계약.

⚠️ 차양이 전혀 없으면 **결과가 통째로 왜곡된다.** 실측(용호동 8,760시간):
창 268㎡ · SHGC 0.76 · 차양 0 → 순 일사취득 **235 kWh/㎡·년**. 그 열이 겨울
난방을 상쇄하고 여름 냉방을 밀어 올려, 서울 사무소인데 난방 10.6 / 냉방 54.1
kWh/㎡ 라는 결과가 나왔다. 블라인드를 넣자 난방 19.0 (+80%) 으로 올랐다.

⚠️ 반대로 ASHRAE 140 에는 **절대 걸면 안 된다.** 600 vs 610 의 유일한 차이가
외부 차양이라, 내부 블라인드가 붙으면 그 델타가 오염되고 참조값 비교가
성립하지 않는다.
"""
import os
import re
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.idf_builder import IdfBuilder  # noqa: E402

GOLDEN = os.path.join(BACKEND, "tests", "golden", "representative.idf")


@pytest.fixture(scope="module")
def idf_text():
    if not os.path.exists(GOLDEN):
        pytest.skip("golden IDF 없음")
    return open(GOLDEN, encoding="utf-8").read()


def test_real_model_gets_interior_blinds(idf_text):
    assert "WindowMaterial:Blind," in idf_text, "블라인드 재료가 없다"
    assert "WindowShadingControl," in idf_text, "일사 제어가 없다"


def test_blind_material_is_defined_once(idf_text):
    """창마다 만들면 IDF 가 부풀고 EnergyPlus 가 중복 이름으로 실패한다."""
    assert idf_text.count("WindowMaterial:Blind,") == 1


def test_control_is_solar_triggered_not_always_on(idf_text):
    """상시 하강이면 겨울 일사취득을 통째로 버린다 — 난방이 과대해진다."""
    assert "OnIfHighSolarOnWindow" in idf_text
    assert "AlwaysOn" not in re.search(
        r"WindowShadingControl,(.*?);", idf_text, re.S).group(1)


def test_every_controlled_window_actually_exists(idf_text):
    """⚠️ 없는 창을 참조하면 EnergyPlus 가 Severe 로 죽는다."""
    windows = set(re.findall(r"^FenestrationSurface:Detailed,\s*\n\s*([^,]+),", idf_text, re.M))
    assert windows, "창이 하나도 없다"
    for m in re.finditer(r"WindowShadingControl,(.*?);", idf_text, re.S):
        fields = [f.strip() for f in m.group(1).split("\n") if f.strip().rstrip(",")]
        referenced = [f.rstrip(",") for f in fields if f.rstrip(",") in windows]
        assert referenced, f"제어가 참조하는 창을 못 찾았다: {fields[:4]}"


def test_shading_type_is_interior(idf_text):
    """외부 차양으로 잘못 넣으면 냉방 저감이 과대해진다 — 내부 블라인드는
    일사를 실내에서 흡수하므로 효과가 훨씬 작다."""
    assert "InteriorBlind" in idf_text


# ── 벤치마크 격리 ────────────────────────────────────────

def test_benchmark_cases_disable_the_blind():
    from tests.ashrae140.cases.bestest import build_payload
    payload = build_payload("600")
    assert payload["benchmark"]["noInteriorBlind"] is True, (
        "ASHRAE 140 에 내부 블라인드가 붙으면 610 델타가 오염된다")


# ── 빌더 단위 ────────────────────────────────────────────

def test_no_control_emitted_without_windows():
    idf = IdfBuilder()
    n = len(idf.objects)
    idf.add_window_shading_control("Z1", [])
    assert len(idf.objects) == n, "창이 없는데 제어를 만들었다"


def test_setpoint_is_overridable():
    idf = IdfBuilder()
    idf.add_window_shading_control("Z1", ["W1"], setpoint_w_m2=350.0)
    fields = idf.objects[-1].fields
    assert 350.0 in fields
    assert "W1" in fields


def test_zone_and_windows_land_in_the_right_fields():
    idf = IdfBuilder()
    idf.add_window_shading_control("Zone_A", ["W1", "W2"])
    f = idf.objects[-1].fields
    assert f[1] == "Zone_A", "존 이름이 2번 필드가 아니다"
    assert f[3] == "InteriorBlind"
    assert "W1" in f and "W2" in f
