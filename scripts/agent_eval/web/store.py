import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.agent_eval.task_io import target_state_of


class DashboardStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_filename TEXT,
                task_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tasks (
                dataset_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                task_json TEXT NOT NULL,
                PRIMARY KEY (dataset_id, task_id),
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                status TEXT NOT NULL,
                agent TEXT NOT NULL,
                model TEXT,
                base_url TEXT,
                trials_per_task INTEGER NOT NULL,
                temperature REAL NOT NULL,
                max_steps INTEGER,
                total_trials INTEGER NOT NULL,
                completed_trials INTEGER NOT NULL DEFAULT 0,
                summary_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trials (
                run_id TEXT NOT NULL,
                trial_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                trial_json TEXT NOT NULL,
                evaluation_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_tasks_dataset_position ON tasks(dataset_id, position)",
            "CREATE INDEX IF NOT EXISTS idx_runs_dataset_created ON runs(dataset_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_trials_run_position ON trials(run_id, position)",
        ]
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            for statement in statements:
                connection.execute(statement)
            connection.execute("PRAGMA optimize")

    def import_dataset(
        self,
        name: str,
        source_filename: str,
        tasks: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("测试集名称不能为空")
        if not tasks:
            raise ValueError("测试集至少需要一条任务")
        task_ids = []
        for position, task in enumerate(tasks, 1):
            if not isinstance(task, dict):
                raise ValueError("第 {} 条任务必须是 JSON object".format(position))
            task_id = task.get("id")
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError("第 {} 条任务缺少 id".format(position))
            target_state_of(task)
            if task_id in task_ids:
                raise ValueError("重复 task id: {}".format(task_id))
            task_ids.append(task_id)

        dataset_id = str(uuid.uuid4())
        created_at = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO datasets(id, name, source_filename, task_count, created_at) VALUES (?, ?, ?, ?, ?)",
                (dataset_id, clean_name, source_filename, len(tasks), created_at),
            )
            connection.executemany(
                "INSERT INTO tasks(dataset_id, task_id, position, task_json) VALUES (?, ?, ?, ?)",
                [
                    (
                        dataset_id,
                        task["id"],
                        position,
                        json.dumps(task, ensure_ascii=False, separators=(",", ":")),
                    )
                    for position, task in enumerate(tasks)
                ],
            )
        return self.get_dataset(dataset_id) or {}

    def list_datasets(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name, source_filename, task_count, created_at FROM datasets ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, source_filename, task_count, created_at FROM datasets WHERE id = ?",
                (dataset_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(self, dataset_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_json FROM tasks WHERE dataset_id = ? ORDER BY position",
                (dataset_id,),
            ).fetchall()
        return [json.loads(row["task_json"]) for row in rows]

    def delete_dataset(self, dataset_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        return cursor.rowcount > 0

    def create_run(
        self,
        dataset_id: str,
        agent: str,
        model: Optional[str],
        trials_per_task: int,
        temperature: float,
        max_steps: Optional[int],
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        dataset = self.get_dataset(dataset_id)
        if dataset is None:
            raise ValueError("测试集不存在: {}".format(dataset_id))
        run_id = str(uuid.uuid4())
        created_at = _now()
        total_trials = dataset["task_count"] * trials_per_task
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs(
                    id, dataset_id, status, agent, model, base_url, trials_per_task,
                    temperature, max_steps, total_trials, completed_trials, created_at
                ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    run_id,
                    dataset_id,
                    agent,
                    model,
                    base_url,
                    trials_per_task,
                    temperature,
                    max_steps,
                    total_trials,
                    created_at,
                ),
            )
        return self.get_run(run_id) or {}

    def mark_run_running(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = 'running', started_at = ?, error = NULL WHERE id = ?",
                (_now(), run_id),
            )

    def save_trial(
        self,
        run_id: str,
        trial: Dict[str, Any],
        evaluation: Dict[str, Any],
        position: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trials(run_id, trial_id, task_id, position, trial_json, evaluation_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    trial["trial_id"],
                    trial["task_id"],
                    position,
                    json.dumps(trial, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(evaluation, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            connection.execute(
                "UPDATE runs SET completed_trials = completed_trials + 1 WHERE id = ?",
                (run_id,),
            )

    def finish_run(self, run_id: str, summary: Dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET status = 'completed', summary_json = ?, completed_at = ?, error = NULL
                WHERE id = ?
                """,
                (json.dumps(summary, ensure_ascii=False, separators=(",", ":")), _now(), run_id),
            )

    def fail_run(self, run_id: str, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
                (error, _now(), run_id),
            )

    def list_runs(self, dataset_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM runs"
        params: tuple = ()
        if dataset_id:
            query += " WHERE dataset_id = ?"
            params = (dataset_id,)
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_run_from_row(row) for row in rows]

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _run_from_row(row) if row else None

    def list_trials(self, run_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT trial_json, evaluation_json FROM trials WHERE run_id = ? ORDER BY position",
                (run_id,),
            ).fetchall()
        return [
            {"trial": json.loads(row["trial_json"]), "evaluation": json.loads(row["evaluation_json"])}
            for row in rows
        ]

    def get_trial(self, trial_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT run_id, trial_json, evaluation_json FROM trials WHERE trial_id = ?",
                (trial_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "trial": json.loads(row["trial_json"]),
            "evaluation": json.loads(row["evaluation_json"]),
        }


def _run_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    payload = dict(row)
    summary_json = payload.pop("summary_json")
    payload["summary"] = json.loads(summary_json) if summary_json else None
    return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
