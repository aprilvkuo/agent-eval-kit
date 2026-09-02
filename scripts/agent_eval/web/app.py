import json
import os
from pathlib import Path
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from scripts.agent_eval.web.service import EvaluationService, RunConfig
from scripts.agent_eval.web.store import DashboardStore


MAX_DATASET_BYTES = 10 * 1024 * 1024


class RunRequest(BaseModel):
    dataset_id: str
    agent: str = "oracle"
    model: Optional[str] = None
    base_url: Optional[str] = None
    trials_per_task: int = Field(default=1, ge=1)
    temperature: float = 0.0
    max_steps: Optional[int] = Field(default=None, ge=1)


def create_app(data_dir: Path) -> FastAPI:
    workspace = Path(data_dir)
    store = DashboardStore(workspace / "dashboard.db")
    service = EvaluationService(store)
    app = FastAPI(title="Agent Eval Kit", version="0.2.0")
    app.state.store = store
    app.state.service = service
    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/api/config")
    def get_config():
        return {
            "model": os.environ.get("ANTHROPIC_MODEL") or os.environ.get("OPENAI_MODEL"),
            "base_url": os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get("OPENAI_BASE_URL"),
            "auth_configured": bool(
                os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("OPENAI_API_KEY")
            ),
        }

    @app.get("/api/datasets")
    def list_datasets():
        return store.list_datasets()

    @app.post("/api/datasets", status_code=status.HTTP_201_CREATED)
    async def import_dataset(
        name: str = Form(...),
        file: UploadFile = File(...),
    ):
        filename = file.filename or "dataset.jsonl"
        if not filename.lower().endswith(".jsonl"):
            raise HTTPException(status_code=400, detail="仅支持 .jsonl 测试集")
        raw = await file.read(MAX_DATASET_BYTES + 1)
        if len(raw) > MAX_DATASET_BYTES:
            raise HTTPException(status_code=413, detail="测试集文件不能超过 10 MB")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="测试集必须使用 UTF-8 编码") from exc
        try:
            tasks = _parse_jsonl(text)
            return store.import_dataset(name, filename, tasks)
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/datasets/{dataset_id}/tasks")
    def list_tasks(dataset_id: str):
        _require_dataset(store, dataset_id)
        return store.list_tasks(dataset_id)

    @app.delete("/api/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_dataset(dataset_id: str):
        if not store.delete_dataset(dataset_id):
            raise HTTPException(status_code=404, detail="测试集不存在")

    @app.get("/api/runs")
    def list_runs(dataset_id: Optional[str] = None):
        if dataset_id is not None:
            _require_dataset(store, dataset_id)
        return store.list_runs(dataset_id)

    @app.post("/api/runs", status_code=status.HTTP_202_ACCEPTED)
    def create_run(request: RunRequest, background_tasks: BackgroundTasks):
        try:
            run_id = service.create_run(RunConfig(**request.model_dump()))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        background_tasks.add_task(service.execute_run, run_id)
        return store.get_run(run_id)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        return run

    @app.get("/api/runs/{run_id}/trials")
    def list_trials(run_id: str):
        if store.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        return store.list_trials(run_id)

    @app.get("/api/trials/{trial_id}")
    def get_trial(trial_id: str):
        trial = store.get_trial(trial_id)
        if trial is None:
            raise HTTPException(status_code=404, detail="Trial 不存在")
        return trial

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(static_dir / "index.html")

    return app


def _parse_jsonl(text: str) -> List[dict]:
    tasks: List[dict] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("第 {} 行不是有效 JSON: {}".format(line_number, exc.msg)) from exc
        if not isinstance(task, dict):
            raise ValueError("第 {} 行必须是 JSON object".format(line_number))
        tasks.append(task)
    return tasks


def _require_dataset(store: DashboardStore, dataset_id: str) -> None:
    if store.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="测试集不存在")
