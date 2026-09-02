import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.agent_eval.web.service import EvaluationService, RunConfig
from scripts.agent_eval.web.store import DashboardStore
from tests.agent_eval_fixtures import sample_task


class EvaluationServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = DashboardStore(Path(self.temp_dir.name) / "dashboard.db")
        self.dataset = self.store.import_dataset("毕业审核", "tasks.jsonl", [sample_task()])
        self.service = EvaluationService(self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_executes_oracle_run_and_persists_progress_and_trace(self):
        run_id = self.service.create_run(
            RunConfig(dataset_id=self.dataset["id"], agent="oracle", trials_per_task=2)
        )
        self.assertEqual("queued", self.store.get_run(run_id)["status"])

        self.service.execute_run(run_id)

        run = self.store.get_run(run_id)
        trials = self.store.list_trials(run_id)
        self.assertEqual("completed", run["status"])
        self.assertEqual(2, run["completed_trials"])
        self.assertEqual(2, run["summary"]["trials"])
        self.assertEqual(1.0, run["summary"]["pass_rate"])
        self.assertEqual(2, len(trials))
        tool_results = [
            event
            for event in trials[0]["trial"]["transcript"]
            if event.get("type") == "tool_result"
        ]
        self.assertEqual(7, len(tool_results))
        self.assertIn("state_before", tool_results[0])
        self.assertIn("state_after", tool_results[0])
        self.assertTrue(trials[0]["evaluation"]["passed"])

    def test_marks_run_failed_when_model_configuration_is_missing(self):
        run_id = self.service.create_run(
            RunConfig(dataset_id=self.dataset["id"], agent="openai", trials_per_task=1)
        )

        with patch.dict("os.environ", {}, clear=True):
            self.service.execute_run(run_id)

        run = self.store.get_run(run_id)
        self.assertEqual("failed", run["status"])
        self.assertIn("--model", run["error"])
        self.assertEqual([], self.store.list_trials(run_id))


if __name__ == "__main__":
    unittest.main()
