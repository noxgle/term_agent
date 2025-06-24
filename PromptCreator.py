from term_ag import term_agent, PIPBOY_ASCII
from rich.console import Console
from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.formatted_text import HTML
import json
from prompt_toolkit.key_binding import KeyBindings


class PromptCreator:
    def __init__(self,promopt_for_agent=False):
        self.agent = term_agent()
        self.console = Console()
        self.prompt_history = []
        self.final_prompt = None
        self.is_for_ai= promopt_for_agent

        # Use PromptSession for multiline Fallout-style input
        self.session = PromptSession(
            multiline=True,
            prompt_continuation=lambda width, line_number, is_soft_wrap: "... ",
            enable_system_prompt=True,
            key_bindings=self.create_keybindings()
        )
        print(PIPBOY_ASCII)

    def create_keybindings(self):
        kb = KeyBindings()
        # Przykład: Ctrl+S akceptuje multiline input
        @kb.add('c-s')
        def _(event):
            event.app.exit(result=event.app.current_buffer.text)
        return kb

    def start(self):
        self.console.print("[bold green]*** WELCOME TO THE ADVANCED PROMPT CREATOR ***[/]")
        self.console.print("Prompt your goal and press [cyan]Ctrl+S[/] to start!")
        try:
            # Pytanie o AI agenta na początku dialogu, nie w __init__!
            if self.is_for_ai:
                self.system_prompt_agent = (
                    "You are an expert prompt engineer. "
                    "Your task is to help the user create a precise, actionable, and detailed prompt for an AI agent. "
                    "Iteratively ask the user for clarifications, missing details, and context. "
                    "After each answer, update and combine all information from previous answers into a single, coherent, comprehensive prompt draft. "
                    "Show the user the current full draft after each step. "
                    "Always reply in the following JSON format: {\n  'prompt_draft': <current full prompt draft>,\n  'question': <your next clarifying question, or null if the prompt is ready>\n}. "
                    "If the prompt is already clear, complete, and actionable, set 'question' to null. "
                    "Ask about: expected results, constraints, examples, use-case context, technologies, environment, level of detail, language of the answer, and any other relevant information. "
                    "If the user provides vague or general information, ask for specifics. "
                    "Always keep the conversation focused on making the prompt as useful as possible for an AI agent."
                )
            else:
                self.system_prompt_agent = (
                    "You are an expert prompt engineer. "
                    "Your task is to help the user create a precise, actionable, and detailed prompt for any purpose. "
                    "Iteratively ask the user for clarifications, missing details, and context. "
                    "After each answer, update and combine all information from previous answers into a single, coherent, comprehensive prompt draft. "
                    "Show the user the current full draft after each step. "
                    "Always reply in the following JSON format: {\n  'prompt_draft': <current full prompt draft>,\n  'question': <your next clarifying question, or null if the prompt is ready>\n}. "
                    "If the prompt is already clear, complete, and actionable, set 'question' to null. "
                    "Ask about: expected results, constraints, examples, use-case context, technologies, environment, level of detail, language of the answer, and any other relevant information. "
                    "If the user provides vague or general information, ask for specifics. "
                    "Always keep the conversation focused on making the prompt as useful as possible."
                )

            user_goal = self.session.prompt(HTML("<ansiyellow><b>Describe your goal: </b></ansiyellow>"))
            self.prompt_history.append({"user": user_goal})
            current_prompt = user_goal
            while True:
                ai_reply = self.ask_ai(f"User's goal: {current_prompt}\nHistory: {self.prompt_history}")
                if not ai_reply:
                    self.console.print("[bold red]AI did not respond or engine is invalid. Exiting.[/]")
                    break
                try:
                    reply_json = json.loads(ai_reply)
                    prompt_draft = reply_json.get("prompt_draft")
                    question = reply_json.get("question")
                    if prompt_draft:
                        self.console.print("[bold cyan]Current prompt draft:[/]")
                        self.console.print_json(data=prompt_draft)
                    if question is None or question == "" or str(question).lower() == "null":
                        self.console.print("[bold green]Prompt is ready![/]")
                        self.console.print_json(data=prompt_draft)
                        # Akceptacja Enterem (jednolinijkowy prompt)
                        add_more = prompt(HTML("<ansiyellow>Do you want to add anything else to the prompt? (y/n): </ansiyellow>"))
                        if add_more.strip().lower() == 'y':
                            user_extra = self.session.prompt(HTML("<ansicyan>Add your extra details: </ansicyan>"))
                            self.prompt_history.append({"user": user_extra})
                            current_prompt += "\n" + user_extra
                            continue
                        else:
                            self.final_prompt = prompt_draft
                            self.console.print("[bold green]Final prompt:[/]")
                            self.console.print_json(data=self.final_prompt)
                            break
                    else:
                        self.console.print(f"[bold blue]AI asks: [bold yellow]{question}[/]")
                        # Akceptacja odpowiedzi Enterem (jednolinijkowy prompt)
                        user_answer = prompt(HTML("<ansigreen>Your answer: </ansigreen>"))
                        self.prompt_history.append({"ai": ai_reply, "user": user_answer})
                        current_prompt += "\n" + user_answer
                except Exception:
                    if "PROMPT_READY" in ai_reply:
                        self.final_prompt = current_prompt
                        self.console.print("[bold green]Prompt is ready![/]")
                        self.console.print(f"[bold yellow]{self.final_prompt}[/]")
                        break
                    self.console.print(f"[bold blue]AI asks: [bold yellow]{ai_reply}[/]")
                    # Akceptacja odpowiedzi Enterem (jednolinijkowy prompt)
                    user_answer = prompt(HTML("<ansigreen>Your answer: </ansigreen>"))
                    self.prompt_history.append({"ai": ai_reply, "user": user_answer})
                    current_prompt += "\n" + user_answer
        except KeyboardInterrupt:
            self.console.print("\n[bold red]Prompt creation interrupted by user (KeyboardInterrupt). Exiting...[/]")

    def ask_ai(self, prompt_text):
        terminal = self.agent
        if terminal.ai_engine == "ollama":
            ai_reply = terminal.connect_to_ollama(self.system_prompt_agent, prompt_text, format="json")
        elif terminal.ai_engine == "google":
            ai_reply = terminal.connect_to_gemini(f"{self.system_prompt_agent}\n{prompt_text}")
        elif terminal.ai_engine == "openai":
            ai_reply = terminal.connect_to_chatgpt(self.system_prompt_agent, prompt_text)
        else:
            terminal.print_console("Invalid AI engine specified. Stopping agent.", color="red")
            self.final_prompt = None
            return None
        return ai_reply

if __name__ == "__main__":
    creator = PromptCreator(promopt_for_agent=True)
    creator.start()