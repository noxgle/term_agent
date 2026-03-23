## ⚠️ Prototype Disclaimer

**This is a prototype agent under active development.** This project serves as a testing ground for new AI agent concepts, automation techniques, and terminal interface innovations. Features may be experimental, unstable, or subject to change without notice. Dont use in production environments.

## Getting Started

Welcome to Vault 3000, your Fallout-inspired Linux Terminal AI Agent! This powerful tool combines advanced AI capabilities with terminal automation to help you manage your system, develop software, and solve complex tasks.

### Quick Start

1. **Prerequisites**: Python 3.9+ and an API key for your chosen AI engine
2. **Installation**: 
   ```bash
   curl -O https://raw.githubusercontent.com/noxgle/term_agent/main/install_term_agent.sh
   chmod +x install_term_agent.sh
   ./install_term_agent.sh
   ```
3. **Configuration**: Copy `.env.copy` to `.env` and add your API keys
4. **Launch**: 
   ```bash
   python term_ag.py  # For automation tasks
   python term_ask.py # For chat mode
   ```

### What You Can Do

- **Automate Tasks**: Let the agent handle complex multi-step operations
- **Ask Questions**: Get instant answers about Linux, programming, and more
- **Manage Files**: Read, write, edit, and search files with AI assistance
- **Remote Operations**: Execute commands on remote servers via SSH
- **Web Research**: The agent can search the internet to gather information
- **Code Analysis**: Analyze and understand complex codebases

### Choose Your Mode

- **Collaborative Mode** (default): Interactive confirmation for each action
- **Automatic Mode**: Hands-off automation for trusted operations

### Next Steps

