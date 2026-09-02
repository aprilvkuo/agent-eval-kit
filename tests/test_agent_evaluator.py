import unittest

from scripts.agent_eval.agents import OraclePolicy, ScriptedPolicy
from scripts.agent_eval.evaluator import evaluate_trial, summarize_evaluations
from scripts.agent_eval.runner import run_task
from tests.agent_eval_fixtures import sample_task


def scripted_turn(name, arguments, number):
    return {
        "content": "",
        "tool_calls": [
            {
                "id": "scripted_{}".format(number),
                "name": name,
                "arguments": arguments,
            }
        ],
        "usage": {},
    }


def target_state_but_one_check_trial(task):
    turns = [
        scripted_turn(
            "verify_identity",
            {"student_id": "STU08089", "code": "5820", "code_type": "id_last4"},
            1,
        ),
        scripted_turn("query_case", {"student_id": "STU08089"}, 2),
        scripted_turn(
            "check_item",
            {"student_id": "STU08089", "item_name": "资格审核"},
            3,
        ),
        scripted_turn(
            "hold_case",
            {"student_id": "STU08089", "reason": "毕业审核合规核查存在问题"},
            4,
        ),
        {"content": "已暂缓", "tool_calls": [], "usage": {}},
    ]
    return run_task(task, ScriptedPolicy(turns))


class EvaluatorTests(unittest.TestCase):
    def test_oracle_trial_passes_all_graders(self):
        task = sample_task()

        result = evaluate_trial(task, run_task(task, OraclePolicy()))

        self.assertTrue(result["passed"])
        self.assertEqual(1.0, result["score"])
        self.assertEqual(1.0, result["metrics"]["item_coverage"])
        self.assertTrue(result["metrics"]["state_exact_match"])

    def test_matching_state_but_missing_items_fails_process_requirement(self):
        task = sample_task()

        result = evaluate_trial(task, target_state_but_one_check_trial(task))

        self.assertTrue(result["metrics"]["state_exact_match"])
        self.assertFalse(result["passed"])
        self.assertEqual(0.25, result["metrics"]["item_coverage"])
        self.assertEqual(["毕业资格", "实习完成", "档案移交"], result["diagnostics"]["missing_items"])

    def test_precondition_violation_is_reported(self):
        turns = [
            scripted_turn(
                "check_item",
                {"student_id": "STU08089", "item_name": "资格审核"},
                1,
            ),
            {"content": "结束", "tool_calls": [], "usage": {}},
        ]
        task = sample_task()

        result = evaluate_trial(task, run_task(task, ScriptedPolicy(turns)))

        self.assertFalse(result["passed"])
        self.assertEqual(1, result["metrics"]["precondition_violations"])
        self.assertEqual(1, result["metrics"]["invalid_tool_calls"])

    def test_summary_groups_by_scenario_and_difficulty(self):
        task = sample_task()
        passing = evaluate_trial(task, run_task(task, OraclePolicy()))
        failing = evaluate_trial(task, target_state_but_one_check_trial(task))

        summary = summarize_evaluations([passing, failing])

        self.assertEqual(1, summary.get("tasks"))
        self.assertEqual(2, summary["trials"])
        self.assertEqual(1, summary["passed"])
        self.assertEqual(0.5, summary["pass_rate"])
        self.assertEqual(1.0, summary.get("pass_at_k"))
        self.assertEqual(0.0, summary.get("pass_all_k"))
        self.assertEqual(2, summary["by_scenario"]["edu_graduation_audit"]["trials"])
        self.assertEqual(0.5, summary["by_difficulty"]["hard"]["pass_rate"])


if __name__ == "__main__":
    unittest.main()
