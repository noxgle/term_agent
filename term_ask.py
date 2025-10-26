import sys
from VaultAIAskRunner import VaultAIAskRunner
from term_ag import term_agent, PIPBOY_ASCII

def main():
    agent = term_agent()
    agent.console.print(PIPBOY_ASCII)
    agent.console.print(f"{agent.print_vault_tip()}\n")
    ai_status, mode_owner, ai_model = agent.check_ai_online()
    agent.console.print("\nWelcome, Vault Dweller, to the Vault 3000.")
    agent.console.print("Mode: Chat.") 
    agent.console.print(f"Your local Linux distribution is: {agent.local_linux_distro[0]} {agent.local_linux_distro[1]}")
    
    
    if ai_status:
        agent.console.print(f"""VaultAI: {ai_model} is online.\n""")
    else:
        agent.console.print("[red]VaultAI is offline.[/]\n")
        agent.console.print("[red][Vault 3000] Please check your API key and network connection.[/]\n")
        sys.exit(1)

    if len(sys.argv) >= 2:
        agent.consle.print(f"Chat dont support remote mode.")
        sys.exit(1)
    else:
        remote = None
        user = None
        host = None
        agent.ssh_connection = False
        agent.remote_host = None

    runner = VaultAIAskRunner(agent, user=user, host=host)
    try:
        runner.run()
    except KeyboardInterrupt:
        agent.console.print("[red][Vault 3000] Agent interrupted by user.[/]")

if __name__ == "__main__":
    main()