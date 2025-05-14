import sys
from VaultAIAskRunner import VaultAIAskRunner
from term_ag import term_agent,PIPBOY_ASCII

def main():
    agent = term_agent()
    agent.console.print(PIPBOY_ASCII)
    ai_status,mode_owner,ai_model = agent.check_ai_online()
    agent.console.print("\nWelcome, Vault Dweller, to the Vault-Tec 3000.\n")
    
    if ai_status:
        agent.console.print(f"""Fallout-inspired AI ({ai_model}) is online.\n""")
    else:
        agent.console.print("[red]Fallout-inspired AI is offline.[/]\n")
        agent.console.print("[red]Please check your API key and network connection.[/]\n")
        sys.exit(1)

    agent.console.print("[Vault-Tec] What can I do for you today?\n")
    
    # try:
    #     user_goal = agent.console.input("> ")
    #     #user_goal = "sprawdz ilsoć wolengo miejsca na dysku"
    # except EOFError:
    #     agent.console.print("\n[red][Vault-Tec] EOFError: Unexpected end of file.[/]")
    #     sys.exit(1)
    # except KeyboardInterrupt:
    #     agent.console.print("\n[red][Vault-Tec] Sttopeed by user.[/]")
    #     sys.exit(1)

    if len(sys.argv) == 2:
        remote = sys.argv[1]
        user = remote.split('@')[0] if '@' in remote else None
        host = remote.split('@')[1] if '@' in remote else remote
        agent.ssh_connection = True  # Ustaw tryb zdalny
        agent.remote_host = remote   # Przechowuj host do użycia w execute_remote
        #agent.console.print(f"[Vault-Tec] AI agent started with goal: {user_goal} on {remote}.\n")
    else:
        remote = None
        user = None
        host = None
        agent.ssh_connection = False
        agent.remote_host = None
        #agent.console.print(f"[Vault-Tec] AI agent started with goal: {user_goal}")
    #runner = VaultAIAskRunner(agent, user_goal, user=user, host=host)
    runner = VaultAIAskRunner(agent, user=user, host=host)
    try:
        runner.run()
    except KeyboardInterrupt:
        agent.console.print("[red]Agent przerwany przez użytkownika.[/]")
        # Możesz dodać podsumowanie lub zapis stanu

if __name__ == "__main__":
    main()