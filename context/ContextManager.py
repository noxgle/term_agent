import json
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

class ContextManager:
    """
    Manages conversation context and sliding window functionality for AI agents.

    This class handles:
    - Maintaining conversation history with sliding window
    - Summarizing older messages to keep context size manageable
    - Tracking request history for debugging and tracing
    - Providing context windows for AI model input
    """

    def __init__(self, window_size: int = 20, logger: Optional[logging.Logger] = None, runner=None, summary_char_limit: int = 5000):
        """
        Initialize the ContextManager.

        Args:
            window_size: Number of recent messages to keep in the sliding window
            logger: Optional logger for debugging and tracing
            runner: Reference to the agent runner for AI operations
            summary_char_limit: Maximum characters for rolling summary
        """
        self.window_size = window_size
        self._rolling_summary: Optional[str] = None
        self._summary_upto_index: int = 2
        self._window_size: int = window_size
        self._summary_char_limit: int = summary_char_limit
        self._summary_metrics: Dict[str, int] = {
            "initial_summaries": 0,
            "update_summaries": 0,
            "total_messages_summarized": 0,
            "truncation_count": 0,
            "frequent_truncation_alerts": 0
        }
        self._last_truncation_warning: Optional[datetime] = None
        self.context: List[Dict[str, str]] = []
        self.request_history: List[Dict[str, Any]] = []
        self.logger = logger or logging.getLogger("ContextManager")
        self.runner = runner

        # Initialize with empty context
        self._initialize_context()

    def _initialize_context(self):
        """Initialize the context with basic structure."""
        self.context = []
        self._rolling_summary = None
        self._summary_upto_index = 2
        self._summary_metrics = {
            "initial_summaries": 0,
            "update_summaries": 0,
            "total_messages_summarized": 0,
            "truncation_count": 0,
            "frequent_truncation_alerts": 0
        }
        self._last_truncation_warning = None

    def add_message(self, role: str, content: str):
        """
        Add a message to the conversation context.

        Args:
            role: Message role (e.g., 'system', 'user', 'assistant')
            content: Message content
        """
        self.context.append({"role": role, "content": content})
        # Clear rolling summary cache when new messages are added
        self._clear_rolling_summary()
        try:
            self.logger.debug("Added message to context. Current context length: %s", len(self.context))
        except Exception:
            pass

    def add_system_message(self, content: str):
        """Add a system message to the context."""
        self.add_message("system", content)

    def add_user_message(self, content: str):
        """Add a user message to the context."""
        self.add_message("user", content)

    def add_assistant_message(self, content: str):
        """Add an assistant message to the context."""
        self.add_message("assistant", content)

    def _inject_state(self, working: List[Dict[str, str]], state: Optional[Dict[str, Any]]) -> None:
        if not state:
            return

        try:
            state_repr = json.dumps(
                state,
                ensure_ascii=False,
                sort_keys=True,
            )
            content = "[Persistent agent state]\n" + state_repr
        except Exception:
            self._safe_log("exception", "Failed to serialize agent state.")
            content = "[Persistent agent state]\n" + str(state)

        working.append({
            "role": "system",
            "content": content,
        })

    def get_sliding_window_context(self, state: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
        """
        High-performance sliding window context with rolling summary + cache.

        Behavior:
        - Always keep the first two messages (system + user goal).
        - Use rolling summary cache for intermediate messages.
        - Keep the last `self._window_size` messages verbatim.
        - Inject the current persistent state as a final system message if provided.

        Returns:
            list: messages to pass to the model.
        """
        context_len = len(self.context)
        max_len = 2 + self._window_size

        # Fast path for small contexts
        if context_len <= max_len:
            working = list(self.context)
            self._inject_state(working, state)
            return working

        initial = self.context[:2]
        recent = self.context[-self._window_size:]

        # Calculate summary range
        summary_end_index = context_len - self._window_size
        new_messages = self.context[self._summary_upto_index:summary_end_index]

        working: List[Dict[str, str]] = list(initial)

        # Update rolling summary if there are new messages
        if new_messages:
            self._update_rolling_summary(new_messages)
            self._summary_upto_index = summary_end_index

        # Add summary if available
        if self._rolling_summary:
            working.append({
                "role": "assistant",
                "content": "[Conversation memory]\n" + self._rolling_summary
            })

        # Add recent messages
        working.extend(recent)

        # Add state
        self._inject_state(working, state)

        return working

    def _summarize(self, messages: List[Dict[str, str]]) -> str:
        """
        Produce a concise summary for a list of messages using AI with heuristic fallback.
        """
        # First attempt AI-powered summary if runner is available
        if self.runner:
            try:
                # Build compact message representation
                joined = [f"{m.get('role','')}: {m.get('content','')[:800]}" for m in messages]
                prompt_text = "\n".join(joined)

                summarizer_system = (
                    "You are a concise summarizer. Create a short summary containing:\n"
                    "- Completed actions and their results\n"
                    "- Key decisions or outcomes\n"
                    "- Pending/open tasks\n"
                    "Format the output as bullet points."
                )

                ai_reply = self.runner._get_ai_reply_with_retry(
                    self.runner.terminal, 
                    summarizer_system, 
                    prompt_text, 
                    retries=1
                )
                if ai_reply:
                    # Clean any code fences from response
                    return re.sub(r'```\w*', '', ai_reply).replace('```', '').strip()
            except Exception:
                self.logger.exception("AI summarization failed, using heuristic fallback")
                
        # Fallback heuristic summarization
        completed = []
        decisions = []
        pending = []

        for m in messages:
            text = m.get("content", "").strip()
            lower = text.lower()
            if any(k in lower for k in ("done", "completed", "finished", "succeeded", "created")):
                completed.append(text.splitlines()[0])
            elif any(k in lower for k in ("decide", "decision", "choose", "will", "should")):
                decisions.append(text.splitlines()[0])
            elif any(k in lower for k in ("todo", "pending", "next", "remaining", "open")):
                pending.append(text.splitlines()[0])

        parts = ["Completed:"] + [f"- {c}" for c in completed or ["(none detected)"]]
        parts += ["\nDecisions:"] + [f"- {d}" for d in decisions or ["(none detected)"]]
        parts += ["\nPending:"] + [f"- {p}" for p in pending or ["(none detected)"]]
        return "\n".join(parts)

    def _safe_log(self, level: str, message: str, *args) -> None:
        """
        Safe logging that doesn't raise exceptions.
        """
        try:
            if level == "debug":
                self.logger.debug(message, *args)
            elif level == "exception":
                self.logger.exception(message, *args)
            elif level == "info":
                self.logger.info(message, *args)
            elif level == "warning":
                self.logger.warning(message, *args)
        except Exception:
            pass

    def _summarize_initial(self, messages: List[Dict[str, str]]) -> str:
        """
        Create initial structured summary with performance tracking.
        """
        self._safe_log("debug", "Creating initial summary for %s messages", len(messages))
        
        summary = self._summarize(
            messages,
            prompt=(
                "Summarize the conversation so far into a compact memory.\n"
                "Focus on:\n"
                "- user goals\n"
                "- decisions made\n"
                "- constraints\n"
                "- unresolved questions\n"
                "Use bullet points."
            ),
        )
        
        self._summary_metrics["initial_summaries"] += 1
        self._summary_metrics["total_messages_summarized"] += len(messages)
        
        self._safe_log("info", "Created initial summary with %s characters", len(summary))
        
        return summary

    def _summarize_update(
        self,
        existing_summary: str,
        new_messages: List[Dict[str, str]],
    ) -> str:
        """
        Update existing summary with new messages only with performance tracking.
        """
        self._safe_log("debug", "Updating summary with %s new messages", len(new_messages))
        self._safe_log("debug", "Current summary length: %s characters", len(existing_summary))
        
        summary = self._summarize(
            new_messages,
            prompt=(
                "You are updating an existing conversation memory.\n\n"
                "Current memory:\n"
                f"{existing_summary}\n\n"
                "New messages:\n"
                "{{messages}}\n\n"
                "Update the memory:\n"
                "- keep it concise\n"
                "- modify existing points if needed\n"
                "- add new important facts\n"
                "- remove obsolete information\n"
            ),
        )
        
        self._summary_metrics["update_summaries"] += 1
        self._summary_metrics["total_messages_summarized"] += len(new_messages)
        
        self._safe_log("info", "Updated summary to %s characters", len(summary))
        
        return summary

    def _update_rolling_summary(
        self,
        new_messages: List[Dict[str, str]],
    ) -> None:
        """
        Update rolling summary incrementally instead of regenerating it.
        """
        try:
            self._safe_log(
                "debug",
                "Updating rolling summary with %s new messages.",
                len(new_messages),
            )

            if self._rolling_summary:
                summary = self._summarize_update(
                    existing_summary=self._rolling_summary,
                    new_messages=new_messages,
                )
            else:
                summary = self._summarize_initial(new_messages)

            # Hard cap on summary length
            if len(summary) > self._summary_char_limit:
                summary = summary[-self._summary_char_limit:]
                self._summary_metrics["truncation_count"] += 1
                
                # Check for frequent truncation
                now = datetime.now()
                if self._last_truncation_warning:
                    time_since_last = now - self._last_truncation_warning
                    if time_since_last.total_seconds() < 3600:  # Within 1 hour
                        self._summary_metrics["frequent_truncation_alerts"] += 1
                        self._safe_log(
                            "warning",
                            "Frequent summary truncation detected! %s truncations in the last hour.",
                            self._summary_metrics["frequent_truncation_alerts"]
                        )
                
                self._last_truncation_warning = now
                self._safe_log(
                    "warning",
                    "Summary exceeded character limit. Truncated to %s characters.",
                    self._summary_char_limit
                )

            self._rolling_summary = summary

            self._safe_log(
                "info",
                "Rolling summary update completed. Current length: %s characters",
                len(summary)
            )

        except Exception:
            self._safe_log(
                "exception",
                "Failed to update rolling summary."
            )
            # Don't destroy old memory if update fails

    def _clear_rolling_summary(self) -> None:
        """
        Clear the rolling summary cache.
        """
        self._rolling_summary = None
        self._summary_upto_index = 2
        try:
            self.logger.debug("Cleared rolling summary cache")
        except Exception:
            pass

    def record_request(self, request_id: str, step: int, assistant_json: str):
        """
        Record an assistant request in the request history.

        Args:
            request_id: Unique identifier for the request
            step: Step number in the conversation
            assistant_json: JSON string of the assistant's response
        """
        self.request_history.append({
            "request_id": request_id,
            "step": step,
            "assistant_json": assistant_json
        })
        try:
            self.logger.debug("Recorded assistant response in request_history; request_id=%s", request_id)
        except Exception:
            pass

    def cleanup_request_history(self, max_entries: int = 1000):
        """
        Clean up request history to prevent memory leaks.
        Keep only the most recent entries.

        Args:
            max_entries: Maximum number of entries to keep
        """
        if len(self.request_history) > max_entries:
            # Keep only the most recent entries
            self.request_history = self.request_history[-max_entries:]
            try:
                self.logger.debug("Cleaned up request_history; kept %s most recent entries", max_entries)
            except Exception:
                pass

    def get_context_length(self) -> int:
        """Get the current length of the conversation context."""
        return len(self.context)

    def get_request_history_length(self) -> int:
        """Get the current length of the request history."""
        return len(self.request_history)

    def clear_context(self):
        """Clear the conversation context."""
        self.context = []
        self._clear_rolling_summary()
        self.reset_summary_metrics()
        try:
            self.logger.debug("Cleared conversation context")
        except Exception:
            pass

    def clear_request_history(self):
        """Clear the request history."""
        self.request_history = []
        try:
            self.logger.debug("Cleared request history")
        except Exception:
            pass

    def get_summary_metrics(self) -> Dict[str, int]:
        """
        Get performance metrics for summary operations.
        """
        return {
            **self._summary_metrics,
            "current_summary_length": len(self._rolling_summary) if self._rolling_summary else 0
        }

    def reset_summary_metrics(self) -> None:
        """
        Reset summary performance metrics.
        """
        self._summary_metrics = {
            "initial_summaries": 0,
            "update_summaries": 0,
            "total_messages_summarized": 0,
            "truncation_count": 0,
            "frequent_truncation_alerts": 0
        }
        self._last_truncation_warning = None
        self._safe_log("info", "Summary metrics reset")

    def export_summary_metrics(self) -> str:
        """
        Export summary metrics as JSON string.
        """
        try:
            metrics = {
                **self._summary_metrics,
                "current_summary_length": len(self._rolling_summary) if self._rolling_summary else 0,
                "last_truncation_warning": self._last_truncation_warning.isoformat() if self._last_truncation_warning else None
            }
            return json.dumps(metrics, indent=2)
        except Exception:
            self._safe_log("exception", "Failed to export summary metrics")
            return "{}"

    def import_summary_metrics(self, metrics_json: str) -> None:
        """
        Import summary metrics from JSON string.
        """
        try:
            metrics = json.loads(metrics_json)
            self._summary_metrics = {
                "initial_summaries": metrics.get("initial_summaries", 0),
                "update_summaries": metrics.get("update_summaries", 0),
                "total_messages_summarized": metrics.get("total_messages_summarized", 0),
                "truncation_count": metrics.get("truncation_count", 0),
                "frequent_truncation_alerts": metrics.get("frequent_truncation_alerts", 0)
            }
            if metrics.get("last_truncation_warning"):
                self._last_truncation_warning = datetime.fromisoformat(metrics["last_truncation_warning"])
            self._safe_log("info", "Summary metrics imported successfully")
        except Exception:
            self._safe_log("exception", "Failed to import summary metrics")