#!/bin/bash

echo "Installing Vault 3000 terminal agent..."

# Check for required system packages
deps_missing=()
if ! command -v git &> /dev/null; then
    deps_missing+=(git)
fi
if ! command -v python3 &> /dev/null; then
    deps_missing+=(python3)
fi
if ! dpkg -l | grep -q "python3.*-venv"; then
    deps_missing+=(python3-venv)
fi
if ! command -v pip3 &> /dev/null; then
    deps_missing+=(python3-pip)
fi
if [ ${#deps_missing[@]} -ne 0 ]; then
    echo "Missing required packages: ${deps_missing[*]}"
    echo "Please install them using:"
    echo "sudo apt update && sudo apt install -y ${deps_missing[*]}"
    exit 1
fi

# Check Python version using Python itself
python3 -c 'import sys; v=sys.version_info; exit(0 if v.major >= 3 and v.minor >= 9 else 1)' || {
    echo "Python 3.9 or higher is required. Please upgrade your Python installation."
    exit 1
}

# Clone repository if not already in it
if [ ! -f "term_ask.py" ]; then
    echo "Cloning Vault 3000 repository..."
    git clone https://github.com/noxgle/term_agent.git || { echo "Failed to clone repository"; exit 1; }
    cd term_agent || { echo "Failed to enter repo directory"; exit 1; }
fi

# Create virtual environment
if [ -d ".venv" ]; then
    echo "Removing existing virtual environment..."
    rm -rf .venv
fi

echo "Creating virtual environment..."
python3 -m venv .venv || { echo "Failed to create virtual environment"; exit 1; }

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate || { echo "Failed to activate virtual environment"; exit 1; }
else
    echo "Virtual environment activation script not found"
    exit 1
fi

# Install requirements
pip install --upgrade pip || { echo "Failed to upgrade pip"; exit 1; }
echo "Installing Google Generative AI package..."
pip install --upgrade google-genai || { echo "Failed to install google-genai"; exit 1; }

echo "Installing requirements..."
pip install -r requirements.txt || { echo "Failed to install requirements"; exit 1; }

# Create .env file from template if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.copy .env
    echo "Please edit .env file and add your API keys"
fi

mkdir -p logs

echo "\nInstallation complete!"
echo "To activate the virtual environment, run: source .venv/bin/activate"
echo "Don't forget to edit .env file and add your API keys"
echo ""
echo "To start Vault 3000 in chat mode, run: python term_ask.py"
echo "To start Vault 3000 in agent mode, run: python term_ag.py"

# Add aliases
echo -e "\nWould you like to add aliases to your shell configuration? (y/n)"
read add_aliases

if [ "$add_aliases" = "y" ]; then
    CURRENT_DIR=$(pwd)
    if [ -n "$ZSH_VERSION" ]; then
        SHELL_RC="$HOME/.zshrc"
    else
        SHELL_RC="$HOME/.bashrc"
    fi
    echo -e "\n# Vault 3000 aliases" >> "$SHELL_RC"
    echo "alias ask='cd $CURRENT_DIR && source .venv/bin/activate && python term_ask.py'" >> "$SHELL_RC"
    echo "alias ag='cd $CURRENT_DIR && source .venv/bin/activate && python term_ag.py'" >> "$SHELL_RC"
    echo -e "\nAliases added to $SHELL_RC"
    echo "Please restart your terminal or run 'source $SHELL_RC' to use the aliases"
    echo "You can now use 'ask' for chat mode and 'ag' for agent mode from anywhere"
fi

echo -e "\nInstallation complete!"
echo "To activate the virtual environment, run: source .venv/bin/activate"
echo "Don't forget to edit .env file and add your API keys"
echo ""
echo "To start Vault 3000 in chat mode, run: python term_ask.py"
echo "To start Vault 3000 in agent mode, run: python term_ag.py"