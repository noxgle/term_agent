---
name: vault_agent
description: High-signal repo instructions for Vault 3000 contributors
---

# AGENTS.md

## What matters most
- `term_ag.py` is the real CLI entrypoint (local + SSH mode).
- `VaultAiAgentRunner.py` is the core execution pipeline (compact/normal/hybrid behavior).
- `api/api_server.py` + `api/api_agent.py` are the HTTP path; API runs non-interactively (`auto_accept=True`, prompt replies forced to `"n"`).
- `term_api.py` only starts uvicorn using `API_HOST`/`API_PORT`.

## Verified run commands
- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Agent CLI: `python term_ag.py`
- Remote mode: `python term_ag.py user@host`
- Prompt-creator mode: `python term_ag.py --prompt` (also separate `python PromptCreator.py` exists)
- Pipeline overrides: `python term_ag.py --compact|--normal|--hybrid`
- Force plan from CLI: `python term_ag.py --plan`
- API server: `python term_api.py`
- Docker dev path: `docker-compose up -d` (SSH on host `:2222`, API on `${API_PORT:-8000}`)

## Behavior and config quirks (easy to miss)
- `.env` must exist in repo root; `term_ag.py` exits immediately if missing.
- `AI_ENGINE` supports comma-separated engines; routing is controlled by `AI_ENGINE_ROUTE` (`round-robin` or `fallback`).
- Default CLI runtime mode is effectively **hybrid** unless `--compact`/`--normal` overrides are passed.
- `Ctrl+A` in CLI switches from collaborative to automatic mode one-way for current session.
- `LOG_FILE` in `.env` is written under `./logs/` unless an absolute/explicit path is provided.
- API defaults to `pipeline_mode="hybrid"` when neither `pipeline_mode` nor `compact_mode` is supplied.
- API remote runs require `ssh_password` in payload (`api/api_agent.py` enforces this).

## Test reality (current repo state)
- No pytest/ruff/mypy config files are present in root.
- `requirements.txt` does **not** include `pytest` or `pytest-asyncio`, even though tests import them.
- Current `tests/test_mcp_*` reference an `mcp` package path not present in this repository; run tests selectively and expect MCP tests to fail until that module is restored.

## Change safety boundaries for agents
- Ask before editing `.env`, AI engine defaults, SSH auth flow, or core runner flow in `term_ag.py` / `VaultAiAgentRunner.py`.
- Do not commit secrets from `.env`.
- Preserve Fallout-themed user-facing console style when touching interactive output.
