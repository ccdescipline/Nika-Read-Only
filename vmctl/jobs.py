from __future__ import annotations

import threading
import time
import traceback
import uuid
from typing import Callable

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def get(job_id: str) -> dict | None:
    with _lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


def list_jobs() -> list[dict]:
    with _lock:
        return [dict(j) for j in _jobs.values()]


def submit(kind: str, fn: Callable, **kwargs) -> str:
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "kind": kind,
        "status": "running",
        "log": [],
        "error": "",
        "result": None,
        "started": time.time(),
        "finished": None,
    }
    with _lock:
        _jobs[job_id] = job

    def progress(msg: str) -> None:
        with _lock:
            job["log"].append(msg)

    def run() -> None:
        try:
            result = fn(progress=progress, **kwargs)
            with _lock:
                job["status"] = "ok"
                job["result"] = result
        except Exception as e:
            with _lock:
                job["status"] = "error"
                job["error"] = str(e)
                job["log"].append(traceback.format_exc())
        finally:
            with _lock:
                job["finished"] = time.time()

    threading.Thread(target=run, daemon=True).start()
    return job_id
