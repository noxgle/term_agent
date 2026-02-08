import json
import os
import re
import tempfile
import shutil
import subprocess
import time
import uuid
from user.UserInteractionHandler import UserInteractionHandler
from security.SecurityValidator import SecurityValidator
from context.ContextManager import ContextManager
from ai.AICommunicationHandler import AICommunicationHandler
from file_operator.FileOperator import FileOperator
from plan.ActionPlanManager import ActionPlanManager, create_simple_plan

# Import our enhanced JSON validator
try:
    from json_validator.JsonValidator import create_validator
    JSON_VALIDATOR_AVAILABLE = True
except ImportError:
    JSON_VALIDATOR_AVAILABLE = False

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
            self.input_text = f"{user+'@' if user else ''}{host}{':'+str(terminal.port) if terminal.port else ''}"
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
                "{'tool': 'bash', 'command': '...', 'timeout': timeout in seconds, 'explain' : 'short explain what the command are doing'} "
                "or {'tool': 'write_file', 'path': '...', 'content': '...', 'explain' : 'short explain what are doing'} "
                "or {'tool': 'edit_file', 'path': '...', 'action': 'replace|insert_after|insert_before|delete_line', 'search': '...', 'replace': '...', 'line': '...', 'explain' : 'short explain what are doing'} "
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
        # Use the provided terminal logger for consistent logging across the app
        try:
            self.logger = terminal.logger
        except Exception:
            import logging
            self.logger = logging.getLogger("VaultAIAgentRunner")

        self.user = user
        self.host = host
        self.window_size = window_size

        if self.user == "root":
            self.system_prompt_agent = f"{self.system_prompt_agent} You dont need sudo, you are root."

        # Initialize ContextManager for conversation context and sliding window functionality
        self.context_manager = ContextManager(window_size=window_size, logger=self.logger, runner=self)

        # Initialize context with system prompt and user goal
        self.context_manager.add_system_message(self.system_prompt_agent)
        self.context_manager.add_user_message(f"Your goal: {user_goal}.")

        self.steps = []
        self.summary = ""

        # Initialize SecurityValidator for command validation and security checks
        self.security_validator = SecurityValidator()
        self.ai_handler = AICommunicationHandler(terminal, logger=self.logger)
        self.file_operator = FileOperator(terminal, logger=self.logger)
        self.user_interaction_handler = UserInteractionHandler(terminal)
        
        # Initialize ActionPlanManager for task planning
        self.plan_manager = ActionPlanManager(terminal=terminal, ai_handler=self.ai_handler)
        
        # Initialize enhanced JSON validator if available
        self.json_validator = None
        if JSON_VALIDATOR_AVAILABLE:
            try:
                self.json_validator = create_validator("flexible")  # Use flexible mode for maximum compatibility
                self.logger.info("Enhanced JSON validator initialized successfully")
            except Exception as e:
                self.logger.warning(f"Failed to initialize enhanced JSON validator: {e}")
                self.json_validator = None
        else:
            self.logger.warning("Enhanced JSON validator not available, falling back to standard parsing")


    def _cleanup_request_history(self, max_entries: int = 1000):
        """
        Clean up request history to prevent memory leaks.
        Keep only the most recent entries.
        """
        self.context_manager.cleanup_request_history(max_entries)

    def _get_user_input(self, prompt_text: str, multiline: bool = False) -> str:
        return self.user_interaction_handler._get_user_input(prompt_text, multiline)

    def _initialize_plan(self):
        """
        Inicjalizuje plan działania na podstawie celu użytkownika.
        Prosi AI o stworzenie początkowego planu lub tworzy prosty plan domyślny.
        """
        terminal = self.terminal
        
        # Spróbuj utworzyć plan z AI
        try:
            terminal.print_console("\n[cyan]📋 Tworzenie planu działania...[/]")
            steps = self.plan_manager.create_plan_with_ai(self.user_goal)
            
            if steps:
                terminal.print_console(f"[green]✓ Utworzono plan z {len(steps)} krokami[/]")
                self.plan_manager.display_plan()
                
                # Dodaj plan do kontekstu AI
                plan_context = self.plan_manager.get_context_for_ai()
                self.context_manager.add_system_message(
                    f"Masz do dyspozycji następujący plan działania. "
                    f"Wykonuj kroki sekwencyjnie i aktualizuj status każdego kroku po jego wykonaniu.\n\n{plan_context}"
                )
            else:
                # Jeśli AI nie zwróciło planu, utwórz prosty plan domyślny
                self._create_default_plan()
                
        except Exception as e:
            self.logger.warning(f"Nie udało się utworzyć planu z AI: {e}")
            self._create_default_plan()

    def _create_default_plan(self):
        """Tworzy domyślny plan z ogólnymi krokami."""
        default_steps = [
            {"description": "Analiza celu i wymagań", "command": None},
            {"description": "Wykonanie niezbędnych operacji", "command": None},
            {"description": "Weryfikacja wyników", "command": None},
            {"description": "Podsumowanie zadania", "command": None},
        ]
        self.plan_manager.create_plan(self.user_goal, default_steps)
        self.terminal.print_console("[yellow]⚠ Użyto domyślnego planu[/]")

    def _update_plan_progress(self, action_description: str, success: bool = True):
        """
        Aktualizuje postęp planu po wykonaniu akcji.
        
        Args:
            action_description: Opis wykonanej akcji
            success: Czy akcja zakończyła się sukcesem
        """
        if not self.plan_manager.steps:
            return
        
        # Znajdź pierwszy oczekujący lub w trakcie krok
        current_step = self.plan_manager.get_current_step()
        if current_step:
            if success:
                self.plan_manager.mark_step_done(current_step.number, action_description)
            else:
                self.plan_manager.mark_step_failed(current_step.number, action_description)
        else:
            # Jeśli nie ma kroku w trakcie, oznacz następny oczekujący
            next_step = self.plan_manager.get_next_pending_step()
            if next_step:
                if success:
                    self.plan_manager.mark_step_done(next_step.number, action_description)
                else:
                    self.plan_manager.mark_step_failed(next_step.number, action_description)
        
        # Wyświetl skrócony postęp
        self.plan_manager.display_compact()

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
        # Get the sliding window context from the ContextManager
        state = getattr(self, "state", None)
        return self.context_manager.get_sliding_window_context(state)

    def _parse_ai_response_with_enhanced_validator(self, ai_reply: str, request_id: str) -> tuple:
        """
        Parse AI response using the enhanced JSON validator for better error recovery.
        
        Args:
            ai_reply: Raw AI response string
            request_id: Request ID for logging
            
        Returns:
            tuple: (success, data, ai_reply_json_string, corrected_successfully, error_message)
        """
        if not self.json_validator:
            # Fallback to original parsing if enhanced validator is not available
            return self._parse_ai_response_original(ai_reply, request_id)
        
        try:
            success, data, error = self.json_validator.validate_response(ai_reply)
            
            if success:
                # Successfully parsed with enhanced validator
                ai_reply_json_string = str(data) if isinstance(data, (dict, list)) else json.dumps(data)
                self.logger.debug(f"Enhanced JSON validator successfully parsed response. request_id={request_id}")
                return True, data, ai_reply_json_string, False, ""
            else:
                # Enhanced validator failed, try original parsing as fallback
                self.logger.warning(f"Enhanced JSON validator failed: {error}. Trying original parsing. request_id={request_id}")
                return self._parse_ai_response_original(ai_reply, request_id)
                
        except Exception as e:
            self.logger.error(f"Error in enhanced JSON validation: {e}. Falling back to original parsing. request_id={request_id}")
            return self._parse_ai_response_original(ai_reply, request_id)

    def _parse_ai_response_original(self, ai_reply: str, request_id: str) -> tuple:
        """
        Original AI response parsing logic (kept for fallback compatibility).
        """
        data = None
        ai_reply_json_string = None
        corrected_successfully = False
        error_message = ""

        try:
            json_match = re.search(r'```json\s*(\{.*\}|\[.*\])\s*```', ai_reply, re.DOTALL)
            if not json_match:
                json_match = re.search(r'(\{.*\}|\[.*\])', ai_reply, re.DOTALL)

            if json_match:
                potential_json_str = json_match.group(1)
                data = json.loads(potential_json_str)
                ai_reply_json_string = potential_json_str
                self.terminal.logger.debug(f"Successfully parsed extracted JSON: {potential_json_str}")
            else:
                data = json.loads(ai_reply)
                ai_reply_json_string = ai_reply
                self.terminal.logger.debug("Successfully parsed JSON from full AI reply.")
        
        except json.JSONDecodeError as e:
            # Implement multiple correction attempts (up to 3 attempts)
            max_correction_attempts = 3
            correction_attempt = 0
            corrected_successfully = False

            # Add original invalid response to context
            self.context_manager.add_assistant_message(ai_reply)

            while correction_attempt < max_correction_attempts and not corrected_successfully:
                correction_attempt += 1
                self.terminal.print_console(f"AI did not return valid JSON (attempt {correction_attempt}): {e}. Asking for correction...")
                self.terminal.logger.warning(f"Invalid JSON from AI (attempt {correction_attempt}): %s; request_id=%s", ai_reply, request_id)
                try:
                    self.logger.warning("JSON decode error from AI on attempt %s: %s; request_id=%s", correction_attempt, e, request_id)
                except Exception:
                    pass

                correction_prompt_content = (
                    f"Your previous response was not valid JSON:\n```\n{ai_reply}\n```\n"
                    f"Please correct it and reply ONLY with the valid JSON object or list of objects. "
                    f"Do not include any explanations or introductory text."
                )
                self.context_manager.add_user_message(correction_prompt_content)

                correction_window_for_prompt = self._sliding_window_context()
                correction_llm_prompt_parts = []
                for m_corr in correction_window_for_prompt:
                    if m_corr["role"] == "system": continue
                    correction_llm_prompt_parts.append(f"{m_corr['role']}: {m_corr['content']}")
                correction_llm_prompt_text = "\n".join(correction_llm_prompt_parts)

                corrected_ai_reply = self.ai_handler.send_request(
                    system_prompt=self.system_prompt_agent, 
                    user_prompt=correction_llm_prompt_text,
                    request_format="json"
                )

                self.terminal.print_console(f"AI agent correction attempt {correction_attempt}: {corrected_ai_reply}")

                if corrected_ai_reply:
                    try:
                        json_match_corr = re.search(r'```json\s*(\{.*\}|\[.*\])\s*```', corrected_ai_reply, re.DOTALL)
                        if not json_match_corr:
                            json_match_corr = re.search(r'(\{.*\}|\[.*\])', corrected_ai_reply, re.DOTALL)

                        if json_match_corr:
                            potential_json_corr_str = json_match_corr.group(1)
                            data = json.loads(potential_json_corr_str)
                            ai_reply_json_string = potential_json_corr_str
                            self.terminal.logger.debug(f"Successfully parsed extracted corrected JSON: {potential_json_corr_str}")
                        else:
                            data = json.loads(corrected_ai_reply)
                            ai_reply_json_string = corrected_ai_reply
                            self.terminal.logger.debug("Successfully parsed corrected JSON from full reply.")

                        self.terminal.print_console(f"Successfully parsed corrected JSON after {correction_attempt} attempt(s).")
                        try:
                            self.logger.debug("Successfully parsed corrected JSON for assistant reply. request_id=%s", request_id)
                        except Exception:
                            pass
                        # Remove the correction request and original failed reply from context
                        self.context_manager.context.pop()  # Remove user's correction request
                        self.context_manager.context.pop()  # Remove assistant's failed reply
                        corrected_successfully = True
                        break  # Exit the correction loop on success
                    except json.JSONDecodeError as e2:
                        self.terminal.print_console(f"AI still did not return valid JSON after correction attempt {correction_attempt} ({e2}).")
                        self.terminal.logger.warning(f"Invalid JSON from AI (attempt {correction_attempt + 1}): {corrected_ai_reply}")
                        # Update ai_reply for next correction attempt
                        ai_reply = corrected_ai_reply
                        e = e2  # Update error for next iteration
                        # If this is the last attempt, we'll handle it after the loop
                        if correction_attempt == max_correction_attempts:
                            error_message = f"Failed to parse JSON after {max_correction_attempts} correction attempts"
                            break
                else: # No corrected reply
                    self.terminal.print_console(f"AI did not provide a correction on attempt {correction_attempt}.")
                    try:
                        self.logger.warning("AI did not respond with corrected JSON to correction request. request_id=%s", request_id)
                    except Exception:
                        pass
                    # If this is the last attempt, we'll handle it after the loop
                    if correction_attempt == max_correction_attempts:
                        error_message = f"Failed to get corrected JSON after {max_correction_attempts} attempts"
                        break

        return data is not None, data, ai_reply_json_string, corrected_successfully, error_message


    def run(self):
        terminal = self.terminal
        keep_running = True

        try:
            self.logger.info("Starting VaultAIAgentRunner.run for goal: %s", self.user_goal)
        except Exception:
            pass

        # Utwórz początkowy plan na podstawie celu użytkownika
        self._initialize_plan()

        while keep_running:
            task_finished_successfully = False
            agent_should_stop_this_turn = False

            for step_count in range(100):  # Limit steps to avoid infinite loops
                try:
                    # Generate a unique request id for this step to trace the flow
                    request_id = uuid.uuid4().hex
                    self.logger.debug("Step %s starting; request_id=%s; current context len=%s", step_count, request_id, self.context_manager.get_context_length())
                except Exception:
                    pass
                window_context = self._sliding_window_context()

                prompt_text_parts = []
                for m in window_context:
                    if m["role"] == "system": # System prompt is handled by connect methods or prepended
                        continue
                    prompt_text_parts.append(f"{m['role']}: {m['content']}")
                prompt_text = "\n".join(prompt_text_parts)

                ai_reply = self.ai_handler.send_request(
                    system_prompt=self.system_prompt_agent, 
                    user_prompt=prompt_text,
                    request_format="json"
                )

                try:
                    self.logger.debug("AI reply received (nil? %s) request_id=%s", ai_reply is None, request_id)
                except Exception:
                    pass

                if ai_reply is None:
                    self.summary = "Agent stopped: Failed to get response from AI after multiple retries."
                    agent_should_stop_this_turn = True
                    break
                
                data = None
                ai_reply_json_string = None
                corrected_successfully = False

                if ai_reply:
                    # Use enhanced JSON validator if available, otherwise fall back to original parsing
                    success, data, ai_reply_json_string, corrected_successfully, error_message = self._parse_ai_response_with_enhanced_validator(ai_reply, request_id)
                    
                    if not success:
                        # Enhanced validator and fallback both failed
                        terminal.print_console(f"JSON parsing failed: {error_message}. Continuing with task using alternative approach.")
                        self.summary = f"Agent continued: JSON parsing failed ({error_message}), trying alternative approach."
                        # Add the failed response to context
                        self.context_manager.add_assistant_message(ai_reply or "")
                        self.context_manager.add_user_message(f"Your response could not be parsed as JSON: {error_message}. Please provide a new response with valid JSON format.")
                        # Set data to None to trigger the fallback behavior
                        data = None

                if data is None:
                    terminal.print_console("JSON parsing failed. Continuing with task using alternative approach.")
                    self.summary = "Agent continued: JSON parsing failed, trying alternative approach."
                    try:
                        self.logger.warning("Data is None after parsing attempts. ai_reply=%s", ai_reply)
                    except Exception:
                        pass
                    if ai_reply and not ai_reply_json_string: # If original reply exists but wasn't parsed
                        self.context_manager.add_assistant_message(ai_reply)
                        self.context_manager.add_user_message("Your response could not be parsed as JSON. Please provide a new response with valid JSON format.")
                    # Continue with the loop instead of breaking
                    continue

                if ai_reply_json_string: # This is the string of the successfully parsed JSON (original or corrected)
                    self.context_manager.add_assistant_message(ai_reply_json_string)
                    # Record the assistant response with the request id for tracing
                    try:
                        self.context_manager.record_request(request_id, step_count, ai_reply_json_string)
                        self.logger.debug("Recorded assistant response in request_history; request_id=%s", request_id)
                    except Exception:
                        try:
                            self.logger.exception("Failed to record request_history for request_id=%s", request_id)
                        except Exception:
                            pass

                    # Clean up request history to prevent memory leaks
                    self._cleanup_request_history()
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
                    self.context_manager.add_user_message(f"Your response was a {type(data)}, but I expected a list or a dictionary of actions. I am stopping.")
                    agent_should_stop_this_turn = True
                    break

                for action_item_idx, action_item in enumerate(actions_to_process):
                    if agent_should_stop_this_turn: break

                    if not isinstance(action_item, dict):
                        terminal.print_console(f"Action item {action_item_idx + 1}/{len(actions_to_process)} is not a dictionary: {action_item}. Skipping.")
                        self.context_manager.add_user_message(f"Action item {action_item_idx + 1} in your list was not a dictionary: {action_item}. I am skipping it.")
                        continue

                    tool = action_item.get("tool")

                    if tool == "finish":
                        summary_text = action_item.get("summary", "Agent reported task finished.")
                        terminal.print_console(f"\nValutAI> Agent finished its task.\nSummary: {summary_text}")
                        self.summary = summary_text
                        task_finished_successfully = True
                        agent_should_stop_this_turn = True
                        try:
                            # Log finish along with the request id for traceability
                            self.logger.info("Agent signaled finish with summary: %s; request_id=%s", summary_text, request_id)
                        except Exception:
                            pass
                        break 
                    
                    elif tool == "bash":
                        command = action_item.get("command")
                        timeout = action_item.get("timeout")
                        explain = action_item.get("explain", "")
                        if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
                            terminal.print_console(f"Invalid timeout value in bash action: {timeout}. Must be a positive number. Skipping.")
                            self.context_manager.add_user_message(f"You provided an invalid timeout: {timeout} in {action_item}. Timeout must be a positive number. I am skipping it.")
                            continue
                        if not command:
                            terminal.print_console(f"No command provided in bash action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided a 'bash' tool action but no command: {action_item}. I am skipping it.")
                            continue

                        # Security: Validate command before execution
                        if terminal.block_dangerous_commands:
                            is_valid, reason = self.security_validator.validate_command(command)
                            if not is_valid:
                                terminal.print_console(f"Command validation failed: {reason}. Skipping.")
                                self.context_manager.add_user_message(f"Command '{command}' failed security validation: {reason}. I am skipping it.")
                                continue

                        if not terminal.auto_accept:
                            if self.terminal.auto_explain_command and explain:
                                confirm_prompt_text = f"\nValutAI> Agent suggests to run command: '{command}' which is intended to: {explain}. Execute? [y/N]: "
                            else:
                                confirm_prompt_text = f"\nValutAI> Agent suggests to run command: '{command}'. Execute? [y/N]: "

                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nValutAI> Provide justification for refusing the command and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nValutAI> Command refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to execute command '{command}' with justification: {justification}. Based on this, what should be the next step?")
                                continue

                        terminal.print_console(f"\nValutAI> Executing: {command}")
                        try:
                            self.logger.info("\nValutAI> Executing bash command: %s; request_id=%s", command, request_id)
                        except Exception:
                            pass
                        out, code = "", 1
                        if self.terminal.ssh_connection:
                            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
                            password = getattr(self.terminal, "ssh_password", None)
                            out, code = self.terminal.execute_remote_pexpect(command, remote, password=password, timeout=timeout)
                        else:
                            out, code = self.terminal.execute_local(command, timeout=timeout) # Corrected method call

                        self.steps.append(f"Step {len(self.steps) + 1}: executed '{command}' (code {code})")
                        terminal.print_console(f"Result (exit code: {code}):\n{out}")
                        try:
                            self.logger.debug("Command result: code=%s, out_len=%s; request_id=%s", code, len(out) if isinstance(out, str) else 0, request_id)
                        except Exception:
                            pass

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

                        user_feedback_content = f"Command '{command}' executed with exit code {code}.\n" \
                                                f"Output:\n```\n{out}\n```\n" \
                                                "Based on this, what should be the next step?"

                        if not agent_should_stop_this_turn:
                            if len(actions_to_process) > 1 and action_item_idx < len(actions_to_process) - 1:
                                user_feedback_content += "\nI will now proceed to the next action you provided."
                            # else: 
                            #     user_feedback_content += "\nWhat is the next step?"
                        
                        self.context_manager.add_user_message(user_feedback_content)
                        
                        # Aktualizuj postęp planu
                        action_desc = f"Wykonano: {command} (kod: {code})"
                        self._update_plan_progress(action_desc, success=(code == 0))

                    elif tool == "ask_user":
                        question = action_item.get("question")
                        if not question:
                            terminal.print_console(f"No question provided in ask_user action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided an 'ask_user' action but no question: {action_item}. I am skipping it.")
                            continue
                        
                        terminal.print_console(f"Agent asks: {question}")
                        user_answer = self._get_user_input("Your answer: ", multiline=True)
                        self.context_manager.add_user_message(f"User answer to '{question}': {user_answer}")

                        if not agent_should_stop_this_turn:
                            if len(actions_to_process) > 1 and action_item_idx < len(actions_to_process) - 1:
                                self.context_manager.add_user_message("I will now proceed to the next action you provided.")
                    
                    elif tool == "write_file":
                        file_path = action_item.get("path")
                        explain = action_item.get("explain", "")
                        file_content = action_item.get("content")
                        if not file_path or file_content is None:
                            terminal.print_console(f"Missing 'path' or 'content' in write_file action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided a 'write_file' tool action but no 'path' or 'content': {action_item}. I am skipping it.")
                            continue

                        if not terminal.auto_accept:
                            confirm_prompt_text = f"\nValutAI> Agent suggests to write file: '{file_path}' which is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nValutAI> Provide justification for refusing to write the file and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nValutAI> File write refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to write file '{file_path}' with justification: {justification}. Based on this, what should be the next step?")
                                continue

                        success = self.file_operator.write_file(file_path, file_content, explain)
                        if success:
                            self.context_manager.add_user_message(f"File '{file_path}' written successfully.")
                            # Aktualizuj postęp planu
                            self._update_plan_progress(f"Utworzono plik: {file_path}", success=True)
                        else:
                            self.context_manager.add_user_message(f"Failed to write file '{file_path}'.")
                            self._update_plan_progress(f"Nie udało się utworzyć pliku: {file_path}", success=False)
                        continue

                    elif tool == "edit_file":
                        file_path = action_item.get("path")
                        action = action_item.get("action")
                        search = action_item.get("search")
                        replace = action_item.get("replace")
                        line = action_item.get("line")
                        explain = action_item.get("explain", "")

                        if not file_path or not action:
                            terminal.print_console(f"Missing 'path' or 'action' in edit_file action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"Missing 'path' or 'action' in edit_file action: {action_item}. Skipping.")
                            continue

                        if not terminal.auto_accept:
                            if action == "replace" and search is not None and replace is not None:
                                desc = f"replace '{search}' with '{replace}'"
                            elif action == "insert_after" and search is not None and line is not None:
                                desc = f"insert '{line}' after '{search}'"
                            elif action == "insert_before" and search is not None and line is not None:
                                desc = f"insert '{line}' before '{search}'"
                            elif action == "delete_line" and search is not None:
                                desc = f"delete lines containing '{search}'"
                            else:
                                desc = f"perform {action} action"
                            confirm_prompt_text = f"\nValutAI> Agent suggests to edit file '{file_path}' with action: {desc}. This is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nValutAI> Provide justification for refusing to edit the file and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nValutAI> File edit refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to edit file '{file_path}' with justification: {justification}. Based on this, what should be the next step?")
                                continue

                        success = self.file_operator.edit_file(file_path, action, search, replace, line, explain)
                        if success:
                            self.context_manager.add_user_message(f"File '{file_path}' edited successfully.")
                            # Aktualizuj postęp planu
                            self._update_plan_progress(f"Edytowano plik: {file_path} ({action})", success=True)
                        else:
                            self.context_manager.add_user_message(f"Failed to edit file '{file_path}'.")
                            self._update_plan_progress(f"Nie udało się edytować pliku: {file_path}", success=False)
                        continue

                    else: 
                        terminal.print_console(f"AI response contained an invalid 'tool': '{tool}' in action: {action_item}.")
                        user_feedback_invalid_tool = (
                            f"Your response included an action with an invalid tool: '{tool}' in {action_item}. "
                            f"Valid tools are 'bash', 'ask_user', 'write_file', 'edit_file', and 'finish'. "
                        )
                        if len(actions_to_process) > 1 and action_item_idx < len(actions_to_process) - 1:
                            user_feedback_invalid_tool += "I am skipping this invalid action and proceeding with the next ones if available."
                            self.context_manager.add_user_message(user_feedback_invalid_tool)
                            continue 
                        else:
                            user_feedback_invalid_tool += "I am stopping processing of your actions for this turn. Please provide a valid set of actions."
                            self.context_manager.add_user_message(user_feedback_invalid_tool)
                            agent_should_stop_this_turn = True 
                            break 
                
                if agent_should_stop_this_turn:
                    break
            
            if not agent_should_stop_this_turn:
                terminal.print_console("Agent reached maximum step limit.")
                self.summary = "Agent stopped: Reached maximum step limit."

            if task_finished_successfully:
                # Wyświetl finalny plan
                self.terminal.print_console("\n[cyan]📋 Finalny plan działania:[/]")
                self.plan_manager.display_plan(show_details=True)
                
                continue_choice = self._get_user_input("\nValutAI> Do you want continue this thread? [y/N]: ", multiline=False).lower().strip()
                if continue_choice == 'y':
                    terminal.console.print("\nValutAI> Prompt your next goal and press [cyan]Ctrl+S[/] to start!")
                    user_input = self._get_user_input(f"{self.input_text}> ", multiline=True)
                    new_instruction = terminal.process_input(user_input)

                    # Append to existing context instead of resetting to preserve conversation history
                    self.context_manager.add_assistant_message(f"Previous task summary: {self.summary}")
                    self.context_manager.add_user_message(f"New instruction (this takes priority): {new_instruction}")

                    self.steps = []
                    self.summary = ""
                    # Reset planu dla nowego zadania
                    self.plan_manager.clear()
                    # Continue the while loop
                else:
                    keep_running = False
            else:
                # If the loop broke for any other reason (error, user cancellation), stop.
                keep_running = False
