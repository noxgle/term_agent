import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from api.api_agent import ApiRunParams, run_agent_via_api, get_api_key_env

app = FastAPI(title="Vault 3000 API Agent", version="1.0")

_MAX_WORKERS = int(os.getenv("API_MAX_WORKERS", "4"))
_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS)
_jobs_lock = Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


class RunRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    system_prompt_agent: Optional[str] = None
    user: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    window_size: int = Field(20, ge=5, le=200)
    max_steps: Optional[int] = Field(None, ge=1, le=500)
    ssh_password: Optional[str] = None


class RunResponse(BaseModel):
    summary: str
    goal_success: Optional[bool] = None
    steps: list
    timings: dict
    token_usage: Optional[dict] = None
    critic_rating: Optional[int] = None
    critic_verdict: Optional[str] = None
    critic_rationale: Optional[str] = None


class BatchRunRequest(BaseModel):
    requests: List[RunRequest] = Field(..., min_items=1, max_items=20)


class SubmitResponse(BaseModel):
    job_id: str


class BatchSubmitResponse(BaseModel):
    job_ids: List[str]


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[RunResponse] = None
    error: Optional[str] = None
    submitted_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None


def _verify_api_key(x_api_key: Optional[str]) -> None:
    expected = get_api_key_env()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


def _build_params(payload: RunRequest) -> ApiRunParams:
    return ApiRunParams(
        goal=payload.goal,
        system_prompt_agent=payload.system_prompt_agent,
        user=payload.user,
        host=payload.host,
        port=payload.port,
        window_size=payload.window_size,
        max_steps=payload.max_steps,
        ssh_password=payload.ssh_password,
    )


def _run_job(job_id: str, params: ApiRunParams) -> None:
    with _jobs_lock:
        if _jobs[job_id]["status"] == "canceled":
            _jobs[job_id]["finished_at"] = time.time()
            return
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["started_at"] = time.time()

    try:
        result = run_agent_via_api(params)
        with _jobs_lock:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["result"] = result
            _jobs[job_id]["goal_success"] = result.get("goal_success", None)
            _jobs[job_id]["finished_at"] = time.time()
    except ValueError as exc:
        with _jobs_lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(exc)
            _jobs[job_id]["goal_success"] = False
            _jobs[job_id]["finished_at"] = time.time()
    except Exception as exc:
        with _jobs_lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = f"Agent error: {exc}"
            _jobs[job_id]["goal_success"] = False
            _jobs[job_id]["finished_at"] = time.time()


@app.post("/run", response_model=RunResponse)
def run_agent(payload: RunRequest, x_api_key: Optional[str] = Header(None)):
    _verify_api_key(x_api_key)

    params = _build_params(payload)

    try:
        result = run_agent_via_api(params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    return RunResponse(**result)


@app.post("/run_async", response_model=SubmitResponse)
def run_agent_async(payload: RunRequest, x_api_key: Optional[str] = Header(None)):
    _verify_api_key(x_api_key)

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "queued",
            "submitted_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "goal_success": None,
            "future": None,
        }

    params = _build_params(payload)
    future = _executor.submit(_run_job, job_id, params)
    with _jobs_lock:
        _jobs[job_id]["future"] = future
    return SubmitResponse(job_id=job_id)


@app.post("/runs", response_model=BatchSubmitResponse)
def run_agent_batch(payload: BatchRunRequest, x_api_key: Optional[str] = Header(None)):
    _verify_api_key(x_api_key)

    job_ids: List[str] = []
    for request in payload.requests:
        job_id = str(uuid.uuid4())
        with _jobs_lock:
            _jobs[job_id] = {
                "status": "queued",
                "submitted_at": time.time(),
                "started_at": None,
                "finished_at": None,
            "result": None,
            "error": None,
            "goal_success": None,
            "future": None,
        }
        params = _build_params(request)
        future = _executor.submit(_run_job, job_id, params)
        with _jobs_lock:
            _jobs[job_id]["future"] = future
        job_ids.append(job_id)

    return BatchSubmitResponse(job_ids=job_ids)


@app.get("/runs/{job_id}", response_model=JobStatusResponse)
def get_run_status(job_id: str, x_api_key: Optional[str] = Header(None)):
    _verify_api_key(x_api_key)

    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = job["result"]
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        result=RunResponse(**result) if result else None,
        error=job["error"],
        submitted_at=job["submitted_at"],
        started_at=job["started_at"],
        finished_at=job["finished_at"],
    )


@app.delete("/runs/{job_id}", response_model=JobStatusResponse)
def cancel_run(job_id: str, x_api_key: Optional[str] = Header(None)):
    _verify_api_key(x_api_key)

    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job["status"] in {"completed", "failed", "canceled"}:
            result = job["result"]
            return JobStatusResponse(
                job_id=job_id,
                status=job["status"],
                result=RunResponse(**result) if result else None,
                error=job["error"],
                submitted_at=job["submitted_at"],
                started_at=job["started_at"],
                finished_at=job["finished_at"],
            )

        future = job.get("future")
        if future and future.cancel():
            job["status"] = "canceled"
            job["goal_success"] = False
            job["finished_at"] = time.time()
        elif job["status"] == "queued":
            job["status"] = "canceled"
            job["goal_success"] = False
            job["finished_at"] = time.time()
        else:
            job["error"] = "Job already running; cannot cancel"

        result = job["result"]

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        result=RunResponse(**result) if result else None,
        error=job["error"],
        submitted_at=job["submitted_at"],
        started_at=job["started_at"],
        finished_at=job["finished_at"],
    )
