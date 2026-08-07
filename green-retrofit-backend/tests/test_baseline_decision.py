"""`simulation/baseline.py` 단위시험 — 전/후 비교 기준선.

⚠️ 기준선을 잘못 잡으면 **절감액이 통째로 틀린다.** 그런데 이 판단은 분리 전까지
시험이 없었다 — 확인하려면 2.5분짜리 EnergyPlus 를 두 번 돌려야 했기 때문이다.
가짜 시뮬레이터를 끼워 판단만 검사한다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.simulation import baseline  # noqa: E402

ZONES = [{"id": "Z1", "area": 100.0}]
SURFACES = [{"id": "S1", "uValue": 0.5}]


def _payload(*, model=True, project=None, overrides=None):
    p = {
        "projectData": project or {},
        "zones": ZONES,
        "surfaces": SURFACES,
        "materials": {"constructions": []},
        "constructionOverrides": overrides or {},
    }
    if model:
        p["baselineModel"] = {"zones": ZONES, "surfaces": SURFACES}
    return p


def _sim(result=None):
    calls = []

    def run(p, d):
        calls.append((p, d))
        return result if result is not None else {"summary": {}, "financial": {}}

    run.calls = calls
    return run


def _run(payload):
    sim = _sim()
    res, dec = baseline.run(payload, ZONES, SURFACES, "/tmp/x",
                            simulate_fn=sim, log=lambda *_a: None)
    return res, dec, sim


# ── 돌리지 않는 경우 ─────────────────────────────────────

@pytest.mark.parametrize("key", ["elecBill", "heatBill", "elecKwh", "heatKwh"])
def test_actual_baseline_skips_the_presimulation(key):
    """실측이 있으면 그쪽이 더 정확하다 — 2.5분을 아낀다."""
    res, dec, sim = _run(_payload(project={"baselineActual": {key: 1_000_000}}))
    assert dec.reason == "actuals"
    assert sim.calls == []
    assert res is None


@pytest.mark.parametrize("bad", [0, "0", "", None, "abc", -5])
def test_non_positive_actuals_do_not_count(bad):
    """⚠️ 빈 입력이나 0 을 실측으로 세면 기준선 없이 결과가 나간다."""
    res, dec, _sim_ = _run(_payload(project={"baselineActual": {"elecBill": bad}}))
    assert dec.reason != "actuals"


def test_identical_models_mean_zero_savings():
    """⚠️ 편집이 전혀 없는데 전-시뮬을 돌리면 수치 잡음이 '절감'으로 둔갑한다."""
    res, dec, sim = _run(_payload())
    assert dec.reason == "identical"
    assert dec.savings_are_zero is True
    assert sim.calls == []


def test_no_baseline_model_means_nothing_to_compare():
    res, dec, sim = _run(_payload(model=False))
    assert dec.reason == "no_model"
    assert dec.savings_are_zero is False, "모델이 없는 것과 전후가 같은 것은 다르다"
    assert sim.calls == []


# ── 돌리는 경우 ──────────────────────────────────────────

def test_edited_geometry_triggers_a_run():
    p = _payload()
    p["baselineModel"] = {"zones": ZONES, "surfaces": [{"id": "S1", "uValue": 2.5}]}
    res, dec, sim = _run(p)
    assert dec.reason == "run"
    assert len(sim.calls) == 1
    assert res is not None


@pytest.mark.parametrize("key", list(baseline.RETROFIT_KEYS))
def test_each_retrofit_element_triggers_a_run(key):
    """⚠️ 하나라도 빠뜨리면 '개선 요소가 있는데 전후 동일'로 판정돼 절감이 0 이 된다."""
    payload = _payload(project={key: True} if key != "pvCapacity" else {"pvCapacity": 10})
    if key == "constructionOverrides":
        payload = _payload(overrides={"S1": {"tier": "high"}})
    _res, dec, sim = _run(payload)
    assert dec.reason == "run", f"{key} 를 개선 요소로 안 봤다"
    assert len(sim.calls) == 1


def test_construction_overrides_at_top_level_also_count():
    _res, dec, _s = _run(_payload(overrides={"S1": {"tier": "high"}}))
    assert dec.reason == "run"


# ── 기준선 payload ───────────────────────────────────────

def test_retrofit_elements_are_stripped_from_the_baseline():
    """개선 전 건물에 PV·지열·LED 가 있으면 절감액이 줄어든다."""
    payload = _payload(project={"pvCapacity": 30, "geothermalApplied": True,
                                "ledReductionActive": True, "hvacUpgradeActive": True,
                                "name": "테스트"})
    base = baseline.build_payload(payload)
    for key in baseline.RETROFIT_KEYS:
        assert key not in base["projectData"], f"{key} 가 기준선에 남았다"
    assert base["projectData"]["name"] == "테스트", "무관한 설정까지 지웠다"
    assert base["constructionOverrides"] == {}


def test_baseline_payload_is_tagged_to_stop_recursion():
    """⚠️ `_variantOf` 가 없으면 기준선 실행이 자기 대안을 또 평가해 무한 재귀다."""
    assert baseline.build_payload(_payload())["_variantOf"] == "baseline"


def test_baseline_uses_the_uploaded_model_not_the_edited_one():
    original = [{"id": "S1", "uValue": 2.5}]
    payload = _payload()
    payload["baselineModel"] = {"zones": ZONES, "surfaces": original}
    assert baseline.build_payload(payload)["surfaces"] == original


def test_original_payload_is_not_mutated():
    payload = _payload(project={"pvCapacity": 30})
    baseline.build_payload(payload)
    assert payload["projectData"]["pvCapacity"] == 30


def test_baseline_runs_in_its_own_directory():
    p = _payload()
    p["baselineModel"] = {"zones": ZONES, "surfaces": [{"id": "S1", "uValue": 2.5}]}
    _res, _dec, sim = _run(p)
    assert sim.calls[0][1].endswith("baseline")
