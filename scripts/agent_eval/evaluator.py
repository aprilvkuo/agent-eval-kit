from collections import defaultdict
from typing import Any, Dict, Iterable, List

from scripts.agent_eval.task_io import target_state_of


def evaluate_trial(task: Dict[str, Any], trial: Dict[str, Any]) -> Dict[str, Any]:
    target_state, schema_warning = target_state_of(task)
    final_state = trial.get("outcome", {}).get("final_state", {})
    missing_state_keys = [key for key in target_state if key not in final_state]
    mismatched_state = {
        key: {"expected": expected, "actual": final_state.get(key)}
        for key, expected in target_state.items()
        if key in final_state and final_state.get(key) != expected
    }
    matched_keys = sum(
        1 for key, expected in target_state.items() if key in final_state and final_state.get(key) == expected
    )
    state_key_accuracy = matched_keys / len(target_state) if target_state else 1.0
    state_exact_match = not missing_state_keys and not mismatched_state

    tool_results = [item for item in trial.get("transcript", []) if item.get("type") == "tool_result"]
    invalid_results = [item for item in tool_results if not item.get("result", {}).get("ok")]
    invalid_tool_calls = len(invalid_results)
    precondition_violations = sum(
        1 for item in invalid_results if item.get("result", {}).get("error_code") == "PRECONDITION_FAILED"
    )
    tool_validity = 1.0 if not tool_results else (len(tool_results) - invalid_tool_calls) / len(tool_results)

    expected_items = _expected_items(task)
    checked_items = []
    for item in tool_results:
        if item.get("name") != "check_item" or not item.get("result", {}).get("ok"):
            continue
        item_name = item.get("arguments", {}).get("item_name")
        if item_name not in checked_items:
            checked_items.append(item_name)
    missing_items = [item for item in expected_items if item not in checked_items]
    covered = sum(1 for item in expected_items if item in checked_items)
    item_coverage = covered / len(expected_items) if expected_items else 1.0

    score = round(
        0.7 * state_key_accuracy + 0.2 * item_coverage + 0.1 * tool_validity,
        6,
    )
    passed = (
        trial.get("status") == "completed"
        and state_exact_match
        and item_coverage == 1.0
        and invalid_tool_calls == 0
    )
    failures = []
    if trial.get("status") != "completed":
        failures.append("trial_not_completed")
    if not state_exact_match:
        failures.append("target_state_mismatch")
    if item_coverage != 1.0:
        failures.append("incomplete_item_coverage")
    if invalid_tool_calls:
        failures.append("invalid_tool_calls")

    metadata = task.get("extra", {})
    warnings = list(trial.get("schema_warnings", []))
    if schema_warning and schema_warning not in warnings:
        warnings.append(schema_warning)
    return {
        "task_id": task.get("id"),
        "trial_id": trial.get("trial_id"),
        "agent": trial.get("agent"),
        "passed": passed,
        "score": score,
        "metrics": {
            "state_key_accuracy": round(state_key_accuracy, 6),
            "state_exact_match": state_exact_match,
            "item_coverage": round(item_coverage, 6),
            "tool_validity": round(tool_validity, 6),
            "invalid_tool_calls": invalid_tool_calls,
            "precondition_violations": precondition_violations,
            "tool_call_count": trial.get("outcome", {}).get("tool_call_count", len(tool_results)),
        },
        "diagnostics": {
            "missing_state_keys": missing_state_keys,
            "mismatched_state": mismatched_state,
            "expected_items": expected_items,
            "checked_items": checked_items,
            "missing_items": missing_items,
            "invalid_calls": [
                {
                    "name": item.get("name"),
                    "arguments": item.get("arguments", {}),
                    "result": item.get("result", {}),
                }
                for item in invalid_results
            ],
        },
        "failures": failures,
        "metadata": {
            "industry": metadata.get("industry"),
            "scenario": metadata.get("scenario"),
            "difficulty": metadata.get("difficulty"),
        },
        "schema_warnings": warnings,
    }


def summarize_evaluations(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    evaluations = list(rows)
    summary = _aggregate(evaluations)
    summary["by_industry"] = _group(evaluations, "industry")
    summary["by_scenario"] = _group(evaluations, "scenario")
    summary["by_difficulty"] = _group(evaluations, "difficulty")
    return summary


def _expected_items(task: Dict[str, Any]) -> List[str]:
    params = task.get("extra", {}).get("hidden", {}).get("params_state", {})
    payload = params.get("case_payload") or params.get("query_case_data") or {}
    items = payload.get("items")
    if items is None:
        items = params.get("_chosen_items", [])
    return list(items)


def _aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    count = len(rows)
    passed = sum(1 for row in rows if row.get("passed"))
    task_groups = defaultdict(list)
    for row in rows:
        task_groups[row.get("task_id")].append(row)
    task_count = len(task_groups)
    any_passed = sum(1 for task_rows in task_groups.values() if any(row.get("passed") for row in task_rows))
    all_passed = sum(1 for task_rows in task_groups.values() if all(row.get("passed") for row in task_rows))
    return {
        "tasks": task_count,
        "trials": count,
        "passed": passed,
        "failed": count - passed,
        "pass_rate": round(passed / count, 6) if count else 0.0,
        "pass_at_k": round(any_passed / task_count, 6) if task_count else 0.0,
        "pass_all_k": round(all_passed / task_count, 6) if task_count else 0.0,
        "average_score": round(sum(row.get("score", 0.0) for row in rows) / count, 6) if count else 0.0,
        "average_tool_calls": round(
            sum(row.get("metrics", {}).get("tool_call_count", 0) for row in rows) / count,
            6,
        )
        if count
        else 0.0,
    }


def _group(rows: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    groups = defaultdict(list)
    for row in rows:
        value = row.get("metadata", {}).get(key)
        groups[str(value) if value is not None else "unknown"].append(row)
    return {value: _aggregate(group_rows) for value, group_rows in sorted(groups.items())}
