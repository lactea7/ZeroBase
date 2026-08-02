"""ASHRAE 140 5.2절 Tier A — 참조모델 재현 확인.

⚠️ **이것은 ASHRAE 140 합격시험이 아니다.** 표 B8 의 6종 min~max 는 비교·진단용이고,
140-2020 Addendum b 이후 판본은 별도의 통계적 acceptance criteria 와 테스트 그룹별
최소 통과 규칙을 따로 둔다 — 여기엔 구현돼 있지 않다.

우리 코드(`IdfBuilder`, `generate_idf_and_simulate()`, gbXML 변환, 기상 탐색)는
**한 줄도 타지 않는다.** 존재 이유는 **Tier B 의 대조군**이다 — Tier A 가 정상인데
Tier B 가 실패하면 원인을 우리 번역 계층 쪽으로 좁힐 수 있다.

stock IDF 는 NREL 이 쓴 것과 같은 조합(OpenStudio 3.11.0 + EnergyPlus 25.2.0)으로
BESTEST-GSR measure 가 **정식 생성**한 것이다. 자세한 내용은 `README.md`.
"""
import csv
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
IDF_DIR = HERE / "stock_idf"
EPW = HERE / "weather" / "725650TYCST.epw"
REF_DIR = HERE / "reference"

J_TO_MWH = 3.6e9

# 기준값 CSV 는 이 버전에 맞춰 고정돼 있다. 다른 버전으로 돌리면 비교가
# 무의미하므로 조용히 통과시키지 않고 실패시킨다.
EXPECTED_EP_VERSION = "25.2.0"

# BESTEST 모델은 IdealLoads 를 지역난방/지역냉방 미터로 받는다.
# 부분문자열(LIKE)이 아니라 미터명을 정확히 못박는다 — 중복 합산 방지.
METERS = {
    "heating": "DistrictHeatingWater:Facility",
    "cooling": "DistrictCooling:Facility",
}

CASES = ("600", "610", "620", "630", "640", "650", "660", "670", "680", "685", "695",
         "900", "910", "920", "930", "940", "950", "985", "995")

# NREL 재현 허용오차. 같은 엔진·같은 생성 경로이므로 반올림 수준이어야 한다.
# 실측 최대 편차는 0.39%(케이스 640 난방)였다.
NREL_TOLERANCE_PCT = 0.5

# 공표 범위를 벗어나는 것이 알려진 항목. 셋 다 **EnergyPlus 자체가 밴드 최상단**인
# 케이스라, 우리가 NREL 값을 0.1% 미만으로 재현해도 상한을 살짝 넘는다.
# 우리 설정 결함이 아니다 — README 「알려진 범위 이탈」 참조.
KNOWN_OUT_OF_RANGE = {
    ("670", "cooling"): "EnergyPlus 제출값 6.623 = 공표 상한 6.6227",
    ("685", "cooling"): "EnergyPlus 제출값 9.119, 상한 9.130",
    ("695", "cooling"): "EnergyPlus 제출값 9.172, 상한 9.1716",
}

# 케이스 간 델타 — 무엇을 격리해서 보는가.
# 델타는 기상·단위·절대 스케일에 둔감하고 **물리 번역만 직접 때린다.**
DELTAS = {
    ("900", "600"): "열용량 (경량 → 중량)",
    ("610", "600"): "남측 차양",
    ("620", "600"): "창 방위 (남 → 동서)",
    ("630", "620"): "동서창 차양",
    ("640", "600"): "난방 설정온도 setback",
    ("650", "600"): "야간 환기",
    ("670", "600"): "단일 유리",
    ("680", "600"): "불투명면 단열 강화",
    ("910", "900"): "남측 차양 (중량)",
    ("920", "900"): "창 방위 (중량)",
    ("940", "900"): "난방 setback (중량)",
}


def _energyplus() -> str:
    exe = shutil.which("energyplus")
    if not exe:
        pytest.skip("energyplus 가 PATH 에 없다")
    return exe


