# src/task_store.py - 시뮬레이션 작업 상태 SQLite 영속화
# 프로세스 메모리 dict의 한계(재시작 시 유실, 단일 프로세스 전제) 해소용.
# 연산마다 새 커넥션을 열어 스레드 안전을 확보한다 (BackgroundTasks는 스레드풀에서 실행됨).
import json
import sqlite3
import time


class TaskStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,           -- queued | running | success | failed
                    result TEXT,                     -- 성공 시 결과 JSON
                    error TEXT,                      -- 실패 시 원인
                    created_at REAL,
                    started_at REAL,
                    finished_at REAL
                )
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def recover_orphans(self) -> int:
        """서버 재시작 시 진행 중이던 작업은 재개할 수 없다 → 명시적으로 실패 처리."""
        with self._conn() as c:
            cur = c.execute(
                "UPDATE tasks SET status='failed', error=?, finished_at=? "
                "WHERE status IN ('queued', 'running')",
                ("서버가 재시작되어 작업이 중단되었습니다. 시뮬레이션을 다시 실행해주세요.", time.time()),
            )
            return cur.rowcount

    def create(self, task_id: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO tasks (id, status, created_at) VALUES (?, 'queued', ?)",
                (task_id, time.time()),
            )

    def mark_running(self, task_id: str):
        with self._conn() as c:
            c.execute(
                "UPDATE tasks SET status='running', started_at=? WHERE id=?",
                (time.time(), task_id),
            )

    def finish(self, task_id: str, result=None, error: str = None):
        status = "success" if error is None else "failed"
        with self._conn() as c:
            c.execute(
                "UPDATE tasks SET status=?, result=?, error=?, finished_at=? WHERE id=?",
                (status, json.dumps(result) if result is not None else None,
                 error, time.time(), task_id),
            )

    def get(self, task_id: str):
        """기존 dict 저장소와 동일한 응답 형태를 유지한다 (프론트 폴링 계약)."""
        with self._conn() as c:
            row = c.execute(
                "SELECT status, result, error, started_at, finished_at FROM tasks WHERE id=?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        status, result, error, started_at, finished_at = row
        task = {"status": status}
        if started_at:
            task["started_at"] = started_at
        if finished_at:
            task["finished_at"] = finished_at
        if status == "success" and result:
            task["result"] = json.loads(result)
        if status == "failed" and error:
            task["error"] = error
        return task

    def count_pending(self) -> int:
        with self._conn() as c:
            (n,) = c.execute(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('queued', 'running')"
            ).fetchone()
        return n

    def prune(self, ttl_seconds: int, max_tasks: int):
        """TTL 지난 종료 작업 삭제 + 그래도 상한 초과면 오래된 종료 작업부터 추가 삭제."""
        now = time.time()
        with self._conn() as c:
            c.execute(
                "DELETE FROM tasks WHERE status IN ('success', 'failed') AND finished_at < ?",
                (now - ttl_seconds,),
            )
            (total,) = c.execute("SELECT COUNT(*) FROM tasks").fetchone()
            overflow = total - max_tasks
            if overflow > 0:
                c.execute(
                    "DELETE FROM tasks WHERE id IN ("
                    "  SELECT id FROM tasks WHERE status IN ('success', 'failed')"
                    "  ORDER BY finished_at ASC LIMIT ?)",
                    (overflow,),
                )
