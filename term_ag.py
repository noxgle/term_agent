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
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False


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
            print(f"ValutAI> ERROR: .env file not found in {self.basedir}. Please create one based on .env.copy.")
            sys.exit(1)
        load_dotenv()
        # --- Logging config from .env ---
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        log_file = os.getenv("LOG_FILE", "")
        log_to_console = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"

        # Create thread-safe logging configuration
        from logging.handlers import QueueHandler, QueueListener
        import queue

        log_queue = queue.Queue(-1)  # Infinite queue size
        handlers = []

        # File handler with proper error handling
        if log_file:
            try:
                logs_dir = os.path.join(self.basedir, "logs")
                os.makedirs(logs_dir, exist_ok=True)
                if os.path.isabs(log_file) or os.path.dirname(log_file):
                    log_path = log_file
                else:
                    log_path = os.path.join(logs_dir, log_file)
                file_handler = logging.FileHandler(log_path, encoding="utf-8")
                file_handler.setLevel(getattr(logging, log_level, logging.INFO))
                file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
                handlers.append(file_handler)
            except Exception as e:
                print(f"ValutAI> WARNING: Could not create log file handler: {e}")

        # Console handler
        if log_to_console or not handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(getattr(logging, log_level, logging.INFO))
            console_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
            handlers.append(console_handler)

        # Set up queue-based logging to prevent reentrant calls
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level, logging.INFO))

        # Route all logs through the queue handler only
        queue_handler = QueueHandler(log_queue)
        root_logger.handlers = []
        root_logger.addHandler(queue_handler)

        # Create queue listener for thread-safe logging (sinks)
        queue_listener = QueueListener(log_queue, *handlers)
        queue_listener.start()

        self.logger = logging.getLogger("TerminalAIAgent")
        
        # Parse AI_ENGINE as comma-separated list for multi-engine support
        ai_engine_env = os.getenv("AI_ENGINE", "openai")
        self.ai_engines = [e.strip() for e in ai_engine_env.split(",") if e.strip()]
        self.ai_engine = self.ai_engines[0]  # Primary/first engine for backward compatibility
        self.ai_engine_route = os.getenv("AI_ENGINE_ROUTE", "round-robin").lower()
        
        # Validate routing mode
        if self.ai_engine_route not in ["round-robin", "fallback"]:
            self.logger.warning(f"Invalid AI_ENGINE_ROUTE '{self.ai_engine_route}', defaulting to 'round-robin'")
            self.ai_engine_route = "round-robin"
        
        # Per-engine API keys mapping
        self.engine_api_keys = {
            "openai": os.getenv("OPENAI_API_KEY", ""),
            "google": os.getenv("GOOGLE_API_KEY", ""),
            "ollama-cloud": os.getenv("OLLAMA_CLOUD_TOKEN", ""),
            "openrouter": os.getenv("OPENROUTER_API_KEY", ""),
            "ollama": None,  # Ollama doesn't require API key
            "groq": os.getenv("GROQ_API_KEY", ""),
        }
        
        # Per-engine model configurations
        self.engine_models = {
            "openai": {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.5")),
                "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "150")),
            },
            "ollama": {
                "model": os.getenv("OLLAMA_MODEL", "granite3.3:8b"),
                "temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0.5")),
                "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "150")),
                "url": os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat"),
            },
            "ollama-cloud": {
                "model": os.getenv("OLLAMA_CLOUD_MODEL", "gpt-oss:120b"),
                "temperature": float(os.getenv("OLLAMA_CLOUD_TEMPERATURE", "0.5")),
                "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "150")),
            },
            "google": {
                "model": os.getenv("GOOGLE_MODEL", "gemini-2.0-flash"),
                "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.5")),
                "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "150")),
            },
            "openrouter": {
                "model": os.getenv("OPENROUTER_MODEL", "openrouter/llama-3.1-70b-instruct:free"),
                "temperature": float(os.getenv("OPENROUTER_TEMPERATURE", "0.5")),
                "max_tokens": int(os.getenv("OPENROUTER_MAX_TOKENS", "1000")),
            },
            "groq": {
                "model": os.getenv("GROQ_MODEL", "llama3-8b-8192"),
                "temperature": float(os.getenv("GROQ_TEMPERATURE", "0.5")),
                "max_tokens": int(os.getenv("GROQ_MAX_TOKENS", "1000")),
            },
        }
        
        # API key selection logic (primary engine for backward compatibility)
        self.api_key = self.engine_api_keys.get(self.ai_engine)
        if self.ai_engine in ["openai", "google", "ollama-cloud", "openrouter"] and not self.api_key:
            self.logger.critical(f"You must set the correct API key in the .env file for engine {self.ai_engine}.")
            raise RuntimeError(f"You must set the correct API key in the .env file for engine {self.ai_engine}.")
        
        # Validate API keys for all configured engines
        for engine in self.ai_engines:
            if engine in ["openai", "google", "ollama-cloud", "openrouter"] and not self.engine_api_keys.get(engine):
                self.logger.warning(f"No API key configured for engine '{engine}' - it will fail when used")
        
        # Log multi-engine configuration
        if len(self.ai_engines) > 1:
            self.logger.info(f"Multi-engine mode: {len(self.ai_engines)} engines configured ({', '.join(self.ai_engines)})")
            self.logger.info(f"Routing mode: {self.ai_engine_route}")
        else:
            self.logger.info(f"Single-engine mode: {self.ai_engine}")
        
        # Backward compatibility aliases
        self.default_model = self.engine_models["openai"]["model"]
        self.default_temperature = self.engine_models["openai"]["temperature"]
        self.default_max_tokens = self.engine_models["openai"]["max_tokens"]
        self.ollama_url = self.engine_models["ollama"]["url"]
        self.ollama_model = self.engine_models["ollama"]["model"]
        self.ollama_temperature = self.engine_models["ollama"]["temperature"]
        self.ollama_cloud_model = self.engine_models["ollama-cloud"]["model"]
        self.ollama_cloud_temperature = self.engine_models["ollama-cloud"]["temperature"]
        self.gemini_model = self.engine_models["google"]["model"]
        self.openrouter_model = self.engine_models["openrouter"]["model"]
        self.openrouter_temperature = self.engine_models["openrouter"]["temperature"]
        self.openrouter_max_tokens = self.engine_models["openrouter"]["max_tokens"]
        self.groq_model = self.engine_models["groq"]["model"]
        self.groq_temperature = self.engine_models["groq"]["temperature"]
        self.groq_max_tokens = self.engine_models["groq"]["max_tokens"]
        self.ssh_remote_timeout = int(os.getenv("SSH_REMOTE_TIMEOUT", "120"));
        self.local_command_timeout = int(os.getenv("LOCAL_COMMAND_TIMEOUT", "300"))
        # AI API timeout and retry configuration
        self.ai_api_timeout = int(os.getenv("AI_API_TIMEOUT", "120"))
        self.ai_api_max_retries = int(os.getenv("AI_API_MAX_RETRIES", "3"))
        self.ai_api_retry_delay = float(os.getenv("AI_API_RETRY_DELAY", "2"))
        self.ai_api_retry_backoff = float(os.getenv("AI_API_RETRY_BACKOFF", "2"))
        self.auto_accept = True if os.getenv("AUTO_ACCEPT", "false").lower() == "true" else False
        self.block_dangerous_commands = True if os.getenv("BLOCK_DANGEROUS_COMMANDS", "false").lower() == "true" else False
        # interactive_mode is the inverse of auto_accept; kept for clarity
        self.interactive_mode = not self.auto_accept
        self.auto_explain_command = True if os.getenv("AUTO_EXPLAIN_COMMAND", "false").lower() == "true" else False
        self.console = Console()
        self.ssh_connection = False  # Dodane do obsługi trybu lokalnego/zdalnego
        self.ssh_password = None
        self.remote_host = None
        self.user = None
        self.host = None
        self.port = None

        self.local_linux_distro = self.detect_linux_distribution()
        self.remote_linux_distro = None
        
        # Workspace directory - defaults to pwd or override from .env
        self.workspace = os.getenv("WORKSPACE_DIR", "") or os.getcwd()


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
            stdout, returncode = self.execute_remote_pexpect(cmd, ssh_prefix,timeout=10)
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
            name_stdout, name_returncode = self.execute_remote_pexpect("lsb_release -si", ssh_prefix,timeout=10)
            version_stdout, version_returncode = self.execute_remote_pexpect("lsb_release -sr", ssh_prefix,timeout=10)
            if name_returncode == 0 and version_returncode == 0:
                return (name_stdout.strip(), version_stdout.strip())
        except Exception as e:
            self.logger.warning(f"detect_remote_linux_distribution: lsb_release failed: {e}")

        # 3. Fallback do uname
        try:
            name_stdout, name_returncode = self.execute_remote_pexpect("uname -s", ssh_prefix,timeout=10)
            version_stdout, version_returncode = self.execute_remote_pexpect("uname -r", ssh_prefix,timeout=10)
            if name_returncode == 0 and version_returncode == 0:
                return (name_stdout.strip(), version_stdout.strip())
        except Exception as e:
            self.logger.warning(f"detect_remote_linux_distribution: uname failed: {e}")

        return ("Unknown", "")

    def check_user_privileges(self, remote=None):
        """
        Check user privileges on local or remote system.
        
        Args:
            remote (str, optional): Remote host in format user@host:port
            
        Returns:
            str: "root", "sudo user", "sudo user passwordless", or "user"
        """
        self.logger.info(f"Checking user privileges on {'remote host ' + remote if remote else 'local system'}")
        
        try:
            # Check if user is root (UID 0)
            if remote:
                stdout, returncode = self.execute_remote_pexpect("id -u", remote, timeout=10)
            else:
                stdout, returncode = self.execute_local("id -u", timeout=10)
            
            if returncode == 0:
                uid = stdout.strip()
                if uid == "0":
                    self.logger.info("User is root")
                    return "root"
            
            # User is not root, check sudo privileges
            if remote:
                stdout, returncode = self.execute_remote_pexpect("sudo -l", remote, timeout=10)
            else:
                stdout, returncode = self.execute_local("sudo -l", timeout=10)
            
            if returncode == 0:
                # User has sudo privileges, check if passwordless
                if remote:
                    # For remote, we need to handle the password prompt differently
                    # Try sudo -S -l with empty password to test passwordless sudo
                    child = pexpect.spawn(f"ssh {remote} 'sudo -S -l'", encoding='utf-8', timeout=10)
                    try:
                        i = child.expect([
                            r"[Pp]assword:",
                            r"are not allowed to run sudo",
                            pexpect.EOF,
                            pexpect.TIMEOUT
                        ])
                        if i == 0:
                            # Password required
                            child.sendline("")  # Send empty password
                            child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=5)
                            child.close()
                            self.logger.info("User has sudo privileges but requires password")
                            return "sudo user"
                        elif i == 1:
                            # No sudo privileges
                            child.close()
                            self.logger.info("User does not have sudo privileges")
                            return "user"
                        else:
                            # Passwordless sudo
                            child.close()
                            self.logger.info("User has passwordless sudo privileges")
                            return "sudo user passwordless"
                    except Exception as e:
                        child.close()
                        self.logger.warning(f"Error checking passwordless sudo: {e}")
                        return "sudo user"
                else:
                    # For local, use a simple approach
                    stdout, returncode = self.execute_local("sudo -S -l < /dev/null", timeout=10)
                    if returncode == 0:
                        self.logger.info("User has passwordless sudo privileges")
                        return "sudo user passwordless"
                    else:
                        self.logger.info("User has sudo privileges but requires password")
                        return "sudo user"
            else:
                self.logger.info("User does not have sudo privileges")
                return "user"
                
        except Exception as e:
            self.logger.error(f"Error checking user privileges: {e}")
            return "user"  # Return safe default for regular user
    
    # --- Gemini Function ---

    def connect_to_gemini(self, prompt, model=None, max_tokens=None, temperature=None, format='json', timeout=None):
        """
        Send a prompt to Google Gemini and return the response as a string.
        """
        if model is None:
            model = getattr(self, "gemini_model", "gemini-2.0-flash")
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is None:
            temperature = self.default_temperature
        if timeout is not None:
            timeout = self.ai_api_timeout

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
                           model=None, max_tokens=None, temperature=None, format='json', timeout=None):
        """
        Send a prompt to OpenAI ChatGPT and return the response as a string.
        
        Args:
            role_system_content: System prompt content
            prompt: User prompt content
            model: Model to use (optional)
            max_tokens: Maximum tokens for response (optional)
            temperature: Temperature setting (optional)
            format: Response format (optional)
            timeout: Request timeout in seconds (optional)
        """
        if model is None:
            model = self.default_model
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is None:
            temperature = self.default_temperature
        if timeout is not None:
            timeout = self.ai_api_timeout

        
        client = OpenAI(api_key=self.api_key, timeout=timeout)
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
    def connect_to_ollama(self, system_prompt, prompt, model=None, max_tokens=None, temperature=None, ollama_url=None, format="json", timeout=None):
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
        if timeout is not None:
            timeout = self.ai_api_timeout

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
            resp = requests.post(ollama_url, json=payload, timeout=timeout)
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
                    if isinstance(content, str):
                        return content.strip()
                    else:
                        return str(content)
            # If nothing found, log and return None
            self.logger.error(f"Unexpected Ollama response format: {result}")
            return None

        except Exception as e:
            self.logger.error(f"Ollama connection error: {e}")
            self.print_console(f"Ollama connection error: {e}")
            return None

    # --- Ollama Cloud Function ---
    def connect_to_ollama_cloud(self, system_prompt, prompt, model=None, max_tokens=None, temperature=None, format="json", timeout=None):
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
        if timeout is not None:
            timeout = self.ai_api_timeout


        try:
            client = ollama.Client(
                host="https://ollama.com",
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=timeout
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
                stream=False,
                format=format if format != 'json_object' else 'json'  # Map to ollama format
            )

            self.logger.info(f"Ollama Cloud prompt: {full_prompt}")
            self.logger.debug(f"Ollama Cloud raw response: {response}")
            response_map = None
            if isinstance(response, dict):
                response_map = response
            elif hasattr(response, "model_dump"):
                try:
                    response_map = response.model_dump()
                except Exception:
                    response_map = None
            elif hasattr(response, "dict"):
                try:
                    response_map = response.dict()
                except Exception:
                    response_map = None

            if isinstance(response_map, dict):
                response_text = response_map.get("response")
                thinking_text = response_map.get("thinking")
                response_len = len(response_text) if isinstance(response_text, str) else 0
                thinking_len = len(thinking_text) if isinstance(thinking_text, str) else 0
                done_reason = response_map.get("done_reason")
                self.logger.debug(
                    "Ollama Cloud stats: done_reason=%s response_len=%s thinking_len=%s",
                    done_reason,
                    response_len,
                    thinking_len,
                )

            # Extract the response content
            if isinstance(response_map, dict) and "response" in response_map:
                response_content = response_map["response"]
                if isinstance(response_content, str):
                    return response_content.strip()
                else:
                    return str(response_content)
            elif isinstance(response_map, dict) and "content" in response_map:
                content = response_map["content"]
                if isinstance(content, str):
                    return content.strip()
                else:
                    return str(content)
            else:
                self.logger.error(f"Unexpected Ollama Cloud response format: {response}")
                return None

        except Exception as e:
            self.logger.error(f"Ollama Cloud connection error: {e}")
            self.print_console(f"Ollama Cloud connection error: {e}")
            return None

    # --- OpenRouter Function ---
    def connect_to_openrouter(self, role_system_content, prompt, model=None, max_tokens=None, temperature=None, format='json', timeout=None):
        """
        Send a prompt to OpenRouter API using OpenAI-compatible interface.
        OpenRouter provides access to multiple AI models through a unified API.
        
        Args:
            role_system_content: System prompt content
            prompt: User prompt content
            model: Model to use (optional)
            max_tokens: Maximum tokens for response (optional)
            temperature: Temperature setting (optional)
            format: Response format (optional)
            timeout: Request timeout in seconds (optional)
        """
        if model is None:
            model = self.openrouter_model
        if max_tokens is None:
            max_tokens = self.openrouter_max_tokens
        if temperature is None:
            temperature = self.openrouter_temperature
        if timeout is not None:
            timeout = self.ai_api_timeout
            
        # OpenRouter uses the same API format as OpenAI
        client = OpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=timeout
        )

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
            self.logger.info(f"OpenRouter prompt: {prompt}")
            self.logger.debug(f"OpenRouter raw response: {response}")
            content = response.choices[0].message.content
            if content is None:
                self.logger.error("OpenRouter response content is None")
                return None
            if isinstance(content, str):
                return content.strip()
            return str(content)
        except Exception as e:
            self.logger.error(f"OpenRouter connection error: {e}")
            return None

    # --- Groq Function ---
    def connect_to_groq(self, role_system_content, prompt, model=None, max_tokens=None, temperature=None, format='json', timeout=None):
        """
        Send a prompt to Groq API and return the response as a string.
        Groq provides access to high-performance LLMs through a unified API.
        
        Args:
            role_system_content: System prompt content
            prompt: User prompt content
            model: Model to use (optional)
            max_tokens: Maximum tokens for response (optional)
            temperature: Temperature setting (optional)
            format: Response format (optional)
            timeout: Request timeout in seconds (optional)
        """
        if model is None:
            model = self.groq_model
        if max_tokens is None:
            max_tokens = self.groq_max_tokens
        if temperature is None:
            temperature = self.groq_temperature
        if timeout is not None:
            timeout = self.ai_api_timeout
            
        # Check if Groq is available
        if not GROQ_AVAILABLE:
            self.logger.error("Groq Python package is not installed. Install it with: pip install groq")
            return None

        # Validate API key
        if not self.api_key:
            self.logger.error("No Groq API key configured. Please set GROQ_API_KEY in your .env file.")
            return None

        try:
            client = Groq(api_key=self.api_key, timeout=timeout)
            
            full_prompt = f"{role_system_content}\n\n{prompt}"

            if format == 'json':
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": role_system_content},
                        {"role": "user",   "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    stream=False
                )
            else:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": role_system_content},
                        {"role": "user",   "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False
                )
            self.logger.info(f"Groq prompt: {prompt}")
            self.logger.debug(f"Groq raw response: {response}")
            content = response.choices[0].message.content
            if content is None:
                self.logger.error("Groq response content is None")
                return None
            if isinstance(content, str):
                return content.strip()
            return str(content)
        except Exception as e:
            self.logger.error(f"Groq connection error: {e}")
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

        # Strip port from remote if present (since we use -p flag)
        if ':' in remote:
            remote, _ = remote.rsplit(':', 1)

        # Ensure command is properly escaped
        marker = "__EXITCODE:"
        command = command.replace("'", "'\\''")
        command_with_exit = f"{command}; echo {marker}$?__"
        ssh_cmd_parts = ["ssh"]
        if self.port:
            ssh_cmd_parts.extend(["-p", str(self.port)])
        ssh_cmd_parts.append(remote)
        ssh_cmd_parts.append(f"'{command_with_exit}'")
        ssh_cmd = " ".join(ssh_cmd_parts)
        child = pexpect.spawn(ssh_cmd, encoding='utf-8', timeout=timeout)
        output = ""
        last_expect = None
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
                elif i == 4:  # EOF
                    output += child.before
                    last_expect = "EOF"
                    break
                elif i == 5:  # TIMEOUT
                    output += child.before
                    last_expect = "TIMEOUT"
                    break
                elif i in [6, 7, 8, 9, 10]:
                    output += child.before
                    output += child.after if hasattr(child, "after") else ""
                    return output, 255
                output += child.before
        except Exception as e:
            output += f"\n[pexpect error] {e}"

        # Parse the exit code from the output
        exit_code = None
        match = re.search(rf"{marker}(\d+)__", output)
        if match:
            exit_code = int(match.group(1))
            # Clean the marker from the output
            output = re.sub(rf"{marker}\d+__\s*", "", output)

        # If no marker, map last_expect -> distinct exit codes
        if exit_code is None:
            if last_expect == "TIMEOUT":
                exit_code = 252
            elif last_expect == "EOF":
                exit_code = 254
            else:
                exit_code = 1

        return str(output), exit_code

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
        elif self.ai_engine == "openrouter":
            try:
                client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://openrouter.ai/api/v1"
                )
                client.models.list()
                return True, "OpenRouter API is online.", self.openrouter_model
            except Exception as e:
                return False, f"OpenRouter API unavailable: {e}", self.openrouter_model
        else:
            return False, f"Unknown AI engine: {self.ai_engine}", None

    def check_all_ai_engines_online(self):
        """
        Check the online status of all configured AI engines.
        Returns a comprehensive status report for all engines.
        """
        engine_status = {}
        
        for engine in self.ai_engines:
            try:
                if engine == "openai":
                    try:
                        client = OpenAI(api_key=self.engine_api_keys.get(engine, ""))
                        client.models.list()
                        engine_status[engine] = {
                            "status": "online",
                            "message": "OpenAI API is online.",
                            "model": self.engine_models[engine]["model"]
                        }
                    except Exception as e:
                        engine_status[engine] = {
                            "status": "offline",
                            "message": f"OpenAI API unavailable: {e}",
                            "model": self.engine_models[engine]["model"]
                        }
                        
                elif engine == "ollama":
                    try:
                        resp = requests.get(self.engine_models[engine]["url"].replace("/api/generate", ""), timeout=5)
                        if resp.status_code == 200:
                            engine_status[engine] = {
                                "status": "online",
                                "message": "Ollama API is online.",
                                "model": self.engine_models[engine]["model"]
                            }
                        else:
                            engine_status[engine] = {
                                "status": "offline",
                                "message": f"Ollama API unavailable: HTTP {resp.status_code}",
                                "model": self.engine_models[engine]["model"]
                            }
                    except Exception as e:
                        engine_status[engine] = {
                            "status": "offline",
                            "message": f"Ollama API unavailable: {e}",
                            "model": self.engine_models[engine]["model"]
                        }
                        
                elif engine == "ollama-cloud":
                    try:
                        client = ollama.Client(
                            host="https://ollama.com",
                            headers={'Authorization': f'Bearer {self.engine_api_keys.get(engine, "")}'}
                        )
                        models = client.list()
                        if models:
                            engine_status[engine] = {
                                "status": "online",
                                "message": "Ollama Cloud API is online.",
                                "model": self.engine_models[engine]["model"]
                            }
                        else:
                            engine_status[engine] = {
                                "status": "offline",
                                "message": "Ollama Cloud API returned no models.",
                                "model": self.engine_models[engine]["model"]
                            }
                    except Exception as e:
                        engine_status[engine] = {
                            "status": "offline",
                            "message": f"Ollama Cloud API unavailable: {e}",
                            "model": self.engine_models[engine]["model"]
                        }
                        
                elif engine == "google":
                    try:
                        client = genai.Client(api_key=self.engine_api_keys.get(engine, ""))
                        models = client.models.list()
                        if models:
                            engine_status[engine] = {
                                "status": "online",
                                "message": "Google Gemini API is online.",
                                "model": self.engine_models[engine]["model"]
                            }
                        else:
                            engine_status[engine] = {
                                "status": "offline",
                                "message": "Google Gemini API returned no models.",
                                "model": self.engine_models[engine]["model"]
                            }
                    except Exception as e:
                        engine_status[engine] = {
                            "status": "offline",
                            "message": f"Google Gemini API unavailable: {e}",
                            "model": self.engine_models[engine]["model"]
                        }
                        
                elif engine == "openrouter":
                    try:
                        client = OpenAI(
                            api_key=self.engine_api_keys.get(engine, ""),
                            base_url="https://openrouter.ai/api/v1"
                        )
                        client.models.list()
                        engine_status[engine] = {
                            "status": "online",
                            "message": "OpenRouter API is online.",
                            "model": self.engine_models[engine]["model"]
                        }
                    except Exception as e:
                        engine_status[engine] = {
                            "status": "offline",
                            "message": f"OpenRouter API unavailable: {e}",
                            "model": self.engine_models[engine]["model"]
                        }
                elif engine == "groq":
                    try:
                        from groq import Groq
                        client = Groq(api_key=self.engine_api_keys.get(engine, ""))
                        # Try to list models to check connectivity
                        models = client.models.list()
                        if models:
                            engine_status[engine] = {
                                "status": "online",
                                "message": "Groq API is online.",
                                "model": self.engine_models[engine]["model"]
                            }
                        else:
                            engine_status[engine] = {
                                "status": "offline",
                                "message": "Groq API returned no models.",
                                "model": self.engine_models[engine]["model"]
                            }
                    except Exception as e:
                        engine_status[engine] = {
                            "status": "offline",
                            "message": f"Groq API unavailable: {e}",
                            "model": self.engine_models[engine]["model"]
                        }
                else:
                    engine_status[engine] = {
                        "status": "offline",
                        "message": f"Unknown AI engine: {engine}",
                        "model": None
                    }
                    
            except Exception as e:
                engine_status[engine] = {
                    "status": "offline",
                    "message": f"Unexpected error checking {engine}: {e}",
                    "model": None
                }
        
        return engine_status

    def create_keybindings(self):
        kb = KeyBindings()
        
        @kb.add('c-s')
        def _(event):
            event.current_buffer.validate_and_handle()

        @kb.add('c-a')
        def _(event):
            """
            One-way: switch from interactive -> automatic.
            If already automatic, do nothing (inform user).
            """
            try:
                # Only switch to automatic mode; do not toggle back
                if not self.auto_accept:
                    self.auto_accept = True
                    try:
                        self.interactive_mode = not self.auto_accept
                    except Exception:
                        pass
                    #self.console.print("ValutAI> Mode set to: automatic")
                else:
                    pass
                    # Already automatic; inform user but do not change state
                    # self.console.print("ValutAI> Mode is already automatic")
            except Exception:
                # Swallow any unexpected errors in key handler to avoid breaking prompt
                pass

        return kb

    def load_data_from_file(self, filepath):
        """Load content from a file given its path."""
        try:
            # Remove the // prefix from filepath
            clean_path = filepath.replace('//', '', 1)
            with open(clean_path, 'r') as file:
                return file.read().strip()
        except Exception as e:
            self.print_console(f"ValutAI> ERROR Could not load goal from file '{escape(filepath)}': {escape(str(e))}")
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
  term_ag.py -p, --prompt       # Run Prompt Creator sub-agent
  term_ag.py --help             # Show this help message

