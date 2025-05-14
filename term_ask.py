import sys
from VaultAIAskRunner import VaultAIAskRunner
from term_ag import term_agent,PIPBOY_ASCII

def main():
    agent = term_agent()
    agent.console.print(PIPBOY_ASCII)
    ai_status,mode_owner,ai_model = agent.check_ai_online()
    agent.console.print("\nWelcome, Vault Dweller, to the Vault 3000.\n")
    
    if ai_status:
        agent.console.print(f"""VaultAI ({ai_model}) is online. Ask your questions?\n""")
    else:
        agent.console.print("[red]VaultAI is offline.[/]\n")
        agent.console.print("[red][Vault 3000] Please check your API key and network connection.[/]\n")
        sys.exit(1)


    if len(sys.argv) == 2:
        remote = sys.argv[1]
        user = remote.split('@')[0] if '@' in remote else None
        host = remote.split('@')[1] if '@' in remote else remote
        agent.ssh_connection = True  # Ustaw tryb zdalny
        agent.remote_host = remote   # Przechowuj host do użycia w execute_remote
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
        agent.console.print("[red][Vault 3000] Agent przerwany przez użytkownika.[/]")
        # Możesz dodać podsumowanie lub zapis stanu

if __name__ == "__main__":
    main()