- Explore the [Features](#features) section to learn about all capabilities
- Check the [Configuration](#env-configuration) section for setup options
- Try the [Examples](#example-chat) to see the agent in action
- Visit our [GitHub Issues](https://github.com/noxgle/term_agent/issues) for support

---

## Video

[![LINUX TERMINAL AGENT](https://img.youtube.com/vi/UeDNO0pWK9c/0.jpg)](https://www.youtube.com/embed/UeDNO0pWK9c)
[![Kali AI Agent Docker Container](https://img.youtube.com/vi/nvP8HA_LTek/0.jpg)](https://youtu.be/nvP8HA_LTek)

## Table of Contents

- [Getting Started](#getting-started)
- [Features](#features)
- [Operating Modes](#operating-modes)
- [AI Model Comparison](#ai-model-comparison)
- [Terminal Agent Capabilities](#terminal-agent-capabilities)
- [Agent Tools](#agent-tools)
- [Action Plan Management](#action-plan-management)
- [Deep Analysis Sub-Agent](#deep-analysis-sub-agent)
- [Critic Sub-Agent](#critic-sub-agent)
- [Web Search Agent](#web-search-agent)
- [Prompt Creator](#prompt-creator)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#env-configuration)
- [Usage](#usage)
- [Files](#files)
- [Aliases](#aliases)
- [Examples](#example-chat)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)
- [Performance & Optimization](#performance--optimization)
- [Contributing](#contributing)
- [TODO](#todo)
- [License](#license)

## Features
- **Task automation**: The agent can perform tasks and commands based on user goals.
- **API**: The agent can be accessed via the API.
- **Multiple AI engine support**: OpenAI (ChatGPT), Google Gemini, Ollama (local and cloud), OpenRouter (unified API for multiple models).
- **Multi-Engine AI Routing**: Connect to multiple AI operators with two intelligent routing modes:
  - **Round-Robin**: Distributes requests evenly across configured engines for load balancing
  - **Fallback**: Automatically tries engines in sequence for high availability when providers fail
- **Local and remote execution (SSH)**: Run commands on your machine or remote hosts.
- **Configurable via `.env`**: Easily switch engines and settings.
- **Logging and colored console (Rich)**: Fallout/Pip-Boy theme for a unique retro look.
- **Chat mode**: Talk to Vault 3000 in the console, with conversation memory.
- **Advanced Prompt Creator**: Interactive tool for building precise, detailed prompts for AI agents. Guides you step-by-step, asks clarifying questions, and combines your answers into a single, actionable prompt. Supports multiline input (Ctrl+S), Fallout-style colors, and easy confirmation with Enter.
- **Two Operating Modes**: Work with the agent in **Collaborative Mode** (interactive confirmation for each command) or **Fully Automatic Mode** (agent executes commands autonomously). Switch dynamically during a session with Ctrl+A or configure via `.env` file.
- **Interactive Action Plan Management**: Before execution, the agent generates a step-by-step plan. In Collaborative Mode you can accept, reject, or edit the plan. The AI revises the plan based on your feedback.
- **Rich File Operations**: Agent has built-in tools to read, write, edit, copy, delete files and list directories — all with user confirmation in Collaborative Mode.
- **Web Search Agent**: Agent can search the internet during task execution using DuckDuckGo (no API key required) or a self-hosted SearxNG instance. Supports multi-source aggregation and content extraction.
- **Deep Analysis Sub-Agent**: After task completion, an optional sub-agent performs a comprehensive analysis of all session data (commands, outputs, file operations, web searches, plan steps) and generates a structured final report.
- **Critic Sub-Agent**: When the agent reports success, a critic sub-agent scores how correct the final answer is (0–10) relative to the original prompt.
- **Thread Continuation**: After finishing a task, you can continue the session with a new goal while preserving the full conversation history.
- **Enhanced JSON Validator**: Robust JSON parsing with up to 3 automatic correction attempts when the AI returns malformed responses.
- **Configurable Step Limit**: Built-in safeguard (`MAX_STEPS=100` by default) prevents infinite loops during task execution.
- **Intelligent Log Compression**: Automatic log compression using AI-powered semantic clustering to reduce verbosity while preserving important information.

## Multi-Engine AI Routing Configuration

The agent supports connecting to multiple AI operators simultaneously with intelligent routing strategies for improved reliability and performance.

### Routing Modes

#### Round-Robin Mode
- **Purpose**: Distributes AI requests evenly across all configured engines
- **Behavior**: Each request gets a different engine in sequential rotation
- **Use Case**: Load balancing across multiple AI providers to optimize costs and performance
- **Example**: With engines [OpenAI, Ollama, Google], requests cycle: OpenAI → Ollama → Google → OpenAI...

#### Fallback Mode
- **Purpose**: Provides high availability by automatically switching to backup engines
- **Behavior**: Tries engines in order until one succeeds; if the first fails, automatically tries the next
- **Use Case**: Ensuring requests complete even when some AI providers are unavailable or rate-limited
- **Example**: With engines [OpenAI, Ollama, Google], if OpenAI fails, automatically tries Ollama, then Google

### Configuration

Configure multiple engines and routing mode in your `.env` file:

```ini
# Multiple engines can be specified as comma-separated list
AI_ENGINE=openai,ollama,google,openrouter

# Routing mode: round-robin or fallback
AI_ENGINE_ROUTE=fallback

# Per-engine API keys
OPENAI_API_KEY=your_openai_key_here
OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=llama3.2:latest
GOOGLE_API_KEY=your_google_key_here
GOOGLE_MODEL=gemini-2.5-flash-preview-05-20
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_MODEL=openrouter/llama-3.1-70b-instruct:free
```

### Supported AI Engines

| Engine | Description | Local/Cloud | Typical Use |
|--------|-------------|-------------|-------------|
| **OpenAI** | ChatGPT models (GPT-4, GPT-3.5) | Cloud | High-quality responses, advanced reasoning |
| **Ollama** | Local LLM models | Local | Privacy-focused, offline capability |
| **Ollama Cloud** | Hosted Ollama models | Cloud | Managed service with local model benefits |
| **Google Gemini** | Google's AI models | Cloud | Strong reasoning, Google ecosystem integration |
| **OpenRouter** | Unified API for 100+ models | Cloud | Access to diverse model selection |

### Configuration Examples

#### High Availability Setup (Fallback Mode)
```ini
AI_ENGINE=openai,google,openrouter
AI_ENGINE_ROUTE=fallback
```
*If OpenAI is rate-limited, automatically falls back to Google, then OpenRouter.*

#### Cost Optimization Setup (Round-Robin Mode)
```ini
AI_ENGINE=ollama,openrouter,ollama-cloud
AI_ENGINE_ROUTE=round-robin
```
*Distributes requests across cheaper local and cloud models to optimize costs.*

#### Performance-First Setup (Fallback Mode)
```ini
AI_ENGINE=openai,gemini-2.5-pro,openrouter
AI_ENGINE_ROUTE=fallback
```
*Tries premium models first, falls back to alternatives if unavailable.*

### Advanced Configuration

#### Per-Engine Settings
Each engine can have its own model, temperature, and other settings:

```ini
# OpenAI settings
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0.5
OPENAI_MAX_TOKENS=4000

# Ollama settings
OLLAMA_MODEL=llama3.2:latest
OLLAMA_TEMPERATURE=0.7

# Google settings
GOOGLE_MODEL=gemini-2.5-pro
GOOGLE_TEMPERATURE=0.3

# OpenRouter settings
OPENROUTER_MODEL=anthropic/claude-sonnet
OPENROUTER_TEMPERATURE=0.5
```

#### Timeout and Retry Configuration
```ini
# AI API timeout in seconds
AI_API_TIMEOUT=120

# Maximum retry attempts (0 = no limit)
AI_API_MAX_RETRIES=3

# Base delay between retries in seconds
AI_API_RETRY_DELAY=2

# Backoff multiplier (2 = exponential backoff)
AI_API_RETRY_BACKOFF=2

# Use timeout-enabled API calls
USE_TIMEOUT_API=true
```

### Monitoring and Logging

The system provides detailed logging for multi-engine operations:

```
[INFO] Multi-engine mode: 3 engines configured (openai, ollama, google)
[INFO] Routing mode: fallback
[DEBUG] Round-robin selected engine: openai (next index: 1)
[WARNING] Engine openai failed: Rate limit exceeded, trying next engine
[DEBUG] Fallback to engine: ollama
[INFO] Engine ollama succeeded
```

### Best Practices

1. **Engine Order Matters**: In fallback mode, list your preferred engines first
2. **Monitor Usage**: Check logs to see which engines are being used most frequently
3. **Test Reliability**: Verify all configured engines work before relying on fallback
4. **Balance Costs**: Use cheaper engines first in fallback mode to optimize costs
5. **Consider Latency**: Local engines (Ollama) are faster than cloud APIs

### Troubleshooting

#### Engine Not Responding
- Check API keys are valid
- Verify network connectivity for cloud engines
- Ensure local Ollama server is running

#### Fallback Not Working
- Verify all engines are properly configured
- Check that API keys are valid for all engines
- Review logs for specific error messages

#### Round-Robin Not Rotating
- Ensure `AI_ENGINE_ROUTE=round-robin` is set
- Check that multiple engines are configured in `AI_ENGINE`
- Verify engines are responding successfully

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

## Agent Pipeline Modes

The agent supports three pipeline modes that control how the AI processes tasks and manages context:

### Compact Mode (`--compact`)
- Uses a simplified pipeline with a maximum of 3 LLM calls
- Compact prompts and streamlined state machine for faster decisions
- Minimal context overhead - ideal for simple, straightforward tasks
- Best for: Quick commands, simple file operations, routine automation

### Normal Mode (`--normal`)
- Full pipeline with complete conversation history and sliding window context
- All tools and features available with detailed step-by-step execution
- Maximum reliability and comprehensive task handling
- Best for: Complex tasks, multi-step workflows, critical operations

### Hybrid Mode (`--hybrid`, default)
- Starts with Compact Mode for efficiency
- Automatically falls back to Normal Mode if Compact fails or gets blocked
- Best of both worlds: speed when possible, reliability when needed
- Best for: General use, unknown task complexity, balanced performance

### Comparison Table

| Feature | Compact | Normal | Hybrid |
|---------|---------|--------|--------|
| LLM Calls | Max 3 | Unlimited | Starts at 3, fallback if needed |
| Context Size | Minimal | Full | Adaptive |
| Speed | Fast | Slower | Balanced |
| Reliability | Basic | High | High |
| Best For | Simple tasks | Complex tasks | General use |

### How to Choose

- **Use Compact** when you know the task is simple and want quick results
- **Use Normal** when reliability is critical or tasks are complex
- **Use Hybrid** (default) for the best balance in most scenarios

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
| `search_in_file` | Search for patterns in file content using regex, with configurable context lines and result limits. |
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
| `finish` | Signal task completion with a detailed summary. On success, triggers the Critic Sub-Agent; also offers the optional Deep Analysis Sub-Agent. |

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

## Critic Sub-Agent

When the agent finishes with `goal_success=true`, the **Critic Sub-Agent** automatically evaluates the answer correctness against the original prompt and assigns a score from 0 to 10.

**Output includes:**
- Rating (0–10)
- Verdict (Correct / Partially / Incorrect)
- Short rationale

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
pip install ddgs beautifulsoup4 lxml
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

## Log Compression

The agent includes intelligent log compression features to reduce verbosity while preserving important information. This is particularly useful when dealing with large volumes of system logs, application logs, or agent output.

### Compression Modes

#### Simple Log Compression
- **Method**: Regex-based template matching and grouping
- **Speed**: Fast, lightweight processing
- **Use Case**: Small to medium log files, quick compression needs
- **Trigger**: Automatically when log length > 5000 characters or unique ratio < 70%

#### Dynamic Log Compression
- **Method**: AI-powered semantic clustering using sentence transformers
- **Technology**: Uses Hugging Face's `sentence-transformers/all-MiniLM-L6-v2` model
- **Speed**: Slower but more intelligent grouping
- **Use Case**: Large log files, semantic understanding required
- **Trigger**: Automatically when log lines > 20 or for better semantic grouping

#### Automatic Mode (Recommended)
- **Method**: Tries Dynamic compression first, falls back to Simple if needed
- **Configuration**: Set `LOG_COMPRESSOR_MODE=auto` in `.env`
- **Benefits**: Best of both worlds - intelligent compression with reliable fallback

### Setup Instructions

#### 1. Obtain Hugging Face API Token
1. Visit [Hugging Face](https://huggingface.co/settings/tokens)
2. Create an account if you don't have one
3. Generate a new API token with read access
4. Add it to your `.env` file:

```ini
# Hugging Face API token for DynamicLogCompressor
HF_TOKEN=your_hf_token_here
```

#### 2. Download the AI Model
Run the model downloader script to fetch the required model:

```bash
python download_hf_model.py
```

This will:
- Download the `sentence-transformers/all-MiniLM-L6-v2` model
- Store it in the `hf_cache` directory
- Configure the model for CPU-only operation

#### 3. Configure Compression Mode
Add the following to your `.env` file:

```ini
# Log compressor mode: auto (try DynamicLogCompressor first, fallback to LogCompressor), 
# dynamic (use only DynamicLogCompressor), simple (use only LogCompressor)
LOG_COMPRESSOR_MODE=auto
```

### Configuration Options

| Setting | Values | Description |
|---------|--------|-------------|
| `LOG_COMPRESSOR_MODE` | `auto`, `dynamic`, `simple` | Compression method to use |
| `HF_TOKEN` | Your Hugging Face token | Required for Dynamic compression |
| `TRANSFORMERS_CACHE` | Directory path | Where to store downloaded models |

### Usage Examples

#### Before Compression
```
2024-03-15 10:30:15 INFO: User login successful for user_id=12345
2024-03-15 10:30:16 INFO: User login successful for user_id=12346
2024-03-15 10:30:17 INFO: User login successful for user_id=12347
2024-03-15 10:30:18 ERROR: Database connection failed for user_id=12345
2024-03-15 10:30:19 INFO: User login successful for user_id=12348
```

#### After Simple Compression
```
<TIME> INFO: User login successful for user_id=<NUM> x4
<TIME> ERROR: Database connection failed for user_id=<NUM>
```

#### After Dynamic Compression
```
<TIME> INFO: User login successful for user_id=<NUM> x4
<TIME> ERROR: Database connection failed for user_id=<NUM>
```

### Performance Comparison

| Metric | Simple Compression | Dynamic Compression |
|--------|-------------------|-------------------|
| **Speed** | Fast (milliseconds) | Slower (seconds) |
| **Accuracy** | Template-based | Semantic clustering |
| **Memory Usage** | Low | Higher (model loading) |
| **Best For** | Real-time processing | Batch processing, analysis |

### Integration with Agent

The log compression feature integrates seamlessly with the agent's logging system:

- **Automatic Triggering**: Compression activates automatically based on log size and content
- **Context Preservation**: Important information is preserved while reducing verbosity
- **Performance Monitoring**: Compression reduces log output size without losing critical details
- **Memory Efficiency**: Helps manage memory usage during long-running agent sessions

### Troubleshooting

#### Model Download Issues
**Problem**: "Failed to load model from local cache"
**Solution**:
1. Verify `HF_TOKEN` is correctly set in `.env`
2. Run `python download_hf_model.py` again
3. Check internet connectivity
4. Ensure `hf_cache` directory has write permissions

#### Token Authentication Problems
**Problem**: "HF_TOKEN not found in .env file"
**Solution**:
1. Verify the token is correctly copied from Hugging Face
2. Ensure no extra spaces or characters in the `.env` file
3. Restart the agent after updating `.env`

#### Performance Issues
**Problem**: Agent is slow when processing large logs
**Solution**:
1. Use `LOG_COMPRESSOR_MODE=simple` for faster processing
2. Increase system memory if possible
3. Monitor CPU usage during compression

### Advanced Configuration

#### Custom Clustering Parameters
For advanced users, the DynamicLogCompressor uses DBSCAN clustering with these default parameters:
- `eps=0.2` (clustering sensitivity)
- `min_samples=2` (minimum cluster size)
- `metric="cosine"` (similarity metric)

#### Cache Management
The model is cached in the `hf_cache` directory. To manage cache:
- **Clear cache**: Delete the `hf_cache` directory
- **Move cache**: Update `TRANSFORMERS_CACHE` in `.env`
- **Monitor size**: The model is approximately 80MB

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
pip install ddgs beautifulsoup4 lxml
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
  - `prom` - to start prompt creator

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
docker compose up -d

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
# agent pipeline mode (compact, normal, hybrid)
AGENT_MODE=hybrid
# show performance summary after task completion
SHOW_PERFORMANCE_SUMMARY=false
# enable correctness critic on successful completion
ENABLE_CRITIC_SUB_AGENT=true

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

# API server configuration
API_ENABLE=true
API_HOST=0.0.0.0
API_PORT=8000
API_SERVER_KEY=your_api_key_here
API_MAX_WORKERS=4
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

Force compact or normal pipeline:

```bash
python term_ag.py --compact
python term_ag.py --normal
python term_ag.py --hybrid
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

### API mode (FastAPI):

The HTTP API exposes simple endpoints to run agent tasks synchronously or asynchronously.
Use `/run` for a single blocking request, `/run_async` for a background job, and `/runs` to submit batches.
If `API_SERVER_KEY` is set, include it in the `X-API-Key` header for all requests.

```bash
python term_api.py
```

Optional environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `API_HOST` | `0.0.0.0` | Address where the API server is listening |
| `API_PORT` | `8000` | API server port |
| `API_SERVER_KEY` | (empty) | Optional key required in X-API-Key header |
| `API_MAX_WORKERS` | `4` | Maximum number of tasks executed in parallel; excess goes to queue |
| `API_ENABLE` | `true` | API startup switch |

Example request:

```bash
curl -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your_key_if_set' \
  -d '{"goal":"list files in current directory"}'
```

If neither `pipeline_mode` nor `compact_mode` is provided, the API defaults to `pipeline_mode="hybrid"`.

Force normal mode and plan creation (API payload):

```bash
curl -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your_key_if_set' \
  -d '{"goal":"create an action plan for nginx setup","compact_mode":false,"force_plan":true}'
```

Hybrid mode (API payload):

```bash
curl -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your_key_if_set' \
  -d '{"goal":"list files in /tmp","pipeline_mode":"hybrid"}'
```

Async single request:

```bash
curl -X POST http://localhost:8000/run_async \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your_key_if_set' \
  -d '{"goal":"list files in current directory"}'
```

Batch async requests:

```bash
curl -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your_key_if_set' \
  -d '{"requests":[{"goal":"list files"},{"goal":"show uptime"}]}'
```

Check job status:

```bash
curl -X GET http://localhost:8000/runs/<job_id> \
  -H 'X-API-Key: your_key_if_set'
```

Note: `goal_success` is returned inside `result` only after the job completes.
If available, the API also returns `critic_rating`, `critic_verdict`, and `critic_rationale`.
These fields are `null` when `goal_success=false` or when the critic is disabled.

Cancel job:

```bash
curl -X DELETE http://localhost:8000/runs/<job_id> \
  -H 'X-API-Key: your_key_if_set'
```

Remote SSH example:

```bash
curl -X POST http://localhost:8000/run_async \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your_key_if_set' \
  -d '{"goal":"check disk space","host":"192.168.1.10","user":"root","port":22,"ssh_password":"your_password"}'
```

Custom system prompt example:

```bash
curl -X POST http://localhost:8000/run_async \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your_key_if_set' \
  -d '{"goal":"list running services","system_prompt_agent":"You are a cautious Linux admin. Avoid destructive commands."}'
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
- `term_api.py` – FastAPI entry point for HTTP usage.
- `api/api_server.py` – FastAPI app and HTTP endpoints.
- `api/api_agent.py` – non-interactive runner wrapper for API usage.
- `ai/AICommunicationHandler.py` – AI API abstraction layer (OpenAI, Gemini, Ollama, OpenRouter).
- `context/ContextManager.py` – conversation context and sliding window management.
- `plan/ActionPlanManager.py` – action plan creation, step tracking, progress display.
- `finish/FinishSubAgent.py` – deep analysis sub-agent for post-task reporting.
- `critic/CriticSubAgent.py` – critic sub-agent for correctness scoring on successful completion.
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

## Troubleshooting

### Common Issues and Solutions

#### Agent Won't Start
**Problem**: Python errors or import failures when starting the agent.
**Solution**: 
- Ensure Python 3.9+ is installed: `python3 --version`
- Activate virtual environment: `source .venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

#### AI Engine Connection Failures
**Problem**: "Engine failed" or timeout errors.
**Solution**:
- Verify API keys in `.env` file are correct
- Check network connectivity for cloud engines
- For Ollama: ensure server is running: `ollama serve`
- Test individual engines with simple requests

#### SSH Connection Issues
**Problem**: Cannot connect to remote hosts.
**Solution**:
- Verify SSH keys or password authentication
- Test SSH connection manually: `ssh user@host`
- Check SSH port and firewall settings
- Ensure remote host has Python and required packages

#### Web Search Not Working
**Problem**: Web search agent fails or returns no results.
**Solution**:
- Install required dependencies: `pip install ddgs beautifulsoup4 lxml`
- For SearxNG: verify instance is running and URL is correct
- Check network connectivity and firewall settings
- Try DuckDuckGo engine as fallback

#### File Operations Fail
**Problem**: Read/write operations fail with permission errors.
**Solution**:
- Check file permissions: `ls -la filename`
- Ensure you have read/write access to target directories
- Run agent with appropriate user privileges
- Verify file paths are correct

#### Performance Issues
**Problem**: Agent is slow or unresponsive.
**Solution**:
- Check system resources: `top` or `htop`
- Reduce `AI_API_TIMEOUT` in `.env` if responses are slow
- Use local engines (Ollama) for faster response times
- Clear conversation history if context is too large

#### JSON Parsing Errors
**Problem**: "Malformed JSON" or parsing failures.
**Solution**:
- The agent has built-in JSON correction, but ensure AI responses are well-formed
- Reduce prompt complexity if JSON errors persist
- Check `LOG_LEVEL=DEBUG` for detailed error information

### Getting Help

1. **Check Logs**: Enable debug logging in `.env`: `LOG_LEVEL=DEBUG`
2. **Test Components**: Test individual features (AI engine, SSH, web search) separately
3. **GitHub Issues**: Search existing issues or create new one at [GitHub Issues](https://github.com/noxgle/term_agent/issues)
4. **Community**: Join discussions for support and tips

### Diagnostic Commands

```bash
# Check Python version
python3 --version

# Test virtual environment
source .venv/bin/activate && python -c "import sys; print(sys.version)"

# Test AI engine connection
python -c "from ai.AICommunicationHandler import AICommunicationHandler; handler = AICommunicationHandler(); print('Engine test successful')"

# Check SSH connectivity
ssh -o ConnectTimeout=5 user@host 'echo "SSH test successful"'

# Test web search
python -c "from web_search.WebSearchAgent import WebSearchAgent; agent = WebSearchAgent(); print('Web search test successful')"
```

## Best Practices

### Security

- **API Keys**: Never commit `.env` files to version control
- **SSH Keys**: Use SSH key authentication instead of passwords when possible
- **File Permissions**: Ensure proper file permissions for sensitive operations
- **Remote Execution**: Always review commands before executing on remote systems

### Performance Optimization

- **Engine Selection**: Use local engines (Ollama) for faster response times
- **Context Management**: Keep conversation history manageable for better performance
- **Timeout Settings**: Adjust timeouts based on your network and AI engine response times
- **Resource Monitoring**: Monitor system resources during long-running tasks

### Workflow Efficiency

- **Clear Goals**: Provide specific, well-defined goals to the agent
- **Mode Selection**: Use Collaborative Mode for learning, Automatic Mode for routine tasks
- **Plan Review**: Always review action plans before execution
- **Error Handling**: Pay attention to error messages and adjust accordingly

### Multi-Engine Configuration

- **Fallback Strategy**: Configure reliable fallback engines for high availability
- **Load Balancing**: Use round-robin for cost optimization across multiple engines
- **Engine Testing**: Regularly test all configured engines to ensure they're working
- **Monitoring**: Enable logging to track engine usage and performance

## Performance & Optimization

### Engine Performance Comparison

| Engine | Response Time | Cost | Privacy | Reliability |
|--------|---------------|------|---------|-------------|
| **Ollama (Local)** | Fast | Free | High | High |
| **OpenAI** | Medium | High | Low | High |
| **Google Gemini** | Medium | Medium | Low | High |
| **OpenRouter** | Variable | Variable | Variable | Variable |

### Configuration Optimization

#### For Speed
```ini
# Use local engines when possible
AI_ENGINE=ollama
AI_API_TIMEOUT=60

# Reduce context overhead
AGENT_MODE=compact
```

#### For Reliability
```ini
# Use fallback mode with multiple engines
AI_ENGINE=openai,google,ollama
AI_ENGINE_ROUTE=fallback
AI_API_MAX_RETRIES=5
```

#### For Cost Efficiency
```ini
# Use round-robin to distribute load
AI_ENGINE=ollama,openrouter
AI_ENGINE_ROUTE=round-robin

# Set appropriate timeouts
AI_API_TIMEOUT=120
```

### System Requirements

- **Minimum**: 4GB RAM, 2 CPU cores, Python 3.9+
- **Recommended**: 8GB RAM, 4 CPU cores, SSD storage
- **For Ollama**: Additional 8GB+ RAM for large models

### Monitoring and Maintenance

- **Regular Updates**: Keep dependencies and AI engines updated
- **Log Analysis**: Review logs periodically for performance insights
- **Resource Monitoring**: Monitor CPU, memory, and disk usage
- **Backup Configuration**: Keep backups of working `.env` configurations

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

### Development Setup

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests for new functionality
5. Run linting and formatting: `black . && flake8 .`
6. Submit pull request

### Code Style

- Follow PEP 8 style guide
- Use type hints for all public functions
- Write docstrings for all public classes and methods
- Maximum line length: 100 characters

### Testing

- Add unit tests for new features in `tests/` directory
- Test with multiple AI engines when possible
- Verify both local and remote execution scenarios
- Test error handling paths

### Reporting Issues

When reporting bugs, please include:
- Python version: `python3 --version`
- Agent version: `git rev-parse HEAD`
- Operating system and version
- Steps to reproduce the issue
- Expected vs. actual behavior
- Any error messages or logs

## TODO

- Add SearxNG Docker Compose example for easy self-hosted web search setup
- Add support for additional web search engines
- Implement more advanced file operation tools
- Add performance benchmarks and optimization guides
- Create video tutorials for common use cases
- Add integration with popular development tools and IDEs

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
 .....................  ###  .... #### .............   ###  .............................. 
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
