from pathlib import Path

import uvicorn

from scripts.agent_eval.web.app import create_app


def serve(data_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    uvicorn.run(create_app(data_dir), host=host, port=port)
