import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from scripts.agent_eval.cli import make_policy
from scripts.agent_eval.task_io import write_jsonl
from tests.agent_eval_fixtures import sample_task


class AgentCliTests(unittest.TestCase):
    def test_openai_policy_uses_anthropic_environment_defaults(self):
        args = Namespace(
            agent="openai",
            model=None,
            base_url=None,
            api_key_env=None,
            temperature=0.0,
        )
        environment = {
            "ANTHROPIC_AUTH_TOKEN": "test-token",
            "ANTHROPIC_BASE_URL": "http://127.0.0.1:4000",
            "ANTHROPIC_MODEL": "test-model",
        }

        with patch.dict("os.environ", environment, clear=True):
            policy = make_policy(args)

        self.assertEqual("test-model", policy.model)
        self.assertEqual("http://127.0.0.1:4000/v1/", str(policy.client.base_url))

    def test_benchmark_runs_and_evaluates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks = root / "tasks.jsonl"
            output_dir = root / "benchmark"
            write_jsonl(str(tasks), [sample_task()])

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.agent_eval.cli",
                    "benchmark",
                    "--tasks",
                    str(tasks),
                    "--output-dir",
                    str(output_dir),
                    "--agent",
                    "oracle",
                    "--trials-per-task",
                    "2",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            trials = [
                json.loads(line)
                for line in (output_dir / "trials.jsonl").read_text(encoding="utf-8").splitlines()
                if line
            ]
            evaluations = [
                json.loads(line)
                for line in (output_dir / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
                if line
            ]
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))

        self.assertEqual(2, len(trials))
        self.assertEqual(2, len(evaluations))
        self.assertEqual(1.0, summary["pass_rate"])
        self.assertIn('"pass_rate": 1.0', result.stdout)

    def test_oracle_run_and_evaluate_end_to_end(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks = root / "tasks.jsonl"
            trials = root / "trials.jsonl"
            details = root / "evaluations.jsonl"
            summary = root / "summary.json"
            write_jsonl(str(tasks), [sample_task()])

            run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.agent_eval.cli",
                    "run",
                    "--tasks",
                    str(tasks),
                    "--output",
                    str(trials),
                    "--agent",
                    "oracle",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
            )
            evaluate = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.agent_eval.cli",
                    "evaluate",
                    "--tasks",
                    str(tasks),
                    "--trials",
                    str(trials),
                    "--details",
                    str(details),
                    "--summary",
                    str(summary),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, run.returncode, run.stderr)
            self.assertEqual(0, evaluate.returncode, evaluate.stderr)
            trial = json.loads(trials.read_text(encoding="utf-8").strip())
            report = json.loads(summary.read_text(encoding="utf-8"))
            evaluation = json.loads(details.read_text(encoding="utf-8").strip())

        self.assertEqual("completed", trial["status"])
        self.assertTrue(evaluation["passed"])
        self.assertEqual(1.0, report["pass_rate"])
        self.assertIn('"trials": 1', evaluate.stdout)

    def test_run_limit_processes_only_requested_tasks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks = root / "tasks.jsonl"
            trials = root / "trials.jsonl"
            first = sample_task()
            second = sample_task()
            second["id"] = "agent_education_083812"
            write_jsonl(str(tasks), [first, second])

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.agent_eval.cli",
                    "run",
                    "--tasks",
                    str(tasks),
                    "--output",
                    str(trials),
                    "--agent",
                    "oracle",
                    "--limit",
                    "1",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            rows = [line for line in trials.read_text(encoding="utf-8").splitlines() if line]

        self.assertEqual(1, len(rows))

    def test_runs_multiple_trials_per_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks = root / "tasks.jsonl"
            trials = root / "trials.jsonl"
            write_jsonl(str(tasks), [sample_task()])

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.agent_eval.cli",
                    "run",
                    "--tasks",
                    str(tasks),
                    "--output",
                    str(trials),
                    "--agent",
                    "oracle",
                    "--trials-per-task",
                    "2",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            rows = [json.loads(line) for line in trials.read_text(encoding="utf-8").splitlines() if line]

        self.assertEqual(2, len(rows))
        self.assertNotEqual(rows[0]["trial_id"], rows[1]["trial_id"])


if __name__ == "__main__":
    unittest.main()
