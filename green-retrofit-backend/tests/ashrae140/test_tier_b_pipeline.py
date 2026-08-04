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

# 기준값 CSV 는 이 버전 기준이다. 다른 버전으로 돌리면 비교가 무의미하다.
EXPECTED_EP_VERSION = "25.2.0"

# NREL 이 같은 EnergyPlus 25.2.0 으로 낸 값(reference/nrel_energyplus_25_2.csv).
# ⚠️ ASHRAE 기준이 아니라 **우리 프로젝트의 회귀 허용치**다.
# Tier A 가 ±0.4% 로 재현하므로 Tier B 도 같은 수준이어야 한다.
# 관측 최대 편차 0.48%(케이스 900) 기준으로 0.75% 로 잡았다.
TOLERANCE_PCT = 0.75
# 기준값이 0 에 가까운 케이스(650·950 난방 등)에서는 백분율이 무의미하므로 병행한다.
TOLERANCE_ABS_MWH = 0.02

# 델타 허용오차는 **기대 효과 크기보다 훨씬 작아야 한다.**
# ⚠️ 예전엔 0.05 MWh 였는데, 610−600 난방의 기대 효과가 바로 그 0.05 MWh 라
# **차양 효과가 0 이어도 통과**했다. "물리 효과를 직접 검증한다"는 목적과 정면으로
# 충돌한다. 관측 최대 오차 0.0113 MWh 기준으로 0.02 로 좁히고, 부호도 함께 본다.
DELTA_TOLERANCE_MWH = 0.02

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
        generate_idf_and_simulate(build_payload(case), str(d), allow_benchmark=True)

        # 실제로 실행된 엔진 버전을 확인한다. Tier B 만 단독 실행하면 다른 PATH
        # 버전으로 NREL 25.2 기준과 비교하게 된다.
        err = (d / "eplusout.err").read_text(errors="replace")
        assert f"Version {EXPECTED_EP_VERSION}" in err, (
            f"기준값은 EnergyPlus {EXPECTED_EP_VERSION} 기준인데 다른 버전으로 실행됐다.\n"
            f"  {err.splitlines()[0] if err else '(err 파일 비어있음)'}"
        )

        csv_path = d / "eplusout.csv"
        assert csv_path.exists(), f"케이스 {case}: eplusout.csv 가 없다"
        rows = list(csv.reader(csv_path.open()))
        header = rows[0]

        def total(fragment: str) -> float:
            # ⚠️ 첫 번째 일치 열만 쓰면 다중 존 케이스(960 sunspace 등)에서
            # 한 존만 집계된다. 일치하는 **모든** 존 열을 합산한다.
            idx = [i for i, h in enumerate(header) if fragment in h]
            assert idx, f"케이스 {case}: 출력 열을 찾을 수 없다 — {fragment}"
            return sum(float(r[i] or 0) for r in rows[1:] for i in idx) / J_TO_MWH

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
    # 기준값이 0 에 가까우면 백분율이 폭주하므로 절대오차와 병행한다
    ok = abs(got - expected) <= TOLERANCE_ABS_MWH or (
        expected != 0 and abs((got - expected) / expected * 100) <= TOLERANCE_PCT)
    delta = (got - expected) / expected * 100 if expected else float("inf")
    assert ok, (
        f"케이스 {case} {metric}: 우리 파이프라인={got:.4f} NREL={expected:.4f} MWh "
        f"({delta:+.2f}%, 허용 ±{TOLERANCE_PCT}% 또는 ±{TOLERANCE_ABS_MWH} MWh)\n"
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

    # 부호부터 본다 — 크기가 허용오차 안이어도 방향이 반대면 물리가 틀린 것이다.
    assert got * expected > 0 or abs(expected) < 1e-9, (
        f"델타 {a}−{b} ({DELTAS[pair]}) {metric}: 부호가 반대다. "
        f"우리={got:+.4f} NREL={expected:+.4f} MWh"
    )
    assert abs(got - expected) <= DELTA_TOLERANCE_MWH, (
        f"델타 {a}−{b} ({DELTAS[pair]}) {metric}: "
        f"우리={got:+.4f} NREL={expected:+.4f} MWh "
        f"(차이 {got - expected:+.4f}, 허용 ±{DELTA_TOLERANCE_MWH})"
    )


def test_benchmark_defaults_do_not_leak_into_builder():
    """`IdfBuilder` 를 벤치마크 없이 만들면 전역 설정이 기존 그대로여야 한다."""
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
    assert "TARP" in text and "DOE-2" in text, "벤치마크 대류 알고리즘이 샜다"


def test_benchmark_key_is_rejected_without_opt_in(tmp_path, monkeypatch):
    """🔒 임의 payload 가 보낸 `benchmark` 는 **거부돼야 한다.**

    이 키를 신뢰하면 외부 사용자가 `weatherFile` 로 임의 경로의 파일을 읽게
    만들 수 있고, AFN·자동부하·HVAC·내부발열을 조작해 자기 결과의 물리 조건을
    통째로 바꿀 수 있다. `allow_benchmark=True` 인 내부 호출에서만 받는다.

    EnergyPlus 를 돌리지 않고 IDF 조립 직전까지만 확인한다 — 존재하지 않는
    기상 경로가 그대로 쓰였다면 `FileNotFoundError` 가 났을 것이다.
    """
    import ep_simulator
    from bestest import build_payload

    payload = build_payload("600")
    payload["benchmark"]["weatherFile"] = "/nonexistent/attacker/path.epw"

    captured = {}

    def fake_run(self, weather_file, out_dir):
        captured["weather"] = weather_file
        raise RuntimeError("stop-after-assembly")   # E+ 실행 전에 중단

    monkeypatch.setattr(ep_simulator.IdfBuilder, "run", fake_run)

    with pytest.raises(Exception):
        ep_simulator.generate_idf_and_simulate(payload, str(tmp_path))   # opt-in 없음

    assert "attacker" not in (captured.get("weather") or ""), (
        "benchmark.weatherFile 이 opt-in 없이 반영됐다 — 임의 경로 파일 읽기가 가능하다"
    )


@pytest.mark.slow
def test_plain_payload_keeps_user_path_objects(tmp_path, monkeypatch):
    """`benchmark` 없는 payload 는 **기존 사용자 경로 객체**를 그대로 만들어야 한다.

    벤치마크 분기는 대부분 `generate_idf_and_simulate()` 안에 있어서
    `IdfBuilder` 만 보는 시험으로는 잡히지 않는다(AFN off, 자동부하 억제,
    상시 설정온도, 이상부하 강제 등). 조립된 IDF 를 직접 확인한다.
    """
    import ep_simulator
    from bestest import build_payload

    payload = build_payload("600")
    payload.pop("benchmark")                 # 일반 사용자 payload 로 되돌린다
    payload["zones"][0]["activityId"] = 1105  # 용도 자동 추정이 살아있어야 한다
    for key in ("peopleDensity", "lightingPower", "equipmentPower"):
        payload["zones"][0].pop(key)

    def fake_run(self, weather_file, out_dir):
        self.write(str(tmp_path / "assembled.idf"))
        raise RuntimeError("stop-after-assembly")

    monkeypatch.setattr(ep_simulator.IdfBuilder, "run", fake_run)
    with pytest.raises(Exception):
        ep_simulator.generate_idf_and_simulate(payload, str(tmp_path))

    text = (tmp_path / "assembled.idf").read_text()
    # 기본 침기 모델은 고정 ACH 다. AFN 은 infiltrationModel="afn" 을 명시했을 때만.
    # (예전 기본값이던 AFN 은 침기가 표면 개수에 좌우되는 결함이 있었다)
    assert "AirflowNetwork:SimulationControl" not in text, \
        "기본 경로에 AFN 이 들어갔다 — 기본은 고정 ACH 여야 한다"
    assert "ZoneInfiltration:DesignFlowRate" in text, "기본 경로에 고정 침기가 없다"
    assert "OtherEquipment" not in text, "벤치마크 전용 고정 발열이 기본 경로로 샜다"
    assert "FullExterior" in text and "FullInteriorAndExterior" not in text, \
        "벤치마크 태양복사 분배가 샜다"
    # heatSource=11(지역난방)은 연료 시스템 경로다. IdealLoads 가 나왔다면
    # forceIdealLoads 가 샌 것이다.
    assert "ZoneHVAC:IdealLoadsAirSystem" not in text, "forceIdealLoads 가 기본 경로로 샜다"
    assert "ZoneHVAC:UnitHeater" in text, "열원별 실기기 경로가 사라졌다"
    # 용도별 자동 부하가 살아있는지 (벤치마크는 이걸 전부 끈다)
    assert "Lights," in text and "ElectricEquipment," in text, \
        "용도별 자동 부하가 기본 경로에서 사라졌다 (suppressAutoLoads 가 샜다)"
    # 아키타입 스케줄(야간 setback)이 상시 고정으로 바뀌지 않았는지
    assert "Op_office" in text, "용도별 운영 스케줄이 사라졌다 (constantSetpoints 가 샜다)"


@pytest.mark.slow
def test_afn_is_opt_in(tmp_path, monkeypatch):
    """AFN 은 제거하지 않고 **명시 opt-in** 으로 남긴다.

    압력시험값·개구부 운전 스케줄이 있으면 의미가 있는 모델이다. 다만 계수의
    형상 의존성은 그대로이므로 정규화 없이 기본값으로 쓰면 안 된다.
    """
    import ep_simulator
    from bestest import build_payload

    payload = build_payload("600")
    payload.pop("benchmark")
    payload["projectData"]["infiltrationModel"] = "afn"

    def fake_run(self, weather_file, out_dir):
        self.write(str(tmp_path / "afn.idf"))
        raise RuntimeError("stop-after-assembly")

    monkeypatch.setattr(ep_simulator.IdfBuilder, "run", fake_run)
    with pytest.raises(Exception):
        ep_simulator.generate_idf_and_simulate(payload, str(tmp_path))

    text = (tmp_path / "afn.idf").read_text()
    assert "AirflowNetwork:SimulationControl" in text, \
        "infiltrationModel='afn' 을 명시했는데 AFN 이 안 들어갔다"
