"""백그라운드 시뮬레이션 실행기.

`main.py` 에 섞여 있던 것을 옮겼다. **순수 이동이다** — 동작을 바꾸지 않았다.

여기서 다루는 것은 작업의 생애주기뿐이다:
동시 실행 제한 → 상태 전이(running/success/failed) → 작업공간 정리.
**시뮬레이션이 무엇을 계산하는지는 알지 못한다** — 실행 함수를 주입받는다.
그래서 나중에 `simulation/service.py` 가 생겨도 이 파일은 바뀌지 않는다.
"""
import os
import shutil
import threading
from typing import Any, Callable, Dict


def cleanup_workspace(path: str) -> None:
    """임시 작업 공간 정리. 실패해도 예외를 올리지 않는다 —
    정리 실패가 시뮬레이션 결과를 잃게 만들면 안 된다."""
    if os.path.exists(path) and os.path.isdir(path):
        try:
            shutil.rmtree(path)
            print(f"🧹 임시 작업 공간 정리 완료: {path}")
        except Exception as e:
            print(f"⚠️ 임시 작업 공간 정리 실패: {e}")


class SimulationWorker:
    """시뮬레이션 작업을 순차 실행한다.

    💡 EnergyPlus 1회 실행이 ~2.5분/수백MB 라서 동시에 여러 개가 돌면 800MB
    컨테이너가 OOM 으로 죽는다. 초과분은 세마포어 앞에서 'queued' 로 대기한다.
    (세마포어는 **프로세스 단위** — 멀티 워커로 띄우면 워커 수만큼 배수가 된다)
    """

    def __init__(self, task_store, simulate: Callable[..., Any],
                 max_concurrent: int = 1):
        self.task_store = task_store
        self._simulate = simulate
        self.max_concurrent = max_concurrent
        self._semaphore = threading.BoundedSemaphore(max_concurrent)

    def run(self, task_id: str, payload: Dict[str, Any], session_dir: str) -> None:
        """백그라운드에서 시뮬레이션을 실행하고 결과를 저장소에 기록한다."""
        try:
            with self._semaphore:
                self.task_store.mark_running(task_id)
                result = self._simulate(
                    payload, session_dir,
                    on_stage=lambda s: self.task_store.set_stage(task_id, s),
                )
            self.task_store.finish(task_id, result=result)
        except Exception as e:
            print(f"❌ 시뮬레이션 에러: {str(e)}")
            self.task_store.finish(task_id, error=str(e))
        finally:
            # 시뮬레이션이 **모두 끝난 뒤에** 삭제한다 — 실행 중 삭제하면
            # EnergyPlus 가 중간 파일을 잃는다.
            cleanup_workspace(session_dir)
