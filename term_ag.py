import requests
import logging
import os
import subprocess
import sys
from dotenv import load_dotenv
from openai import OpenAI
from google import genai
from rich.console import Console
from AiAgentRunner import VaultAIAgentRunner


class term_agent:
    def __init__(self):
        load_dotenv()
        # --- Logging config from .env ---
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        log_file = os.getenv("LOG_FILE", "")
        log_to_console = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"
        handlers = []
        if log_file:
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        if log_to_console or not handlers:
            handlers.append(logging.StreamHandler())
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format='[%(asctime)s] %(levelname)s: %(message)s',
            handlers=handlers
        )
        self.logger = logging.getLogger("TerminalAIAgent")
        self.ai_engine = os.getenv("AI_ENGINE", "openai")
        # API key selection logic
        if self.ai_engine == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY", "")
        elif self.ai_engine == "google":
            self.api_key = os.getenv("GOOGLE_API_KEY", "")
        else:
            self.api_key = None
        if self.ai_engine in ["openai", "google"] and not self.api_key:
            self.logger.critical(f"You must set the correct API key in the .env file for engine {self.ai_engine}.")
            raise RuntimeError(f"You must set the correct API key in the .env file for engine {self.ai_engine}.")
        
        self.default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.default_temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.5"))
        self.default_max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "150"))
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "granite3.3:8b")
        self.ollama_temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.5"))
        self.gemini_model = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash")
        self.console = Console()
        self.ssh_connection = False  # Dodane do obsługi trybu lokalnego/zdalnego

    def connect_to_gemini(self, prompt, model=None, max_tokens=None, temperature=None):
        """
        Send a prompt to Google Gemini and return the response as a string.
        """
        if model is None:
            model = getattr(self, "gemini_model", "gemini-2.0-flash")
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is None:
            temperature = self.default_temperature
        try:
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                }
            )


            self.logger.info(f"Gemini prompt: {prompt}")
            self.logger.debug(f"Gemini raw response: {response}")
            if hasattr(response, "text"):
                return response.text.strip()
            elif hasattr(response, "candidates") and response.candidates:
                return response.candidates[0].content.strip()
            elif hasattr(response, "result"):
                return response.result.strip()
            else:
                return str(response)
        except Exception as e:
            self.logger.error(f"Gemini connection error: {e}")
            self.print_green(f"Gemini connection error: {e}")
            return None


    # --- ChatGPT Function ---
    def connect_to_chatgpt(self, role_system_content, prompt,
                           model=None, max_tokens=None, temperature=None):
        if model is None:
            model = self.default_model
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is None:
            temperature = self.default_temperature
        client = OpenAI(api_key=self.api_key)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": role_system_content},
                    {"role": "user",   "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"}
            )
            self.logger.info(f"OpenAI prompt: {prompt}")
            self.logger.debug(f"OpenAI raw response: {response}")
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"OpenAI connection error: {e}")
            self.print_green(f"OpenAI connection error: {e}")
            return None

    # --- Ollama Function ---
    def connect_to_ollama(self, system_prompt, prompt, model=None, max_tokens=None, temperature=None, ollama_url=None, format=None):
        """
        Send a prompt to Ollama API and return the response as a string.
        Uses simple prompt (not chat format) for best compatibility.
        """

        if model is None:
            model = self.ollama_model
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is None:
            temperature = self.ollama_temperature
        if ollama_url is None:
            ollama_url = self.ollama_url

        # Compose the prompt with system message for context
        full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        if format is not None:
            payload["format"] = format

        try:
            resp = requests.post(ollama_url, json=payload, timeout=120)
            resp.raise_for_status()
            response_text = resp.text.strip()
            self.logger.info(f"Ollama prompt: {full_prompt}")
            self.logger.debug(f"Ollama raw response: {response_text}")

            # Ollama returns JSON with a 'response' or 'message' or 'content' field
            try:
                result = resp.json()
            except Exception as e:
                self.logger.error(f"Failed to parse Ollama JSON: {e}")
                return None

            # Try to extract the main content
            for key in ("response", "message", "content"):
                if key in result:
                    content = result[key]
                    # Sometimes 'message' is a dict with 'content'
                    if isinstance(content, dict) and "content" in content:
                        content = content["content"]
                    return content.strip()
            # If nothing found, log and return None
            self.logger.error(f"Unexpected Ollama response format: {result}")
            return None

        except Exception as e:
            self.logger.error(f"Ollama connection error: {e}")
            self.print_green(f"Ollama connection error: {e}")
            return None

    def run(self, command, remote=None):
        """
        Run a shell command locally or remotely (via SSH).
        Returns (returncode, stdout, stderr).
        """
        if remote is None:
            self.logger.info(f"Running local command: {command}")
            try:
                result = subprocess.run(command, shell=True, capture_output=True, text=True)
                self.logger.debug(f"Local command output: {result.stdout}")
                if result.stderr:
                    self.logger.warning(f"Local command error: {result.stderr}")
                return result.returncode, result.stdout, result.stderr
            except Exception as e:
                self.logger.error(f"Local command execution failed: {e}")
                return 1, '', str(e)
        else:
            self.logger.info(f"Running remote command: {command} on {remote}")
            ssh_command = ["ssh", remote, command]
            try:
                result = subprocess.run(ssh_command, capture_output=True, text=True)
                self.logger.debug(f"Remote command output: {result.stdout}")
                if result.stderr:
                    self.logger.warning(f"Remote command error: {result.stderr}")
                return result.returncode, result.stdout, result.stderr
            except Exception as e:
                self.logger.error(f"Remote command execution failed: {e}")
                return 1, '', str(e)

    def run_local(self):
        while True:
            command = self.console.input("[bold yellow]Enter command to run locally (or 'exit' to quit): [/] ")
            if command.strip().lower() == 'exit':
                break
            if not command.strip():
                continue
            confirm = self.console.input(f"[bold yellow]Are you sure you want to run: '{command}' locally? (y/n): [/] ")
            if confirm.lower() == 'y':
                result = subprocess.run(command, shell=True, capture_output=True, text=True)
                self.console.print(f"[green]Command output:[/]")
                self.console.print(result.stdout)
                if result.stderr:
                    self.console.print(f"[red]Error output:[/]")
                    self.console.print(result.stderr)
            else:
                self.console.print("[red]Command cancelled.[/]")

    def run_remote(self, remote):
        while True:
            command = self.console.input(f"[bold yellow]Enter command to run on {remote} (or 'exit' to quit): [/] ")
            if command.strip().lower() == 'exit':
                break
            if not command.strip():
                continue
            confirm = self.console.input(f"[bold yellow]Are you sure you want to run: '{command}' on {remote}? (y/n): [/] ")
            if confirm.lower() == 'y':
                ssh_command = ["ssh", remote, command]
                result = subprocess.run(ssh_command, capture_output=True, text=True)
                self.console.print(f"[green]Command output:[/]")
                self.console.print(result.stdout)
                if result.stderr:
                    self.console.print(f"[red]Error output:[/]")
                    self.console.print(result.stderr)
            else:
                self.console.print("[red]Command cancelled.[/]")

    def print_green(self, text):
        self.console.print(f"[bold green]{text}[/]")

    def execute_local(self, command):
        """
        Wykonuje komendę lokalnie i zwraca (stdout, returncode)
        """
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout, result.returncode

    def execute_remote(self, command):
        """
        Wykonuje komendę zdalnie przez SSH i zwraca (stdout, returncode)
        """
        remote = getattr(self, 'remote_host', None)
        if not remote:
            return '', 1
        ssh_command = ["ssh", remote, command]
        result = subprocess.run(ssh_command, capture_output=True, text=True)
        return result.stdout, result.returncode

def main():
    agent = term_agent()
    agent.console.print("[bold green]Witaj w Terminal AI Agent![/]")
    agent.console.print("Podaj cel/zadanie do wykonania przez AI (np. 'Zainstaluj nginx', 'Znajdź duże pliki w katalogu /tmp', itp.)")
    #user_goal = agent.console.input("[bold yellow]Cel: [/] ")
    user_goal = "sprawdz ilsoć wolengo miejsca na dysku"
    if len(sys.argv) == 2:
        remote = sys.argv[1]
        user = remote.split('@')[0] if '@' in remote else None
        host = remote.split('@')[1] if '@' in remote else remote
        agent.ssh_connection = True  # Ustaw tryb zdalny
        agent.remote_host = remote   # Przechowuj host do użycia w execute_remote
    else:
        remote = None
        user = None
        host = None
        agent.ssh_connection = False
        agent.remote_host = None
    runner = VaultAIAgentRunner(agent, user_goal, user=user, host=host)
    runner.run()

if __name__ == "__main__":
    main()
