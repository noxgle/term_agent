from prompt_toolkit import prompt
from prompt_toolkit.key_binding import KeyBindings

class UserInteractionHandler:
    def __init__(self, terminal):
        self.terminal = terminal
        self.key_bindings = self.terminal.create_keybindings()

    def _get_user_input(self, prompt_text: str, multiline: bool = False) -> str:
        """
        Unified input helper that uses prompt_toolkit so Ctrl+S (configured in
        the terminal keybindings) can be used to submit input consistently.

        Returns the entered text (empty string on cancel/EOF).
        """
        try:
            user_input = prompt(
                prompt_text,
                multiline=multiline,
                prompt_continuation=(lambda width, line_number, is_soft_wrap: "... ") if multiline else None,
                enable_system_prompt=True,
                key_bindings=self.key_bindings,
            )
            return user_input
        except (EOFError, KeyboardInterrupt):
            return ""
        except Exception as e:
            # Do not silently swallow prompt-toolkit failures.
            # For single-line confirmations (y/n), fallback to plain input()
            # so manual approvals still work in CLI mode.
            try:
                if hasattr(self.terminal, "logger"):
                    self.terminal.logger.warning(
                        "Prompt toolkit input failed (multiline=%s): %s",
                        multiline,
                        e,
                    )
            except Exception:
                pass

            if not multiline:
                try:
                    return input(prompt_text)
                except Exception:
                    return ""

            return ""
