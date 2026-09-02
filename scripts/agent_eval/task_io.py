import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def target_state_of(task: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    output = task.get("output") or {}
    if isinstance(output.get("target_state"), dict):
        return output["target_state"], None
    if isinstance(task.get("target_state"), dict):
        return task["target_state"], "legacy_top_level_target_state"
    raise ValueError("任务缺少 output.target_state")


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    records = []
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("{}:{} 不是合法 JSON: {}".format(source, line_number, exc)) from exc
            if not isinstance(record, dict):
                raise ValueError("{}:{} 必须是 JSON object".format(source, line_number))
            records.append(record)
    return records


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
