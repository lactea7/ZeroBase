"""ASHRAE 140 Tier B — **우리 파이프라인**이 케이스를 정확히 번역하는가.

Tier A 와 달리 여기서는 케이스를 우리 payload 형식으로 만들어
`generate_idf_and_simulate()` 에 그대로 넣는다. 즉 `IdfBuilder`,
구성체 생성, 창 형상, 경계조건, 스케줄, HVAC 조립이 전부 시험 대상이다.

같은 EnergyPlus 로 도는 Tier A 결과가 대조군이다 —
**Tier A 가 통과하는데 Tier B 가 실패하면 결함은 우리 번역 계층에 있다.**

⚠️ 이 시험을 통과해도 "우리 외피 구현이 옳다"고 말할 수 없다. 단순 상자 하나이고
보상오차가 있을 수 있다. 케이스와 델타를 늘려야 강한 진술이 된다 — README 참조.
"""
import csv
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "cases"))
sys.path.insert(0, str(HERE.parent.parent))          # green-retrofit-backend
sys.path.insert(0, str(HERE.parent.parent / "src"))

J_TO_MWH = 3.6e9

# NREL 이 같은 EnergyPlus 25.2.0 으로 낸 값. Tier A 가 이미 ±0.4% 로 재현하므로
# Tier B 도 같은 수준이어야 한다 — 벌어지면 우리 번역 계층의 결함이다.
TOLERANCE_PCT = 1.0

CASES = {
    "600": {"heating": 4.3250, "cooling": 6.0417},
}


def _energyplus():
    if not shutil.which("energyplus"):
        pytest.skip("energyplus 가 PATH 에 없다")


@pytest.fixture(scope="module")
def case600_result(tmp_path_factory):
    _energyplus()
    from case600 import build_payload
    from ep_simulator import generate_idf_and_simulate

    tmp = tmp_path_factory.mktemp("tierb600")
    generate_idf_and_simulate(build_payload(), str(tmp))

    csv_path = tmp / "eplusout.csv"
    assert csv_path.exists(), "eplusout.csv 가 없다 — 시뮬레이션이 실패했을 수 있다"

    rows = list(csv.reader(csv_path.open()))
    header = rows[0]

    def total(fragment: str) -> float:
        idx = [i for i, h in enumerate(header) if fragment in h]
        assert idx, f"출력 열을 찾을 수 없다: {fragment}"
        return sum(float(r[idx[0]] or 0) for r in rows[1:]) / J_TO_MWH

    return {
        "heating": total("Zone Air System Sensible Heating Energy"),
        "cooling": total("Zone Air System Sensible Cooling Energy"),
    }


@pytest.mark.slow
@pytest.mark.parametrize("metric", ["heating", "cooling"])
def test_case600_matches_reference(metric, case600_result):
    """우리 파이프라인이 만든 케이스 600 이 NREL 기준값을 재현하는가."""
    expected = CASES["600"][metric]
    got = case600_result[metric]
    delta = (got - expected) / expected * 100
    assert abs(delta) <= TOLERANCE_PCT, (
        f"케이스 600 {metric}: 우리 파이프라인={got:.4f} NREL={expected:.4f} MWh "
        f"({delta:+.2f}%, 허용 ±{TOLERANCE_PCT}%)\n"
        f"  Tier A(표준 IDF)는 통과하는데 여기서 벌어졌다면 원인은 우리 번역 계층이다.\n"
        f"  확인 순서: 구성체 레이어 → 창 형상·유리 → 경계조건/노출 →\n"
        f"            설정온도 스케줄 → 침기(AFN 이 ZoneInfiltration 을 대체하는지) → 내부발열"
    )


@pytest.mark.slow
def test_benchmark_config_is_opt_in():
    """`benchmark` 키가 없으면 일반 사용자 경로가 조금도 달라지지 않아야 한다.

    벤치마크는 외기 0·자동부하 억제·AFN off 처럼 실제 프로젝트에 적용하면 안 되는
    값을 강제한다. 그 설정이 기본값으로 새면 모든 프로젝트가 조용히 망가진다.
    """
    from idf_builder import IdfBuilder

    plain = IdfBuilder(version="25.2")
    plain.add_building("X", 0)
    plain.add_ideal_hvac("Z1")
    text = "\n".join(o.to_idf() for o in plain.objects)

    assert "FullExterior" in text and "FullInteriorAndExterior" not in text, \
        "벤치마크용 태양복사 분배가 기본 경로로 샜다"
    assert "Suburbs" in text, "벤치마크용 지형이 기본 경로로 샜다"
    assert "DesignSpecification:OutdoorAir" in text, \
        "기본 경로에서 외기 도입이 사라졌다 — 벤치마크 설정이 샜다"
    assert "Timestep,\n  4" in text, "벤치마크 타임스텝이 기본 경로로 샜다"
