# TaskStore: 생명주기, 재시작 복구, 정리(prune) 검증
import time

import pytest

from src.jobs.repository import TaskStore


@pytest.fixture
def store(tmp_path):
    return TaskStore(str(tmp_path / "tasks.db"))


def test_lifecycle_success(store):
    store.create("t1")
    assert store.get("t1")["status"] == "queued"
    assert store.count_pending() == 1

    store.mark_running("t1")
    assert store.get("t1")["status"] == "running"

    store.finish("t1", result={"summary": {"consume_per_m2": 104.5}})
    task = store.get("t1")
    assert task["status"] == "success"
    assert task["result"]["summary"]["consume_per_m2"] == 104.5
    assert store.count_pending() == 0


def test_lifecycle_failure(store):
    store.create("t1")
    store.mark_running("t1")
    store.finish("t1", error="EnergyPlus 시뮬레이션 실패")
    task = store.get("t1")
    assert task["status"] == "failed"
    assert "EnergyPlus" in task["error"]


def test_unknown_task_returns_none(store):
    assert store.get("no-such-task") is None


def test_stage_tracking(store):
    """진행 단계(개선 전/후)가 폴링 응답에 실려야 로딩 화면이 표시 가능."""
    store.create("t1")
    store.mark_running("t1")
    assert "stage" not in store.get("t1")
    store.set_stage("t1", "baseline")
    assert store.get("t1")["stage"] == "baseline"
    store.set_stage("t1", "retrofit")
    assert store.get("t1")["stage"] == "retrofit"


def test_restart_recovers_orphans(tmp_path):
    """재시작 시 queued/running 작업은 실패 처리, 완료 결과는 유지되어야 한다."""
    db = str(tmp_path / "tasks.db")
    s1 = TaskStore(db)
    s1.create("done")
    s1.finish("done", result={"ok": True})
    s1.create("stuck-queued")
    s1.create("stuck-running")
    s1.mark_running("stuck-running")

    # 서버 재기동 시나리오
    s2 = TaskStore(db)
    assert s2.recover_orphans() == 2
    assert s2.get("stuck-queued")["status"] == "failed"
    assert "재시작" in s2.get("stuck-running")["error"]
    assert s2.get("done")["status"] == "success"  # 완료 결과는 유실되지 않음


def test_prune_ttl_and_cap(store):
    for i in range(5):
        store.create(f"t{i}")
        store.finish(f"t{i}", result={"i": i})
    store.create("running")
    store.mark_running("running")

    # TTL 0초 → 종료 작업 전부 삭제, 진행 중 작업은 유지
    time.sleep(0.01)
    store.prune(ttl_seconds=0, max_tasks=100)
    assert store.get("t0") is None
    assert store.get("running")["status"] == "running"

    # 상한 초과 시 오래된 종료 작업부터 삭제
    for i in range(4):
        store.create(f"n{i}")
        store.finish(f"n{i}", result={})
        time.sleep(0.01)
    store.prune(ttl_seconds=3600, max_tasks=3)
    assert store.get("n0") is None          # 가장 오래된 것 삭제
    assert store.get("n3")["status"] == "success"
