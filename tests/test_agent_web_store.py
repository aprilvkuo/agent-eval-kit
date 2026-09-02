import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.agent_eval.web.store import DashboardStore
from tests.agent_eval_fixtures import sample_task


class DashboardStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "dashboard.db"
        self.store = DashboardStore(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_imports_lists_and_deletes_dataset(self):
        first = sample_task()
        second = copy.deepcopy(first)
        second["id"] = "agent_education_083812"

        dataset = self.store.import_dataset(
            name="毕业审核测试集",
            source_filename="education.jsonl",
            tasks=[first, second],
        )

        self.assertEqual(2, dataset["task_count"])
        self.assertEqual("毕业审核测试集", self.store.list_datasets()[0]["name"])
        tasks = self.store.list_tasks(dataset["id"])
        self.assertEqual([first["id"], second["id"]], [row["id"] for row in tasks])
        self.assertEqual(first["output"], tasks[0]["output"])
        self.assertTrue(self.store.delete_dataset(dataset["id"]))
        self.assertEqual([], self.store.list_datasets())

    def test_rejects_duplicate_task_ids(self):
        task = sample_task()

        with self.assertRaisesRegex(ValueError, "重复 task id"):
            self.store.import_dataset("重复数据", "duplicate.jsonl", [task, copy.deepcopy(task)])

    def test_persists_run_trial_evaluation_and_cascades_delete(self):
        task = sample_task()
        dataset = self.store.import_dataset("测试集", "tasks.jsonl", [task])
        run = self.store.create_run(
            dataset_id=dataset["id"],
            agent="oracle",
            model=None,
            trials_per_task=1,
            temperature=0.0,
            max_steps=None,
        )
        trial = {
            "trial_id": "trial-1",
            "task_id": task["id"],
            "status": "completed",
            "transcript": [{"type": "assistant", "content": "完成"}],
            "outcome": {"final_state": {}, "tool_call_count": 0},
        }
        evaluation = {"trial_id": "trial-1", "task_id": task["id"], "passed": True, "score": 1.0}

        self.store.mark_run_running(run["id"])
        self.store.save_trial(run["id"], trial, evaluation, position=0)
        self.store.finish_run(run["id"], {"trials": 1, "pass_rate": 1.0})

        stored_run = self.store.get_run(run["id"])
        stored_trial = self.store.get_trial("trial-1")
        self.assertEqual("completed", stored_run["status"])
        self.assertEqual(1, stored_run["completed_trials"])
        self.assertEqual(1.0, stored_run["summary"]["pass_rate"])
        self.assertEqual(trial["transcript"], stored_trial["trial"]["transcript"])
        self.assertTrue(stored_trial["evaluation"]["passed"])

        self.store.delete_dataset(dataset["id"])
        self.assertIsNone(self.store.get_run(run["id"]))
        self.assertIsNone(self.store.get_trial("trial-1"))

    def test_schema_has_query_indexes(self):
        with sqlite3.connect(str(self.db_path)) as connection:
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema WHERE type = 'index' AND name LIKE 'idx_%'"
                )
            }

        self.assertEqual(
            {"idx_tasks_dataset_position", "idx_runs_dataset_created", "idx_trials_run_position"},
            names,
        )


if __name__ == "__main__":
    unittest.main()
