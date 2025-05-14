import sys
import json

class VaultAIAskRunner:
    #def __init__(self, agent, user_goal, user=None, host=None):
    def __init__(self, agent, user=None, host=None):
        self.agent = agent
        #self.user_goal = user_goal
        self.user = user
        self.host = host
        self.history = []

    def run(self):
        #self.agent.console.print(f"[Vault-Tec] Chat mode started. Ask your questions! (type 'exit' to quit)")
        # Initial system prompt for context
        system_prompt = (
            "You are VaultAI, a helpful Fallout-inspired AI assistant. "
            "Answer user questions clearly and concisely. "
            "If the question is about Linux or terminal commands, provide the answer as a code block. "
            "Stay in character as a Vault-Tec assistant."
        )
        context = [
            {"role": "system", "content": system_prompt},
            #{"role": "user", "content": self.user_goal}
        ]
        while True:
            try:
                user_input = self.agent.console.input("[bold green]> [/] ")
            except (EOFError, KeyboardInterrupt):
                self.agent.console.print("\n[red][Vault-Tec] Session ended by user.[/]")
                sys.exit(0)
            if user_input.strip().lower() in ("exit", "quit"):  
                self.agent.console.print("[Vault-Tec] Exiting chat mode. Goodbye!")
                break
            context.append({"role": "user", "content": user_input})
            # Choose AI engine
            if self.agent.ai_engine == "ollama":
                response = self.agent.connect_to_ollama(system_prompt, user_input)
            elif self.agent.ai_engine == "google":
                response = self.agent.connect_to_gemini(f"{system_prompt}\n{user_input}")
            elif self.agent.ai_engine == "openai":
                response = self.agent.connect_to_chatgpt(system_prompt, user_input)
            else:
                self.agent.console.print("[red]Unknown AI engine. Stopping chat.[/]")
                break
            if response:
                str_response = json.loads(response)
                self.agent.console.print(f"[cyan]VaultAI:[/] {str_response['response']}")
                context.append({"role": "assistant", "content": response})
            else:
                self.agent.console.print("[red]No response from AI.[/]")
