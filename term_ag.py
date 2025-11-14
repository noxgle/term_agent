import requests
import logging
import os
import subprocess
import sys
import random
import argparse
from dotenv import load_dotenv
from openai import OpenAI
from google import genai
import ollama
from rich.console import Console
from rich.markup import escape
from VaultAiAgentRunner import VaultAIAgentRunner
import pexpect
import re
from prompt_toolkit import prompt
from prompt_toolkit.key_binding import KeyBindings

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
 ..................find me on: https://www.linkedin.com/in/sebastian-wielgosz-linux-admin
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
        self.basedir = os.path.dirname(os.path.abspath(__file__))
        # check if .env file exists in the basedir
        if not os.path.isfile(os.path.join(self.basedir, '.env')):
            print(f"[Vault 3000] ERROR: .env file not found in {self.basedir}. Please create one based on .env.copy.")
            sys.exit(1)
        load_dotenv()
        # --- Logging config from .env ---
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        log_file = os.getenv("LOG_FILE", "")
        log_to_console = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"
        handlers = []
        if log_file:
            handlers.append(logging.FileHandler(f"{self.basedir}/{log_file}", encoding="utf-8"))
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
        elif self.ai_engine == "ollama-cloud":
            self.api_key = os.getenv("OLLAMA_CLOUD_TOKEN", "")
        else:
            self.api_key = None
        if self.ai_engine in ["openai", "google", "ollama-cloud"] and not self.api_key:
            self.logger.critical(f"You must set the correct API key in the .env file for engine {self.ai_engine}.")
            raise RuntimeError(f"You must set the correct API key in the .env file for engine {self.ai_engine}.")
        
        self.default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.default_temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.5"))
        self.default_max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "150"))
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "granite3.3:8b")
        self.ollama_temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.5"))
        self.ollama_cloud_model = os.getenv("OLLAMA_CLOUD_MODEL", "gpt-oss:120b")
        self.ollama_cloud_temperature = float(os.getenv("OLLAMA_CLOUD_TEMPERATURE", "0.5"))
        self.gemini_model = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash")
        self.ssh_remote_timeout = int(os.getenv("SSH_REMOTE_TIMEOUT", "120"))
        self.local_command_timeout = int(os.getenv("LOCAL_COMMAND_TIMEOUT", "300"))
        self.auto_accept = True if os.getenv("AUTO_ACCEPT", "false").lower() == "true" else False
        self.auto_explain_command = True if os.getenv("AUTO_EXPLAIN_COMMAND", "false").lower() == "true" else False
        self.console = Console()
        self.ssh_connection = False  # Dodane do obsługi trybu lokalnego/zdalnego
        self.ssh_password = None
        self.remote_host = None
        self.user = None
        self.host = None

        self.local_linux_distro = self.detect_linux_distribution()
        self.remote_linux_distro = None

       


    def print_vault_tip(self):
        return random.choice(VAULT_TEC_TIPS)
    
    def maybe_print_finding(self):
        return random.choice(FALLOUT_FINDINGS)
    
    
    def detect_linux_distribution(self):
        """
        Returns a tuple: (distribution_name, version)
        Tries /etc/os-release, then lsb_release, then fallback to uname.
        """
        # Try /etc/os-release
        os_release_path = "/etc/os-release"
        if os.path.isfile(os_release_path):
            with open(os_release_path) as f:
                lines = f.readlines()
            info = {}
            for line in lines:
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    info[key] = val.strip('"')
            name = info.get("NAME", "")
            version = info.get("VERSION_ID", info.get("VERSION", ""))
            if name:
                return (name, version)
        
        # Try lsb_release
        try:
            name = subprocess.check_output(["lsb_release", "-si"], text=True).strip()
            version = subprocess.check_output(["lsb_release", "-sr"], text=True).strip()
            return (name, version)
        except Exception:
            pass
    
        # Fallback to uname
        try:
            name = subprocess.check_output(["uname", "-s"], text=True).strip()
            version = subprocess.check_output(["uname", "-r"], text=True).strip()
            return (name, version)
        except Exception:
            pass
    
        return ("Unknown", "")
    
    def detect_remote_linux_distribution(self, remote_host, user=None):
        """
        Wykrywa dystrybucję Linuksa na zdalnej maszynie przez SSH.
        Zwraca tuple: (distribution_name, version)
        """
        ssh_prefix = f"{user}@{remote_host}" if user else remote_host

        # 1. Check /etc/os-release
        try:
            cmd = "cat /etc/os-release"
            stdout, returncode = self.execute_remote_pexpect(cmd, ssh_prefix)
            if returncode == 0:
                info = {}
                for line in stdout.splitlines():
                    if "=" in line:
                        key, val = line.strip().split("=", 1)
                        info[key] = val.strip('"')
                name = info.get("NAME", "")
                version = info.get("VERSION_ID", info.get("VERSION", ""))
                if name:
                    return (name, version)
        except Exception as e:
            self.logger.warning(f"detect_remote_linux_distribution: /etc/os-release failed: {e}")

        # 2. Check lsb_release
        try:
            name_stdout, name_returncode = self.execute_remote_pexpect("lsb_release -si", ssh_prefix)
            version_stdout, version_returncode = self.execute_remote_pexpect("lsb_release -sr", ssh_prefix)
            if name_returncode == 0 and version_returncode == 0:
                return (name_stdout.strip(), version_stdout.strip())
        except Exception as e:
            self.logger.warning(f"detect_remote_linux_distribution: lsb_release failed: {e}")

        # 3. Fallback do uname
        try:
            name_stdout, name_returncode = self.execute_remote_pexpect("uname -s", ssh_prefix)
            version_stdout, version_returncode = self.execute_remote_pexpect("uname -r", ssh_prefix)
            if name_returncode == 0 and version_returncode == 0:
                return (name_stdout.strip(), version_stdout.strip())
        except Exception as e:
            self.logger.warning(f"detect_remote_linux_distribution: uname failed: {e}")

        return ("Unknown", "")
    
    # --- Gemini Function ---

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
                           model=None, max_tokens=None, temperature=None, format='json_object'):
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
                    response_format={"type": "json_object"}
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

    # --- Ollama Cloud Function ---
    def connect_to_ollama_cloud(self, system_prompt, prompt, model=None, max_tokens=None, temperature=None, format="json"):
        """
        Send a prompt to Ollama Cloud API using the official ollama client.
        Based on the example in test_ol_cloud.py.
        """
        if model is None:
            model = self.ollama_cloud_model
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is None:
            temperature = self.ollama_cloud_temperature

        try:
            client = ollama.Client(
                host="https://ollama.com",
                headers={'Authorization': f'Bearer {self.api_key}'}
            )
            # Compose the prompt with system message for context
            full_prompt = f"{system_prompt}\n\n{prompt}"

            # Use generate method, as per the example
            response = client.generate(
                model=model,
                prompt=full_prompt,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens
                },
                format=format if format != 'json_object' else 'json'  # Map to ollama format
            )

            self.logger.info(f"Ollama Cloud prompt: {full_prompt}")
            self.logger.debug(f"Ollama Cloud raw response: {response}")

            # Extract the response content
            if 'response' in response:
                return response['response'].strip()
            elif 'content' in response:
                return response['content'].strip()
            else:
                self.logger.error(f"Unexpected Ollama Cloud response format: {response}")
                return None

        except Exception as e:
            self.logger.error(f"Ollama Cloud connection error: {e}")
            self.print_console(f"Ollama Cloud connection error: {e}")
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

    def print_console(self, text,color=None):
        self.console.print(text, style=color, markup=False)

    def execute_local(self, command, timeout=None):
        """
        Execute a command locally and return (output, exit_code).
        Returns tuple: (output, exit_code)
        """
        # Fix timeout logic - use default timeout when none provided
        if timeout is None:
            timeout = self.local_command_timeout

        self.logger.info(f"Executing local command: {command}")
        try:
            if timeout == 0:
                timeout = None  # No timeout
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            self.logger.debug(f"Local command output: {result.stdout}")
            if result.stderr:
                self.logger.warning(f"Local command stderr: {result.stderr}")
            return result.stdout, result.returncode
        except subprocess.TimeoutExpired as e:
            self.logger.error(f"Local command timed out after {timeout}s: {command}")
            return f'Command timed out after {timeout} seconds', 124
        except Exception as e:
            self.logger.error(f"Local command execution failed: {e}")
            return str(e), 1    
        
    def execute_remote_pexpect(self, command, remote, password=None, auto_yes=False, timeout=None):
        # Use cached password if available
        if self.ssh_password:
            password = self.ssh_password

        if timeout is None:
            timeout = self.ssh_remote_timeout

        # Ensure command is properly escaped
        marker = "__EXITCODE:"
        command = command.replace("'", "'\\''")
        command_with_exit = f"{command}; echo {marker}$?__"
        ssh_cmd = f"ssh {remote} '{command_with_exit}'"
        child = pexpect.spawn(ssh_cmd, encoding='utf-8', timeout=timeout)
        output = ""
        try:
            while True:
                i = child.expect([
                    r"[Pp]assword:",
                    r"Are you sure you want to continue connecting \(yes/no/\[fingerprint]\)\?",
                    r"\[sudo\] password for .*:",
                    r"\[Yy]es/[Nn]o",
                    pexpect.EOF,
                    pexpect.TIMEOUT,
                    r"ssh: connect to host .* port .*: Connection refused",
                    r"ssh: Could not resolve hostname .*",
                    r"ssh: connect to host .* port .*: No route to host",
                    r"ssh: connect to host .* port .*: Operation timed out",
                    r"ssh: connect to host .* port .*: Permission denied",
                ])
                if i == 0:  # SSH Password or Sudo password
                    if password:
                        child.sendline(password)
                    else:
                        password_prompted = prompt("Enter SSH password: ", is_password=True)
                        self.ssh_password = password_prompted  # Cache the password
                        password = password_prompted
                        child.sendline(password)
                elif i == 1:  # Host key verification
                    # Display the fingerprint to the user
                    self.print_console(child.before + child.after)
                    child.sendline("yes")
                elif i == 2:  # Sudo password prompt
                    if password:
                        child.sendline(password)
                    else:
                        password_prompted = prompt("Enter sudo password: ", is_password=True)
                        self.ssh_password = password_prompted # Cache the password
                        password = password_prompted
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
                    output += child.before
                    output += child.after if hasattr(child, "after") else ""
                    return output, 255
                output += child.before
        except Exception as e:
            output += f"\n[pexpect error] {e}"

        # Parase the exit code from the output
        exit_code = 1
        match = re.search(rf"{marker}(\d+)__", output)
        if match:
            exit_code = int(match.group(1))
            # Clean the marker from the output 
            output = re.sub(rf"{marker}\d+__\s*", "", output)
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
        elif self.ai_engine == "ollama-cloud":
            try:
                client = ollama.Client(
                    host="https://ollama.com",
                    headers={'Authorization': f'Bearer {self.api_key}'}
                )
                # Try to list models to check connectivity
                models = client.list()
                if models:
                    return True, "Ollama Cloud API is online.", self.ollama_cloud_model
                else:
                    return False, "Ollama Cloud API returned no models.", self.ollama_cloud_model
            except Exception as e:
                return False, f"Ollama Cloud API unavailable: {e}", self.ollama_cloud_model
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

    def create_keybindings(self):
        kb = KeyBindings()
        
        @kb.add('c-s')
        def _(event):
            event.current_buffer.validate_and_handle()        
        return kb

    def load_data_from_file(self, filepath):
        """Load content from a file given its path."""
        try:
            # Remove the // prefix from filepath
            clean_path = filepath.replace('//', '', 1)
            with open(clean_path, 'r') as file:
                return file.read().strip()
        except Exception as e:
            self.print_console(f"[Vault 3000] ERROR Could not load goal from file '{escape(filepath)}': {escape(str(e))}")
            sys.exit(1)

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