Controls:
  Ctrl+S    Submit input
  Ctrl+A    Toggle automatic mode (one-way)
  Ctrl+C    Exit program
        """
    )
    parser.add_argument('remote', nargs='?', help='Remote host in format user@host (optional)')
    parser.add_argument('-p', '--prompt', action='store_true', 
                        help='Run Prompt Creator sub-agent to create a prompt with AI assistance')
    parser.add_argument('--plan', action='store_true',
                        help='Force action plan creation for the task')
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--compact', action='store_true',
                            help='Force compact pipeline (overrides AGENT_MODE/COMPACT_MODE)')
    mode_group.add_argument('--normal', action='store_true',
                            help='Force normal pipeline (disables compact mode)')
    mode_group.add_argument('--hybrid', action='store_true',
                            help='Force hybrid pipeline (compact then fallback to legacy)')

    args = parser.parse_args()
    
    agent = term_agent()
    agent.console.print(PIPBOY_ASCII)
    agent.console.print(f"{agent.print_vault_tip()}\n")
    
    agent.console.print(f"Current workspace directory: {agent.workspace}")

    agent.console.print("""
Controls:
  Ctrl+S    Submit input
  Ctrl+A    Toggle automatic mode (one-way)
  Ctrl+C    Exit program
        """)
    
    # Check status of all configured AI engines
    all_engine_status = agent.check_all_ai_engines_online()

    compact_mode_override = None
    hybrid_mode_override = None
    if args.compact:
        agent_mode = "compact"
        compact_mode_override = True
        hybrid_mode_override = False
    elif args.normal:
        agent_mode = "normal"
        compact_mode_override = False
        hybrid_mode_override = False
    else:
        agent_mode = "hybrid"
        compact_mode_override = True
        hybrid_mode_override = True
    
    agent.console.print("\nWelcome, Vault Dweller, to the Vault 3000.")
    agent.console.print(f"Mode: Linux Terminal AI Agent ({agent_mode} mode)")
    agent.console.print(f"Local Linux distribution is: {agent.local_linux_distro[0]} {agent.local_linux_distro[1]}")
    if agent.auto_accept:
        agent.console.print("Working mode: [green]automatic[/]")
    else:
        agent.console.print("Working mode: [yellow]cooperative.[/]")
    
    # Display AI engine status
    agent.console.print("\n[bold]AI Engine Status:[/bold]")
    all_online = True
    for engine, status_info in all_engine_status.items():
        status_icon = "ONLINE" if status_info["status"] == "online" else "OFFLINE"
        model_info = f" ({status_info['model']})" if status_info.get("model") else ""
        agent.console.print(f"  {status_icon} {engine}: {status_info['message']}{model_info}")
        if status_info["status"] == "offline":
            all_online = False
    
    # Display routing mode
    agent.console.print(f"\n[bold]Routing Mode:[/bold] {agent.ai_engine_route}")
    
    if not all_online:
        agent.console.print("[red]Warning: Some AI engines are offline. The agent may not function properly.[/]")
        # Still allow the agent to start, but warn the user
    else:
        agent.console.print("[green]All configured AI engines are online and ready.[/]")
    


    # Handle --prompt flag: Run Prompt Creator Sub-Agent
    if args.prompt:
        from prompt.PromptCreatorSubAgent import PromptCreatorSubAgent
        from ai.AICommunicationHandler import AICommunicationHandler
        
        ai_handler = AICommunicationHandler(agent, logger=agent.logger)
        prompt_creator = PromptCreatorSubAgent(
            terminal=agent,
            ai_handler=ai_handler,
            logger=agent.logger
        )
        
        try:
            final_prompt, should_execute = prompt_creator.run(prompt_for_agent=True)
            
            if should_execute and final_prompt:
                # Run VaultAIAgentRunner with the created prompt
                agent.console.print(f"\nExecuting created prompt with VaultAI Agent...")
                runner = VaultAIAgentRunner(
                    agent,
                    final_prompt,
                    compact_mode=compact_mode_override,
                    hybrid_mode=hybrid_mode_override,
                )
                runner.run()
                agent.console.print(f"\n{agent.maybe_print_finding()}")
            elif final_prompt:
                agent.console.print("\n[yellow]Prompt created but not executed.[/]")
                agent.console.print(f"\n[cyan]Your prompt:[/]\n{final_prompt}")
            else:
                agent.console.print("\n[yellow]No prompt was created.[/]")
                
        except KeyboardInterrupt:
            agent.console.print("\n[red]ValutAI> Prompt Creator interrupted by user.[/]")
            sys.exit(1)
        except Exception as e:
            agent.console.print(f"ValutAI> ERROR: {e}", style="red", markup=False)
            sys.exit(1)
        
        return

    if args.remote:
        remote = args.remote
        if '@' in remote:
            user_part, host_part = remote.split('@', 1)
            user = user_part
            if ':' in host_part:
                host, port_str = host_part.split(':', 1)
                port = int(port_str)
            else:
                host = host_part
                port = None
        else:
            user = None
            if ':' in remote:
                host, port_str = remote.split(':', 1)
                port = int(port_str)
            else:
                host = remote
                port = None
        agent.ssh_connection = True
        agent.remote_host = remote
        agent.user = user
        agent.host = host
        agent.port = port if port is not None else None
        try:
            output, returncode = agent.execute_remote_pexpect("echo Connection successful", remote, auto_yes=agent.auto_accept, timeout=5)
            if agent.ssh_password is not None:
                ask_input= input("Do you want to use passwordless SSH login in the future? (y/n): ")
                if ask_input.lower() == 'y':
                    agent.console.print(f"[yellow]ValutAI> Setting up passwordless SSH login to {remote}...[/]")
                    try:
                        cmd = ["ssh-copy-id"]
                        if agent.port:
                            cmd.extend(["-p", str(agent.port)])
                        clean_remote = remote
                        if ':' in clean_remote:
                            clean_remote, _ = clean_remote.rsplit(':', 1)
                        cmd.append(clean_remote)
                        subprocess.run(cmd, check=True)
                        agent.console.print(f"[green]ValutAI> Passwordless SSH login set up successfully.[/]")
                    except subprocess.CalledProcessError as e:
                        agent.console.print(f"ValutAI> ERROR: ssh-copy-id failed: {e}", style="red", markup=False)
                    except Exception as e:
                        agent.console.print(f"ValutAI> ERROR: Unexpected error during ssh-copy-id: {e}", style="red", markup=False)
            if returncode != 0:
                agent.console.print(f"[red]ValutAI> ERROR: Could not connect to remote host {remote}.[/]")
                if output:
                    agent.console.print(f"[red]ValutAI> Details: {output}[/]")
                sys.exit(1)

            agent.remote_linux_distro = agent.detect_remote_linux_distribution(host, user=user)
        except KeyboardInterrupt:
            agent.console.print("[red]ValutAI> Agent interrupted by user.[/]")
            sys.exit(1)
        except Exception as e:
            agent.console.print(f"ValutAI> ERROR: SSH connection to {remote} failed: {e}", style="red", markup=False)
            sys.exit(1)

        agent.console.print(f"Remote Linux distribution is: {agent.remote_linux_distro[0]} {agent.remote_linux_distro[1]}")
        agent.console.print("\n\nValutAI> What can I do for you today? Enter your goal and press [cyan]Ctrl+S[/] to start!")
        input_text = f"{user}@{host}:{port}" if port else f"{user}@{host}" if user else f"{host}:{port}" if port else host
    else:
        remote = None
        user = None
        host = None
        agent.ssh_connection = False
        agent.remote_host = None
        agent.user = None
        agent.host = None
        input_text = "local"
        agent.console.print("\n\n\nValutAI> What can I do for you today? Enter your goal and press [cyan]Ctrl+S[/] to start!")
    
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
        agent.console.print("\n[red]ValutAI> EOFError: Unexpected end of file.[/]")
        sys.exit(1)
    except KeyboardInterrupt:
        agent.console.print("\n[red]ValutAI> Stopped by user.[/]")
        sys.exit(1)

    runner = VaultAIAgentRunner(
        agent,
        user_input_text,
        user=user,
        host=host,
        compact_mode=compact_mode_override,
        hybrid_mode=hybrid_mode_override,
    )
    
    # Check for --plan flag or [plan] keyword in prompt
    force_plan = args.plan
    if not force_plan:
        # Check for [plan] or plan: keyword in the prompt
        prompt_lower = user_input_text.lower()
        if prompt_lower.startswith('[plan]') or prompt_lower.startswith('plan:'):
            force_plan = True
            # Remove the keyword from the goal
            if user_input_text.lower().startswith('[plan]'):
                user_input_text = user_input_text[6:].strip()
            elif user_input_text.lower().startswith('plan:'):
                user_input_text = user_input_text[5:].strip()
            runner.user_goal = user_input_text
            agent.console.print("[cyan]Plan mode: Action plan will be created automatically.[/]")
    
    runner.force_plan = force_plan
    
    try:
        runner.run()
        agent.console.print(f"\n{agent.maybe_print_finding()}")
    except KeyboardInterrupt:
        agent.console.print("[red]ValutAI> Agent interrupted by user.[/]")
        sys.exit(1)
    except Exception as e:
        agent.console.print(f"ValutAI> ERROR: Unexpected error: {e}", style="red", markup=False)
        sys.exit(1)

if __name__ == "__main__":
    main()