def _read_csv(name: str) -> list:
    with (REF_DIR / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="session")
def published_range() -> dict:
    return {(r["case"], r["metric"]): (float(r["ref_min"]), float(r["ref_max"]), r["energyplus_ref"])
            for r in _read_csv("std140_annual_loads.csv")}


@pytest.fixture(scope="session")
def nrel_reference() -> dict:
    return {(r["case"], r["metric"]): float(r["value"])
            for r in _read_csv("nrel_energyplus_25_2.csv")}


@pytest.fixture(scope="session")
def by_program() -> dict:
    """(case, metric) → {프로그램: 값}. 델타 범위를 직접 계산하는 데 쓴다."""
    out = {}
    for r in _read_csv("std140_by_program.csv"):
        out.setdefault((r["case"], r["metric"]), {})[r["program"]] = float(r["value"])
    return out


@pytest.fixture(scope="session")
def results(tmp_path_factory) -> dict:
    """모든 케이스를 한 번씩 실행한다. 케이스당 약 1초."""
    tmp = tmp_path_factory.mktemp("ashrae140")
    return {case: _run_case(case, tmp) for case in CASES}


def _run_case(case: str, tmp_path: Path) -> dict:
    idf = IDF_DIR / f"case{case}.idf"
    if not idf.exists():
        pytest.skip(f"stock IDF 없음: {idf.name} — README 의 재생성 절차 참조")

    out_dir = tmp_path / f"out{case}"
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [_energyplus(), "-w", str(EPW), "-d", str(out_dir), str(idf)],
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, f"케이스 {case} EnergyPlus 실패:\n{proc.stdout[-2000:]}"

    sql = out_dir / "eplusout.sql"
    assert sql.exists(), f"케이스 {case}: eplusout.sql 이 없다"

    con = sqlite3.connect(sql)
    try:
        # 실제로 실행된 엔진 버전을 SQL 에서 읽는다 — PATH 의 실행파일과 결과를 낸
        # 엔진이 같다는 보장이 된다(`energyplus --version` 보다 정확).
        raw = con.execute("SELECT EnergyPlusVersion FROM Simulations LIMIT 1").fetchone()[0]
        m = re.search(r"Version (\d+\.\d+\.\d+)", raw or "")
        actual = m.group(1) if m else raw
        assert actual == EXPECTED_EP_VERSION, (
            f"기준값은 EnergyPlus {EXPECTED_EP_VERSION} 기준인데 {actual} 로 실행됐다.\n"
            f"  버전이 다르면 비교가 무의미하다. reference/ 를 다시 만들거나\n"
            f"  EXPECTED_EP_VERSION 과 README 결과표를 함께 갱신할 것."
        )

        def total(meter: str) -> float:
            q = """SELECT SUM(rd.Value) FROM ReportData rd
                   JOIN ReportDataDictionary rdd
                     ON rd.ReportDataDictionaryIndex = rdd.ReportDataDictionaryIndex
                   WHERE rdd.Name = ?"""
            return (con.execute(q, (meter,)).fetchone()[0] or 0.0) / J_TO_MWH

        return {k: total(v) for k, v in METERS.items()}
    finally:
        con.close()


def _params():
    """(case, metric). 알려진 범위 이탈 항목엔 xfail(strict) 를 붙인다."""
    out = []
    for case in CASES:
        for metric in METERS:
            reason = KNOWN_OUT_OF_RANGE.get((case, metric))
            marks = [pytest.mark.xfail(strict=True, reason=reason)] if reason else []
            out.append(pytest.param(case, metric, marks=marks, id=f"{case}-{metric}"))
    return out


@pytest.mark.slow
@pytest.mark.parametrize("case,metric", sorted(
    (pytest.param(c, m, id=f"{c}-{m}") for c in CASES for m in METERS),
    key=lambda p: p.id))
