import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.agent_eval.agents import OpenAICompatiblePolicy, OraclePolicy
from scripts.agent_eval.evaluator import evaluate_trial, summarize_evaluations
from scripts.agent_eval.runner import run_task
from scripts.agent_eval.task_io import load_jsonl, write_jsonl


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("必须大于等于 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行并评估带 mock 环境的 Agent 任务")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="运行 Agent trial")
    run_parser.add_argument("--tasks", required=True, help="任务 JSONL")
    run_parser.add_argument("--output", required=True, help="trial 输出 JSONL")
    run_parser.add_argument("--agent", choices=("oracle", "openai"), default="oracle")
    run_parser.add_argument("--model", help="OpenAI-compatible 模型名")
    run_parser.add_argument("--base-url", help="OpenAI-compatible API base URL")
    run_parser.add_argument("--api-key-env", help="API Key 环境变量名")
    run_parser.add_argument("--temperature", type=float, default=0.0)
    run_parser.add_argument("--max-steps", type=positive_int)
    run_parser.add_argument("--limit", type=positive_int)
    run_parser.add_argument("--trials-per-task", type=positive_int, default=1)
    run_parser.set_defaults(handler=run_command)

    evaluate_parser = subparsers.add_parser("evaluate", help="评估 trial")
    evaluate_parser.add_argument("--tasks", required=True, help="任务 JSONL")
    evaluate_parser.add_argument("--trials", required=True, help="trial JSONL")
    evaluate_parser.add_argument("--details", required=True, help="逐条评估 JSONL")
    evaluate_parser.add_argument("--summary", required=True, help="汇总 JSON")
    evaluate_parser.set_defaults(handler=evaluate_command)

    benchmark_parser = subparsers.add_parser("benchmark", help="一次完成运行和评估")
    benchmark_parser.add_argument("--tasks", required=True, help="任务 JSONL")
    benchmark_parser.add_argument("--output-dir", required=True, help="本次评测输出目录")
    benchmark_parser.add_argument("--agent", choices=("oracle", "openai"), default="oracle")
    benchmark_parser.add_argument("--model", help="OpenAI-compatible 模型名")
    benchmark_parser.add_argument("--base-url", help="OpenAI-compatible API base URL")
    benchmark_parser.add_argument("--api-key-env", help="API Key 环境变量名")
    benchmark_parser.add_argument("--temperature", type=float, default=0.0)
    benchmark_parser.add_argument("--max-steps", type=positive_int)
    benchmark_parser.add_argument("--limit", type=positive_int)
    benchmark_parser.add_argument("--trials-per-task", type=positive_int, default=1)
    benchmark_parser.set_defaults(handler=benchmark_command)
    return parser


def run_command(args: argparse.Namespace) -> int:
    tasks = load_jsonl(args.tasks)
    if args.limit is not None:
        tasks = tasks[: args.limit]
    policy = make_policy(args)
    trials = [
        run_task(task, policy, max_steps=args.max_steps)
        for task in tasks
        for _ in range(args.trials_per_task)
    ]
    write_jsonl(args.output, trials)
    status_counts: Dict[str, int] = {}
    for trial in trials:
        status = trial["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    report = {
        "tasks": len(tasks),
        "trials": len(trials),
        "agent": getattr(policy, "name", policy.__class__.__name__),
        "status_counts": status_counts,
        "output": str(Path(args.output)),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def evaluate_command(args: argparse.Namespace) -> int:
    tasks = load_jsonl(args.tasks)
    trials = load_jsonl(args.trials)
    task_by_id = {task.get("id"): task for task in tasks}
    evaluations = []
    for trial in trials:
        task_id = trial.get("task_id")
        if task_id not in task_by_id:
            raise ValueError("trial 引用了不存在的 task_id: {}".format(task_id))
        evaluations.append(evaluate_trial(task_by_id[task_id], trial))
    summary = summarize_evaluations(evaluations)
    write_jsonl(args.details, evaluations)
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def benchmark_command(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    run_args = argparse.Namespace(**vars(args))
    run_args.output = str(output_dir / "trials.jsonl")
    run_command(run_args)

    evaluate_args = argparse.Namespace(
        tasks=args.tasks,
        trials=run_args.output,
        details=str(output_dir / "evaluations.jsonl"),
        summary=str(output_dir / "summary.json"),
    )
    return evaluate_command(evaluate_args)


def make_policy(args: argparse.Namespace) -> Any:
    if args.agent == "oracle":
        return OraclePolicy()
    model = args.model or os.environ.get("ANTHROPIC_MODEL") or os.environ.get("OPENAI_MODEL")
    if not model:
        raise ValueError("--agent openai 时必须提供 --model")
    api_key_env = args.api_key_env
    if api_key_env:
        api_key = os.environ.get(api_key_env)
    else:
        api_key_env = "ANTHROPIC_AUTH_TOKEN" if os.environ.get("ANTHROPIC_AUTH_TOKEN") else "OPENAI_API_KEY"
        api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError("环境变量 {} 未设置".format(api_key_env))
    base_url = args.base_url or os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    if base_url and "://" in base_url and base_url.split("://", 1)[1].rstrip("/").count("/") == 0:
        base_url = base_url.rstrip("/") + "/v1"
    return OpenAICompatiblePolicy(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=args.temperature,
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except Exception as exc:
        print("错误: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
