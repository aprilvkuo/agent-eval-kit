import json
import unittest
from pathlib import Path


class AgentDemoDatasetTests(unittest.TestCase):
    def test_agent_demo_dataset_uses_output_target_state(self):
        dataset_path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "agent_eval"
            / "agent_demo.jsonl"
        )
        self.assertTrue(dataset_path.is_file(), "agent_demo.jsonl must be included")

        rows = [
            json.loads(line)
            for line in dataset_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(20, len(rows))
        self.assertEqual(20, len({row["id"] for row in rows}))

        for row in rows:
            self.assertEqual(
                ["id", "type", "abilities", "input", "output", "source", "extra"],
                list(row),
            )
            self.assertEqual(
                ["prompt", "files", "initial_state", "tools"],
                list(row["input"]),
            )
            self.assertNotIn("target_state", row)
            self.assertEqual(["target_state"], list(row["output"]))
            self.assertIsInstance(row["output"]["target_state"], dict)


if __name__ == "__main__":
    unittest.main()
