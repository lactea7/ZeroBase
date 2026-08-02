"""ASHRAE 140 5.2절 Tier A — 격리된 참조모델 진단.

⚠️ **이것은 ASHRAE 140 합격시험이 아니다.** 표준 케이스 IDF 를 우리 EnergyPlus
바이너리로 직접 돌려 공표된 **비교 프로그램 범위** 안에 드는지 볼 뿐이다.
우리 코드(`IdfBuilder`, `generate_idf_and_simulate()`, gbXML 변환, 기상 탐색)는
**한 줄도 타지 않는다.**

무엇을 확인하나:
  - 격리된 IDF/EPW 를 EnergyPlus 실행파일이 정상 실행하는가
  - SQL 에서 연간 부하를 읽어낼 수 있는가
  - 그 값이 과거 여러 프로그램 결과와 대체로 비슷한가

무엇을 확인하지 **않나**:
  - 우리 애플리케이션의 기상 선택·gbXML 번역·IDF 생성
  - ASHRAE 140 전체 적합성 (판본별 통계적 acceptance criteria + 테스트 그룹별
    최소 통과 규칙은 구현돼 있지 않다. 표 B8 의 6종 min~max 안에 든다는 것과
    표준 합격은 같지 않다.)

존재 이유는 **Tier B 의 대조군**이다. Tier A 가 정상인데 Tier B 가 실패하면
원인을 우리 번역 계층 쪽으로 좁힐 수 있다. 자세한 내용은 `README.md`.
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
REF = HERE / "reference" / "std140_annual_loads.csv"
NREL_REF = HERE / "reference" / "nrel_energyplus_25_2.csv"

J_TO_MWH = 3.6e9

# 기준값 CSV 는 이 버전에 맞춰 고정돼 있다. 다른 버전으로 돌리면 비교 자체가
# 무의미하므로 조용히 통과시키지 않고 실패시킨다.
EXPECTED_EP_VERSION = "25.2.0"

# 부분문자열 매칭(LIKE '%...%')은 같은 조각을 가진 변수나 다른 보고주기가
# 추가되면 중복 합산한다. 변수명·보고주기를 정확히 못박는다.
VARIABLES = {
    "heating": "Zone Air System Sensible Heating Energy",
    "cooling": "Zone Air System Sensible Cooling Energy",
}
REPORTING_FREQUENCY = "Hourly"

# 현재 stock IDF 로 관측된 값. 공표 범위를 벗어난 항목이 있어도
# **"어떤 값이든 허용"이 되지 않도록** 좁은 회귀 구간을 따로 건다.
# (xfail 만 걸어두면 냉방이 6.26 이 아니라 20 이 되어도 같은 known failure 가 된다)
RECORDED = {
    ("600", "heating"): 4.2201,
    ("600", "cooling"): 6.2592,
}
REGRESSION_TOLERANCE_PCT = 0.5

# 공표 범위를 벗어나는 것이 알려진 항목. README 「알려진 편차」 참조.
# strict=True — 해소되어 통과하기 시작하면 XPASS 로 알려준다.
KNOWN_OUT_OF_RANGE = {
    ("600", "cooling"): "stock IDF 출처 차이 (README 「알려진 편차」)",
}


def _case_params():
    """(case, metric) 조합. 알려진 범위 이탈 항목에는 xfail 마커를 붙인다."""
    out = []
    for case in ("600",):
        for metric in ("heating", "cooling"):
            reason = KNOWN_OUT_OF_RANGE.get((case, metric))
            marks = [pytest.mark.xfail(strict=True, reason=reason)] if reason else []
            out.append(pytest.param(case, metric, marks=marks, id=f"{case}-{metric}"))
    return out


def _energyplus() -> str:
    exe = shutil.which("energyplus")
    if not exe:
        pytest.skip("energyplus 가 PATH 에 없다")
    return exe


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return {(r["case"], r["metric"]): r for r in csv.DictReader(fh)}


@pytest.fixture(scope="module")
def reference() -> dict:
    return _load(REF)


@pytest.fixture(scope="module")
def nrel_reference() -> dict:
    return _load(NREL_REF)


@pytest.fixture(scope="module")
def results(tmp_path_factory) -> dict:
    """케이스별 연간 부하. 모듈당 한 번만 실행한다(케이스 하나가 약 1초)."""
    tmp = tmp_path_factory.mktemp("ashrae140")
    return {case: _run_case(case, tmp) for case in ("600",)}


def _run_case(case: str, tmp_path: Path) -> dict:
    idf = IDF_DIR / f"case{case}.idf"
    if not idf.exists():
        pytest.skip(f"stock IDF 없음: {idf.name} — README 의 조달 절차 참조")

    out_dir = tmp_path / f"out{case}"
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [_energyplus(), "-w", str(EPW), "-d", str(out_dir), str(idf)],
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, f"EnergyPlus 실패:\n{proc.stdout[-2000:]}"

    sql = out_dir / "eplusout.sql"
    assert sql.exists(), "eplusout.sql 이 없다 — IDF 에 Output:SQLite 가 있는지 확인"

    con = sqlite3.connect(sql)
    try:
        # 실제로 실행된 엔진 버전을 SQL 에서 읽는다. `energyplus --version` 보다
        # 정확하다 — PATH 의 실행파일과 결과를 낸 엔진이 같다는 보장이 된다.
        raw = con.execute("SELECT EnergyPlusVersion FROM Simulations LIMIT 1").fetchone()[0]
        m = re.search(r"Version (\d+\.\d+\.\d+)", raw or "")
        actual = m.group(1) if m else raw
        assert actual == EXPECTED_EP_VERSION, (
            f"기준값 CSV 는 EnergyPlus {EXPECTED_EP_VERSION} 기준인데 {actual} 로 실행됐다.\n"
            f"  버전이 다르면 비교가 무의미하다. reference/ 를 해당 버전으로 다시 만들거나\n"
            f"  EXPECTED_EP_VERSION 을 갱신하고 README 의 결과표도 함께 고칠 것."
        )

        def total(variable: str) -> float:
            q = """SELECT SUM(rd.Value) FROM ReportData rd
                   JOIN ReportDataDictionary rdd
                     ON rd.ReportDataDictionaryIndex = rdd.ReportDataDictionaryIndex
                   WHERE rdd.Name = ? AND rdd.ReportingFrequency = ?"""
            return (con.execute(q, (variable, REPORTING_FREQUENCY)).fetchone()[0] or 0.0) / J_TO_MWH

        return {k: total(v) for k, v in VARIABLES.items()}
    finally:
        con.close()


@pytest.mark.slow
@pytest.mark.parametrize("case,metric", _case_params())
def test_within_reference_program_range(case, metric, reference, nrel_reference, results):
    """연간 부하가 공표된 **비교 프로그램 6종**의 min~max 안에 드는가.

    ⚠️ 이것은 ASHRAE 140 합격이나 인증을 의미하지 않는다. 표 B8 의 범위는 원래
    비교·진단용이고, 140-2020 Addendum b 이후 판본은 별도의 통계적 acceptance
    criteria 와 테스트 그룹별 통과 규칙을 따로 둔다 — 여기엔 구현돼 있지 않다.
    """
    ref = reference[(case, metric)]
    lo, hi = float(ref["ref_min"]), float(ref["ref_max"])
    got = results[case][metric]

    detail = (
        f"\n  케이스 {case} {metric}: 우리={got:.4f} MWh"
        f"\n  비교 프로그램 범위 = [{lo:.4f}, {hi:.4f}] (6종)"
        f"\n  EnergyPlus 제출값 = {ref['energyplus_ref']}"
    )
    nrel = nrel_reference.get((case, metric))
    if nrel:
        expected = float(nrel["value"])
        detail += f"\n  NREL {EXPECTED_EP_VERSION} 생성모델 = {expected} → 편차 {(got - expected) / expected * 100:+.2f}%"

    assert lo <= got <= hi, f"비교 프로그램 범위를 벗어났다{detail}"


@pytest.mark.slow
@pytest.mark.parametrize("case,metric", sorted(RECORDED))
def test_recorded_value_regression(case, metric, results):
    """관측된 값에서 벗어나지 않았는가 — **회귀 감지용**.

    범위 시험이 xfail 인 항목도 여기서는 실패한다. "1.6% 초과를 알고 있다"와
    "어떤 초과도 허용한다"는 다르다. stock IDF 나 엔진이 바뀌면 여기가 먼저 운다.
    """
    expected = RECORDED[(case, metric)]
    got = results[case][metric]
    delta = (got - expected) / expected * 100
    assert abs(delta) <= REGRESSION_TOLERANCE_PCT, (
        f"케이스 {case} {metric} 이 기록값에서 벗어났다: "
        f"기록={expected:.4f} 현재={got:.4f} MWh ({delta:+.2f}%, 허용 ±{REGRESSION_TOLERANCE_PCT}%)\n"
        f"  stock IDF·기상·엔진 중 무엇이 바뀌었는지 확인하고, 의도한 변경이면 "
        f"RECORDED 와 README 결과표를 함께 갱신할 것."
    )


@pytest.mark.slow
@pytest.mark.parametrize("case", ["600"])
def test_against_nrel_generated_model_diagnostic(case, nrel_reference, results):
    """NREL 이 같은 EnergyPlus 로 낸 값과 얼마나 벌어지는가 — **진단용, 관문 아님**.

    이름에 유의: 엔진은 같아도 **비교 대상 IDF 가 서로 다르다**(우리는 버전
    전이본, NREL 은 OpenStudio measure 생성본). 따라서 이 값은 엔진 일치도가
    아니라 **서로 다른 두 모델 산출물의 근접도**를 잰다.

    허용오차 5%는 검증 근거가 있는 수치가 아니라 **탐색용 경보선**이다.
    정식 생성 IDF 를 확보하면 같은 엔진·같은 모델이므로 반올림 수준까지
    좁혀야 하고, 그때 이 시험을 관문으로 승격할 수 있다.
    """
    got = results[case]
    alarm_pct = 5.0
    problems = []
    for metric in VARIABLES:
        ref = nrel_reference.get((case, metric))
        if not ref:
            continue
        expected = float(ref["value"])
        delta = (got[metric] - expected) / expected * 100
        if abs(delta) > alarm_pct:
            problems.append(f"{metric}: 우리={got[metric]:.4f} NREL={expected:.4f} 편차={delta:+.2f}%")
    assert not problems, (
        f"경보선 {alarm_pct}% 를 넘었다 — 모델 차이를 의심하라(엔진 문제가 아니다):\n  "
        + "\n  ".join(problems)
    )
