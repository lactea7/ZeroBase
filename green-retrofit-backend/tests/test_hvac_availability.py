"""HVAC 가용 스케줄 계약.

⚠️ EnergyPlus 의 Availability Schedule 은 값이 0 이면 **장비를 완전히 끈다.**
여기에 재실률 스케줄(Op_office 등)을 넣으면 재실이 0 인 시간 — 즉 **하루 중 가장
추운 새벽** — 에 난방기가 통째로 정지한다. 그런데 서모스탯 스케줄은 그 시간에
16℃ 셋백을 요구한다. 모델이 표방한 셋백을 스스로 실행하지 못하는 모순이 된다.

실측(용호동 0.5 ACH): 겨울 01~06시 난방이 **정확히 0.0 kWh** 였고 실온이 셋백
설정 16℃ 아래인 15.3℃ 까지 떨어졌다. 고친 뒤 난방 +19.3%, 냉방 +0.4% —
냉방은 야간 설정이 30℃ 라 손해가 없었다. **난방만 편향되게 깎였다.**
"""
import os
import re
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

GOLDEN = os.path.join(BACKEND, "tests", "golden", "representative.idf")

#: 가용 스케줄이 0 이면 서모스탯 지시를 못 따르는 객체들.
HVAC_OBJECTS = (
    "ZoneHVAC:UnitHeater",
    "ZoneHVAC:WindowAirConditioner",
    "ZoneHVAC:PackagedTerminalHeatPump",
    "ZoneHVAC:IdealLoadsAirSystem",
    "Coil:Heating:Fuel",
    "Coil:Cooling:DX:SingleSpeed",
    "Fan:SystemModel",
)

#: 재실을 따르는 게 **맞는** 객체들 — 사람이 없으면 실제로 꺼진다.
OCCUPANCY_OBJECTS = ("People", "Lights", "ElectricEquipment", "WaterUse:Equipment")


@pytest.fixture(scope="module")
def idf_text():
    if not os.path.exists(GOLDEN):
        pytest.skip("golden IDF 없음 — 먼저 test_idf_golden 을 돌려 생성할 것")
    return open(GOLDEN, encoding="utf-8").read()


def _objects(text, kind):
    """`kind` 객체들의 필드 리스트."""
    out = []
    for m in re.finditer(rf"^{re.escape(kind)},\s*\n(.*?);", text, re.S | re.M):
        out.append([f.strip() for f in m.group(1).split("\n") if f.strip()])
    return out


def test_hvac_availability_is_never_an_occupancy_schedule(idf_text):
    """⚠️ 난방기가 새벽에 꺼지면 셋백을 지킬 수 없다."""
    offenders = []
    for kind in HVAC_OBJECTS:
        for fields in _objects(idf_text, kind):
            avail = " ".join(fields)
            if re.search(r"\bOp_\w+", avail) or "CustomOpSch" in avail:
                offenders.append((kind, fields[:3]))
    assert offenders == [], f"설비 가용 스케줄에 재실률 스케줄이 들어갔다: {offenders}"


def test_occupancy_driven_loads_still_follow_occupancy(idf_text):
    """조명·기기·사람·급탕까지 AlwaysOn 으로 바꿔 버리면 내부발열이 폭증한다."""
    found = {k: False for k in OCCUPANCY_OBJECTS}
    for kind in OCCUPANCY_OBJECTS:
        for fields in _objects(idf_text, kind):
            if any(re.fullmatch(r"Op_\w+,?", f) or f.startswith("CustomOpSch") for f in fields):
                found[kind] = True
    missing = [k for k, v in found.items() if not v]
    assert missing == [], f"재실 기반이어야 할 객체가 재실 스케줄을 안 쓴다: {missing}"


def test_setback_setpoint_exists_so_availability_must_allow_it(idf_text):
    """셋백을 지정해 놓고 장비를 끄면 모순이다 — 셋백이 실재함을 확인한다."""
    m = re.search(r"(\w+_HeatSch),\s*\n\s*AnyNumber,\s*\n(.*?);", idf_text, re.S)
    assert m, "난방 설정온도 스케줄을 찾지 못했다"
    values = [float(v) for v in re.findall(r"^\s*(\d+\.\d+),?\s*$", m.group(2), re.M)]
    assert values, "설정온도 값을 읽지 못했다"
    assert min(values) < max(values), (
        "난방 설정온도가 상시 동일하다 — 셋백이 없으면 이 계약의 전제가 사라진다")
