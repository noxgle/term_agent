from term_ag import term_agent, PIPBOY_ASCII
from rich.console import Console
from rich.markup import escape

from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.formatted_text import HTML
import json
from prompt_toolkit.key_binding import KeyBindings
import sys

# Constants
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

class PromptCreator:
    """
    A class for creating and refining prompts interactively with AI assistance.
    """

    def __init__(self, prompt_for_agent=False):
        self.agent = term_agent()
        self.console = Console()
        self.prompt_history = []
        self.final_prompt = None
        self.is_for_ai = prompt_for_agent

        # Use PromptSession for multiline Fallout-style input
        self.session = PromptSession(
            multiline=True,
            prompt_continuation=lambda width, line_number, is_soft_wrap: "... ",
            enable_system_prompt=True,
            key_bindings=self.create_keybindings()
        )

    def create_keybindings(self):
        """
        Create key bindings for the prompt session.
        """
        kb = KeyBindings()
        # Example: Ctrl+S accepts multiline input
        @kb.add('c-s')
        def _(event):
            event.app.exit(result=event.app.current_buffer.text)
        return kb

    def main(self):
        """
        Main method to run the prompt creation process.
        """
        self.agent.console.print(PIPBOY_ASCII)
        self.agent.console.print(f"{self.agent.print_vault_tip()}\n")
        ai_status, mode_owner, ai_model = self.agent.check_ai_online()    
        self.agent.console.print("\nWelcome, Vault Dweller, to the Vault 3000.")
        self.agent.console.print("Mode: Prompt Creator") 
        self.agent.console.print(f"Your local Linux distribution is: {self.agent.local_linux_distro[0]} {self.agent.local_linux_distro[1]}")
        if ai_status:
            self.agent.console.print(f"""VaultAI: {ai_model} is online.\n""")
        else:
            self.agent.console.print("[red]AgentAI: is offline.[/]\n")
            self.agent.console.print("[red]Please check your API key and network connection.[/]\n")
            sys.exit(1)
        try:
            # Ask about AI agent at the beginning of the dialog, not in __init__!
            if self.is_for_ai:
                self.system_prompt_agent = SYSTEM_PROMPT_FOR_AGENT
            else:
                self.system_prompt_agent = SYSTEM_PROMPT_GENERAL

            while True:
                user_goal = self.session.prompt(HTML("Describe your idea and press Ctrl+S to start!\nlocal>"))
                if not user_goal.strip():
                    self.console.print("[red]Error: Please provide a description of your idea.[/]")
                    continue
                self.prompt_history.append({"user": user_goal})
                current_prompt = user_goal
                break
            iteration_count = 0
            while iteration_count < MAX_ITERATIONS:
                iteration_count += 1
                self.console.print("\n")
                ai_reply = self.ask_ai(f"User's goal: {current_prompt}")
                if not ai_reply:
                    self.console.print("[red]AI did not respond or engine is invalid. Exiting.[/]")
                    break
                try:
                    reply_json = json.loads(ai_reply)
                    prompt_draft = reply_json.get("prompt_draft")
                    question = reply_json.get("question")
                    if prompt_draft and question is not None:
                        self.console.print("Current prompt draft:")
                        self.console.print(prompt_draft)
                    if question is None or question == "" or str(question).lower() == "null":
                        self.console.print("Final prompt:")
                        self.console.print(prompt_draft)
                        # Acceptance with Ctrl+S (using session)
                        add_more = self.session.prompt(HTML("\nPress Ctrl+S to submit\nDo you want to add anything else to the prompt? (y/n): "))
                        if add_more.strip().lower() == 'y':
                            user_extra = self.session.prompt(HTML("\nPress Ctrl+S to submit\nAdd your extra details\nlocal>"))
                            self.prompt_history.append({"user": user_extra})
                            current_prompt += "\n" + user_extra
                            continue
                        else:
                            self.final_prompt = prompt_draft
                            self.save_prompt_option()
                            break
                    else:
                        self.console.print(f"\nAI asks: {question}")
                        # Acceptance with Ctrl+S (using session)
                        user_answer = self.session.prompt(HTML("\nPress Ctrl+S to submit\nYour answer: "))
                        self.prompt_history.append({"ai": ai_reply, "user": user_answer})
                        current_prompt += "\n" + user_answer
                except json.JSONDecodeError:
                    self.console.print(f"[red]Error: Invalid JSON response from AI: {ai_reply}[/]")
                    break
                except Exception as e:
                    self.console.print("[red]Unexpected error:", e, "[/]")
                    break
            if iteration_count >= MAX_ITERATIONS:
                self.console.print("[red]Maximum iterations reached. Prompt creation stopped.[/]")
        except KeyboardInterrupt:
            self.console.print("\n[red]Prompt creation interrupted by user (KeyboardInterrupt). Exiting...[/]")

    def format_history(self):
        """
        Format the prompt history for AI query.
        """
        formatted = ""
        for i, entry in enumerate(self.prompt_history, 1):
            if "user" in entry:
                formatted += f"{i}. User: {entry['user']}\n"
            if "ai" in entry:
                formatted += f"{i}. AI: {entry['ai']}\n"
        return formatted.strip()

    def ask_ai(self, prompt_text):
        """
        Send a prompt to the AI and return the response.
        """
        formatted_history = self.format_history()
        full_prompt = f"{prompt_text}\n\nConversation History:\n{formatted_history}"
        terminal = self.agent
        if terminal.ai_engine == "ollama":
            ai_reply = terminal.connect_to_ollama(self.system_prompt_agent, full_prompt, format="json")
        elif terminal.ai_engine == "google":
            ai_reply = terminal.connect_to_gemini(f"{self.system_prompt_agent}\n{full_prompt}")
        elif terminal.ai_engine == "openai":
            ai_reply = terminal.connect_to_chatgpt(self.system_prompt_agent, full_prompt)
        else:
            terminal.print_console("Invalid AI engine specified. Stopping agent.", color="red")
            self.final_prompt = None
            return None
        return ai_reply

    def save_prompt_option(self):
        """
        Offer to save the final prompt to a file.
        """
        save_option = self.session.prompt(HTML("Press Ctrl+S to submit\nDo you want to save the prompt to a file? (y/n): "))
        if save_option.strip().lower() == 'y':
            filename = self.session.prompt(HTML("Press Ctrl+S to submit\nEnter filename (e.g., prompt.txt): "))
            if not filename.strip():
                filename = "prompt.txt"
            try:
                with open(filename, 'w') as f:
                    f.write(self.final_prompt)
                self.console.print(f"[green]Prompt saved to {filename}[/]")
            except Exception as e:
                self.console.print("[red]Error saving prompt:", e, "[/]")

if __name__ == "__main__":
    creator = PromptCreator(prompt_for_agent=True)
    creator.main()
