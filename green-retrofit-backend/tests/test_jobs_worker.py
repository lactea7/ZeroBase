"""SimulationWorker 단위시험.

`main.py` 에 있을 때는 시험이 하나도 없었다. 분리하면서 계약을 고정한다.
시뮬레이션 함수를 주입받으므로 EnergyPlus 없이 전 경로를 검사할 수 있다.
"""
import os
import sys
import threading

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.jobs.worker import SimulationWorker, cleanup_workspace  # noqa: E402


class FakeStore:
    def __init__(self):
        self.calls = []

    def mark_running(self, task_id):
        self.calls.append(("running", task_id))

    def set_stage(self, task_id, stage):
        self.calls.append(("stage", stage))

    def finish(self, task_id, result=None, error=None):
        self.calls.append(("finish", "error" if error else "success", error or result))


def test_success_path_records_running_then_success(tmp_path):
    store = FakeStore()
    worker = SimulationWorker(store, lambda p, d, on_stage=None: {"ok": True})
    worker.run("t1", {}, str(tmp_path))
    assert store.calls[0] == ("running", "t1")
    assert store.calls[-1] == ("finish", "success", {"ok": True})


def test_stage_callback_is_forwarded(tmp_path):
    store = FakeStore()

    def sim(payload, d, on_stage=None):
        on_stage("baseline")
        on_stage("retrofit")
        return {}

    SimulationWorker(store, sim).run("t1", {}, str(tmp_path))
    assert ("stage", "baseline") in store.calls
    assert ("stage", "retrofit") in store.calls


def test_failure_is_recorded_not_raised(tmp_path):
    """작업 실패가 예외로 새면 백그라운드 스레드가 조용히 죽는다."""
    store = FakeStore()

    def boom(payload, d, on_stage=None):
        raise RuntimeError("엔진 폭발")

    SimulationWorker(store, boom).run("t1", {}, str(tmp_path))   # 예외가 올라오면 실패
    kind, status, detail = store.calls[-1]
    assert (kind, status) == ("finish", "error")
    assert "엔진 폭발" in detail


def test_workspace_is_cleaned_even_on_failure(tmp_path):
    """정리를 빼먹으면 디스크가 찬다 — 실패 경로에서 특히 중요하다."""
    work = tmp_path / "session"
    work.mkdir()
    (work / "eplusout.csv").write_text("x")

    def boom(payload, d, on_stage=None):
        raise RuntimeError("실패")

    SimulationWorker(FakeStore(), boom).run("t1", {}, str(work))
    assert not work.exists(), "실패 경로에서 작업공간이 남았다"


def test_workspace_is_cleaned_on_success(tmp_path):
    work = tmp_path / "session"
    work.mkdir()
    SimulationWorker(FakeStore(), lambda p, d, on_stage=None: {}).run("t1", {}, str(work))
    assert not work.exists()


def test_concurrency_is_limited(tmp_path):
    """EnergyPlus 동시 실행은 메모리 때문에 반드시 제한돼야 한다(800MB 컨테이너 OOM)."""
    peak = {"n": 0, "cur": 0}
    lock = threading.Lock()

    def sim(payload, d, on_stage=None):
        with lock:
            peak["cur"] += 1
            peak["n"] = max(peak["n"], peak["cur"])
        threading.Event().wait(0.05)
        with lock:
            peak["cur"] -= 1
        return {}

    worker = SimulationWorker(FakeStore(), sim, max_concurrent=1)
    threads = [threading.Thread(target=worker.run, args=(f"t{i}", {}, str(tmp_path / f"s{i}")))
               for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak["n"] == 1, f"동시 실행이 {peak['n']}개까지 올라갔다 (제한 1)"


def test_cleanup_missing_path_is_noop(tmp_path):
    cleanup_workspace(str(tmp_path / "없는경로"))     # 예외가 나면 실패


def test_cleanup_failure_does_not_raise(tmp_path, monkeypatch):
    """정리 실패가 결과를 잃게 만들면 안 된다."""
    work = tmp_path / "s"
    work.mkdir()
    monkeypatch.setattr("src.jobs.worker.shutil.rmtree",
                        lambda p: (_ for _ in ()).throw(OSError("권한 없음")))
    cleanup_workspace(str(work))                      # 예외가 나면 실패
