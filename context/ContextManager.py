import json
import re
import logging
from collections import deque
from typing import List, Dict, Any, Optional
from datetime import datetime


class ContextManager:
    """
    High-performance context manager with sliding window + rolling summary.
    """

    def __init__(
        self,
        window_size: int = 20,
        logger: Optional[logging.Logger] = None,
        runner=None,
        summary_char_limit: int = 5000,
        min_messages_before_summary: int = 3,
        max_context_history: int = 1000,
    ):
        self.window_size = window_size
        self.summary_char_limit = summary_char_limit
        self.runner = runner
        self.logger = logger or logging.getLogger("ContextManager")
        self._min_messages_before_summary = min_messages_before_summary

        # Context with automatic pruning
        self.context: deque[Dict[str, str]] = deque(maxlen=max_context_history)
        self.request_history: deque[Dict[str, Any]] = deque(maxlen=max_context_history)

        # Rolling summary state
        self._rolling_summary: Optional[str] = None
        self._summary_upto_index: int = 2

        # Metrics
        self._summary_metrics = {
            "initial_summaries": 0,
            "update_summaries": 0,
            "total_messages_summarized": 0,
            "truncation_count": 0,
            "frequent_truncation_alerts": 0,
        }
        self._last_truncation_warning: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        self.context.append({"role": role, "content": content})
        self._safe_log("debug", "Added %s message. Context size=%s", role, len(self.context))

    def add_system_message(self, content: str) -> None:
        self.add_message("system", content)

    def add_user_message(self, content: str) -> None:
        self.add_message("user", content)

    def add_assistant_message(self, content: str) -> None:
        self.add_message("assistant", content)

    # ------------------------------------------------------------------
    # Sliding window
    # ------------------------------------------------------------------

    def get_sliding_window_context(
        self,
        state: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        context_len = len(self.context)
        max_len = 2 + self.window_size

        if context_len <= max_len:
            working = list(self.context)
            self._inject_state(working, state)
            return working

        initial = list(self.context)[:2]
        recent = list(self.context)[-self.window_size:]

        summary_end_index = context_len - self.window_size
        new_messages = list(self.context)[self._summary_upto_index:summary_end_index]

        working = initial

        if len(new_messages) >= self._min_messages_before_summary:
            self._update_rolling_summary(new_messages)
            self._summary_upto_index = summary_end_index

        if self._rolling_summary:
            working.append({
                "role": "system",
                "content": "[Conversation memory]\n" + self._rolling_summary,
            })

        working.extend(recent)
        self._inject_state(working, state)
        return working

    # ------------------------------------------------------------------
    # Rolling summary logic
    # ------------------------------------------------------------------

    def _update_rolling_summary(self, new_messages: List[Dict[str, str]]) -> None:
        try:
            if self._rolling_summary:
                summary = self._summarize_update(self._rolling_summary, new_messages)
                self._summary_metrics["update_summaries"] += 1
            else:
                summary = self._summarize_initial(new_messages)
                self._summary_metrics["initial_summaries"] += 1

            self._summary_metrics["total_messages_summarized"] += len(new_messages)

            if len(summary) > self.summary_char_limit:
                summary = summary[-self.summary_char_limit:]
                self._handle_truncation()

            self._rolling_summary = summary
            self._safe_log("debug", "Rolling summary length=%s", len(summary))
        except Exception:
            self._safe_log("exception", "Failed to update rolling summary")

    def _summarize_initial(self, messages: List[Dict[str, str]]) -> str:
        return self._summarize(
            messages,
            system_prompt=(
                "Summarize the conversation into long-term memory.\n"
                "Focus on goals, decisions, constraints, and open issues.\n"
                "Use bullet points."
            ),
        )

    def _summarize_update(
        self,
        existing_summary: str,
        new_messages: List[Dict[str, str]],
    ) -> str:
        return self._summarize(
            new_messages,
            system_prompt=(
                "You are updating an existing conversation memory.\n\n"
                f"Current memory:\n{existing_summary}\n\n"
                "Update it using the new messages:\n"
                "- keep concise\n"
                "- modify outdated facts\n"
                "- add important new info\n"
                "- remove obsolete items\n"
            ),
        )

    # ------------------------------------------------------------------
    # Summarization engine
    # ------------------------------------------------------------------

    def _summarize(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
    ) -> str:
        if self.runner:
            try:
                joined = "\n".join(
                    f"{m['role']}: {m['content'][:800]}" for m in messages
                )
                ai_reply = self.runner._get_ai_reply_with_retry(
                    self.runner.terminal,
                    system_prompt,
                    joined,
                    retries=1,
                )
                if ai_reply:
                    return re.sub(r"```.*?```", "", ai_reply, flags=re.S).strip()
            except Exception:
                self._safe_log("exception", "AI summarization failed")

        # heuristic fallback
        bullets = []
        for m in messages:
            line = m.get("content", "").strip().splitlines()[0]
            if line:
                bullets.append(f"- {line}")
        return "\n".join(bullets[:20])

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _inject_state(
        self,
        working: List[Dict[str, str]],
        state: Optional[Dict[str, Any]],
    ) -> None:
        if not state:
            return
        try:
            content = json.dumps(state, ensure_ascii=False, sort_keys=True)
        except Exception:
            content = str(state)
        working.append({
            "role": "system",
            "content": "[Persistent agent state]\n" + content,
        })

    def _handle_truncation(self) -> None:
        self._summary_metrics["truncation_count"] += 1
        now = datetime.now()
        if (
            self._last_truncation_warning
            and (now - self._last_truncation_warning).total_seconds() < 3600
        ):
            self._summary_metrics["frequent_truncation_alerts"] += 1
            self._safe_log("warning", "Frequent summary truncation detected")
        self._last_truncation_warning = now

    def _safe_log(self, level: str, msg: str, *args) -> None:
        try:
            getattr(self.logger, level)(msg, *args)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Maintenance / metrics
    # ------------------------------------------------------------------

    def cleanup_request_history(self, max_entries: Optional[int] = None) -> None:
        """
        Clean up request history to prevent memory leaks.
        Keeps only the most recent entries.
        """
        if max_entries is not None:
            # Zmień maxlen deque tymczasowo
            old_maxlen = self.request_history.maxlen
            self.request_history = deque(list(self.request_history)[-max_entries:], maxlen=max_entries)
            self._safe_log(
                "debug",
                "Cleaned up request_history; kept %s most recent entries (was maxlen=%s)",
                max_entries, old_maxlen
            )
        else:
            self.request_history.clear()

    def clear_context(self) -> None:
        self.context.clear()
        self._rolling_summary = None
        self._summary_upto_index = 2
        self.reset_summary_metrics()

    def clear_request_history(self) -> None:
        self.request_history.clear()

    def reset_summary_metrics(self) -> None:
        for k in self._summary_metrics:
            self._summary_metrics[k] = 0
        self._last_truncation_warning = None

    def get_summary_metrics(self) -> Dict[str, Any]:
        return {
            **self._summary_metrics,
            "current_summary_length": len(self._rolling_summary) if self._rolling_summary else 0,
        }
