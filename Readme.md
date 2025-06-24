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


# Vault 3000 Console Agent

**Vault 3000** is a Fallout-inspired terminal application that not only answers your questions and helps with Linux commands, but can also autonomously achieve complex goals for you—automating tasks, creating and editing files, and executing multi-step operations—using advanced AI engines (OpenAI, Google Gemini, Ollama). It works both locally and remotely via SSH.

## Demo

See Vault 3000 in action:  
[![Vault 3000 Demo](https://img.youtube.com/vi/gFWQzcY27ds/0.jpg)](https://youtu.be/gFWQzcY27ds)

[Watch the demo on YouTube](https://youtu.be/gFWQzcY27ds)

## Features

- **Chat mode**: Talk to Vault 3000 in the console, with conversation memory.
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

## System Requirements

- Operating system: Linux or macOS

## Installation

### Quick Install (using install script)

```bash
# Download and run the installation script
curl -O https://raw.githubusercontent.com/noxgle/term_agent/main/install_term_agent.sh
chmod +x install_term_agent.sh
./install_term_agent.sh
```

The install script will:
- Check Python version requirements (3.9+)
- Create and configure virtual environment
- Install all required packages
- Create initial `.env` file from template
- Optionally add convenient aliases to your shell configuration:
  - `ask` - to start chat mode
  - `ag` - to start agent mode

### Manual Installation

```bash
git clone https://github.com/noxgle/term_agent.git
cd vault3000
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## `.env` Configuration

Copy `.env.copy` to `.env` and paste your api key.

Example `.env` file:

```
AI_ENGINE=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.5
OPENAI_MAX_TOKENS=1000

GOOGLE_API_KEY=...
GOOGLE_MODEL=gemini-2.0-flash

OLLAMA_URL=http://localhost:11434/api/chat
OLLAMA_MODEL=granite3.3:8b
OLLAMA_TEMPERATURE=0.5

SSH_REMOTE_TIMEOUT=360
AUTO_ACCEPT=false

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

### Loading a prompt/goal from a file

You can load a prompt or goal from a file by typing:

//path/to/your_prompt.txt

The agent will read the file and use its contents as your goal or question.

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

> **Tip:**  For the best experience with the remote agent mode (SSH), it is recommended to set up SSH key-based authentication on your target servers.  
> This allows the agent to execute commands without repeatedly prompting for a password and improves both security and usability.

> **Tip:** Change the path `/home/username/term_agent` to your own if the project is in a different location.

> **Warning:**  
> The agent can execute arbitrary shell commands (locally or remotely via SSH) based on user input or AI suggestions.  
> **Always review and understand the commands before running the agent.**  
> Using this tool may be unsafe on production systems or with sensitive data.  
> You are responsible for any actions performed by the agent on your system.

> **Note:**  
> The larger and more advanced the AI model you use (e.g., GPT-4, Gemini 1.5, or large Ollama models), the better and more reliable the agent's results will be.  
> Smaller or older models may not handle complex tasks or multi-step automation as effectively.

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