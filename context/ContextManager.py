import json
import re
import logging
from typing import List, Dict, Any, Optional

class ContextManager:
    """
    Manages conversation context and sliding window functionality for AI agents.

    This class handles:
    - Maintaining conversation history with sliding window
    - Summarizing older messages to keep context size manageable
    - Tracking request history for debugging and tracing
    - Providing context windows for AI model input
    """

    def __init__(self, window_size: int = 20, logger: Optional[logging.Logger] = None):
        """
        Initialize the ContextManager.

        Args:
            window_size: Number of recent messages to keep in the sliding window
            logger: Optional logger for debugging and tracing
        """
        self.window_size = window_size
        self.context: List[Dict[str, str]] = []
        self.request_history: List[Dict[str, Any]] = []
        self.logger = logger or logging.getLogger("ContextManager")

        # Initialize with empty context
        self._initialize_context()

    def _initialize_context(self):
        """Initialize the context with basic structure."""
        self.context = []

    def add_message(self, role: str, content: str):
        """
        Add a message to the conversation context.

        Args:
            role: Message role (e.g., 'system', 'user', 'assistant')
            content: Message content
        """
        self.context.append({"role": role, "content": content})
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

    def get_sliding_window_context(self, state: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
        """
        Build a sliding-window context combining summarization and persistent state.

        Behavior:
        - Always keep the first two messages (system + user goal).
        - If there are older messages beyond the sliding window, summarize them
          into a single system message.
        - Keep the last `self.window_size` messages verbatim.
        - Inject the current persistent state as a final system message if provided.

        Returns:
            list: messages to pass to the model.
        """
        # If context is small, return it (plus state injection)
        if len(self.context) <= 2 + self.window_size:
            working = list(self.context)
        else:
            # Keep first two messages (system + user goal)
            initial = self.context[:2]

            # Messages eligible for summarization: everything between the first two
            # and the recent window (exclusive).
            messages_to_summarize = self.context[2:-self.window_size]

            # Keep the most recent `window_size` messages
            recent = self.context[-self.window_size:]

            working = list(initial)

            # If there is anything to summarize, create one system summary message
            if messages_to_summarize:
                try:
                    # Log summarization activity
                    try:
                        self.logger.debug("Summarizing %s older messages into one summary.", len(messages_to_summarize))
                    except Exception:
                        pass
                    summary_text = self._summarize(messages_to_summarize)
                    summary_message = {
                        "role": "system",
                        "content": f"[Summary of earlier conversation]\n{summary_text}"
                    }
                    working.append(summary_message)
                except Exception:
                    # If summarization fails for any reason, append a short fallback note
                    try:
                        self.logger.exception("Failed to summarize older messages.")
                    except Exception:
                        pass
                    working.append({
                        "role": "system",
                        "content": "[Summary of earlier conversation could not be generated.]"
                    })

            # Append the recent messages (the sliding window)
            working.extend(recent)

        # Finally, inject the persistent agent state so the model knows current progress
        if state is not None:
            try:
                if isinstance(state, dict) and state:
                    state_repr = json.dumps(state, ensure_ascii=False)
                    state_message = {"role": "system", "content": f"Current agent state: {state_repr}"}
                    working.append(state_message)
            except Exception:
                # If serializing state fails, include a basic representation
                try:
                    self.logger.exception("Failed to serialize agent state for context injection.")
                except Exception:
                    pass
                working.append({"role": "system", "content": f"Current agent state: {str(state)}"})

        return working

    def _summarize(self, messages: List[Dict[str, str]]) -> str:
        """
        Produce a concise summary for a list of messages.

        The summary should include:
        - what has been done (completed actions),
        - decisions or results,
        - outstanding/pending tasks.

        This implementation uses a lightweight heuristic extraction.

        Args:
            messages: list of message dicts to summarize (each with 'role' and 'content').

        Returns:
            str: concise multi-line summary.
        """
        # Log summarization request
        try:
            self.logger.debug("_summarize called for %s messages", len(messages))
        except Exception:
            pass

        # Fallback heuristic summarization: simple extraction by keywords
        completed = []
        decisions = []
        pending = []

        for m in messages:
            text = m.get("content", "").strip()
            lower = text.lower()
            # Heuristics: look for typical phrases
            if any(k in lower for k in ("done", "completed", "finished", "succeeded", "created", "written")):
                completed.append(text.splitlines()[0])
            elif any(k in lower for k in ("decide", "decision", "choose", "will", "should")):
                decisions.append(text.splitlines()[0])
            elif any(k in lower for k in ("todo", "pending", "next", "remaining", "open")):
                pending.append(text.splitlines()[0])

        # Build the summary text
        parts = []
        parts.append("Completed:")
        parts.extend([f"- {c}" for c in (completed or ["(none detected)"])])
        parts.append("\nDecisions:")
        parts.extend([f"- {d}" for d in (decisions or ["(none detected)"])])
        parts.append("\nPending:")
        parts.extend([f"- {p}" for p in (pending or ["(none detected)"])])

        return "\n".join(parts)

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