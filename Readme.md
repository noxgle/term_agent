[![LINUX TERMINAL AGENT](https://img.youtube.com/vi/UeDNO0pWK9c/0.jpg)](https://www.youtube.com/embed/UeDNO0pWK9c)

## Table of Contents

- [Features](#features)
- [AI Model Comparison](#ai-model-comparison)
- [Terminal Agent Capabilities](#terminal-agent-capabilities)
- [Prompt Creator](#prompt-creator)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#env-configuration)
- [Usage](#usage)
- [Files](#files)
- [Aliases](#aliases)
- [Examples](#example-chat)
- [TODO](#todo)
- [License](#license)

## Features

- **Chat mode**: Talk to Vault 3000 in the console, with conversation memory.
- **Task automation**: The agent can perform tasks and commands based on user goals.
- **Multiple AI engine support**: OpenAI (ChatGPT), Google Gemini, Ollama (local and cloud), OpenRouter (unified API for multiple models).
- **Local and remote execution (SSH)**: Run commands on your machine or remote hosts.
- **Configurable via `.env`**: Easily switch engines and settings.
- **Logging and colored console (Rich)**: Fallout/Pip-Boy theme for a unique retro look.
- **Advanced Prompt Creator**: Interactive tool for building precise, detailed prompts for AI agents. Guides you step-by-step, asks clarifying questions, and combines your answers into a single, actionable prompt. Supports multiline input (Ctrl+S), Fallout-style colors, and easy confirmation with Enter.

- **Interactive -> Automatic mode**: Press Ctrl+A at the prompt to switch the agent from interactive mode (agent asks for confirmation before running suggested bash commands) to automatic mode (agent executes suggested commands without asking). This shortcut is one-way: it only switches from interactive to automatic during a session.

## AI Model Comparison

Before configuring your AI engine, check out the comprehensive comparison of AI models at [Artificial Analysis](https://artificialanalysis.ai/models). This independent analysis covers intelligence benchmarks, performance metrics, and pricing across 337+ models from major providers including OpenAI, Google, Anthropic, and others. It's an invaluable resource for choosing the right AI model for your specific needs and budget.

## Terminal Agent Capabilities

The main terminal agent is a powerful tool designed to streamline your command-line operations. It allows you to perform a wide range of tasks, including:
- **Linux Administration**: Manage your system with ease.
- **Security**: Implement and maintain security measures.
- **Log Analysis**: Monitor and analyze system logs effectively.
- **Script Creation**: Develop custom scripts for automation.
- **Configuration Files**: Manage configuration files, such as those for Ansible.
- **Software Development**: Build and deploy applications.

## Prompt Creator

The **Prompt Creator** is an interactive assistant that helps you build high-quality prompts for AI agents.

**How it works:**
- Guides you step-by-step, asking clarifying questions to gather all necessary details.
- Combines your answers into a single, coherent prompt draft.
- Supports multiline input (accept with Ctrl+S) and Fallout-style color themes.
- Lets you confirm or add more details at each step with Enter or Ctrl+S.
- Ensures your final prompt is precise, actionable, and ready for use with any supported AI engine.



## Requirements

- Python 3.9+
- API key for the selected AI engine
- `.env` configuration file (see below)
- Linux or macOS

## Installation


### Quick Install (using install script)

```bash
curl -O https://raw.githubusercontent.com/noxgle/term_agent/main/install_term_agent.sh
chmod +x install_term_agent.sh
./install_term_agent.sh
```

The install script will:
- Check Python version requirements (3.9+)
- Create and configure a virtual environment
- Install all required packages
- Create initial `.env` file from template
- Optionally add convenient aliases to your shell configuration:
  - `ask` - to start chat mode
  - `ag` - to start agent mode

### Manual Installation

```bash
git clone https://github.com/noxgle/term_agent.git
cd term_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Docker Installation

This project can also be installed and run using Docker for a containerized environment with SSH access.

#### Prerequisites

- Docker installed on your system
- Docker Compose installed
- Your `.env` file with API keys (copy from .env.copy and fill in your keys)

#### Quick Setup

```bash
# Copy and configure your .env file
cp .env.copy .env
# Edit .env with your API keys (OpenAI, Google, etc.)

# Build the container
docker-compose up -d

# Alternative: build manually
docker build -t vault3000/term-agent .
docker run -d -p 2222:22 --name term-agent vault3000/term-agent
```

#### Connect and Use

```bash
# Connect to the container via SSH
ssh root@localhost -p 2222
# Password: 123456 (change this in production)

# Once connected, use the same commands as regular installation
ag      # Start the AI agent
ask     # Start chat mode
prom    # Start prompt creator
```

For detailed Docker setup instructions, including advanced usage, troubleshooting, and security notes, see [Docker_README.md](Docker_README.md).

## `.env` Configuration

Copy `.env.copy` to `.env` and paste your API key(s).

Example `.env` file:
```
# engine options: openai, ollama, ollama-cloud, google, openrouter
AI_ENGINE=ollama

# openai configuration
OPENAI_API_KEY=openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.5
OPENAI_MAX_TOKENS=1000

# ollama configuration
# granite3.3:8b,gemma3.3:12b,cogito:8b,qwen3:8b
OLLAMA_URL=http://192.168.200.202:11434/api/generate
OLLAMA_MODEL=cogito:8b
OLLAMA_TEMPERATURE=0.5

# ollama cloud configuration (hosted service at https://ollama.com)
OLLAMA_CLOUD_TOKEN=ollama_cloud_token_here
OLLAMA_CLOUD_MODEL=gpt-oss:120b
OLLAMA_CLOUD_TEMPERATURE=0.5

# google configuration
# gemini-2.5-pro-exp-03-25,gemini-2.0-flash
GOOGLE_MODEL=gemini-2.5-flash-preview-05-20
GOOGLE_API_KEY=google_api_key_here

# openrouter configuration (unified API for multiple AI models)
OPENROUTER_API_KEY=openrouter_api_key_here
OPENROUTER_MODEL=openrouter/llama-3.1-70b-instruct:free
OPENROUTER_TEMPERATURE=0.5
OPENROUTER_MAX_TOKENS=1000

# local timeout in seconds for command execution, 0 means no timeout
LOCAL_COMMAND_TIMEOUT=300
# remote ssh timeout in seconds for command execution, 0 means no timeout
SSH_REMOTE_TIMEOUT=300
# interactive mode or auto (accept commands without confirmation)
AUTO_ACCEPT=false
# auto explain generated commands before execution
AUTO_EXPLAIN_COMMAND=true

 # logging configuration, options: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO
LOG_FILE=app.log
LOG_TO_CONSOLE=false
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

### Prompt Creator (interactive prompt builder):

```bash
python PromptCreator.py
```

### Loading a prompt/goal from a file

You can load a prompt or goal from a file by typing:

```
/path/to/your_prompt.txt
```

The agent will read the file and use its contents as your goal or question.

## Files

- `term_ag.py` – main agent, automation, tasks, agent class, AI and command handling.
- `term_ask.py` – AI chat, questions, dialogs.
- `VaultAIAskRunner.py` – chat logic.
- `VaultAiAgentRunner.py` – agent logic.
- `PromptCreator.py` – interactive prompt builder.


The agent will read the file and use its contents as your goal or question.

### Aliases

Add short aliases to your `~/.bashrc` (or `~/.zshrc`):

```bash
alias ask='cd /home/username/term_agent && source .venv/bin/activate && python term_ask.py'
alias ag='cd /home/username/term_agent && source .venv/bin/activate && python term_ag.py'
alias prom='cd /home/username/term_agent && source .venv/bin/activate && python PromptCreator.py'
```

Reload aliases:

```bash
source ~/.bashrc
```

> **Tip:** For the best experience with remote agent mode (SSH), set up SSH key-based authentication on your target servers. This allows the agent to execute commands without repeatedly prompting for a password and improves both security and usability.
> **Tip:** Change the path `/home/username/term_agent` to your own if the project is in a different location.

> **Warning:**
> The agent can execute arbitrary shell commands (locally or remotely via SSH) based on user input or AI suggestions.
> **Always review and understand the commands before running the agent.**
> Using this tool may be unsafe on production systems or with sensitive data.
> You are responsible for any actions performed by the agent on your system.

> **Note:**
> The larger and more advanced the AI model you use (e.g., GPT-4, Gemini 1.5, or large Ollama models), the better and more reliable the agent's results will be. Smaller or older models may not handle complex tasks or multi-step automation as effectively.

## TODO

- SSH connections to non-standard ports

## License


MIT

---

Vault 3000 – Your Fallout-inspired console application!

## Example (chat)

When you start the chat, you might see:

```
VaultAI (cogito:8b) is online. Ask your questions?
```

**User:**
```
How do I install Docker on Ubuntu and run an nginx container?
```

**VaultAI:**
```
Here's how to install Docker on Ubuntu and run an Nginx container:

1. Update package list:
    sudo apt update

2. Install required packages:
    sudo apt install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg-agent \
        software-properties-common

3. Add Docker's official GPG key:
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

4. Set up the stable repository:
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

5. Install Docker Engine:
    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io

6. Start and enable Docker:
    sudo systemctl start docker
    sudo systemctl enable docker

7. Run an Nginx container:
    sudo docker run --name mynginx -d -p 8080:80 nginx

Now you can access Nginx at http://localhost:8080.
```

## Example (agent)

When you start the agent, you might see:

```
AgentAI (cogito:8b) is online. What can I do for you today?
```

**User:**
```
Create a bash deploy script that does: git pull, pip install, database migrations, and restarts uWSGI
```

**VaultAI agent:**
```
VaultAI AI agent started with goal: Create a bash deploy script that does: git pull, pip install, database migrations, and restarts uWSGI on 
root@192.168.200.198.

> 'mkdir -p deploy_script'. Execute? [y/N]: y
Executing: mkdir -p deploy_script
Result (code 0):

Agent asks: Do you want to create a bash script named 'deploy.sh' inside the 'deploy_script' directory?
Your answer: y

> 'touch deploy_script/deploy.sh'. Execute? [y/N]: y
Executing: touch deploy_script/deploy.sh
Result (code 0):

> 'chmod 755 deploy_script/deploy.sh'. Execute? [y/N]: y
Executing: chmod 755 deploy_script/deploy.sh
Result (code 0):

Agent asks: Do you want to add a shebang line at the top of the script?
Your answer: y

> 'echo '#!/bin/bash' > deploy_script/deploy.sh'. Execute? [y/N]: y
Executing: echo '#!/bin/bash' > deploy_script/deploy.sh
Result (code 0):

> 'echo -e "#!/bin/bash
cd /to/project

git pull
pip install -r requirements.txt
python manage.py migrate
sudo systemctl restart uwsgi" >> deploy_script/deploy.sh'. Execute? [y/N]: y
Executing: echo -e "#!/bin/bash
cd /to/project

git pull
pip install -r requirements.txt
python manage.py migrate
sudo systemctl restart uwsgi" >> deploy_script/deploy.sh
Result (code 0):

Agent finished its task. Summary: I've created a bash deployment script that does the following steps: 1) Created an empty deploy script file, 2) Made it executable, 3) Added a shebang line at the top, and 4) Appended all the required commands to execute git pull, pip install, database migrations, and restart uWSGI service.
```

## Support & Issues

If you find a bug or want to request a feature, please open an issue on [GitHub Issues](https://github.com/noxgle/term_agent/issues).

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

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
 ..................find me on: https://www.linkedin.com/in/sebastian-wielgosz-linux-admin
 ........................................................................................
