import json
import os
import re
import tempfile
import shutil
import subprocess
import time
from prompt_toolkit import prompt

class VaultAIAgentRunner:
    def __init__(self, 
                terminal, 
                user_goal,
                system_prompt_agent=None,
                user=None, 
                host=None,
                window_size=20
                ):
        
        self.linux_distro = None
        self.linux_version = None

        if host is None:
            self.input_text = "local"
            self.linux_distro, self.linux_version = terminal.local_linux_distro
        else:
            self.input_text = f"{user+'@' if user else ''}{host}"
            self.linux_distro, self.linux_version = terminal.remote_linux_distro

        if self.linux_distro == "Unknown":
            terminal.print_console("Could not detect Linux distribution. Please ensure you are running this on a Linux system.")
            raise RuntimeError("Linux distribution detection failed.")
        
        self.user_goal = user_goal
        if system_prompt_agent is None:
            self.system_prompt_agent = (
                f"Solve the following problem. Think step-by-step before providing the final answer."
                f"You are an autonomous AI agent with access to a '{self.linux_distro} {self.linux_version}' terminal. "
                "Your task is to achieve the user's goal by executing shell commands and reading/editing/writing files. "
                "Your first task is to analyze the user's goal and decide what to do next. "
                "For each step, always reply in JSON: "
                "{'tool': 'bash', 'command': '...', 'timeout': timeout in seconds} "
                "or {'tool': 'write_file', 'path': '...', 'content': '...'} "
                "or {'tool': 'edit_file', 'path': '...', 'action': 'replace|insert_after|insert_before|delete_line', 'search': '...', 'replace': '...', 'line': '...'} "
                "or {'tool': 'ask_user', 'question': '...'} "
                "or {'tool': 'finish', 'summary': '...'} when done. "
                "At the last step, always provide a detailed summary and analysis of the entire task you performed. The summary should clearly explain what was achieved, what actions were taken, and any important results or issues encountered. "
                "Every action object MUST include a 'tool' field. Never omit the 'tool' field. "
                "Use the 'write_file' tool to create or overwrite files with specific content. "
                "After each command, you will receive its exit code and output. Decide yourself if the command was successful and what to do next. If the result is acceptable, continue. If not, try to fix the command or ask the user for clarification. "
                "At the end, always summarize what you have done in the 'summary' field of the finish message. "
                "Please remember that in this environment, each command is executed in a separate shell process (subprocess). This means that changing the directory using the `cd` command will not persist between subsequent command invocations. If you need to operate on files within a specific directory, ensure you provide the full path to those files in each command, or consider performing all related operations in a single invocation (if possible) with appropriately nested commands. "
                "Never use interactive commands (such as editors, passwd, top, less, more, nano, vi, vim, htop, mc, etc.) or commands that require user interaction. "
                "You can also use the 'edit_file' tool to modify existing files in a structured way. "
                "The 'edit_file' tool supports actions such as: "
                "- 'replace': replace all occurrences of a string, "
                "- 'insert_after': insert a line after a line containing a given string, "
                "- 'insert_before': insert a line before a line containing a given string, "
                "- 'delete_line': delete lines containing a given string. "
                " Example usage: "
                "{'tool': 'edit_file', 'path': '/etc/example.conf', 'action': 'replace', 'search': 'foo=bar', 'replace': 'foo=baz'} "
                "{'tool': 'edit_file', 'path': '/etc/example.conf', 'action': 'insert_after', 'search': '[section]', 'line': 'new_option=1'} "
                "{'tool': 'edit_file', 'path': '/etc/example.conf', 'action': 'delete_line', 'search': 'deprecated_option'} "
                """Important: Always reply with a valid JSON object. Use double quotes for all keys and string values, e.g. {"tool": "bash", "command": "ls"}. Do not use single quotes. Do not include any explanation, only the JSON object. """
            )
        else:
            self.system_prompt_agent = system_prompt_agent

        self.terminal = terminal
        self.user = user
        self.host = host
        self.window_size=window_size

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

    def _get_ai_reply_with_retry(self, terminal, system_prompt, prompt_text, retries=0, delay=10):
        if retries == 0:
            attempt = 0
            while True:
                attempt += 1
                ai_reply = None
                try:
                    if terminal.ai_engine == "ollama":
                        ai_reply = terminal.connect_to_ollama(system_prompt, prompt_text, format="json")
                    elif terminal.ai_engine == "google":
                        ai_reply = terminal.connect_to_gemini(f"{system_prompt}\n{prompt_text}")
                    elif terminal.ai_engine == "openai":
                        ai_reply = terminal.connect_to_chatgpt(system_prompt, prompt_text)
                    else:
                        terminal.print_console("Invalid AI engine specified. Stopping agent.")
                        self.summary = "Agent stopped: Invalid AI engine specified."
                        return None

                    if ai_reply and "503" not in ai_reply:
                        return ai_reply
                    else:
                        terminal.print_console(f"AI returned an error or empty response (Attempt {attempt}). Retrying in {delay}s...")
                        time.sleep(delay)

                except Exception as e:
                    terminal.print_console(f"An exception occurred while contacting AI (Attempt {attempt}): {e}. Retrying in {delay}s...")
                    time.sleep(delay)
        else:
            for attempt in range(retries):
                ai_reply = None
                try:
                    if terminal.ai_engine == "ollama":
                        ai_reply = terminal.connect_to_ollama(system_prompt, prompt_text, format="json")
                    elif terminal.ai_engine == "google":
                        ai_reply = terminal.connect_to_gemini(f"{system_prompt}\n{prompt_text}")
                    elif terminal.ai_engine == "openai":
                        ai_reply = terminal.connect_to_chatgpt(system_prompt, prompt_text)
                    else:
                        terminal.print_console("Invalid AI engine specified. Stopping agent.")
                        self.summary = "Agent stopped: Invalid AI engine specified."
                        return None

                    if ai_reply and "503" not in ai_reply:
                        return ai_reply
                    else:
                        terminal.print_console(f"AI returned an error or empty response (Attempt {attempt + 1}/{retries}). Retrying in {delay}s...")
                        time.sleep(delay)

                except Exception as e:
                    terminal.print_console(f"An exception occurred while contacting AI (Attempt {attempt + 1}/{retries}): {e}. Retrying in {delay}s...")
                    time.sleep(delay)
            
            terminal.print_console("Failed to get a valid response from AI after multiple retries.")
            return None

    def _sliding_window_context(self):
        """
        Build a sliding-window context combining summarization and persistent state.

        Behavior:
        - Always keep the first two messages (system + user goal).
        - If there are older messages beyond the sliding window, summarize them
          into a single system message (generated by _summarize).
        - Keep the last `self.window_size` messages verbatim.
        - Inject the current persistent state (`self.state`) as a final system message.

        Returns:
            list: messages to pass to the model.
        """
        # If context is small, return it (plus state injection)
        if len(self.context) <= 2 + self.window_size:
            working = list(self.context)
        else:
            # Keep first two messages (system + user goal)
            initial = self.context[:2]

            # Messages eligible for summarization: everything between the first two
            # and the recent window (exclusive).
            messages_to_summarize = self.context[2:-self.window_size]

            # Keep the most recent `window_size` messages
            recent = self.context[-self.window_size:]

            working = list(initial)

            # If there is anything to summarize, create one system summary message
            if messages_to_summarize:
                try:
                    summary_text = self._summarize(messages_to_summarize)
                    summary_message = {
                        "role": "system",
                        "content": f"[Summary of earlier conversation]\n{summary_text}"
                    }
                    working.append(summary_message)
                except Exception:
                    # If summarization fails for any reason, append a short fallback note
                    working.append({
                        "role": "system",
                        "content": "[Summary of earlier conversation could not be generated.]"
                    })

            # Append the recent messages (the sliding window)
            working.extend(recent)

        # Finally, inject the persistent agent state so the model knows current progress
        try:
            if hasattr(self, "state") and isinstance(self.state, dict) and self.state:
                state_repr = json.dumps(self.state, ensure_ascii=False)
                state_message = {"role": "system", "content": f"Current agent state: {state_repr}"}
                working.append(state_message)
        except Exception:
            # If serializing state fails, include a basic representation
            working.append({"role": "system", "content": f"Current agent state: {str(self.state)}"})

        return working

    def _summarize(self, messages: list) -> str:
        """
        Produce a concise summary for a list of messages.

        The summary should include:
        - what has been done (completed actions),
        - decisions or results,
        - outstanding/pending tasks.

        This implementation first attempts to use the configured AI engine via
        `_get_ai_reply_with_retry`. If that fails or is unavailable, it falls
        back to a lightweight heuristic extraction.

        Args:
            messages: list of message dicts to summarize (each with 'role' and 'content').

        Returns:
            str: concise multi-line summary.
        """
        # Build a compact textual representation of the messages
        joined = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            # Truncate long contents to keep prompt sizes reasonable
            preview = content if len(content) <= 800 else content[:800] + "..."
            joined.append(f"{role}: {preview}")
        prompt_text = "\n".join(joined)

        # Try to use the AI to create a high-quality summary
        summarizer_system = (
            "You are a concise summarizer. Create a short summary containing:\n"
            "- Completed actions and their results\n"
            "- Key decisions or outcomes\n"
            "- Pending/open tasks\n"
            "Format the output as bullet points, prefixed by categories: Completed:, Decisions:, Pending:."
        )

        try:
            ai_reply = self._get_ai_reply_with_retry(self.terminal, summarizer_system, prompt_text, retries=1)
            if ai_reply:
                # If AI returns a JSON-wrapped or fenced block, strip fences
                # and return the plain text reply.
                # Remove markdown code fences if present
                ai_reply = re.sub(r'```\w*', '', ai_reply)
                ai_reply = ai_reply.replace('```', '').strip()
                return ai_reply
        except Exception:
            # fall through to heuristic
            pass

        # Fallback heuristic summarization: simple extraction by keywords
        completed = []
        decisions = []
        pending = []

        for m in messages:
            text = m.get("content", "").strip()
            lower = text.lower()
            # Heuristics: look for typical phrases
            if any(k in lower for k in ("done", "completed", "finished", "succeeded", "created", "written")):
                completed.append(text.splitlines()[0])
            elif any(k in lower for k in ("decide", "decision", "choose", "will", "should")):
                decisions.append(text.splitlines()[0])
            elif any(k in lower for k in ("todo", "pending", "next", "remaining", "open")):
                pending.append(text.splitlines()[0])

        # Build the summary text
        parts = []
        parts.append("Completed:")
        parts.extend([f"- {c}" for c in (completed or ["(none detected)"])])
        parts.append("\nDecisions:")
        parts.extend([f"- {d}" for d in (decisions or ["(none detected)"])])
        parts.append("\nPending:")
        parts.extend([f"- {p}" for p in (pending or ["(none detected)"])])

        return "\n".join(parts)

    def run(self):
        terminal = self.terminal
        keep_running = True

        while keep_running:
            task_finished_successfully = False
            agent_should_stop_this_turn = False

            for step_count in range(100):  # Limit steps to avoid infinite loops
                window_context = self._sliding_window_context()

                prompt_text_parts = []
                for m in window_context:
                    if m["role"] == "system": # System prompt is handled by connect methods or prepended
                        continue
                    prompt_text_parts.append(f"{m['role']}: {m['content']}")
                prompt_text = "\n".join(prompt_text_parts)

                ai_reply = self._get_ai_reply_with_retry(terminal, self.system_prompt_agent, prompt_text)

                if ai_reply is None:
                    self.summary = "Agent stopped: Failed to get response from AI after multiple retries."
                    agent_should_stop_this_turn = True
                    break
                
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
                        
                        corrected_ai_reply = self._get_ai_reply_with_retry(terminal, self.system_prompt_agent, correction_llm_prompt_text)
                        
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
                                agent_should_stop_this_turn = True
                                break 
                        else: # No corrected reply
                            terminal.print_console("AI did not provide a correction. Stopping agent.")
                            self.summary = "Agent stopped: AI did not respond to correction request."
                            agent_should_stop_this_turn = True
                            break
                
                if data is None:
                    terminal.print_console("Internal error: JSON data is None after parsing attempts. Stopping agent.")
                    self.summary = "Agent stopped: Internal error during JSON parsing."
                    if ai_reply and not ai_reply_json_string and not corrected_ai_reply_string: # If original reply exists but wasn't parsed
                        self.context.append({"role": "assistant", "content": ai_reply})
                        self.context.append({"role": "user", "content": "Your response could not be parsed as JSON and no correction was successful. Stopping."})
                    agent_should_stop_this_turn = True
                    break

                if ai_reply_json_string: # This is the string of the successfully parsed JSON (original or corrected)
                    self.context.append({"role": "assistant", "content": ai_reply_json_string})
                else:
                    terminal.logger.error("Logic error: data is not None, but no JSON string was stored for context.")
                    self.summary = "Agent stopped: Internal logic error in response handling for context."
                    agent_should_stop_this_turn = True
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
                    agent_should_stop_this_turn = True
                    break

                for action_item_idx, action_item in enumerate(actions_to_process):
                    if agent_should_stop_this_turn: break

                    if not isinstance(action_item, dict):
                        terminal.print_console(f"Action item {action_item_idx + 1}/{len(actions_to_process)} is not a dictionary: {action_item}. Skipping.")
                        self.context.append({"role": "user", "content": f"Action item {action_item_idx + 1} in your list was not a dictionary: {action_item}. I am skipping it."})
                        continue

                    tool = action_item.get("tool")

                    if tool == "finish":
                        summary_text = action_item.get("summary", "Agent reported task finished.")
                        terminal.print_console(f"Agent finished its task. Summary: {summary_text}")
                        self.summary = summary_text
                        task_finished_successfully = True
                        agent_should_stop_this_turn = True
                        break 
                    
                    elif tool == "bash":
                        command = action_item.get("command")
                        timeout = action_item.get("timeout")
                        if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
                            terminal.print_console(f"Invalid timeout value in bash action: {timeout}. Must be a positive number. Skipping.")
                            self.context.append({"role": "user", "content": f"You provided an invalid timeout: {timeout} in {action_item}. Timeout must be a positive number. I am skipping it."})
                            continue
                        if not command:
                            terminal.print_console(f"No command provided in bash action: {action_item}. Skipping.")
                            self.context.append({"role": "user", "content": f"You provided a 'bash' tool action but no command: {action_item}. I am skipping it."})
                            continue

                        if not terminal.auto_accept:

                            confirm_prompt_text = f"ValutAI> '{command}'. Execute? [y/N]: "
                            if len(actions_to_process) > 1:
                                confirm_prompt_text = f"Agent suggests action {action_item_idx + 1}/{len(actions_to_process)}: '{command}'. Execute? [y/N]: "

                            confirm = input(f"{confirm_prompt_text}").lower().strip()
                            if confirm != 'y':
                                justification = input("Provide justification for refusing the command: ").strip()
                                terminal.print_console(f"Command refused by user. Justification: {justification}\n")
                                self.context.append({"role": "user", "content": f"User refused to execute command '{command}' with justification: {justification}. Based on this, what should be the next step?"})
                                continue

                        terminal.print_console(f"\nValutAI> Executing: {command}")
                        out, code = "", 1
                        if self.terminal.ssh_connection:
                            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
                            password = getattr(self.terminal, "ssh_password", None)
                            out, code = self.terminal.execute_remote_pexpect(command, remote, password=password, timeout=timeout)
                        else:
                            out, code = self.terminal.execute_local(command, timeout=timeout) # Corrected method call

                        self.steps.append(f"Step {len(self.steps) + 1}: executed '{command}' (code {code})")
                        terminal.print_console(f"Result (code {code}):\n{out}")

                        # Check for SSH connection error (code 255)
                        # Note: code 255 may also occur due to remote command failures or traps,
                        # so we only stop for true connection issues when output indicates connection problems
                        if self.terminal.ssh_connection and code == 255 and ("Connection refused" in out or "No route to host" in out or "Connection timed out" in out or "Permission denied" in out or "Operation timed out" in out):
                            terminal.print_console(
                                "[ERROR] SSH connection failed (host may be offline or unreachable). "
                                "Agent is stopping."
                            )
                            self.summary = "Agent stopped: SSH connection failed (host offline or unreachable)."
                            agent_should_stop_this_turn = True
                            break
                        elif self.terminal.ssh_connection and code == 255:
                            # Likely a command failure misinterpreted as connection error, continue
                            terminal.print_console(
                                "[WARNING] Received exit code 255 from remote command, "
                                "but no connection error detected. Treating as command failure."
                            )

                        user_feedback_content = (
                            f"Command '{command}' executed with exit code {code}.\n"
                            f"Output:\n```\n{out}\n```\n"
                            "Based on this, what should be the next step?"
                        )

                        if not agent_should_stop_this_turn:
                            if len(actions_to_process) > 1 and action_item_idx < len(actions_to_process) - 1:
                                user_feedback_content += "\nI will now proceed to the next action you provided."
                            # else: 
                            #     user_feedback_content += "\nWhat is the next step?"
                        
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
                    
                    elif tool == "write_file":
                        file_path = action_item.get("path")
                        if file_path and not file_path.startswith("/"):
                            file_path = os.path.join(os.getcwd(), file_path)
                        file_content = action_item.get("content")
                        if not file_path or file_content is None:
                            terminal.print_console(f"Missing 'path' or 'content' in write_file action: {action_item}. Skipping.")
                            self.context.append({"role": "user", "content": f"You provided a 'write_file' tool action but no 'path' or 'content': {action_item}. I am skipping it."})
                            continue

                        preview = file_content[:100] + ("..." if len(file_content) > 100 else "")

                        if self.terminal.ssh_connection:
                            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmpf:
                                tmpf.write(file_content)
                                tmpf_path = tmpf.name

                            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
                            password = getattr(self.terminal, "ssh_password", None)

                            remote_tmp_path = f"/tmp/{os.path.basename(file_path)}"

                            # Remove existing file on remote host if exists
                            rm_cmd = f"rm -f '{file_path}'"
                            self.terminal.execute_remote_pexpect(rm_cmd, remote, password=password)
                            # Remove existing temp file on remote host if exists
                            rm_tmp_cmd = f"rm -f '{remote_tmp_path}'"
                            self.terminal.execute_remote_pexpect(rm_tmp_cmd, remote, password=password)

                            scp_cmd = ["scp", tmpf_path, f"{remote}:{remote_tmp_path}"]
                            try:
                                result = subprocess.run(scp_cmd, capture_output=True, text=True)
                                if result.returncode == 0:
                                    needs_sudo = not (self.user == "root" or file_path.startswith(f"/home/{self.user}") or file_path.startswith("/tmp"))
                                    if remote_tmp_path == file_path:
                                        code = 0
                                        out = ""
                                    else:
                                        if needs_sudo:
                                            cp_cmd = f"sudo cp '{remote_tmp_path}' '{file_path}' && sudo rm '{remote_tmp_path}'"
                                        else:
                                            cp_cmd = f"mv '{remote_tmp_path}' '{file_path}'"
                                        out, code = self.terminal.execute_remote_pexpect(cp_cmd, remote, password=password)
                                    if code == 0:
                                        terminal.print_console(f"File '{file_path}' copied to remote host.\nPreview:\n{preview}")
                                        self.context.append({"role": "user", "content": f"File '{file_path}' copied to remote host. Preview:\n{preview}"})
                                    else:
                                        terminal.print_console(f"Failed to move file to '{file_path}' on remote host: {out}")
                                        self.context.append({"role": "user", "content": f"Failed to move file to '{file_path}' on remote host: {out}"})
                                else:
                                    terminal.print_console(f"Failed to copy file to remote tmp: {result.stderr}")
                                    self.context.append({"role": "user", "content": f"Failed to copy file to remote tmp: {result.stderr}"})
                            finally:
                                try:
                                    os.remove(tmpf_path)
                                except Exception:
                                    pass
                        else:
                            try:
                                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                                # Remove existing file if it exists
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                                with open(file_path, "w", encoding="utf-8") as f:
                                    f.write(file_content)
                                terminal.print_console(f"File '{file_path}' written successfully.\nPreview:\n{preview}")
                                self.context.append({"role": "user", "content": f"File '{file_path}' written successfully. Preview:\n{preview}"})
                            except Exception as e:
                                terminal.print_console(f"Failed to write file '{file_path}': {e}")
                                self.context.append({"role": "user", "content": f"Failed to write file '{file_path}': {e}"})
                        continue

                    elif tool == "edit_file":
                        file_path = action_item.get("path")
                        action = action_item.get("action")
                        search = action_item.get("search")
                        replace = action_item.get("replace")
                        line = action_item.get("line")

                        if not file_path or not action:
                            terminal.print_console(f"Missing 'path' or 'action' in edit_file action: {action_item}. Skipping.")
                            self.context.append({"role": "user", "content": f"Missing 'path' or 'action' in edit_file action: {action_item}. Skipping."})
                            continue

                        def edit_file_local():
                            try:
                                with open(file_path, "r", encoding="utf-8") as f:
                                    lines = f.readlines()
                            except Exception as e:
                                terminal.print_console(f"Failed to read file '{file_path}': {e}")
                                self.context.append({"role": "user", "content": f"Failed to read file '{file_path}': {e}"})
                                return False

                            changed = False
                            new_lines = []
                            if action == "replace" and search is not None and replace is not None:
                                for l in lines:
                                    if search in l:
                                        new_lines.append(l.replace(search, replace))
                                        changed = True
                                    else:
                                        new_lines.append(l)
                            elif action == "insert_after" and search is not None and line is not None:
                                for l in lines:
                                    new_lines.append(l)
                                    if search in l:
                                        new_lines.append(line + "\n")
                                        changed = True
                            elif action == "insert_before" and search is not None and line is not None:
                                for l in lines:
                                    if search in l:
                                        new_lines.append(line + "\n")
                                        changed = True
                                    new_lines.append(l)
                            elif action == "delete_line" and search is not None:
                                for l in lines:
                                    if search in l:
                                        changed = True
                                        continue
                                    new_lines.append(l)
                            else:
                                terminal.print_console(f"Unsupported or missing parameters for edit_file: {action_item}")
                                self.context.append({"role": "user", "content": f"Unsupported or missing parameters for edit_file: {action_item}"})
                                return False

                            if changed:
                                try:
                                    with open(file_path, "w", encoding="utf-8") as f:
                                        f.writelines(new_lines)
                                    terminal.print_console(f"File '{file_path}' edited successfully.")
                                    self.context.append({"role": "user", "content": f"File '{file_path}' edited successfully."})
                                    return True
                                except Exception as e:
                                    terminal.print_console(f"Failed to write file '{file_path}': {e}")
                                    self.context.append({"role": "user", "content": f"Failed to write file '{file_path}': {e}"})
                                    return False
                            else:
                                terminal.print_console(f"No changes made to '{file_path}'.")
                                self.context.append({"role": "user", "content": f"No changes made to '{file_path}'."})
                                return False

                        if self.terminal.ssh_connection:
                            # Get the file from remote, edit locally, then send back
                            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
                            password = getattr(self.terminal, "ssh_password", None)
                            with tempfile.TemporaryDirectory() as tmpdir:
                                local_tmp_path = os.path.join(tmpdir, os.path.basename(file_path))
                                remote_tmp_path = f"/tmp/{os.path.basename(file_path)}"
                                # Get remote file
                                scp_get = ["scp", f"{remote}:{file_path}", local_tmp_path]
                                result = subprocess.run(scp_get, capture_output=True, text=True)
                                if result.returncode != 0:
                                    terminal.print_console(f"Failed to fetch remote file '{file_path}': {result.stderr}")
                                    self.context.append({"role": "user", "content": f"Failed to fetch remote file '{file_path}': {result.stderr}"})
                                    continue
                                # Edit locally
                                file_path_backup = file_path
                                file_path = local_tmp_path
                                ok = edit_file_local()
                                file_path = file_path_backup
                                if ok:
                                   # Remove existing target file on remote if it exists
                                    rm_cmd = f"rm -f '{file_path}'"
                                    self.terminal.execute_remote_pexpect(rm_cmd, remote, password=password)
                                    rm_tmp_cmd = f"rm -f '{remote_tmp_path}'"
                                    self.terminal.execute_remote_pexpect(rm_tmp_cmd, remote, password=password)
                                    # Send back edited file
                                    scp_put = ["scp", local_tmp_path, f"{remote}:{remote_tmp_path}"]
                                    result = subprocess.run(scp_put, capture_output=True, text=True)
                                    if result.returncode == 0:
                                        needs_sudo = not (self.user == "root" or file_path.startswith(f"/home/{self.user}") or file_path.startswith("/tmp"))
                                        if remote_tmp_path == file_path:
                                            code = 0
                                            out = ""
                                        else:
                                            if needs_sudo:
                                                cp_cmd = f"sudo cp '{remote_tmp_path}' '{file_path}' && sudo rm '{remote_tmp_path}'"
                                            else:
                                                cp_cmd = f"mv '{remote_tmp_path}' '{file_path}'"
                                            out, code = self.terminal.execute_remote_pexpect(cp_cmd, remote, password=password)
                                        if code == 0:
                                            terminal.print_console(f"File '{file_path}' edited and uploaded to remote host.")
                                            self.context.append({"role": "user", "content": f"File '{file_path}' edited and uploaded to remote host."})
                                        else:
                                            terminal.print_console(f"Failed to move edited file to '{file_path}' on remote host: {out}")
                                            self.context.append({"role": "user", "content": f"Failed to move edited file to '{file_path}' on remote host: {out}"})
                                    else:
                                        terminal.print_console(f"Failed to upload edited file to remote tmp: {result.stderr}")
                                        self.context.append({"role": "user", "content": f"Failed to upload edited file to remote tmp: {result.stderr}"})
                        else:
                            edit_file_local()
                        continue

                    else: 
                        terminal.print_console(f"AI response contained an invalid 'tool': '{tool}' in action: {action_item}.")
                        user_feedback_invalid_tool = (
                            f"Your response included an action with an invalid tool: '{tool}' in {action_item}. "
                            f"Valid tools are 'bash', 'ask_user', 'write_file', 'edit_file', and 'finish'. "
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
            
            if not agent_should_stop_this_turn:
                terminal.print_console("Agent reached maximum step limit.")
                self.summary = "Agent stopped: Reached maximum step limit."

            if task_finished_successfully:
                continue_choice = input("\nDo you want continue this thread? [y/N]: ").lower().strip()
                if continue_choice == 'y':
                    terminal.console.print("\nPrompt your text and press [cyan]Ctrl+S[/] to start!")
                    user_input= prompt(
                        f"{self.input_text}> ", 
                        multiline=True,
                        prompt_continuation=lambda width, line_number, is_soft_wrap: "... ",
                        enable_system_prompt=True,
                        key_bindings=terminal.create_keybindings()
                    )
                    new_instruction = terminal.process_input(user_input)
                    
                    # Partially reset context
                    original_system_prompt = self.context[0]
                    original_user_goal = self.context[1]
                    
                    self.context = [
                        original_system_prompt,
                        original_user_goal,
                        {"role": "assistant", "content": f"Previous task completed successfully. Summary: {self.summary}"},
                        {"role": "user", "content": f"New instruction (this takes priority): {new_instruction}"}
                    ]

                    self.steps = []
                    self.summary = ""
                    # Continue the while loop
                else:
                    keep_running = False
            else:
                # If the loop broke for any other reason (error, user cancellation), stop.
                keep_running = False
