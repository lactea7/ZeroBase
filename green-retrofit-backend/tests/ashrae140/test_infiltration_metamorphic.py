"""침기 모델의 형상 의존성 — 메타모픽 시험.

**불변조건**: 형상·체적·재료·누기 입력이 같은 건물은 **표면 polygon 분할만 바꿔도**
총 침기량과 냉난방부하가 변하지 않아야 한다.

이 시험이 존재하는 이유:
`AirflowNetwork:MultiZone:Surface:Crack`(`WallCrack` 0.01/0.65)이 모든 Outdoors
표면에 factor 1.0 으로 동일하게 붙는다. 면적·둘레·부재로 정규화돼 있지 않아
**총 누기가 외피 기밀성이 아니라 표면 개수에 좌우된다.** gbXML 은 벽 하나를 여러
폴리곤으로 내보내는 경우가 흔하므로, 같은 건물이라도 도면 작성 방식에 따라
침기율이 달라진다.

실측(ASHRAE 140 케이스 600, 북벽만 분할):

    분할  외기면  난방 MWh   변화
      1     6     6.4972      —
      2     7     7.0484   +8.5%
      4     9     7.8030  +20.1%
      8    13     8.6720  +33.5%

용호동(실제 건물)에서는 반대로 실효 침기가 0.327 ACH 로 표기값 0.5 보다 **낮았다.**
즉 AFN 은 "항상 과대"가 아니라 외피면수/체적 비에 따라 방향이 뒤집힌다.
그래서 목표는 "침기를 줄이는 것"이 아니라 **형상 의존성을 없애는 것**이다.
"""
import copy
import csv
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "cases"))
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE.parent.parent / "src"))

J_TO_MWH = 3.6e9
SPLITS = (1, 2, 4, 8)

# 분할을 바꿔도 이 이상 벌어지면 형상 의존성이 남아 있다는 뜻이다.
# 정규화된 모델이라면 완전히 동일해야 하므로 수치오차 수준만 허용한다.
LOAD_TOLERANCE_MWH = 0.01
ACH_TOLERANCE = 0.005


def _energyplus():
    if not shutil.which("energyplus"):
        pytest.skip("energyplus 가 PATH 에 없다")


def _split_north_wall(payload: dict, n: int) -> dict:
    """북벽(창 없음)을 n 개 폴리곤으로 나눈다. 총 면적·형상·재료는 그대로."""
    payload = copy.deepcopy(payload)
    base = next(s for s in payload["surfaces"] if s["id"] == "NORTH")
    others = [s for s in payload["surfaces"] if s["id"] != "NORTH"]
    h = 2.7
    pieces = []
    for i in range(n):
        x0, x1 = 8 - 8 * i / n, 8 - 8 * (i + 1) / n
        piece = copy.deepcopy(base)
        piece["id"] = f"NORTH_{i}"
        piece["vertices"] = [[x0, 6, h], [x0, 6, 0], [x1, 6, 0], [x1, 6, h]]
        pieces.append(piece)
    payload["surfaces"] = others + pieces
    return payload


@pytest.fixture(scope="module")
def split_results(tmp_path_factory) -> dict:
    """북벽을 1/2/4/8 로 나눈 네 모델의 결과. 물리적으로 전부 같은 건물이다."""
    _energyplus()
    from bestest import build_payload
    from ep_simulator import generate_idf_and_simulate

    root = tmp_path_factory.mktemp("metamorphic")
    out = {}
    for n in SPLITS:
        payload = _split_north_wall(build_payload("600"), n)
        # ⚠️ 벤치마크의 AFN 차단을 **일부러 뺀다.** 이 시험이 검사하는 것은
        # ASHRAE 140 재현이 아니라 **실제 프로젝트가 타는 기본 침기 경로**다.
        # 여기서 AFN 을 꺼버리면 결함이 재현되지 않아 시험이 무의미해진다.
        payload["benchmark"].pop("disableAirflowNetwork", None)
        d = root / f"split{n}"
        d.mkdir(parents=True, exist_ok=True)
        generate_idf_and_simulate(payload, str(d), allow_benchmark=True)

        rows = list(csv.reader((d / "eplusout.csv").open()))
        header = rows[0]

        def total(fragment: str, scale: float = 1.0) -> float:
            idx = [i for i, h in enumerate(header) if fragment in h]
            return sum(float(r[i] or 0) for r in rows[1:] for i in idx) / scale

        out[n] = {
            "heating": total("Zone Air System Sensible Heating Energy", J_TO_MWH),
            "cooling": total("Zone Air System Sensible Cooling Energy", J_TO_MWH),
            # AFN 경로와 고정 ACH 경로 중 살아있는 쪽이 잡힌다
            # ACH 는 체적/존체적/시간으로 직접 계산한다 — Zone Infiltration Air Change
            # Rate 는 Output:Diagnostics 없이는 생성되지 않는다.
            "infiltration_volume": (total("AFN Zone Infiltration Volume")
                                    or total("Zone Infiltration Standard Density Volume")),
        }
    return out


@pytest.mark.slow
@pytest.mark.parametrize("metric", ["heating", "cooling"])
def test_load_is_independent_of_surface_subdivision(metric, split_results):
    """분할을 바꿔도 냉난방부하가 같아야 한다."""
    values = {n: split_results[n][metric] for n in SPLITS}
    spread = max(values.values()) - min(values.values())
    assert spread <= LOAD_TOLERANCE_MWH, (
        f"{metric} 이 표면 분할에 따라 달라진다 — 물리적으로 같은 건물이다.\n"
        + "\n".join(f"  분할 {n}개: {v:.4f} MWh" for n, v in values.items())
        + f"\n  최대-최소 = {spread:.4f} MWh (허용 {LOAD_TOLERANCE_MWH})\n"
        f"  침기 계수가 면적·둘레로 정규화되지 않아 표면 개수에 비례하고 있다."
    )


@pytest.mark.slow
def test_air_change_rate_is_independent_of_surface_subdivision(split_results):
    """분할을 바꿔도 실효 환기횟수(ACH)가 같아야 한다.

    부하보다 직접적인 지표다 — 부하는 다른 요인으로도 움직이지만 ACH 는
    침기 모델만 반영한다.
    """
    # 존 체적 129.6 m3 (8×6×2.7), 8760 시간
    values = {n: split_results[n]["infiltration_volume"] / 129.6 / 8760 for n in SPLITS}
    if not any(values.values()):
        pytest.skip("침기 ACH 출력이 없다")
    spread = max(values.values()) - min(values.values())
    assert spread <= ACH_TOLERANCE, (
        "실효 ACH 가 표면 분할에 따라 달라진다.\n"
        + "\n".join(f"  분할 {n}개: {v:.4f} ACH" for n, v in values.items())
        + f"\n  최대-최소 = {spread:.4f} (허용 {ACH_TOLERANCE})"
    )