def main():
    parser = argparse.ArgumentParser(
        description="Vault 3000 - Linux Terminal AI Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage:
  term_ag.py                    # Run locally
  term_ag.py user@host          # Run remotely via SSH
  term_ag.py --help             # Show this help message

Controls:
  Ctrl+S    Submit input
  Ctrl+C    Exit program
        """
    )
    parser.add_argument('remote', nargs='?', help='Remote host in format user@host (optional)')

    args = parser.parse_args()

    agent = term_agent()
    agent.console.print(PIPBOY_ASCII)
    agent.console.print(f"{agent.print_vault_tip()}\n")
    ai_status, mode_owner, ai_model = agent.check_ai_online()
    agent.console.print("\nWelcome, Vault Dweller, to the Vault 3000.")
    agent.console.print("Mode: Linux Terminal AI Agent.")
    agent.console.print(f"Local Linux distribution is: {agent.local_linux_distro[0]} {agent.local_linux_distro[1]}")

    if ai_status:
        agent.console.print(f"""Model: {ai_model} is online.""")
    else:
        agent.console.print("[red]Model: is offline.[/]\n")
        agent.console.print("[red]Please check your API key and network connection.[/]\n")
        sys.exit(1)

    if args.remote:
        remote = args.remote
        user = remote.split('@')[0] if '@' in remote else None
        host = remote.split('@')[1] if '@' in remote else remote
        agent.ssh_connection = True
        agent.remote_host = remote
        agent.user = user
        agent.host = host
        try:
            output, returncode = agent.execute_remote_pexpect("echo Connection successful", remote, auto_yes=agent.auto_accept)
            if agent.ssh_password is not None:
                ask_input= input("Do you want to use passwordless SSH login in the future? (y/n): ")
                if ask_input.lower() == 'y':
                    agent.console.print(f"[yellow][Vault 3000] Setting up passwordless SSH login to {remote}...[/]")
                    try:
                        subprocess.run(["ssh-copy-id", remote], check=True)
                        agent.console.print(f"[green][Vault 3000] Passwordless SSH login set up successfully.[/]")
                    except subprocess.CalledProcessError as e:
                        agent.console.print(f"[Vault 3000] ERROR: ssh-copy-id failed: {e}", style="red", markup=False)
                    except Exception as e:
                        agent.console.print(f"[Vault 3000] ERROR: Unexpected error during ssh-copy-id: {e}", style="red", markup=False)
            if returncode != 0:
                agent.console.print(f"[red][Vault 3000] ERROR: Could not connect to remote host {remote}.[/]")
                agent.console.print(f"[red][Vault 3000] Details: {output}[/]")
                sys.exit(1)

            agent.remote_linux_distro = agent.detect_remote_linux_distribution(host, user=user)
        except KeyboardInterrupt:
            agent.console.print("[red][Vault 3000] Agent interrupted by user.[/]")
            sys.exit(1)
        except Exception as e:
            agent.console.print(f"[Vault 3000] ERROR: SSH connection to {remote} failed: {e}", style="red", markup=False)
            sys.exit(1)

        agent.console.print(f"Remote Linux distribution is: {agent.remote_linux_distro[0]} {agent.remote_linux_distro[1]}")
        agent.console.print("\n\nValutAI> What can I do for you today? Enter your goal and press [cyan]Ctrl+S[/] to start!")
        input_text = f"{user}@{host}" if user else host
    else:
        remote = None
        user = None
        host = None
        agent.ssh_connection = False
        agent.remote_host = None
        agent.user = None
        agent.host = None
        input_text = "local"
        agent.console.print("\n\nValutAI> What can I do for you today? Enter your goal and press [cyan]Ctrl+S[/] to start!")
    
    try:
        user_input = prompt(
                    f"{input_text}> ", 
                    multiline=True,
                    prompt_continuation=lambda width, line_number, is_soft_wrap: "... ",
                    enable_system_prompt=True,
                    key_bindings=agent.create_keybindings()
                )
        user_input_text = agent.process_input(user_input)

    except EOFError:
        agent.console.print("\n[red][Vault 3000] EOFError: Unexpected end of file.[/]")
        sys.exit(1)
    except KeyboardInterrupt:
        agent.console.print("\n[red][Vault 3000] Stopped by user.[/]")
        sys.exit(1)

    runner = VaultAIAgentRunner(agent, user_input_text, user=user, host=host)
    try:
        runner.run()
        agent.console.print(f"\n{agent.maybe_print_finding()}")
    except KeyboardInterrupt:
        agent.console.print("[red][Vault 3000] Agent interrupted by user.[/]")
        sys.exit(1)
    except Exception as e:
        agent.console.print(f"[Vault 3000] ERROR: Unexpected error: {e}", style="red", markup=False)
        sys.exit(1)

if __name__ == "__main__":
    main()
