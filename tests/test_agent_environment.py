import unittest

from scripts.agent_eval.environment import MockEnvironment
from scripts.agent_eval.task_io import target_state_of
from tests.agent_eval_fixtures import sample_task


class TargetStateTests(unittest.TestCase):
    def test_reads_output_target_state(self):
        target, warning = target_state_of(sample_task())

        self.assertTrue(target["case_held"])
        self.assertIsNone(warning)

    def test_supports_legacy_top_level_target_state(self):
        task = sample_task()
        target = task.pop("output")["target_state"]
        task["target_state"] = target

        actual, warning = target_state_of(task)

        self.assertEqual(target, actual)
        self.assertEqual("legacy_top_level_target_state", warning)


class MockEnvironmentTests(unittest.TestCase):
    def test_replays_oracle_tools_to_target(self):
        task = sample_task()
        env = MockEnvironment(task)

        for call in task["extra"]["hidden"]["oracle_trace"]:
            result = env.call_tool(call["tool"], call["arguments"])
            self.assertTrue(result["ok"], result)

        self.assertEqual(task["output"]["target_state"], env.target_view())

    def test_rejects_check_before_identity_verification(self):
        env = MockEnvironment(sample_task())

        result = env.call_tool(
            "check_item",
            {"student_id": "STU08089", "item_name": "资格审核"},
        )

        self.assertFalse(result["ok"])
        self.assertEqual("PRECONDITION_FAILED", result["error_code"])
        self.assertFalse(env.state["item_checked"])

    def test_unknown_item_does_not_mutate_state(self):
        env = MockEnvironment(sample_task())
        env.call_tool(
            "verify_identity",
            {"student_id": "STU08089", "code": "5820", "code_type": "id_last4"},
        )

        result = env.call_tool(
            "check_item",
            {"student_id": "STU08089", "item_name": "不存在项目"},
        )

        self.assertFalse(result["ok"])
        self.assertEqual("ITEM_NOT_FOUND", result["error_code"])
        self.assertFalse(env.state["item_checked"])

    def test_instances_do_not_share_state(self):
        first = MockEnvironment(sample_task())
        second = MockEnvironment(sample_task())

        first.call_tool(
            "verify_identity",
            {"student_id": "STU08089", "code": "5820", "code_type": "id_last4"},
        )

        self.assertTrue(first.state["identity_verified"])
        self.assertFalse(second.state["identity_verified"])

    def test_missing_required_argument_returns_structured_error(self):
        env = MockEnvironment(sample_task())

        result = env.call_tool("query_case", {})

        self.assertFalse(result["ok"])
        self.assertEqual("INVALID_ARGUMENT", result["error_code"])
        self.assertIn("student_id", result["reason"])


if __name__ == "__main__":
    unittest.main()
