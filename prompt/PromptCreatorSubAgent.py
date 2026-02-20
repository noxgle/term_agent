"""
PromptCreatorSubAgent - Interactive prompt creation sub-agent for Vault 3000.

This sub-agent helps users create precise, actionable prompts through
iterative refinement with AI assistance. After creation, the user can
choose to immediately execute the prompt with VaultAIAgentRunner.

Usage:
    python term_ag.py -p
    python term_ag.py --prompt
"""

import json
from typing import Optional, Tuple
from rich.console import Console
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings


# System prompts for different modes
SYSTEM_PROMPT_FOR_AGENT = (
    "You are an expert prompt engineer. "
    "Your task is to help the user create a precise, actionable, and detailed prompt for an AI agent. "
    "Iteratively ask the user for clarifications, missing details, and context. "
    "After each answer, update and combine all information from previous answers into a single, coherent, comprehensive prompt draft. "
    "Show the user the current full draft after each step. "
    "Always reply in the following JSON format: {\n  'prompt_draft': <current full prompt draft>,\n  'question': <your next clarifying question, or null if the prompt is ready>\n}. "
    "If the prompt is already clear, complete, and actionable, set 'question' to null. "
    "Ask about: expected results, constraints, examples, use-case context, technologies, environment, level of detail, language of the answer, and any other relevant information. "
    "If the user provides vague or general information, ask for specifics. "
    "Always keep the conversation focused on making the prompt as useful as possible for an AI agent. "
    "Use markdown formatting where appropriate."
)

SYSTEM_PROMPT_GENERAL = (
    "You are an expert prompt engineer. "
    "Your task is to help the user create a precise, actionable, and detailed prompt for any purpose. "
    "Iteratively ask the user for clarifications, missing details, and context. "
    "After each answer, update and combine all information from previous answers into a single, coherent, comprehensive prompt draft. "
    "Show the user the current full draft after each step. "
    "Always reply in the following JSON format: {\n  'prompt_draft': <current full prompt draft>,\n  'question': <your next clarifying question, or null if the prompt is ready>\n}. "
    "If the prompt is already clear, complete, and actionable, set 'question' to null. "
    "Ask about: expected results, constraints, examples, use-case context, technologies, environment, level of detail, language of the answer, and any other relevant information. "
    "If the user provides vague or general information, ask for specifics. "
    "Always keep the conversation focused on making the prompt as useful as possible. "
    "Use markdown formatting where appropriate."
)

MAX_ITERATIONS = 20


