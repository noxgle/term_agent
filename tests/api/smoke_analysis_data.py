#!/usr/bin/env python3
"""
API smoke test for analysis_data tool handling.

This script validates:
1) analysis_data executes successfully (number output),
2) invalid analysis_data arguments are handled safely,
3) analyze_data alias is mapped to analysis_data.
"""

import argparse
import json
import os
import time
from typing import Dict, Optional

import requests


def _headers(api_key: Optional[str]) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _wait_for_health(base_url: str, api_key: Optional[str], timeout_s: int = 60) -> None:
    started = time.time()
    url = f"{base_url.rstrip('/')}/health"
    while time.time() - started < timeout_s:
        try:
            resp = requests.get(url, headers=_headers(api_key), timeout=5)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"API health check did not pass within {timeout_s}s: {url}")


def _run_case(
    base_url: str,
    api_key: Optional[str],
    goal: str,
    system_prompt: str,
    expected_summary: str,
    expected_timing_key: Optional[str] = None,
    timeout_s: int = 240,
) -> Dict:
    url = f"{base_url.rstrip('/')}/run"
    payload = {
        "goal": goal,
        "pipeline_mode": "normal",
        "max_steps": 6,
        "system_prompt_agent": system_prompt,
    }
    resp = requests.post(
        url,
        headers=_headers(api_key),
        data=json.dumps(payload),
        timeout=timeout_s,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"/run returned HTTP {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    summary = data.get("summary")
    if summary != expected_summary:
        raise RuntimeError(
            f"Unexpected summary. Expected '{expected_summary}', got '{summary}'. "
            f"Body: {json.dumps(data, ensure_ascii=False)[:1000]}"
        )

    if expected_timing_key:
        timings = data.get("timings", {})
        if expected_timing_key not in timings:
            raise RuntimeError(
                f"Expected timing key '{expected_timing_key}' not found. "
                f"Available: {list(timings.keys())}"
            )

    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test analysis_data via API")
    parser.add_argument("--base-url", default=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.getenv("API_SERVER_KEY", ""))
    parser.add_argument("--health-timeout", type=int, default=60)
    args = parser.parse_args()

    print("[smoke] waiting for API health...")
    _wait_for_health(args.base_url, args.api_key, timeout_s=args.health_timeout)
    print("[smoke] health OK")

    case1_prompt = (
        "You are a deterministic integration-test agent. Return only JSON. "
        "If context does NOT contain phrase analysis_data completed successfully, "
        "return exactly one action: "
        "{\"tool\":\"analysis_data\",\"arguments\":{\"type\":\"calculate\","
        "\"input\":\"numbers: 2, 3, 5\",\"instructions\":\"Compute sum and return number only\","
        "\"context\":\"smoke test\",\"output_format\":\"number\","
        "\"constraints\":{\"max_tokens\":60,\"precision\":\"high\"}},"
        "\"explain\":\"smoke success path\"}. "
        "If context contains analysis_data completed successfully, return exactly: "
        "{\"tool\":\"finish\",\"summary\":\"smoke-analysis-success\",\"goal_success\":false}."
    )
    print("[smoke] case 1: analysis_data success path")
    _run_case(
        base_url=args.base_url,
        api_key=args.api_key,
        goal="Smoke test analysis_data success path.",
        system_prompt=case1_prompt,
        expected_summary="smoke-analysis-success",
        expected_timing_key="ANALYSIS_DATA_CALCULATE",
    )
    print("[smoke] case 1 OK")

    case2_prompt = (
        "Return only JSON. "
        "If context contains phrase invalid 'analysis_data' action, return exactly: "
        "{\"tool\":\"finish\",\"summary\":\"smoke-analysis-invalid\",\"goal_success\":false}. "
        "Otherwise return exactly: "
        "{\"tool\":\"analysis_data\",\"arguments\":{\"type\":\"calculate\","
        "\"instructions\":\"sum numbers\",\"output_format\":\"number\","
        "\"constraints\":{\"max_tokens\":50,\"precision\":\"high\"}},"
        "\"explain\":\"missing input validation\"}."
    )
    print("[smoke] case 2: invalid arguments validation")
    _run_case(
        base_url=args.base_url,
        api_key=args.api_key,
        goal="Smoke test analysis_data validation path.",
        system_prompt=case2_prompt,
        expected_summary="smoke-analysis-invalid",
    )
    print("[smoke] case 2 OK")

    case3_prompt = (
        "Return only JSON. "
        "If context contains analysis_data completed successfully, return exactly: "
        "{\"tool\":\"finish\",\"summary\":\"smoke-analysis-alias\",\"goal_success\":false}. "
        "Otherwise return exactly: "
        "{\"tool\":\"analyze_data\",\"arguments\":{\"type\":\"calculate\","
        "\"input\":\"numbers: 4, 6\",\"instructions\":\"sum and return number only\","
        "\"context\":\"alias smoke\",\"output_format\":\"number\","
        "\"constraints\":{\"max_tokens\":60,\"precision\":\"high\"}},"
        "\"explain\":\"alias test\"}."
    )
    print("[smoke] case 3: analyze_data alias")
    _run_case(
        base_url=args.base_url,
        api_key=args.api_key,
        goal="Smoke test analyze_data alias path.",
        system_prompt=case3_prompt,
        expected_summary="smoke-analysis-alias",
        expected_timing_key="ANALYSIS_DATA_CALCULATE",
    )
    print("[smoke] case 3 OK")

    print("[smoke] all checks passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[smoke] FAILED: {exc}")
        raise