def test_reproduces_nrel_reference_run(case, metric, nrel_reference, results):
    """NREL 이 같은 OpenStudio 3.11 + EnergyPlus 25.2.0 으로 낸 값을 재현하는가.

    **이것이 Tier A 의 주 관문이다.** 같은 엔진·같은 생성 경로이므로 결과가
    반올림 수준까지 같아야 한다. 여기서 벌어지면 우리 EnergyPlus 설치나
    stock IDF 에 문제가 생긴 것이다.
    """
    expected = nrel_reference.get((case, metric))
    if expected is None:
        pytest.skip(f"NREL 기준값 없음: {case} {metric}")
    got = results[case][metric]

    if expected == 0.0:      # 650·950 의 난방은 정확히 0
        assert got < 1e-6, f"케이스 {case} {metric}: 0 이어야 하는데 {got:.6f} MWh"
        return

    delta = (got - expected) / expected * 100
    assert abs(delta) <= NREL_TOLERANCE_PCT, (
        f"케이스 {case} {metric}: 우리={got:.4f} NREL={expected:.4f} MWh "
        f"({delta:+.2f}%, 허용 ±{NREL_TOLERANCE_PCT}%)\n"
        f"  같은 엔진·같은 모델인데 벌어졌다 — EnergyPlus 설치나 stock IDF 를 확인할 것."
    )


@pytest.mark.slow
@pytest.mark.parametrize("case,metric", _params())
def test_within_reference_program_range(case, metric, published_range, results):
    """연간 부하가 공표된 **비교 프로그램 6종**의 min~max 안에 드는가.

    ⚠️ 합격이나 인증을 의미하지 않는다(모듈 docstring 참조).
    주 관문은 `test_reproduces_nrel_reference_run` 쪽이다.
    """
    entry = published_range.get((case, metric))
    if entry is None:
        pytest.skip(f"공표 범위 없음: {case} {metric}")
    lo, hi, ep_ref = entry
    got = results[case][metric]
    assert lo <= got <= hi, (
        f"케이스 {case} {metric}: 우리={got:.4f} MWh, "
        f"비교 프로그램 범위 [{lo:.4f}, {hi:.4f}], EnergyPlus 제출값 {ep_ref}"
    )


@pytest.mark.slow
@pytest.mark.parametrize("pair", sorted(DELTAS), ids=lambda p: f"{p[0]}-{p[1]}")
@pytest.mark.parametrize("metric", sorted(METERS))
def test_case_delta_within_program_range(pair, metric, by_program, results):
    """케이스 간 **차이**가 비교 프로그램들의 차이 범위 안에 드는가.

    델타는 기상·단위·절대 스케일에 둔감하고 **격리된 물리 효과만 직접 때린다**
    (열용량·차양·창 방위 등). 절대값보다 예민한 지표다.

    범위는 **각 프로그램의 (A−B) 를 구한 뒤 그것들의 min/max** 로 계산한다.
    min(A)−max(B) 처럼 집계값끼리 빼면 실제보다 훨씬 넓은 가짜 범위가 나온다.
    """
    a, b = pair
    progs_a = by_program.get((a, metric), {})
    progs_b = by_program.get((b, metric), {})
    common = sorted(set(progs_a) & set(progs_b))
    if len(common) < 3:
        pytest.skip(f"프로그램별 값이 부족하다: {a}-{b} {metric}")

    deltas = [progs_a[p] - progs_b[p] for p in common]
    lo, hi = min(deltas), max(deltas)
    # 6종의 산포가 좁을 때 반올림(소수 4자리)만으로 실패하지 않도록 최소 여유를 둔다.
    pad = max((hi - lo) * 0.05, 0.01)
    got = results[a][metric] - results[b][metric]

    assert lo - pad <= got <= hi + pad, (
        f"델타 {a}−{b} ({DELTAS[pair]}) {metric}: 우리={got:+.4f} MWh\n"
        f"  비교 프로그램 델타 범위 = [{lo:+.4f}, {hi:+.4f}] (여유 ±{pad:.4f}, {len(common)}종)\n"
        f"  프로그램별: " + ", ".join(f"{p}={progs_a[p] - progs_b[p]:+.3f}" for p in common)
    )
