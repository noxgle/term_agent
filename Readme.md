## Video

[![LINUX TERMINAL AGENT](https://img.youtube.com/vi/UeDNO0pWK9c/0.jpg)](https://www.youtube.com/embed/UeDNO0pWK9c)
[![Kali AI Agent Docker Container](https://img.youtube.com/vi/nvP8HA_LTek/0.jpg)](https://youtu.be/nvP8HA_LTek)

## Table of Contents

- [Features](#features)
- [Operating Modes](#operating-modes)
- [AI Model Comparison](#ai-model-comparison)
- [Terminal Agent Capabilities](#terminal-agent-capabilities)
- [Agent Tools](#agent-tools)
- [Action Plan Management](#action-plan-management)
- [Deep Analysis Sub-Agent](#deep-analysis-sub-agent)
- [Web Search Agent](#web-search-agent)
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
- **Two Operating Modes**: Work with the agent in **Collaborative Mode** (interactive confirmation for each command) or **Fully Automatic Mode** (agent executes commands autonomously). Switch dynamically during a session with Ctrl+A or configure via `.env` file.
- **Interactive Action Plan Management**: Before execution, the agent generates a step-by-step plan. In Collaborative Mode you can accept, reject, or edit the plan. The AI revises the plan based on your feedback.
- **Rich File Operations**: Agent has built-in tools to read, write, edit, copy, delete files and list directories — all with user confirmation in Collaborative Mode.
- **Web Search Agent**: Agent can search the internet during task execution using DuckDuckGo (no API key required) or a self-hosted SearxNG instance. Supports multi-source aggregation and content extraction.
- **Deep Analysis Sub-Agent**: After task completion, an optional sub-agent performs a comprehensive analysis of all session data (commands, outputs, file operations, web searches, plan steps) and generates a structured final report.
- **Thread Continuation**: After finishing a task, you can continue the session with a new goal while preserving the full conversation history.
- **Enhanced JSON Validator**: Robust JSON parsing with up to 3 automatic correction attempts when the AI returns malformed responses.
- **Configurable Step Limit**: Built-in safeguard (`MAX_STEPS=100` by default) prevents infinite loops during task execution.

## Operating Modes

The agent supports two distinct modes of operation, allowing you to choose the level of control that best fits your workflow:

### Collaborative Mode (Interactive)
In this mode, the agent works as your collaborative partner. Before executing any bash command, file operation, or web search, the agent presents it to you and asks for confirmation. You can approve (`y`) or reject (`N`) each action individually, giving you full oversight of all actions performed on your system.

**When to use:**
- Learning new commands and their effects
- Working on production systems where caution is required
- Tasks where you want to understand each step before execution
- First-time automation of sensitive operations

**How to enable:**
- Set `AUTO_ACCEPT=false` in your `.env` file (default)
- Or press the mode switch shortcut during a session

### Fully Automatic Mode
In this mode, the agent operates autonomously, executing suggested commands without prompting for confirmation. The agent proceeds with the task workflow independently, only stopping to report results or ask clarifying questions when necessary.

**When to use:**
- Routine, well-understood automation tasks
- Development or testing environments
- Time-sensitive operations where speed is critical
- Tasks you've already verified and trust the agent to handle

**How to enable:**
- Set `AUTO_ACCEPT=true` in your `.env` file to start in automatic mode
- Or press `Ctrl+A` during an interactive session to switch to automatic mode on-the-fly

**Note:** The `Ctrl+A` shortcut is one-way - it switches from interactive to automatic mode during the current session. To return to collaborative mode, restart the agent with `AUTO_ACCEPT=false`.

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
- **Internet Research**: Search the web for information needed to complete tasks.

## Agent Tools

The agent communicates via JSON tool calls. Each tool is available to the AI during task execution:

### Execution Tools
| Tool | Description |
|------|-------------|
| `bash` | Execute shell commands locally or via SSH. Supports custom timeout. |
| `web_search_agent` | Search the internet using DuckDuckGo or SearxNG. |

### File Operation Tools
| Tool | Description |
|------|-------------|
| `read_file` | Read file content, optionally specifying start/end line numbers. |
| `write_file` | Create or overwrite a file with specified content. |
| `edit_file` | Edit a file: `replace`, `insert_after`, `insert_before`, or `delete_line`. |
| `list_directory` | List directory contents, optionally recursive with glob pattern. |
| `copy_file` | Copy a file to a new location (with optional overwrite). |
| `delete_file` | Delete a file (with optional backup). |

### Plan & Communication Tools
| Tool | Description |
|------|-------------|
| `update_plan_step` | Mark a plan step as `completed`, `failed`, `skipped`, or `in_progress`. |
| `ask_user` | Ask the user a question (only available in Collaborative Mode). |

### Completion Tool
| Tool | Description |
|------|-------------|
| `finish` | Signal task completion with a detailed summary. Triggers the optional Deep Analysis Sub-Agent. |

All file and search operations in **Collaborative Mode** ask for user confirmation (`[y/N]`) before proceeding. If refused, the user is prompted for a justification that is fed back to the AI.

## Action Plan Management

Before starting task execution, the agent automatically generates a step-by-step action plan based on your goal.

### How it works:
1. **Plan Generation**: The AI creates a structured plan with numbered steps, each with a description and optional command.
2. **Plan Review** (Collaborative Mode only): The plan is displayed and you are asked:
   - `y` — Accept the plan and start execution
   - `n` / `e` — Reject or edit: describe your changes, the AI revises the plan accordingly
3. **Plan Execution**: The agent executes steps in order, marking each as `completed`, `failed`, or `skipped` using the `update_plan_step` tool.
4. **Finish Guard**: The agent cannot call `finish` until all plan steps are completed (or marked as failed/skipped). If it tries, it is reminded to complete the remaining steps first.
5. **Progress Display**: After each action, a compact plan progress summary is shown.

### Example plan display:
```
 ACTION PLAN
 Step 1: [✓] Analyze goal and requirements
 Step 2: [✓] Install required packages
 Step 3: [⟳] Configure the service
 Step 4: [ ] Verify the installation
 Progress: 2/4 (50%)
```

## Deep Analysis Sub-Agent

After the agent finishes a task, you are offered an optional **Deep Analysis Sub-Agent** that performs a comprehensive post-task report.

```
VaultAI> Run Deep Analysis Sub-Agent for a detailed session report? [y/N]:
```

### What it analyzes:
- ✅ Full conversation history (user, agent, system messages)
- ✅ All executed bash commands and their outputs
- ✅ File operations performed (read, write, edit, copy, delete)
- ✅ Web search results gathered during the session
- ✅ Action plan steps with statuses and results
- ✅ Agent's own finish summary

### Report structure:
| Section | Content |
|---------|---------|
| **Goal Achievement Assessment** | Was the goal achieved? Success rating (1–10). |
| **Execution Summary** | Total steps, key actions, critical decisions. |
| **What Worked Well** | Successful operations with specific details. |
| **Problems & Failures** | Failed commands, root cause analysis, workarounds. |
| **Deep Technical Analysis** | Key outputs, system state changes, security notes. |
| **Recommendations** | Next steps, potential risks, improvements. |
| **Final Verdict** | COMPLETED / PARTIALLY COMPLETED / FAILED |

The report is rendered as formatted Markdown in the terminal with Vault-Tec themed panels.

## Web Search Agent

The agent can search the internet during task execution using the built-in **WebSearchAgent**.

### Supported search engines:
| Engine | Setup | Notes |
|--------|-------|-------|
| **DuckDuckGo** | No API key required | Default engine |
| **SearxNG** | Requires self-hosted instance | More control, no rate limits |

### Features:
- **Multi-source aggregation**: Iterative internal loop gathers data from multiple sources
- **Content extraction**: Extracts and cleans main content from web pages (requires `beautifulsoup4`)
- **AI-powered evaluation**: Uses AI to assess search completeness and refine queries
- **Relevance scoring**: Keyword-based relevance scoring for each source (0.0–1.0)
- **Confidence scoring**: Overall confidence metric based on source count, relevance, and content depth

### Required dependencies for web search:
```bash
pip install duckduckgo-search beautifulsoup4 lxml
```

### Web search `.env` configuration:
```ini
# Search engine: duckduckgo or searxng
WEB_SEARCH_ENGINE=duckduckgo

# SearxNG URL (only needed if using searxng engine)
SEARXNG_URL=http://localhost:8888

# Maximum search iterations per query (default: 5)
WEB_SEARCH_MAX_ITERATIONS=5

# Maximum sources per iteration (default: 5)
WEB_SEARCH_MAX_SOURCES=5

# Minimum confidence to stop searching (default: 0.7)
WEB_SEARCH_MIN_CONFIDENCE=0.7

# HTTP timeout in seconds (default: 30)
WEB_SEARCH_TIMEOUT=30

# Enable page content extraction (default: true)
WEB_SEARCH_EXTRACT_CONTENT=true

# Max characters extracted per page (default: 10000)
WEB_SEARCH_MAX_CONTENT_LENGTH=10000
```

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

### Optional dependencies (for web search):
```bash
pip install duckduckgo-search beautifulsoup4 lxml
```

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

# web search agent configuration (optional)
WEB_SEARCH_ENGINE=duckduckgo        # duckduckgo or searxng
SEARXNG_URL=http://localhost:8888   # only needed for searxng engine
WEB_SEARCH_MAX_ITERATIONS=5
WEB_SEARCH_MAX_SOURCES=5
WEB_SEARCH_MIN_CONFIDENCE=0.7
WEB_SEARCH_TIMEOUT=30
WEB_SEARCH_EXTRACT_CONTENT=true
WEB_SEARCH_MAX_CONTENT_LENGTH=10000
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

> **Operating Modes:** By default, the agent runs in **Collaborative Mode** and asks for confirmation before executing each command (`[y/N]`). To run in **Fully Automatic Mode**, either:
> - Set `AUTO_ACCEPT=true` in your `.env` file before starting
> - Press `Ctrl+A` during a session to switch from collaborative to automatic mode on-the-fly

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

### Continuing a session after task completion

After a task finishes, the agent asks if you want to continue:

```
VaultAI> Do you want continue this thread? [y/N]:
```

If you answer `y`, you can type a new goal. The full conversation history is preserved, giving the AI context from the previous task.

## Files

- `term_ag.py` – main agent, automation, tasks, agent class, AI and command handling.
- `term_ask.py` – AI chat, questions, dialogs.
- `VaultAIAskRunner.py` – chat logic.
- `VaultAiAgentRunner.py` – agent execution logic, tool dispatch, plan management.
- `PromptCreator.py` – interactive prompt builder.
- `ai/AICommunicationHandler.py` – AI API abstraction layer (OpenAI, Gemini, Ollama, OpenRouter).
- `context/ContextManager.py` – conversation context and sliding window management.
- `plan/ActionPlanManager.py` – action plan creation, step tracking, progress display.
- `finish/FinishSubAgent.py` – deep analysis sub-agent for post-task reporting.
- `web_search/WebSearchAgent.py` – web search sub-agent (DuckDuckGo, SearxNG).
- `file_operator/FileOperator.py` – file read/write/edit/copy/delete operations.
- `security/SecurityValidator.py` – command security validation.
- `json_validator/JsonValidator.py` – enhanced JSON parsing with auto-correction.
- `user/UserInteractionHandler.py` – user input handling.

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

- Add SearxNG Docker Compose example for easy self-hosted web search setup
- Add support for additional web search engines

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

**VaultAI agent — plan phase:**
```
Creating action plan...
[OK] Created plan with 4 steps

 ACTION PLAN
 Step 1: [ ] Create deploy_script directory
 Step 2: [ ] Create deploy.sh script file
 Step 3: [ ] Add deployment commands to the script
 Step 4: [ ] Make script executable and verify

Accept this plan? [y/n/e(edit)]:
```

**VaultAI agent — execution phase:**
```
VaultAI> Agent suggests to run command: 'mkdir -p deploy_script'. Execute? [y/N]: y
Executing: mkdir -p deploy_script
Result (code 0):

...

VaultAI> Agent finished its task.
Summary: Created a bash deployment script at deploy_script/deploy.sh that performs git pull, pip install, database migrations, and uWSGI service restart.

VaultAI> Run Deep Analysis Sub-Agent for a detailed session report? [y/N]: y

Vault 3000 Deep Analysis Sub-Agent initializing...
Sub-agent analyzing all available sources...

╔══════════════════════════════════════════════════════════════════════╗
║  VAULT 3000 — DEEP ANALYSIS COMPLETE                                 ║
║  Goal: Create a bash deploy script...                                ║
╚══════════════════════════════════════════════════════════════════════╝

### GOAL ACHIEVEMENT ASSESSMENT
- Was the goal achieved? **Yes**
- Overall success rating: **9/10**
...

VaultAI> Do you want continue this thread? [y/N]:
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
```
