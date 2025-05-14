import sys
import json

class VaultAIAskRunner:
    def __init__(self, agent, user=None, host=None):
        self.agent = agent
        self.user = user
        self.host = host
        self.history = []

    def run(self):
        system_prompt = (
            "You are a helpful AI assistant. "
            "Answer user questions clearly and concisely. "
            "If the question is about Linux or terminal commands, provide the answer as a code block. "
        )
        context = [
            {"role": "system", "content": system_prompt},
        ]
        self.history = context.copy()
        while True:
            try:
                user_input = self.agent.console.input("> ")
            except (EOFError, KeyboardInterrupt):
                self.agent.console.print("\n[red][Vault-Tec 3000] Session ended by user.[/]")
                sys.exit(0)
            if user_input.strip().lower() in ("exit", "quit"):  
                self.agent.console.print("[Vault-Tec 3000] Exiting chat mode. Goodbye!")
                break
            # Add user message to history
            self.history.append({"role": "user", "content": user_input})
            # Prepare prompt with memory (last 10 exchanges)
            prompt_context = self.history[-20:] if len(self.history) > 20 else self.history
            # Compose prompt for LLM
            if self.agent.ai_engine == "ollama":
                prompt_text = "\n".join(f"{m['role']}: {m['content']}" for m in prompt_context if m["role"] != "system")
                response = self.agent.connect_to_ollama(system_prompt, prompt_text)
            elif self.agent.ai_engine == "google":
                prompt_text = "\n".join(f"{m['role']}: {m['content']}" for m in prompt_context if m["role"] != "system")
                response = self.agent.connect_to_gemini(f"{system_prompt}\n{prompt_text}")
            elif self.agent.ai_engine == "openai":
                # OpenAI supports full chat context
                response = self.agent.connect_to_chatgpt(system_prompt, user_input if len(self.history) <= 2 else self.history[1:])
            else:
                self.agent.console.print("[red]Unknown AI engine. Stopping chat.[/]")
                break
            if response:
                try:
                    str_response = json.loads(response)
                    answer = str_response.get('response', response)
                except Exception:
                    answer = response
                self.agent.console.print(f"[cyan]VaultAI:[/] {answer}")
                self.history.append({"role": "assistant", "content": answer})
            else:
                self.agent.console.print("[red]No response from AI.[/]")
