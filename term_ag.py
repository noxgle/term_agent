import requests
import logging
import os
import subprocess
import sys
import random
from dotenv import load_dotenv
from openai import OpenAI
from google import genai
from rich.console import Console
from VaultAiAgentRunner import VaultAIAgentRunner
import pexpect

PIPBOY_ASCII = r"""

 ........................................................................................ 
 ........................................................................................ 
 ........................................................................................ 
 ..........................................       ....................................... 
 ........................................   #####    .................................... 
 ......................................   ##     ###       .............................. 
 ...............................    .   ###  ...   .  +###   ............................ 
 .....................     ...   ## . ### . ..........   .##  ........................... 
 ...................   ### .   ##   .     ...............  ##   ......................... 
 ..................  ##.##   ##.  ........       .........  -##   ....................... 
 ..................  # . #####     .       .####   ........    ##   ..................... 
 .................. ## .         ###### ##########          .   -#.  .................... 
 ..................  #  ......  #                ###  ########    ## .................... 
 ................... ##   . . ##  ..............    .       ###...##  ................... 
 ................... .### . ##   ............     .........  ## .. ## ................... 
 ................... #   ##   ## ............ ###  ......   ##  .. +# ................... 
 ................... #  ## ##### ............  ###  ..... ###. ...  #  .................. 
 ...................  ###.       .............    # .....  -#.. .. ### .................. 
 ...................  ##  .     ....   ..... .      .....  ## #     #  .................. 
 ...................  ## .  ### ...  # ....  ### ........ # ## ##  ##  .................. 
 ................... ## .. #### ..  ## .... --## ........  ##   # ###  .................. 
 ................... ## .. .##  .  ##  ....  ##  ........ ## ### # #+ ................... 
 ..................  ## ...       ##  ......    .........   ## #  +#  ...................
 .................. ##  ....... -##  ..................... # ## .##  .................... 
 .................. .# ........ ###   .....   ............  #  ###   .................... 
 .................. ##  .......   ### ......#    ..........      ##  .................... 
 ..................  ## .    ....   . ..     ### . ............. ##  .................... 
 ..................  ##   ##           . #### -### ............  .# ..................... 
 ................... ##  ###  ######## .     #### ........      ##  ..................... 
 ...................  ##  ####           ####  ## .......  +####+  ...................... 
 .................... ###      ##########         .....   ###     ....................... 
 ....................  ###  ..            ............  ###   ........................... 
 .....................  ###  .... #### .............   ###  ............................. 
 ......................   ##   ..      ..........    ####  .............................. 
 ........................  .##    ............... ### ##  ............................... 
 .........................    ###     ............   ##. ................................ 
 ............................    ####          .    ##   ................................ 
 ...............................   ###########   ###   .................................. 
 .................................    ###########    .................................... 
 ...................................               ...................................... 
 ........................................................................................ 
 ........................................................................................ 
 ........................................................................................ 
 ........................................................................................ 
 """ 

VAULT_TEC_TIPS = [
    "Vault-Tec reminds you: Always back up your data!",
    "Tip: Stay hydrated. Even in the Wasteland.",
    "Remember: War never changes.",
    "Tip: Use 'ls -l' to see more details.",
    "Vault-Tec: Safety is our number one priority.",
    "Tip: You can use TAB for autocompletion.",
    "Vault-Tec recommends: Don't feed the radroaches.",
    "Tip: Use 'history' to see previous commands.",
    "Vault-Tec: Have you tried turning it off and on again?",
    "Tip: 'man <command>' gives you the manual."
]

