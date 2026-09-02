import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from scripts.agent_eval.web.app import create_app
from tests.agent_eval_fixtures import sample_task


class AgentWebApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self.temp_dir.name)))

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def import_dataset(self):
        payload = json.dumps(sample_task(), ensure_ascii=False).encode("utf-8") + b"\n"
        response = self.client.post(
            "/api/datasets",
            data={"name": "毕业审核测试集"},
            files={"file": ("education.jsonl", payload, "application/x-ndjson")},
        )
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    def test_imports_lists_and_deletes_dataset(self):
        dataset = self.import_dataset()

        datasets = self.client.get("/api/datasets")
        tasks = self.client.get("/api/datasets/{}/tasks".format(dataset["id"]))
        deleted = self.client.delete("/api/datasets/{}".format(dataset["id"]))
        missing = self.client.get("/api/datasets/{}/tasks".format(dataset["id"]))

        self.assertEqual(1, len(datasets.json()))
        self.assertEqual(sample_task()["id"], tasks.json()[0]["id"])
        self.assertEqual(204, deleted.status_code)
        self.assertEqual(404, missing.status_code)

    def test_runs_oracle_and_returns_trial_details(self):
        dataset = self.import_dataset()

        response = self.client.post(
            "/api/runs",
            json={"dataset_id": dataset["id"], "agent": "oracle", "trials_per_task": 2},
        )
        self.assertEqual(202, response.status_code, response.text)
        run_id = response.json()["id"]
        run = self.client.get("/api/runs/{}".format(run_id)).json()
        trials = self.client.get("/api/runs/{}/trials".format(run_id)).json()
        detail = self.client.get("/api/trials/{}".format(trials[0]["trial"]["trial_id"])).json()

        self.assertEqual("completed", run["status"])
        self.assertEqual(1.0, run["summary"]["pass_rate"])
        self.assertEqual(2, len(trials))
        self.assertTrue(detail["evaluation"]["passed"])
        self.assertTrue(detail["trial"]["transcript"])
        self.assertEqual(sample_task()["input"]["prompt"], detail["task"]["input"]["prompt"])
        self.assertEqual(sample_task()["output"]["target_state"], detail["task"]["output"]["target_state"])

    def test_config_reports_auth_presence_without_returning_token(self):
        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_AUTH_TOKEN": "secret-value",
                "ANTHROPIC_MODEL": "test-model",
                "ANTHROPIC_BASE_URL": "http://127.0.0.1:4000",
            },
            clear=True,
        ):
            response = self.client.get("/api/config")

        self.assertEqual(200, response.status_code)
        self.assertEqual("test-model", response.json()["model"])
        self.assertTrue(response.json()["auth_configured"])
        self.assertNotIn("secret-value", response.text)

    def test_lists_available_models_and_places_current_model_first(self):
        fake_models = SimpleNamespace(
            data=[
                SimpleNamespace(id="another-model"),
                SimpleNamespace(id="current-model"),
                SimpleNamespace(id="another-model"),
            ]
        )
        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_AUTH_TOKEN": "secret-value",
                "ANTHROPIC_MODEL": "current-model",
                "ANTHROPIC_BASE_URL": "http://127.0.0.1:4000",
            },
            clear=True,
        ), patch("openai.OpenAI") as openai_client:
            openai_client.return_value.models.list.return_value = fake_models
            response = self.client.get("/api/models")

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("current-model", response.json()["current"])
        self.assertEqual(["current-model", "another-model"], response.json()["models"])
        self.assertNotIn("secret-value", response.text)

    def test_serves_dashboard(self):
        response = self.client.get("/")

        self.assertEqual(200, response.status_code)
        self.assertIn("Agent Eval Console", response.text)
        self.assertIn("测试集", response.text)
        self.assertIn('<select id="model"', response.text)

    def test_dashboard_renders_complete_harness_timeline(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "agent_eval"
            / "web"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("Harness 调用链", source)
        self.assertIn("model_request", source)
        self.assertIn('event.type === "assistant"', source)

    def test_read_only_mode_blocks_mutations_and_reports_access_mode(self):
        payload = json.dumps(sample_task(), ensure_ascii=False).encode("utf-8") + b"\n"
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ", {"AGENT_EVAL_READ_ONLY": "1"}, clear=False
        ):
            with TestClient(create_app(Path(temp_dir))) as client:
                config = client.get("/api/config")
                response = client.post(
                    "/api/datasets",
                    data={"name": "不可写入"},
                    files={"file": ("blocked.jsonl", payload, "application/x-ndjson")},
                )

        self.assertTrue(config.json()["read_only"])
        self.assertEqual(403, response.status_code)
        self.assertIn("只读", response.json()["detail"])

    def test_dashboard_has_public_read_only_state(self):
        root = Path(__file__).resolve().parents[1] / "scripts" / "agent_eval" / "web" / "static"
        html = (root / "index.html").read_text(encoding="utf-8")
        javascript = (root / "app.js").read_text(encoding="utf-8")

        self.assertIn("read-only-banner", html)
        self.assertIn("公开只读", html)
        self.assertIn("state.config.read_only", javascript)


if __name__ == "__main__":
    unittest.main()
