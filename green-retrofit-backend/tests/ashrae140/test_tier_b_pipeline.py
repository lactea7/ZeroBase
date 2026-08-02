"""ASHRAE 140 Tier B — **우리 파이프라인**이 케이스를 정확히 번역하는가.

Tier A 와 달리 여기서는 케이스를 우리 payload 형식으로 만들어
`generate_idf_and_simulate()` 에 그대로 넣는다. 즉 `IdfBuilder`, 구성체 생성,
창 형상, 경계조건, 차양, 스케줄, HVAC 조립이 전부 시험 대상이다.

Tier A 가 대조군이다 — **Tier A 가 통과하는데 Tier B 가 실패하면 결함은
우리 번역 계층에 있다.**

케이스별로 기준(600)에서 **하나씩만** 바꾼다. 델타 검사는 그 하나의 물리 효과를
격리해서 때리므로 절대값보다 예민하다:
  620−600  창 방위 (남 12 ㎡ → 동·서 각 6 ㎡)
  900−600  열용량 (경량 → 중량)   ← `layers` 가 열용량을 보존하는지 검증
  610−600  차양 (남벽 1 m 돌출)   ← 차양 지원이 일사를 실제로 깎는지 검증

⚠️ 전부 통과해도 "우리 외피 구현이 옳다"고 단정할 수 없다. 단순 상자이고
보상오차가 있을 수 있다 — README 「이 벤치마크가 답해주지 않는 것」 참조.
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

CASES = ("600", "620", "900", "610")

# NREL 이 같은 EnergyPlus 25.2.0 으로 낸 값(reference/nrel_energyplus_25_2.csv).
# Tier A 가 ±0.4% 로 재현하므로 Tier B 도 같은 수준이어야 한다.
TOLERANCE_PCT = 1.0

# 델타는 절대 MWh 로 본다 — 작은 델타에서 백분율은 과민해진다.
# 관측 최대 오차는 0.0113 MWh(900−600 냉방)였다.
DELTA_TOLERANCE_MWH = 0.05

DELTAS = {
    ("620", "600"): "창 방위",
    ("900", "600"): "열용량",
    ("610", "600"): "차양",
}


def _energyplus():
    if not shutil.which("energyplus"):
        pytest.skip("energyplus 가 PATH 에 없다")


@pytest.fixture(scope="session")
def nrel_reference() -> dict:
    path = HERE / "reference" / "nrel_energyplus_25_2.csv"
    with path.open(encoding="utf-8") as fh:
        return {(r["case"], r["metric"]): float(r["value"]) for r in csv.DictReader(fh)}


@pytest.fixture(scope="module")
def results(tmp_path_factory) -> dict:
    """케이스별로 우리 파이프라인을 통과시킨 결과. 케이스당 약 3초."""
    _energyplus()
    from bestest import build_payload
    from ep_simulator import generate_idf_and_simulate

    root = tmp_path_factory.mktemp("tierb")
    out = {}
    for case in CASES:
        d = root / case
        d.mkdir(parents=True, exist_ok=True)
        generate_idf_and_simulate(build_payload(case), str(d))

        csv_path = d / "eplusout.csv"
        assert csv_path.exists(), f"케이스 {case}: eplusout.csv 가 없다"
        rows = list(csv.reader(csv_path.open()))
        header = rows[0]

        def total(fragment: str) -> float:
            idx = [i for i, h in enumerate(header) if fragment in h]
            assert idx, f"케이스 {case}: 출력 열을 찾을 수 없다 — {fragment}"
            return sum(float(r[idx[0]] or 0) for r in rows[1:]) / J_TO_MWH

        out[case] = {
            "heating": total("Zone Air System Sensible Heating Energy"),
            "cooling": total("Zone Air System Sensible Cooling Energy"),
        }
    return out


@pytest.mark.slow
@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("metric", ["heating", "cooling"])
def test_case_matches_reference(case, metric, nrel_reference, results):
    """우리 파이프라인이 만든 케이스가 NREL 기준값을 재현하는가."""
    expected = nrel_reference[(case, metric)]
    got = results[case][metric]
    delta = (got - expected) / expected * 100
    assert abs(delta) <= TOLERANCE_PCT, (
        f"케이스 {case} {metric}: 우리 파이프라인={got:.4f} NREL={expected:.4f} MWh "
        f"({delta:+.2f}%, 허용 ±{TOLERANCE_PCT}%)\n"
        f"  Tier A(표준 IDF)가 통과하는데 여기서 벌어졌다면 원인은 우리 번역 계층이다.\n"
        f"  확인 순서: 구성체 레이어 → 창 형상·유리 → 경계조건/노출 → 차양 →\n"
        f"            설정온도 스케줄 → 침기(AFN 이 ZoneInfiltration 을 대체한다) → 내부발열"
    )


@pytest.mark.slow
@pytest.mark.parametrize("pair", sorted(DELTAS), ids=lambda p: f"{p[0]}-{p[1]}")
@pytest.mark.parametrize("metric", ["heating", "cooling"])
def test_case_delta_matches_reference(pair, metric, nrel_reference, results):
    """케이스 간 **차이**를 재현하는가 — 격리된 물리 효과를 직접 때린다.

    절대값이 맞아도 델타가 틀릴 수 있다(두 케이스가 같은 방향으로 치우친 경우).
    특히 900−600 은 `layers` 가 열용량을 실제로 보존하는지 보는 유일한 시험이다 —
    U-value 합성 경로로는 600 과 900 이 같은 값을 낸다.
    """
    a, b = pair
    got = results[a][metric] - results[b][metric]
    expected = nrel_reference[(a, metric)] - nrel_reference[(b, metric)]
    assert abs(got - expected) <= DELTA_TOLERANCE_MWH, (
        f"델타 {a}−{b} ({DELTAS[pair]}) {metric}: "
        f"우리={got:+.4f} NREL={expected:+.4f} MWh "
        f"(차이 {got - expected:+.4f}, 허용 ±{DELTA_TOLERANCE_MWH})"
    )


@pytest.mark.slow
def test_benchmark_config_is_opt_in():
    """`benchmark` 키가 없으면 일반 사용자 경로가 조금도 달라지지 않아야 한다.

    벤치마크는 외기 0·자동부하 억제·AFN off·상시 설정온도처럼 실제 프로젝트에
    적용하면 안 되는 값을 강제한다. 그 설정이 기본값으로 새면 모든 프로젝트가
    조용히 망가진다.
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
