"""ASHRAE 140 5.2절 Tier A — 엔진 확인.

**이 시험은 우리 코드를 한 줄도 타지 않는다.** 표준 케이스 IDF 를 우리
EnergyPlus 25.2 바이너리로 직접 돌려 공표 범위와 대조할 뿐이다.
목적은 "우리 설치·버전·기상 처리가 정상인가"를 확정해서, Tier B(파이프라인)가
실패했을 때 원인을 우리 번역 계층으로 좁힐 대조군을 만드는 것이다.

⚠️ 현재 stock IDF 의 출처 한계가 있다. `README.md` 의 「알려진 편차」를 반드시 읽을 것.
"""
import csv
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

# J → MWh
J_TO_MWH = 3.6e9

# 우리 stock IDF 는 OpenStudio 9.3 세대 모델을 25.2 로 버전 전이한 것이라
# NREL 이 OpenStudio 3.11 measure 로 생성한 모델과 완전히 같지 않다.
# 같은 엔진(25.2)끼리도 아래만큼 벌어지는 것이 관측됐다 — README 참조.
KNOWN_DEVIATION = {
    ("600", "cooling"): "stock IDF 출처 차이로 공표 상한을 약 1.6% 초과 (README 「알려진 편차」)",
}


def _energyplus() -> str:
    exe = shutil.which("energyplus")
    if not exe:
        pytest.skip("energyplus 가 PATH 에 없다")
    return exe


def _load(path: Path) -> dict:
    out = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[(row["case"], row["metric"])] = row
    return out


@pytest.fixture(scope="module")
def reference() -> dict:
    return _load(REF)


@pytest.fixture(scope="module")
def nrel_reference() -> dict:
    return _load(NREL_REF)


def _run_case(case: str, tmp_path: Path) -> dict:
    """케이스 IDF 를 실행하고 연간 난방·냉방 부하(MWh)를 돌려준다."""
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
        def total(pattern: str) -> float:
            q = """SELECT SUM(rd.Value) FROM ReportData rd
                   JOIN ReportDataDictionary rdd
                     ON rd.ReportDataDictionaryIndex = rdd.ReportDataDictionaryIndex
                   WHERE rdd.Name LIKE ?"""
            return (con.execute(q, (pattern,)).fetchone()[0] or 0.0) / J_TO_MWH

        return {
            "heating": total("%Sensible Heating Energy%"),
            "cooling": total("%Sensible Cooling Energy%"),
        }
    finally:
        con.close()


@pytest.mark.slow
@pytest.mark.parametrize("case", ["600"])
@pytest.mark.parametrize("metric", ["heating", "cooling"])
def test_annual_load_within_published_range(case, metric, reference, nrel_reference, tmp_path):
    """연간 부하가 기준 프로그램 6종의 min~max 안에 드는가.

    이것이 ASHRAE 140 의 실제 합격 기준이다. 통과했다고 "정확하다"는 뜻은 아니고,
    기준 프로그램들이 서로 벌어지는 폭 안에 있다는 뜻이다.
    """
    ref = reference[(case, metric)]
    lo, hi = float(ref["ref_min"]), float(ref["ref_max"])
    got = _run_case(case, tmp_path)[metric]

    nrel = nrel_reference.get((case, metric))
    detail = (
        f"\n  케이스 {case} {metric}: 우리={got:.4f} MWh"
        f"\n  공표 범위 = [{lo:.4f}, {hi:.4f}]  (기준 프로그램 6종)"
        f"\n  EnergyPlus 제출값 = {ref['energyplus_ref']}"
    )
    if nrel:
        delta = (got - float(nrel["value"])) / float(nrel["value"]) * 100
        detail += f"\n  NREL 25.2.0 동일버전 = {nrel['value']} → 편차 {delta:+.2f}%"

    known = KNOWN_DEVIATION.get((case, metric))
    if known and not (lo <= got <= hi):
        pytest.xfail(f"알려진 편차: {known}{detail}")

    assert lo <= got <= hi, f"공표 범위를 벗어났다{detail}"


@pytest.mark.slow
@pytest.mark.parametrize("case", ["600"])
def test_same_engine_agreement(case, nrel_reference, tmp_path):
    """같은 EnergyPlus 25.2.0 으로 NREL 이 낸 값과 얼마나 벌어지는가.

    범위 통과보다 훨씬 예민한 지표다. 엔진이 같으므로 여기서 벌어지면
    **모델(IDF)이 다르다**는 뜻이지 엔진 문제가 아니다.
    현재 stock IDF 출처 한계 때문에 느슨하게 잡아뒀다 — README 참조.
    """
    got = _run_case(case, tmp_path)
    tolerance_pct = 5.0
    problems = []
    for metric in ("heating", "cooling"):
        ref = nrel_reference.get((case, metric))
        if not ref:
            continue
        expected = float(ref["value"])
        delta = (got[metric] - expected) / expected * 100
        if abs(delta) > tolerance_pct:
            problems.append(
                f"{metric}: 우리={got[metric]:.4f} NREL={expected:.4f} 편차={delta:+.2f}%"
            )
    assert not problems, (
        f"같은 25.2 엔진인데 {tolerance_pct}% 넘게 벌어졌다 — 모델 차이를 의심하라:\n  "
        + "\n  ".join(problems)
    )
