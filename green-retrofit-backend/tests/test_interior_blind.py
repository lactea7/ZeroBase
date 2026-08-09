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


# ── 가정의 노출 ──────────────────────────────────────────
# ⚠️ gbXML 은 블라인드 유무를 담지 않는다. **있다고 가정**하는 것이고 결과에
# 크게 영향을 주므로(난방 10.6 → 19.0 kWh/㎡) 응답에 드러나야 한다.

def test_setpoint_default_is_within_the_literature_range():
    """문헌 문턱값은 50~377 W/㎡ 다. 그 밖이면 근거 없는 값이다."""
    assert 50 <= IdfBuilder.BLIND_SOLAR_SETPOINT_W_M2 <= 377


def test_blind_assumption_is_reported_in_the_response():
    """사용자가 '차양 가정'을 볼 수 없으면 결과를 검증할 수 없다."""
    import re
    src = open(os.path.join(BACKEND, "src", "ep_simulator.py"), encoding="utf-8").read()
    m = re.search(r'"key":\s*"interior_blind".*?"confidence":\s*"(\w+)"', src, re.S)
    assert m, "assumptions 에 interior_blind 항목이 없다"
    assert m.group(1) == "low", "측정값이 아니라 가정이므로 confidence 는 low 여야 한다"


# ── 창이 많은 존 ─────────────────────────────────────────
# ⚠️ IDD 는 반복 필드를 **예시로 10개만** 나열한다. 그 개수를 상한으로 착각해
# 이름으로 넣었더니 11번째부터 "IDD에 없는 필드"로 거부됐고, 창 22개짜리 존이 있는
# 실제 모델(회의실.xml)에서 **시뮬레이션이 통째로 죽었다.**

@pytest.mark.parametrize("count", [1, 9, 10, 11, 22, 50])
def test_any_number_of_windows_is_accepted(count):
    idf = IdfBuilder()
    idf.add_window_shading_control("Z1", [f"W{i}" for i in range(count)])
    fields = idf.objects[-1].fields
    assert fields[-count:] == [f"W{i}" for i in range(count)]


def test_windows_start_at_the_extensible_position():
    """⚠️ 반복 값이 한 칸이라도 밀리면 EnergyPlus 가 엉뚱한 필드로 읽는다."""
    from src.idf_builder import _get_idd_index
    start = _get_idd_index()["windowshadingcontrol"]["ext_start"]
    idf = IdfBuilder()
    idf.add_window_shading_control("Z1", ["W1", "W2"])
    fields = idf.objects[-1].fields
    assert fields[start] == "W1"
    assert fields[start + 1] == "W2"
    # 반복 시작 **직전**은 명시 필드여야 한다(빈칸으로 밀리지 않았는지)
    assert fields[start - 1] == "Sequential"


def test_named_fields_are_still_validated():
    """확장을 허용했다고 오타 검출까지 잃으면 안 된다."""
    idf = IdfBuilder()
    with pytest.raises(ValueError, match="IDD에 없는 필드"):
        idf._emit_by_idd("WindowShadingControl", {"없는필드": 1})


def test_non_extensible_object_rejects_extensible_values():
    idf = IdfBuilder()
    with pytest.raises(ValueError, match="확장"):
        idf._emit_by_idd("Zone", {"Name": "Z1"}, extensible=["x"])


def test_named_field_inside_the_extensible_range_is_rejected():
    """⚠️ 명시 필드가 반복 구간을 침범하면 값이 통째로 밀린다."""
    idf = IdfBuilder()
    with pytest.raises(ValueError, match="extensible"):
        idf._emit_by_idd("WindowShadingControl",
                         {"Name": "C", "Fenestration Surface 1 Name": "W1"},
                         extensible=["W2"])
