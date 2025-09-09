import sys
import json
from prompt_toolkit import prompt
from prompt_toolkit.key_binding import KeyBindings

def create_keybindings():
    kb = KeyBindings()
    
    @kb.add('c-s')
    def _(event):
        event.current_buffer.validate_and_handle()
    
    return kb


def multiline_input(prompt="Paste your input (end with empty line):"):
    print(prompt)
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)

class VaultAIAskRunner:
    def __init__(self, agent, user=None, host=None):
        self.agent = agent
        self.user = user
        self.host = host
        self.history = []

    def load_data_from_file(self, filepath):
        """Load content from a file given its path."""
        try:
            # Remove the // prefix from filepath
            clean_path = filepath.replace('//', '', 1)
            with open(clean_path, 'r') as file:
                return file.read().strip()
        except Exception as e:
            return f"Error loading file: {str(e)}"

    def process_input(self, text):
        """Process input text and replace file paths with file contents."""
        words = text.split()
        result = []
        
        for word in words:
            if word.startswith('//'):
                file_content = self.load_data_from_file(word)
                result.append(f"\nFile content from {word}:\n{file_content}\n")
            else:
                result.append(word)
                
        return ' '.join(result)

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
                user_input = prompt(
                    "local> ", 
                    multiline=True,
                    prompt_continuation=lambda width, line_number, is_soft_wrap: "... ",
                    enable_system_prompt=True,
                    key_bindings=create_keybindings()
                )
                
                # Process the input to handle file loading
                processed_input = self.process_input(user_input)
                
            except (EOFError, KeyboardInterrupt):
                self.agent.console.print("\n[red][Vault 3000] Session ended by user.[/]")
                sys.exit(0)
            if user_input.strip().lower() in ("exit", "quit"):  
                self.agent.console.print("[Vault 3000] Exiting chat mode. Goodbye!")
                break
            # Add user message to history
            self.history.append({"role": "user", "content": processed_input})
            # Prepare prompt with memory (last 10 exchanges)
            prompt_context = self.history[-20:] if len(self.history) > 20 else self.history
            # Compose prompt for LLM
            if self.agent.ai_engine == "ollama":
                prompt_text = "\n".join(f"{m['role']}: {m['content']}" for m in prompt_context if m["role"] != "system")
                response = self.agent.connect_to_ollama(system_prompt, prompt_text, format=None)
            elif self.agent.ai_engine == "google":
                prompt_text = "\n".join(f"{m['role']}: {m['content']}" for m in prompt_context if m["role"] != "system")
                response = self.agent.connect_to_gemini(f"{system_prompt}\n{prompt_text}", format=None)
            elif self.agent.ai_engine == "openai":
                # OpenAI supports full chat context
                response = self.agent.connect_to_chatgpt(system_prompt, user_input if len(self.history) <= 2 else self.history[1:], format=None)
            else:
                self.agent.console.print("[red]Unknown AI engine. Stopping chat.[/]")
                break
            if response:
                try:
                    str_response = json.loads(response)
                    answer = str_response.get('response', response['response'])
                except Exception:
                    answer = response
                self.agent.console.print(f"[cyan]VaultAI:[/] {answer}")
                self.history.append({"role": "assistant", "content": answer})
            else:
                self.agent.console.print("[red]No response from AI.[/]")
