import json
import unittest
from types import SimpleNamespace

from scripts.agent_eval.agents import OpenAICompatiblePolicy, OraclePolicy, ScriptedPolicy
from scripts.agent_eval.runner import run_task
from tests.agent_eval_fixtures import sample_task


def target_projection(task, final_state):
    target = task["output"]["target_state"]
    return {key: final_state.get(key) for key in target}


class RunnerTests(unittest.TestCase):
    def test_oracle_policy_produces_target_outcome(self):
        task = sample_task()

        trial = run_task(task, OraclePolicy())

        self.assertEqual("completed", trial["status"])
        self.assertEqual(task["output"]["target_state"], target_projection(task, trial["outcome"]["final_state"]))
        self.assertEqual(7, trial["outcome"]["tool_call_count"])
        self.assertIsNone(trial["outcome"]["error"])

    def test_step_limit_stops_repeated_tool_calls(self):
        action = {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_repeat",
                    "name": "query_case",
                    "arguments": {"student_id": "STU08089"},
                }
            ],
            "usage": {},
        }

        trial = run_task(sample_task(), ScriptedPolicy([action] * 20), max_steps=2)

        self.assertEqual("max_steps_exceeded", trial["status"])
        self.assertEqual(2, trial["outcome"]["tool_call_count"])

    def test_tool_errors_are_recorded_without_crashing_trial(self):
        actions = [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "check_item",
                        "arguments": {"student_id": "STU08089", "item_name": "资格审核"},
                    }
                ],
                "usage": {},
            },
            {"content": "无法继续", "tool_calls": [], "usage": {}},
        ]

        trial = run_task(sample_task(), ScriptedPolicy(actions))

        self.assertEqual("completed", trial["status"])
        tool_result = next(item for item in trial["transcript"] if item["type"] == "tool_result")
        self.assertEqual("PRECONDITION_FAILED", tool_result["result"]["error_code"])
        self.assertEqual("无法继续", trial["outcome"]["final_answer"])

    def test_records_legacy_schema_warning(self):
        task = sample_task()
        task["target_state"] = task.pop("output")["target_state"]

        trial = run_task(task, OraclePolicy())

        self.assertIn("legacy_top_level_target_state", trial["schema_warnings"])


class FakeCompletions:
    def __init__(self):
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        tool_call = SimpleNamespace(
            id="model_call_1",
            function=SimpleNamespace(
                name="query_case",
                arguments=json.dumps({"student_id": "STU08089"}, ensure_ascii=False),
            ),
        )
        message = SimpleNamespace(content=None, tool_calls=[tool_call])
        usage = SimpleNamespace(prompt_tokens=11, completion_tokens=3, total_tokens=14)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="tool_calls")], usage=usage)


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


class OpenAICompatiblePolicyTests(unittest.TestCase):
    def test_only_sends_visible_input_and_converts_tools(self):
        client = FakeClient()
        policy = OpenAICompatiblePolicy(model="test-model", client=client)

        turn = policy.next_turn(sample_task(), [])

        request = client.chat.completions.request
        serialized_messages = json.dumps(request["messages"], ensure_ascii=False)
        self.assertIn("EDU5112", serialized_messages)
        self.assertIn("initial_state", serialized_messages)
        self.assertNotIn("target_state", serialized_messages)
        self.assertNotIn("oracle_trace", serialized_messages)
        function = request["tools"][0]["function"]
        self.assertEqual("verify_identity", function["name"])
        self.assertEqual(["student_id", "code", "code_type"], function["parameters"]["required"])
        self.assertEqual("query_case", turn["tool_calls"][0]["name"])
        self.assertEqual(14, turn["usage"]["total_tokens"])


if __name__ == "__main__":
    unittest.main()
