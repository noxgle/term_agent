"""
CriticSubAgent - Answer quality critic for the Vault 3000 AI terminal agent.

When the main agent signals task completion with goal_success=True (tool: finish),
this sub-agent evaluates whether the agent's answer correctly addresses the user's
original prompt, producing a score from 0 to 10.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.console import Console


class CriticSubAgent:
    """
    Sub-agent performing a strict correctness check of the final answer.

    This is triggered only when the agent signals success. It compares
    the original user goal to the agent's finish summary and produces
    a numeric rating (0-10) with a short rationale.
    """
    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    CRITIC_SYSTEM_PROMPT = (
        f"Current date and time: {current_datetime}\n"
        "You are a strict answer critic. Your task is to assess whether the agent's "
        "final answer correctly addresses the user's original prompt.\n\n"
        "Return ONLY a JSON object with the following keys:\n"
        "- rating: integer 0-10 (0 = completely incorrect, 10 = fully correct)\n"
        "- verdict: one of 'Correct', 'Partially', 'Incorrect'\n"
        "- rationale: 1-3 concise sentences\n\n"
        "Be conservative. If the answer is incomplete, unclear, or misses key details, "
        "reduce the score accordingly. Do not include any extra keys."
    )

    def __init__(self, terminal, ai_handler, logger=None):
        """
        Initialize CriticSubAgent.

        Args:
            terminal: Terminal instance for display and configuration
            ai_handler: AICommunicationHandler for AI requests
            logger: Logger instance (optional)
        """
        self.terminal = terminal
        self.ai_handler = ai_handler
        self.logger = logger or self._create_dummy_logger()
        self.console = getattr(terminal, 'console', Console())

    def run(self, user_goal: str, agent_summary: str, agent_results: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Execute the critic sub-agent.

        Args:
            user_goal: Original goal provided by the user
            agent_summary: Summary provided by the agent in the 'finish' tool call
            agent_results: Optional list of actual command results/outputs for context

        Returns:
            dict: Parsed critic result with rating, verdict, and rationale
        """
        self.terminal.print_console(
            "\nVaultAI> Critic Sub-Agent initializing..."
        )
        self.logger.info("CriticSubAgent: Starting critique for goal: %s", user_goal)

        prompt = self._build_critic_prompt(user_goal, agent_summary, agent_results)

        critic_result = self.ai_handler.send_request(
            system_prompt=self.CRITIC_SYSTEM_PROMPT,
            user_prompt=prompt,
            request_format="json"
        )

        parsed = self._parse_critic_result(critic_result, fallback_goal=user_goal)
        self._display_critic_result(parsed, user_goal)

        self.logger.info(
            "CriticSubAgent: Completed with rating=%s verdict=%s",
            parsed.get("rating"),
            parsed.get("verdict")
        )
        return parsed

    def _build_critic_prompt(self, user_goal: str, agent_summary: str, agent_results: Optional[List[Dict[str, Any]]] = None) -> str:
        prompt = (
            "=== USER PROMPT ===\n"
            f"{user_goal}\n\n"
            "=== AGENT ANSWER ===\n"
            f"{agent_summary}\n\n"
        )
        
        # Include actual command results if available for better evaluation
        if agent_results and isinstance(agent_results, list) and len(agent_results) > 0:
            prompt += "=== ACTUAL COMMAND RESULTS ===\n"
            for i, result in enumerate(agent_results[:3], 1):  # Limit to first 3 results
                if isinstance(result, dict):
                    out = result.get("out", "")
                    tool = result.get("tool", "unknown")
                    code = result.get("code", -1)
                    prompt += f"Result {i} (tool={tool}, exit_code={code}):\n{out[:20000]}\n\n"  # Limit output length
            prompt += "Evaluate correctness of the answer relative to the prompt, considering the actual command results.\n"
        else:
            prompt += "Evaluate correctness of the answer relative to the prompt.\n"
        
        return prompt

    def _parse_critic_result(
        self,
        critic_result: Optional[str],
        fallback_goal: str,
    ) -> Dict[str, Any]:
        """
        Parse the critic JSON response, with a robust fallback.
        """
        if not critic_result:
            self.logger.warning("CriticSubAgent: AI returned no result")
            return {
                "rating": 0,
                "verdict": "Incorrect",
                "rationale": "Critic sub-agent returned no response.",
            }

        try:
            data = json.loads(critic_result)
            rating = data.get("rating")
            verdict = data.get("verdict")
            rationale = data.get("rationale")

            if not isinstance(rating, int) or not (0 <= rating <= 10):
                raise ValueError("Invalid rating")
            if verdict not in {"Correct", "Partially", "Incorrect"}:
                raise ValueError("Invalid verdict")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError("Invalid rationale")

            return {
                "rating": rating,
                "verdict": verdict,
                "rationale": rationale.strip(),
            }
        except Exception as e:
            self.logger.warning("CriticSubAgent: Failed to parse JSON: %s", e)

        # Fallback: extract a rating from text if possible
        match = re.search(r"(\b10\b|\b[0-9]\b)", critic_result)
        rating = int(match.group(1)) if match else 0
        rating = max(0, min(10, rating))

        return {
            "rating": rating,
            "verdict": "Partially" if 3 <= rating <= 7 else "Incorrect",
            "rationale": "Critic response was malformed; used fallback parsing.",
        }

    def _display_critic_result(self, result: Dict[str, Any], user_goal: str):
        rating = result.get("rating", 0)
        verdict = result.get("verdict", "Incorrect")
        rationale = result.get("rationale", "")

        # Minimalist output
        self.terminal.print_console(
            f"Critic: {rating}/10 — {verdict}. {rationale}"
        )

    def _create_dummy_logger(self):
        """Fallback logger if none provided."""
        class DummyLogger:
            def log(self, *args, **kwargs):
                pass
            def debug(self, *args, **kwargs):
                pass
            def info(self, *args, **kwargs):
                pass
            def warning(self, *args, **kwargs):
                pass
            def error(self, *args, **kwargs):
                pass
            def exception(self, *args, **kwargs):
                pass
        return DummyLogger()
