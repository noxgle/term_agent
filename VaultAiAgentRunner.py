import json
import os
import re


# system_prompt_agent=(
#                     "You are an autonomous AI agent with access to a Linux terminal. "
#                     "Your task is to achieve the user's goal by executing shell commands and reading/writing files. "
#                     "For each step, always reply in JSON: "
#                     "{'tool': 'bash', 'command': '...'} "
#                     "or {'tool': 'ask_user', 'question': '...'} "   
#                     "or {'tool': 'finish', 'summary': '...'} when done. "
#                     "Every action object MUST include a 'tool' field. Never omit the 'tool' field. "
#                     "After each command, you will receive its exit code and output. Decide yourself if the command was successful and what to do next. If the result is acceptable, continue. If not, try to fix the command or ask the user for clarification. "
#                     "At the end, always summarize what you have done in the 'summary' field of the finish message. "
#                     "Be careful and always use safe commands. "
#                     "Never use interactive commands (such as editors, passwd, top, less, more, nano, vi, vim, htop, mc, etc.) or commands that require user interaction. "
#                     "All commands must be non-interactive and must not require additional input after execution."
#                     ),


class VaultAIAgentRunner:
    def __init__(self, 
                terminal, 
                user_goal,
                system_prompt_agent=None,
                user=None, 
                host=None,
                window_size=20
                ):
        

        
        self.user_goal = user_goal
        if system_prompt_agent is None:
            self.system_prompt_agent = (
                                        f"You are an autonomous AI agent with access to a {terminal.linux_distro} {terminal.linux_version} terminal. "
                                        "Your task is to achieve the user's goal by executing shell commands and reading/writing files. "
                                        "Your first task is to analyze the user's goal and decide what to do next. "
                                        "For each step, always reply in JSON: "
                                        "{'tool': 'bash', 'command': '...'} "
                                        "or {'tool': 'ask_user', 'question': '...'} "
                                        "or {'tool': 'finish', 'summary': '...'} when done. "
                                        "Every action object MUST include a 'tool' field. Never omit the 'tool' field. "
                                        "After each command, you will receive its exit code and output. Decide yourself if the command was successful and what to do next. If the result is acceptable, continue. If not, try to fix the command or ask the user for clarification. "
                                        "At the end, always summarize what you have done in the 'summary' field of the finish message. "
                                        "Never use interactive commands (such as editors, passwd, top, less, more, nano, vi, vim, htop, mc, etc.) or commands that require user interaction. "
                                        ),
        else:
            self.system_prompt_agent = system_prompt_agent

        self.terminal = terminal
        self.user = user
        self.host = host
        self.widow_size=window_size

        if self.user == "root":
            self.system_prompt_agent = f"{self.system_prompt_agent} You dont need sudo, you are root."

        self.context = [
            {"role": "system", "content": self.system_prompt_agent},
            {"role": "user", "content": (
                f"Your goal: {user_goal}."
            )}
        ]
        self.steps = []
        self.summary = ""

    def _sliding_window_context(self):
        # Always include the first two messages (system + user goal)
        # plus the last WINDOW_SIZE messages from the rest of the context
        base = self.context[:2]
        tail = self.context[2:]
        if len(tail) > self.widow_size:
            tail = tail[-self.widow_size:]
        return base + tail

    def run(self):
        terminal = self.terminal
        #terminal.print_console(f"[Vault-Tec] AI agent started with goal: {self.user_goal}")

        for step_count in range(100):  # Limit steps to avoid infinite loops
            window_context = self._sliding_window_context()

            prompt_text_parts = []
            for m in window_context:
                if m["role"] == "system": # System prompt is handled by connect methods or prepended
                    continue
                prompt_text_parts.append(f"{m['role']}: {m['content']}")
            prompt_text = "\n".join(prompt_text_parts)

            ai_reply = None
            if terminal.ai_engine == "ollama":
                ai_reply = terminal.connect_to_ollama(self.system_prompt_agent, prompt_text, format="json")
            elif terminal.ai_engine == "google":
                ai_reply = terminal.connect_to_gemini(f"{self.system_prompt_agent}\n{prompt_text}")
            elif terminal.ai_engine == "openai":
                ai_reply = terminal.connect_to_chatgpt(self.system_prompt_agent, prompt_text)
            else:
                terminal.print_console("Invalid AI engine specified. Stopping agent.")
                self.summary = "Agent stopped: Invalid AI engine specified."
                break
            
            #terminal.print_console(f"AI agent step {step_count + 1}: {ai_reply}")

            data = None
            ai_reply_json_string = None
            corrected_ai_reply_string = None # Stores the string of a successfully parsed corrected reply

            if ai_reply:
                try:
                    json_match = re.search(r'```json\s*(\{.*\}|\[.*\])\s*```', ai_reply, re.DOTALL)
                    if not json_match:
                        json_match = re.search(r'(\{.*\}|\[.*\])', ai_reply, re.DOTALL)

                    if json_match:
                        potential_json_str = json_match.group(1)
                        data = json.loads(potential_json_str)
                        ai_reply_json_string = potential_json_str
                        terminal.logger.debug(f"Successfully parsed extracted JSON: {potential_json_str}")
                    else:
                        data = json.loads(ai_reply)
                        ai_reply_json_string = ai_reply
                        terminal.logger.debug("Successfully parsed JSON from full AI reply.")
                
                except json.JSONDecodeError as e:
                    terminal.print_console(f"AI did not return valid JSON (attempt 1): {e}. Asking for correction...")
                    terminal.logger.warning(f"Invalid JSON from AI (attempt 1): {ai_reply}")
                    self.context.append({"role": "assistant", "content": ai_reply})
                    
                    correction_prompt_content = (
                        f"Your previous response was not valid JSON:\n```\n{ai_reply}\n```\n"
                        f"Please correct it and reply ONLY with the valid JSON object or list of objects. "
                        f"Do not include any explanations or introductory text."
                    )
                    self.context.append({"role": "user", "content": correction_prompt_content})

                    correction_window_for_prompt = self._sliding_window_context()
                    correction_llm_prompt_parts = []
                    for m_corr in correction_window_for_prompt:
                        if m_corr["role"] == "system": continue
                        correction_llm_prompt_parts.append(f"{m_corr['role']}: {m_corr['content']}")
                    correction_llm_prompt_text = "\n".join(correction_llm_prompt_parts)
                    
                    corrected_ai_reply = None
                    if terminal.ai_engine == "ollama":
                        corrected_ai_reply = terminal.connect_to_ollama(self.system_prompt_agent, correction_llm_prompt_text, format="json")
                    elif terminal.ai_engine == "google":
                        corrected_ai_reply = terminal.connect_to_gemini(f"{self.system_prompt_agent}\n{correction_llm_prompt_text}")
                    else: # openai
                        corrected_ai_reply = terminal.connect_to_chatgpt(self.system_prompt_agent, correction_llm_prompt_text)
                    
                    terminal.print_console(f"AI agent correction attempt: {corrected_ai_reply}")

                    if corrected_ai_reply:
                        try:
                            json_match_corr = re.search(r'```json\s*(\{.*\}|\[.*\])\s*```', corrected_ai_reply, re.DOTALL)
                            if not json_match_corr:
                                json_match_corr = re.search(r'(\{.*\}|\[.*\])', corrected_ai_reply, re.DOTALL)

                            if json_match_corr:
                                potential_json_corr_str = json_match_corr.group(1)
                                data = json.loads(potential_json_corr_str)
                                corrected_ai_reply_string = potential_json_corr_str
                                terminal.logger.debug(f"Successfully parsed extracted corrected JSON: {potential_json_corr_str}")
                            else:
                                data = json.loads(corrected_ai_reply)
                                corrected_ai_reply_string = corrected_ai_reply
                                terminal.logger.debug("Successfully parsed corrected JSON from full reply.")
                            
                            terminal.print_console("Successfully parsed corrected JSON.")
                            self.context.pop()  # Remove user's correction request
                            self.context.pop()  # Remove assistant's failed reply
                            ai_reply_json_string = corrected_ai_reply_string # This is now the primary response string
                        except json.JSONDecodeError as e2:
                            terminal.print_console(f"AI still did not return valid JSON after correction ({e2}). Stopping agent.")
                            terminal.logger.error(f"Invalid JSON from AI (attempt 2): {corrected_ai_reply}")
                            self.summary = f"Agent stopped: AI failed to provide valid JSON even after retry ({e2})."
                            self.context.append({"role": "assistant", "content": corrected_ai_reply or ""})
                            self.context.append({"role": "user", "content": f"Your response was still not valid JSON: {e2}. I am stopping."})
                            break 
                    else: # No corrected reply
                        terminal.print_console("AI did not provide a correction. Stopping agent.")
                        self.summary = "Agent stopped: AI did not respond to correction request."
                        break
            
            if data is None:
                 terminal.print_console("Internal error: JSON data is None after parsing attempts. Stopping agent.")
                 self.summary = "Agent stopped: Internal error during JSON parsing."
                 if ai_reply and not ai_reply_json_string and not corrected_ai_reply_string: # If original reply exists but wasn't parsed
                     self.context.append({"role": "assistant", "content": ai_reply})
                     self.context.append({"role": "user", "content": "Your response could not be parsed as JSON and no correction was successful. Stopping."})
                 break

            if ai_reply_json_string: # This is the string of the successfully parsed JSON (original or corrected)
                self.context.append({"role": "assistant", "content": ai_reply_json_string})
            else:
                terminal.logger.error("Logic error: data is not None, but no JSON string was stored for context.")
                self.summary = "Agent stopped: Internal logic error in response handling for context."
                break

            actions_to_process = []
            if isinstance(data, list):
                actions_to_process = data
            elif isinstance(data, dict):
                actions_to_process = [data]
            else:
                terminal.print_console(f"AI response was not a list or dictionary after parsing: {type(data)}. Stopping agent.")
                self.summary = f"Agent stopped: AI response type was {type(data)} after successful JSON parsing."
                self.context.append({"role": "user", "content": f"Your response was a {type(data)}, but I expected a list or a dictionary of actions. I am stopping."})
                break

            agent_should_stop_this_turn = False
            for action_item_idx, action_item in enumerate(actions_to_process):
                if not isinstance(action_item, dict):
                    terminal.print_console(f"Action item {action_item_idx + 1}/{len(actions_to_process)} is not a dictionary: {action_item}. Skipping.")
                    self.context.append({"role": "user", "content": f"Action item {action_item_idx + 1} in your list was not a dictionary: {action_item}. I am skipping it."})
                    continue

                tool = action_item.get("tool")

                if tool == "finish":
                    summary_text = action_item.get("summary", "Agent reported task finished.")
                    terminal.print_console(f"Agent finished its task. Summary: {summary_text}")
                    self.summary = summary_text
                    agent_should_stop_this_turn = True
                    break 
                
                elif tool == "bash":
                    command = action_item.get("command")
                    if not command:
                        terminal.print_console(f"No command provided in bash action: {action_item}. Skipping.")
                        self.context.append({"role": "user", "content": f"You provided a 'bash' tool action but no command: {action_item}. I am skipping it."})
                        continue
                    
                    confirm_prompt_text = f"> '{command}'. Execute? [y/N]: "
                    if len(actions_to_process) > 1:
                        confirm_prompt_text = f"Agent suggests action {action_item_idx + 1}/{len(actions_to_process)}: '{command}'. Execute? [y/N]: "
                    
                    confirm = input(f"{confirm_prompt_text}").lower().strip()
                    if confirm != 'y':
                        terminal.print_console("Command execution cancelled by user. Stopping agent.")
                        self.summary = "Agent stopped: Command execution cancelled by user."
                        agent_should_stop_this_turn = True
                        break

                    terminal.print_console(f"Executing: {command}")
                    out, code = "", 1 
                    if self.terminal.ssh_connection:
                        remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
                        password = getattr(self.terminal, "ssh_password", None)
                        out, code = self.terminal.execute_remote_pexpect(command, remote, password=password)
                    else:
                        out, code = self.terminal.execute_local(command) # Corrected method call

                    self.steps.append(f"Step {len(self.steps) + 1}: executed '{command}' (code {code})")
                    terminal.print_console(f"Result (code {code}):\n{out}")

                    # Check for SSH connection error (code 255)
                    if self.terminal.ssh_connection and code == 255:
                        terminal.print_console(
                            "[ERROR] SSH connection failed (host may be offline or unreachable). "
                            "Agent is stopping."
                        )
                        self.summary = "Agent stopped: SSH connection failed (host offline or unreachable)."
                        agent_should_stop_this_turn = True
                        break

                    user_feedback_content = ""
                    # if code == 0:
                    #     user_feedback_content = f"Command '{command}' executed successfully. Output:\n```\n{out}\n```\n"
                    # else:
                    #     user_feedback_content = (
                    #         f"The command '{command}' failed with exit code {code}.\n"
                    #         f"Output:\n```\n{out}\n```\n"
                    #         f"Please analyze this error. Should you try a different command, correct this one, or stop?"
                    #     )
                    user_feedback_content = (
                        f"Command '{command}' executed with exit code {code}.\n"
                        f"Output:\n```\n{out}\n```\n"
                        "Based on this, what should be the next step?"
                    )

                    if not agent_should_stop_this_turn:
                        if len(actions_to_process) > 1 and action_item_idx < len(actions_to_process) - 1:
                            user_feedback_content += "\nI will now proceed to the next action you provided."
                        else: 
                            user_feedback_content += "\nWhat is the next step?"
                    
                    self.context.append({"role": "user", "content": user_feedback_content})

                elif tool == "ask_user":
                    question = action_item.get("question")
                    if not question:
                        terminal.print_console(f"No question provided in ask_user action: {action_item}. Skipping.")
                        self.context.append({"role": "user", "content": f"You provided an 'ask_user' action but no question: {action_item}. I am skipping it."})
                        continue
                    
                    terminal.print_console(f"Agent asks: {question}")
                    user_answer = input(f"Your answer: ")
                    self.context.append({"role": "user", "content": f"User answer to '{question}': {user_answer}"})

                    if not agent_should_stop_this_turn:
                        if len(actions_to_process) > 1 and action_item_idx < len(actions_to_process) - 1:
                             self.context.append({"role": "user", "content": "I will now proceed to the next action you provided."})
                
                elif tool == "filesystem":
                    """
                    {
                        "tool": "filesystem",
                        "structure": {
                            "dir1": {
                            "file1.txt": "Zawartość pliku 1",
                            "subdir": {
                                "file2.txt": "Zawartość pliku 2"
                            }
                            },
                            "README.md": "# Projekt"
                        }
                    }
                    """
                    # Oczekiwany format: {"tool": "filesystem", "structure": {...}}
                    structure = action_item.get("structure")
                    if not structure:
                        terminal.print_console(f"No 'structure' provided in filesystem action: {action_item}. Skipping.")
                        self.context.append({"role": "user", "content": f"You provided a 'filesystem' tool action but no 'structure': {action_item}. I am skipping it."})
                        continue

                    def create_structure(base_path, struct):
                        import os
                        for name, value in struct.items():
                            path = os.path.join(base_path, name)
                            if isinstance(value, dict):
                                # katalog
                                os.makedirs(path, exist_ok=True)
                                create_structure(path, value)
                            elif isinstance(value, str):
                                # plik z zawartością
                                os.makedirs(base_path, exist_ok=True)
                                with open(path, "w", encoding="utf-8") as f:
                                    f.write(value)
                            else:
                                terminal.print_console(f"Unknown value for '{name}' in structure: {value}")

                    try:
                        create_structure(".", structure)
                        terminal.print_console("Filesystem structure created successfully.")
                        self.context.append({"role": "user", "content": "Filesystem structure created successfully."})
                    except Exception as e:
                        terminal.print_console(f"Failed to create filesystem structure: {e}")
                        self.context.append({"role": "user", "content": f"Failed to create filesystem structure: {e}"})
                    # Po utworzeniu struktury przejdź do kolejnej akcji
                    continue

                else: 
                    terminal.print_console(f"AI response contained an invalid 'tool': '{tool}' in action: {action_item}.")
                    user_feedback_invalid_tool = (
                        f"Your response included an action with an invalid tool: '{tool}' in {action_item}. "
                        f"Valid tools are 'bash', 'ask_user', 'finish'. "
                    )
                    if len(actions_to_process) > 1 and action_item_idx < len(actions_to_process) - 1:
                        user_feedback_invalid_tool += "I am skipping this invalid action and proceeding with the next ones if available."
                        self.context.append({"role": "user", "content": user_feedback_invalid_tool})
                        continue 
                    else:
                        user_feedback_invalid_tool += "I am stopping processing of your actions for this turn. Please provide a valid set of actions."
                        self.context.append({"role": "user", "content": user_feedback_invalid_tool})
                        agent_should_stop_this_turn = True 
                        break 
            
            if agent_should_stop_this_turn:
                break 

        # terminal.print_console("\n--- Agent summary ---")
        # for s_item in self.steps:
        #     terminal.print_console(s_item)
        # terminal.print_console(self.summary)
        # terminal.print_console("--- End of agent summary ---")
