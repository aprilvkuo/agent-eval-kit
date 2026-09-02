import copy
import time
import uuid
from typing import Any, Dict, Optional

from scripts.agent_eval.environment import MockEnvironment
from scripts.agent_eval.task_io import target_state_of


def run_task(task: Dict[str, Any], policy: Any, max_steps: Optional[int] = None) -> Dict[str, Any]:
    started = time.perf_counter()
    environment = MockEnvironment(task)
    _, schema_warning = target_state_of(task)
    schema_warnings = [schema_warning] if schema_warning else []
    step_budget = max_steps if max_steps is not None else _default_step_budget(task)
    transcript = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    tool_call_count = 0
    final_answer = ""
    error = None
    status = "completed"
    turn_number = 0

    if hasattr(policy, "begin"):
        policy.begin(task)

    while True:
        turn_number += 1
        turn_started = time.perf_counter()
        try:
            turn = policy.next_turn(task, copy.deepcopy(transcript))
        except Exception as exc:
            status = "agent_error"
            error = "{}: {}".format(type(exc).__name__, exc)
            transcript.append(
                {
                    "turn": turn_number,
                    "type": "agent_error",
                    "error": error,
                    "duration_ms": round((time.perf_counter() - turn_started) * 1000, 3),
                }
            )
            break

        content = turn.get("content") or ""
        tool_calls = copy.deepcopy(turn.get("tool_calls") or [])
        turn_usage = copy.deepcopy(turn.get("usage") or {})
        transcript.append(
            {
                "turn": turn_number,
                "type": "assistant",
                "content": content,
                "tool_calls": tool_calls,
                "finish_reason": turn.get("finish_reason"),
                "usage": turn_usage,
                "duration_ms": round((time.perf_counter() - turn_started) * 1000, 3),
                "model_request": copy.deepcopy(turn.get("model_request")),
            }
        )
        _add_usage(usage, turn_usage)

        if not tool_calls:
            final_answer = content
            break

        budget_exceeded = False
        for call in tool_calls:
            if tool_call_count >= step_budget:
                status = "max_steps_exceeded"
                error = "工具调用达到步数上限 {}".format(step_budget)
                budget_exceeded = True
                break
            tool_call_count += 1
            state_before = copy.deepcopy(environment.state)
            tool_started = time.perf_counter()
            result = environment.call_tool(call.get("name", ""), call.get("arguments", {}))
            transcript.append(
                {
                    "turn": turn_number,
                    "step": tool_call_count,
                    "type": "tool_result",
                    "call_id": call.get("id") or "call_{}".format(tool_call_count),
                    "name": call.get("name", ""),
                    "arguments": copy.deepcopy(call.get("arguments", {})),
                    "result": copy.deepcopy(result),
                    "state_before": state_before,
                    "state_after": copy.deepcopy(environment.state),
                    "duration_ms": round((time.perf_counter() - tool_started) * 1000, 3),
                }
            )
        if budget_exceeded:
            break

    extra = task.get("extra", {})
    return {
        "task_id": task.get("id"),
        "trial_id": str(uuid.uuid4()),
        "agent": getattr(policy, "name", policy.__class__.__name__),
        "status": status,
        "metadata": {
            "industry": extra.get("industry"),
            "scenario": extra.get("scenario"),
            "difficulty": extra.get("difficulty"),
        },
        "transcript": transcript,
        "outcome": {
            "final_state": copy.deepcopy(environment.state),
            "final_answer": final_answer,
            "tool_call_count": tool_call_count,
            "error": error,
        },
        "usage": usage,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "schema_warnings": schema_warnings,
    }


def _default_step_budget(task: Dict[str, Any]) -> int:
    bucket = task.get("extra", {}).get("max_autonomous_steps", "")
    try:
        return int(str(bucket).split("-")[-1])
    except ValueError:
        return 20


def _add_usage(total: Dict[str, int], usage: Dict[str, Any]) -> None:
    for key in total:
        total[key] += int(usage.get(key, 0) or 0)
