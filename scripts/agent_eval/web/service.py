import argparse
from dataclasses import dataclass
from typing import Optional

from scripts.agent_eval.cli import make_policy
from scripts.agent_eval.evaluator import evaluate_trial, summarize_evaluations
from scripts.agent_eval.runner import run_task
from scripts.agent_eval.web.store import DashboardStore


@dataclass(frozen=True)
class RunConfig:
    dataset_id: str
    agent: str = "oracle"
    model: Optional[str] = None
    base_url: Optional[str] = None
    trials_per_task: int = 1
    temperature: float = 0.0
    max_steps: Optional[int] = None

    def validate(self) -> None:
        if self.agent not in {"oracle", "openai"}:
            raise ValueError("agent 只能是 oracle 或 openai")
        if self.trials_per_task < 1:
            raise ValueError("trials_per_task 必须大于等于 1")
        if self.max_steps is not None and self.max_steps < 1:
            raise ValueError("max_steps 必须大于等于 1")


class EvaluationService:
    def __init__(self, store: DashboardStore):
        self.store = store

    def create_run(self, config: RunConfig) -> str:
        config.validate()
        run = self.store.create_run(
            dataset_id=config.dataset_id,
            agent=config.agent,
            model=config.model,
            base_url=config.base_url,
            trials_per_task=config.trials_per_task,
            temperature=config.temperature,
            max_steps=config.max_steps,
        )
        return run["id"]

    def execute_run(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError("运行不存在: {}".format(run_id))
        self.store.mark_run_running(run_id)
        try:
            policy = make_policy(
                argparse.Namespace(
                    agent=run["agent"],
                    model=run["model"],
                    base_url=run["base_url"],
                    api_key_env=None,
                    temperature=run["temperature"],
                )
            )
            tasks = self.store.list_tasks(run["dataset_id"])
            evaluations = []
            position = 0
            for task in tasks:
                for _ in range(run["trials_per_task"]):
                    trial = run_task(task, policy, max_steps=run["max_steps"])
                    evaluation = evaluate_trial(task, trial)
                    self.store.save_trial(run_id, trial, evaluation, position)
                    evaluations.append(evaluation)
                    position += 1
            self.store.finish_run(run_id, summarize_evaluations(evaluations))
        except Exception as exc:
            self.store.fail_run(run_id, "{}: {}".format(type(exc).__name__, exc))
