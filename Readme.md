```
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
```

# Vault 3000 Terminal Agent

**Vault 3000** is a Fallout-inspired terminal AI assistant that answers user questions, helps with Linux commands, supports various AI engine (OpenAI, Google Gemini, Ollama), and can work locally or remotely via SSH.

## Features

- **Chat mode**: Talk to Vault 3000 in the terminal, with conversation memory.
- **Task execution and automation**: The agent can perform tasks and commands based on user goals.
- **Multiple AI engine support**: OpenAI (ChatGPT), Google Gemini, Ollama.
- **Execute commands locally and remotely (SSH)**.
- **Configurable via `.env`**.
- **Logging and colored console (Rich)**.
- **Fallout/Pip-Boy theme**.

## Requirements

- Python 3.9+
- API key for the selected AI engine (OpenAI, Google Gemini, Ollama)
- `.env` configuration file (see below)

## Installation

```bash
git clone https://github.com/noxgle/term_agent.git
cd vault3000
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## `.env` Configuration

Example `.env.copy` file:

```
AI_ENGINE=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.5
OPENAI_MAX_TOKENS=150

GOOGLE_API_KEY=...
GOOGLE_MODEL=gemini-2.0-flash

OLLAMA_URL=http://localhost:11434/api/chat
OLLAMA_MODEL=granite3.3:8b
OLLAMA_TEMPERATURE=0.5

LOG_LEVEL=INFO
LOG_TO_CONSOLE=true
```

## Usage

### Chat mode (questions, dialog):

```bash
python term_ask.py
```

### Agent mode (automation, tasks):

```bash
python term_ag.py
```

### Remote agent mode (SSH):

```bash
python term_ag.py user@host
```

## Files

- `term_ag.py` – main agent, automation, tasks, agent class, AI and command handling.
- `term_ask.py` – AI chat, questions, dialogs.
- `VaultAIAskRunner.py` – chat logic.
- `VaultAiAgentRunner.py` – agent logic.

## Alias

1. **Add short aliases to your `~/.bashrc` (or `~/.zshrc`):**

```bash
alias ask='cd /home/username/term_agent && source .venv/bin/activate && python term_ask.py'
alias ag='cd /home/username/term_agent && source .venv/bin/activate && python term_ag.py'
```

2. **Reload aliases:**

```bash
source ~/.bashrc
```

3. **Usage:**

- Start chat:  
  ```bash
  ask
  ```
- Start agent:  
  ```bash
  ag
  ```

> **Tip:** Change the path `/home/username/term_agent` to your own if the project is in a different location.

> **Warning:**  
> The agent can execute arbitrary shell commands (locally or remotely via SSH) based on user input or AI suggestions.  
> **Always review and understand the commands before running the agent.**  
> Using this tool may be unsafe on production systems or with sensitive data.  
> You are responsible for any actions performed by the agent on your system.

## License

MIT

---

Vault 3000 – Your Fallout-inspired terminal AI assistant!