class PromptCreatorSubAgent:
    """
    Sub-agent for interactive prompt creation with AI assistance.
    
    Guides users through iterative refinement of prompts, then offers
    the option to immediately execute the created prompt with VaultAIAgentRunner.
    """

    def __init__(self, terminal, ai_handler, logger=None):
        """
        Initialize PromptCreatorSubAgent.

        Args:
            terminal: Terminal instance for display and configuration
            ai_handler: AICommunicationHandler for AI requests
            logger: Logger instance (optional)
        """
        self.terminal = terminal
        self.ai_handler = ai_handler
        self.logger = logger or self._create_dummy_logger()
        self.console = getattr(terminal, 'console', Console())
        self.prompt_history = []
        self.final_prompt = None
        
        # Create prompt session with keybindings
        self.session = PromptSession(
            multiline=True,
            prompt_continuation=lambda width, line_number, is_soft_wrap: "... ",
            enable_system_prompt=True,
            key_bindings=self._create_keybindings()
        )

    def _create_keybindings(self):
        """Create key bindings for the prompt session."""
        kb = KeyBindings()
        
        @kb.add('c-s')
        def _(event):
            """Ctrl+S submits the input."""
            event.app.exit(result=event.app.current_buffer.text)
        
        return kb

    def run(self, prompt_for_agent: bool = True) -> Tuple[Optional[str], bool]:
        """
        Execute the prompt creation sub-agent.

        Args:
            prompt_for_agent: If True, create prompts for AI agent execution.
                             If False, create general-purpose prompts.

        Returns:
            tuple: (final_prompt, should_execute)
                - final_prompt: The created prompt string (or None if cancelled)
                - should_execute: True if user wants to run with VaultAIAgentRunner
        """
        self.terminal.print_console("\nPROMPT CREATOR")
        
        self.logger.info("PromptCreatorSubAgent: Starting prompt creation session")

        system_prompt = SYSTEM_PROMPT_FOR_AGENT if prompt_for_agent else SYSTEM_PROMPT_GENERAL
        
        self.terminal.print_console("\nDescribe your idea (Ctrl+S):")

        try:
            user_goal = self.session.prompt(HTML("> "))
            if not user_goal.strip():
                self.console.print("Empty input.")
                return None, False
            
            self.prompt_history.append({"user": user_goal})
            current_prompt = user_goal

            iteration_count = 0
            while iteration_count < MAX_ITERATIONS:
                iteration_count += 1
                
                ai_reply = self._ask_ai(system_prompt, current_prompt)
                if not ai_reply:
                    self.console.print("[red]AI error.[/]")
                    return None, False
                
                try:
                    reply_json = json.loads(ai_reply)
                    prompt_draft = reply_json.get("prompt_draft")
                    question = reply_json.get("question")
                    
                    if prompt_draft:
                        self.console.print("Draft:")
                        self.console.print(prompt_draft)
                    
                    if question is None or question == "" or str(question).lower() == "null":
                        self.console.print("\n[green]Ready![/]")
                        self.final_prompt = prompt_draft
                        return self._ask_final_action()
                    else:
                        self.console.print(f"\n[cyan]VaultAI>[/] {question}")
                        user_answer = self.session.prompt(HTML(">    "))
                        self.prompt_history.append({"ai": ai_reply, "user": user_answer})
                        current_prompt += "\n" + user_answer
                        
                except json.JSONDecodeError:
                    self.console.print(f"[red]JSON error.[/]")
                    return None, False
                except Exception as e:
                    self.console.print(f"[red]Error: {e}[/]")
                    return None, False
            
            self.console.print("[red]Max iterations.[/]")
            return None, False

        except KeyboardInterrupt:
            self.console.print("\n[red]Interrupted.[/]")
            return None, False

    def _ask_final_action(self) -> Tuple[Optional[str], bool]:
        while True:
            self.console.print(f"\n[cyan][r][/cyan] Run  [cyan][e][/cyan] Edit  [cyan][x][/cyan] Exit")
            choice = self.session.prompt(HTML("Choice [r/e/x]: ")).lower().strip()
            
            if choice == 'r':
                return self.final_prompt, True
            elif choice == 'e':
                self.console.print("\n[yellow]Current prompt:[/]")
                self.console.print(self.final_prompt)
                edit_input = self.session.prompt(HTML("\nAdd/modify (Ctrl+S): "))
                if edit_input.strip():
                    self.final_prompt += "\n" + edit_input
                    self.console.print("\n[yellow]Updated:[/]")
                    self.console.print(self.final_prompt)
            elif choice == 'x':
                return self.final_prompt, False
            else:
                self.console.print("[red]Invalid. Use 'r', 'e' or 'x'.[/]")

    def _format_history(self) -> str:
        """Format the prompt history for AI query."""
        formatted = ""
        for i, entry in enumerate(self.prompt_history, 1):
            if "user" in entry:
                formatted += f"{i}. User: {entry['user']}\n"
            if "ai" in entry:
                formatted += f"{i}. VaultAI> {entry['ai']}\n"
        return formatted.strip()

    def _ask_ai(self, system_prompt: str, prompt_text: str) -> Optional[str]:
        """
        Send a prompt to the AI and return the response.

        Args:
            system_prompt: System instructions for the AI
            prompt_text: User prompt content

        Returns:
            AI response string or None on failure
        """
        formatted_history = self._format_history()
        full_prompt = f"{prompt_text}\n\nConversation History:\n{formatted_history}"
        
        return self.ai_handler.send_request(
            system_prompt=system_prompt,
            user_prompt=full_prompt,
            request_format="json"
        )

    def _create_dummy_logger(self):
        """Fallback logger if none provided."""
        class DummyLogger:
            def log(self, *args, **kwargs): pass
            def debug(self, *args, **kwargs): pass
            def info(self, *args, **kwargs): pass
            def warning(self, *args, **kwargs): pass
            def error(self, *args, **kwargs): pass
            def exception(self, *args, **kwargs): pass
        return DummyLogger()