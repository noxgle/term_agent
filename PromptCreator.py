from term_ag import term_agent
from rich.console import Console
import json

class PromptCreator:
    def __init__(self):
        self.agent = term_agent()
        self.console = Console()
        self.prompt_history = []
        self.final_prompt = None

        # NEW: Ask if the prompt is for an AI agent
        is_for_ai = self.console.input("[bold yellow]Is this prompt being created for an AI agent? (y/n): [/] ")
        self.is_for_ai = is_for_ai.strip().lower() == "y"
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

    def start(self):
        self.console.print("[bold green]Welcome to the Advanced Prompt Creator![/]")
        user_goal = self.console.input("[bold yellow]Describe your goal: [/] ")
        self.prompt_history.append({"user": user_goal})
        current_prompt = user_goal
        while True:
            ai_reply = self.ask_ai(f"User's goal: {current_prompt}\nHistory: {self.prompt_history}")
            if not ai_reply:
                self.console.print("[red]AI did not respond or engine is invalid. Exiting.[/]")
                break
            # Try to parse as JSON
            try:
                reply_json = json.loads(ai_reply)
                prompt_draft = reply_json.get("prompt_draft")
                question = reply_json.get("question")
                if prompt_draft:
                    self.console.print("[bold magenta]Current prompt draft:[/]")
                    self.console.print_json(data=prompt_draft)
                # Now handle end-of-questions logic
                if question is None or question == "" or str(question).lower() == "null":
                    self.console.print("[bold green]Prompt is ready![/]")
                    self.console.print_json(data=prompt_draft)
                    add_more = self.console.input("[bold yellow]Do you want to add anything else to the prompt? (y/n): [/] ")
                    if add_more.strip().lower() == 'y':
                        user_extra = self.console.input("[bold yellow]Add your extra details: [/] ")
                        self.prompt_history.append({"user": user_extra})
                        current_prompt += "\n" + user_extra
                        continue
                    else:
                        self.final_prompt = prompt_draft
                        self.console.print("[bold green]Final prompt:[/]")
                        self.console.print_json(data=self.final_prompt)
                        break
                else:
                    self.console.print(f"[bold blue]AI asks: {question}[/]")
                    user_answer = self.console.input("[bold yellow]Your answer: [/] ")
                    self.prompt_history.append({"ai": ai_reply, "user": user_answer})
                    current_prompt += "\n" + user_answer
            except Exception:
                # Fallback: treat as plain text
                if "PROMPT_READY" in ai_reply:
                    self.final_prompt = current_prompt
                    self.console.print("[bold green]Prompt is ready![/]")
                    self.console.print(f"[cyan]{self.final_prompt}[/]")
                    break
                self.console.print(f"[bold blue]AI asks: {ai_reply}[/]")
                user_answer = self.console.input("[bold yellow]Your answer: [/] ")
                self.prompt_history.append({"ai": ai_reply, "user": user_answer})
                current_prompt += "\n" + user_answer

if __name__ == "__main__":
    creator = PromptCreator()
    creator.start()
