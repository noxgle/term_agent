from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from api.api_agent import ApiRunParams, run_agent_via_api, get_api_key_env

app = FastAPI(title="Vault 3000 API Agent", version="1.0")


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
    steps: list
    timings: dict
    token_usage: Optional[dict] = None


def _verify_api_key(x_api_key: Optional[str]) -> None:
    expected = get_api_key_env()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


@app.post("/run", response_model=RunResponse)
def run_agent(payload: RunRequest, x_api_key: Optional[str] = Header(None)):
    _verify_api_key(x_api_key)

    params = ApiRunParams(
        goal=payload.goal,
        system_prompt_agent=payload.system_prompt_agent,
        user=payload.user,
        host=payload.host,
        port=payload.port,
        window_size=payload.window_size,
        max_steps=payload.max_steps,
        ssh_password=payload.ssh_password,
    )

    try:
        result = run_agent_via_api(params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    return RunResponse(**result)
