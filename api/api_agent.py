import os
from dataclasses import dataclass
from typing import Optional, Dict, Any

from term_ag import term_agent
from VaultAiAgentRunner import VaultAIAgentRunner
from ai.PromptFilter import compress_prompt, estimate_token_savings


class VaultAIApiAgentRunner(VaultAIAgentRunner):
    """
    Non-interactive runner for API usage.
    Forces any prompt to return a safe default ("n").
    """

    def _get_user_input(self, prompt_text: str, multiline: bool = False) -> str:
        return "n"


@dataclass
class ApiRunParams:
    goal: str
    system_prompt_agent: Optional[str] = None
    user: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    window_size: int = 20
    max_steps: Optional[int] = None
    ssh_password: Optional[str] = None
    compact_mode: Optional[bool] = None
    force_plan: Optional[bool] = None
    pipeline_mode: Optional[str] = None


def _build_terminal(params: ApiRunParams) -> term_agent:
    terminal = term_agent()
    terminal.auto_accept = True
    terminal.interactive_mode = False
    terminal.auto_explain_command = False

    if params.host:
        if not params.ssh_password:
            raise ValueError("ssh_password is required for remote host connections")
        terminal.ssh_connection = True
        terminal.user = params.user
        terminal.host = params.host
        terminal.port = params.port
        terminal.ssh_password = params.ssh_password
        terminal.remote_linux_distro = terminal.detect_remote_linux_distribution(
            params.host, user=params.user
        )
    else:
        terminal.ssh_connection = False

    return terminal


def run_agent_via_api(params: ApiRunParams) -> Dict[str, Any]:
    terminal = _build_terminal(params)

    compact_mode = params.compact_mode
    hybrid_mode = None
    if params.pipeline_mode:
        mode = params.pipeline_mode.strip().lower()
        if mode == "compact":
            compact_mode = True
            hybrid_mode = False
        elif mode == "legacy":
            compact_mode = False
            hybrid_mode = False
        elif mode == "hybrid":
            compact_mode = True
            hybrid_mode = True

    filtered_goal = compress_prompt(params.goal)

    runner = VaultAIApiAgentRunner(
        terminal=terminal,
        user_goal=filtered_goal,
        system_prompt_agent=params.system_prompt_agent,
        user=params.user,
        host=params.host,
        window_size=params.window_size,
        max_steps=params.max_steps,
        compact_mode=compact_mode,
        hybrid_mode=hybrid_mode,
    )

    if params.force_plan:
        runner.force_plan = True

    runner.run()

    critic_enabled = getattr(runner, "enable_critic_sub_agent", False)
    critic_available = runner.goal_success and critic_enabled

    return {
        "summary": runner.summary,
        "goal_success": runner.goal_success,
        "steps": runner.steps,
        "timings": runner.timings,
        "token_usage": getattr(runner.ai_handler, "token_usage", None),
        "critic_rating": runner.critic_rating if critic_available else None,
        "critic_verdict": runner.critic_verdict if critic_available else None,
        "critic_rationale": runner.critic_rationale if critic_available else None,
    }


def get_api_key_env() -> Optional[str]:
    return os.getenv("API_SERVER_KEY")