FALLOUT_FINDINGS = [
    "You found: [Stimpak]",
    "You found: [Bottle of Nuka-Cola]",
    "You found: [Vault Boy Cap]",
    "You found: [Bottlecap]",
    "You found: [Terminal Fragment]",
    "You found: [Old Holotape]",
    "You found: [Empty Syringe]",
    "You found: [Miniature Reactor]",
    "You found: [Pack of RadAway]",
    "You found: [Rusty Key]"
]

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
        self.user = None
        self.host = None


    def print_vault_tip(self):
        return random.choice(VAULT_TEC_TIPS)
    
    def maybe_print_finding(self):
        return random.choice(FALLOUT_FINDINGS)

    def connect_to_gemini(self, prompt, model=None, max_tokens=None, temperature=None, format='json'):
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
            if format == 'json':
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json"
                    }
                )
            else:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt
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
            self.print_console(f"Gemini connection error: {e}")
            return None


    # --- ChatGPT Function ---
    def connect_to_chatgpt(self, role_system_content, prompt,
                           model=None, max_tokens=None, temperature=None, format='json'):
        if model is None:
            model = self.default_model
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is None:
            temperature = self.default_temperature
        client = OpenAI(api_key=self.api_key)
        try:
            if format == 'json':
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": role_system_content},
                        {"role": "user",   "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format={"type": "json"}
                )
            else:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": role_system_content},
                        {"role": "user",   "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature
                )
            self.logger.info(f"OpenAI prompt: {prompt}")
            self.logger.debug(f"OpenAI raw response: {response}")
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"OpenAI connection error: {e}")
            self.print_console(f"OpenAI connection error: {e}")
            return None

    # --- Ollama Function ---
    def connect_to_ollama(self, system_prompt, prompt, model=None, max_tokens=None, temperature=None, ollama_url=None, format="json"):
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

        if format == "json":
            payload["format"] = "json"

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
            self.print_console(f"Ollama connection error: {e}")
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

    def print_console(self, text,color=None):
        if color:
            self.console.print(f"[{color}]{text}[/]")
        else:
            self.console.print(text)

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
        try:
            result = subprocess.run(ssh_command, capture_output=True, text=True)
            return result.stdout, result.returncode
        except Exception as e:
            self.logger.error(f"SSH execution failed: {e}")
            return '', 1
    
    def execute_remote_pexpect(self, command, remote, password=None, auto_yes=False):
        """
        Wykonuje komendę zdalnie przez SSH z obsługą promptów (pexpect).
        Jeśli nie można połączyć się po SSH, zwraca kod 255.
        """
        ssh_cmd = f"ssh {remote} '{command}'"
        child = pexpect.spawn(ssh_cmd, encoding='utf-8', timeout=120)
        output = ""
        try:
            while True:
                i = child.expect([
                    r"[Pp]assword:",           # hasło do ssh
                    r"\(yes/no\)\?",           # fingerprint confirmation
                    r"\[sudo\] password for .*:", # sudo password
                    r"\[Yy]es/[Nn]o",          # interaktywne pytania
                    pexpect.EOF,
                    pexpect.TIMEOUT,
                    r"ssh: connect to host .* port .*: Connection refused",
                    r"ssh: Could not resolve hostname .*",
                    r"ssh: connect to host .* port .*: No route to host",
                    r"ssh: connect to host .* port .*: Operation timed out",
                    r"Permission denied",
                ])
                if i == 0 and password:
                    child.sendline(password)
                elif i == 1:
                    child.sendline("yes")
                elif i == 2 and password:
                    child.sendline(password)
                elif i == 3:
                    if auto_yes:
                        child.sendline("y")
                    else:
                        answer = input("Remote command asks [yes/no]: ")
                        child.sendline(answer)
                elif i == 4 or i == 5:
                    output += child.before
                    break
                elif i in [6, 7, 8, 9, 10]:
                    # SSH connection error
                    output += child.before
                    output += child.after if hasattr(child, "after") else ""
                    #output += "\n[ERROR] SSH connection failed."
                    return output, 255
                output += child.before
        except Exception as e:
            output += f"\n[pexpect error] {e}"
        # --- POPRAWKA: kod wyjścia ---
        exit_code = child.exitstatus
        if exit_code is None:
            if hasattr(child, "signalstatus") and child.signalstatus is not None:
                exit_code = 128 + child.signalstatus
            else:
                exit_code = 1  # domyślny kod błędu
        return output, exit_code

    def check_ai_online(self):
        if self.ai_engine == "openai":
            try:
                client = OpenAI(api_key=self.api_key)
                client.models.list()
                return True, "OpenAI API is online.", self.default_model
            except Exception as e:
                return False, f"OpenAI API unavailable: {e}", self.default_model
        elif self.ai_engine == "ollama":
            try:
                resp = requests.get(self.ollama_url.replace("/api/generate", ""), timeout=5)
                if resp.status_code == 200:
                    return True, "Ollama API is online.", self.ollama_model
                else:
                    return False, f"Ollama API unavailable: HTTP {resp.status_code}", self.ollama_model
            except Exception as e:
                return False, f"Ollama API unavailable: {e}", self.ollama_model
        elif self.ai_engine == "google":
            try:
                client = genai.Client(api_key=self.api_key)
                models = client.models.list()
                if models:
                    return True, "Google Gemini API is online.", self.gemini_model
                else:
                    return False, "Google Gemini API returned no models.", self.gemini_model
            except Exception as e:
                return False, f"Google Gemini API unavailable: {e}", self.gemini_model
        else:
            return False, f"Unknown AI engine: {self.ai_engine}", None
def main():
    agent = term_agent()
    agent.console.print(PIPBOY_ASCII)
    ai_status,mode_owner,ai_model = agent.check_ai_online()    
    agent.console.print("\nWelcome, Vault Dweller, to the Vault 3000.")
    agent.console.print(f"{agent.print_vault_tip()}\n")
    
    if ai_status:
        agent.console.print(f"""AgentAI ({ai_model}) is online. What can I do for you today?\n""")
    else:
        agent.console.print("[red]AgentAI is offline.[/]\n")
        agent.console.print("[red]Please check your API key and network connection.[/]\n")
        sys.exit(1)
    
    try:
        user_goal = agent.console.input("> ")
    except EOFError:
        agent.console.print("\n[red][Vault 3000] EOFError: Unexpected end of file.[/]")
        sys.exit(1)
    except KeyboardInterrupt:
        agent.console.print("\n[red][Vault 3000] Sttopeed by user.[/]")
        sys.exit(1)
    if len(sys.argv) == 2:
        remote = sys.argv[1]
        user = remote.split('@')[0] if '@' in remote else None
        host = remote.split('@')[1] if '@' in remote else remote
        agent.ssh_connection = True
        agent.remote_host = remote
        agent.user = user
        agent.host = host
        agent.console.print(f"VaultAI AI agent started with goal: {user_goal} on {remote}.\n")
    else:
        remote = None
        user = None
        host = None
        agent.ssh_connection = False
        agent.remote_host = None
        agent.user = None
        agent.host = None
        agent.console.print(f"VaultAI AI agent started with goal: {user_goal}")
    runner = VaultAIAgentRunner(agent, user_goal, user=user, host=host)
    try:
        runner.run()
    except KeyboardInterrupt:
        agent.console.print("[red][Vault 3000] Agent przerwany przez użytkownika.[/]")

if __name__ == "__main__":
    main()
