#!/bin/bash

echo "Installing Vault 3000 terminal agent..."

# Check if Python 3.9+ is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not installed. Please install Python 3.9 or higher."
    exit 1
fi

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if (( $(echo "$python_version < 3.9" | bc -l) )); then
    echo "Python 3.9 or higher is required. Current version: $python_version"
    exit 1
fi

# Clone repository
echo "Cloning Vault 3000 repository..."
git clone https://github.com/noxgle/term_agent.git
cd term_agent

# Create and activate virtual environment
echo "Creating virtual environment..."
python3 -m venv .venv

# Create and activate virtual environment
echo "Creating virtual environment..."
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install requirements
echo "Installing requirements..."
pip install -r requirements.txt

# Create .env file from template if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.copy .env
    echo "Please edit .env file and add your API keys"
fi#

echo "Installation complete!"
echo "To activate the virtual environment, run: source .venv/bin/activate"
echo "Don't forget to edit .env file and add your API keys"
echo ""
echo "To start Vault 3000 in chat mode, run: python term_ask.py"
echo "To start Vault 3000 in agent mode, run: python term_ag.py"

# Add aliases
echo -e "\nWould you like to add aliases to your shell configuration? (y/n)"
read add_aliases

if [ "$add_aliases" = "y" ]; then
    # Get the current directory path
    CURRENT_DIR=$(pwd)
    
    # Detect shell and get config file
    if [ -n "$ZSH_VERSION" ]; then
        SHELL_RC="$HOME/.zshrc"
    else
        SHELL_RC="$HOME/.bashrc"
    fi

    # Add aliases to shell config
    echo -e "\n# Vault 3000 aliases" >> "$SHELL_RC"
    echo "alias ask='cd $CURRENT_DIR && source .venv/bin/activate && python term_ask.py'" >> "$SHELL_RC"
    echo "alias ag='cd $CURRENT_DIR && source .venv/bin/activate && python term_ag.py'" >> "$SHELL_RC"

    echo -e "\nAliases added to $SHELL_RC"
    echo "Please restart your terminal or run 'source $SHELL_RC' to use the aliases"
    echo "You can now use 'ask' for chat mode and 'ag' for agent mode from anywhere"
fi

echo "Installation complete!"
echo "To activate the virtual environment, run: source .venv/bin/activate"
echo "Don't forget to edit .env file and add your API keys"
echo ""
echo "To start Vault 3000 in chat mode, run: python term_ask.py"
echo "To start Vault 3000 in agent mode, run: python term_ag.py"