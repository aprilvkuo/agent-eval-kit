import tempfile
import unittest
from pathlib import Path

from scripts.agent_eval.task_io import load_jsonl, write_jsonl
from tests.agent_eval_fixtures import sample_task


class JsonlTests(unittest.TestCase):
    def test_round_trips_unicode_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "tasks.jsonl"

            write_jsonl(str(path), [sample_task()])
            records = load_jsonl(str(path))

        self.assertEqual("陈某", records[0]["input"]["initial_state"]["name"])

    def test_reports_invalid_json_line_number(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.jsonl"
            path.write_text('{"ok": true}\nnot-json\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"broken\.jsonl:2"):
                load_jsonl(str(path))


if __name__ == "__main__":
    unittest.main()
