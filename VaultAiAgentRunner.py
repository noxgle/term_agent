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
from plan.ActionPlanManager import ActionPlanManager, StepStatus, create_simple_plan

# Import Web Search Agent
try:
    from web_search.WebSearchAgent import WebSearchAgent
    WEB_SEARCH_AGENT_AVAILABLE = True
except ImportError:
    WEB_SEARCH_AGENT_AVAILABLE = False

# Import FinishSubAgent for deep task completion analysis
try:
    from finish.FinishSubAgent import FinishSubAgent
    FINISH_SUB_AGENT_AVAILABLE = True
except ImportError:
    FINISH_SUB_AGENT_AVAILABLE = False

# Import our enhanced JSON validator
try:
    from json_validator.JsonValidator import create_validator
    JSON_VALIDATOR_AVAILABLE = True
except ImportError:
    JSON_VALIDATOR_AVAILABLE = False

class VaultAIAgentRunner:
    # Maximum number of steps per task execution before stopping
    MAX_STEPS_DEFAULT = 100

    def __init__(self, 
                terminal, 
                user_goal,
                system_prompt_agent=None,
                user=None, 
                host=None,
                window_size=20,
                max_steps=None
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
                f"You are an autonomous AI agent with access to a '{self.linux_distro} {self.linux_version}' terminal.\n"
                "Your task is to achieve the user's goal by executing shell commands and file operations.\n\n"
                "## ACTION PLAN\n"
                "Follow your action plan step by step. Execute each step in order and wait for results before proceeding.\n"
                "- Only mark a step as completed after verifying success\n"
                "- Do NOT call 'finish' until all steps are completed (or unrecoverable error)\n"
                "- Use 'update_plan_step' tool to mark steps: completed, failed, or skipped\n\n"
                "## AVAILABLE TOOLS (always reply with JSON object, use double quotes)\n\n"
                "### Execution\n"
                '- {"tool": "bash", "command": "...", "timeout": seconds, "explain": "what it does"}\n'
                '- {"tool": "web_search_agent", "query": "...", "engine": "duckduckgo|searxng", "max_sources": 5, "deep_search": true, "explain": "why search"}\n\n'
                "### File Operations\n"
                '- {"tool": "read_file", "path": "...", "start_line": N, "end_line": M, "explain": "..."}\n'
                '- {"tool": "write_file", "path": "...", "content": "...", "explain": "..."}\n'
                '- {"tool": "edit_file", "path": "...", "action": "replace|insert_after|insert_before|delete_line", "search": "...", "replace": "...", "line": "...", "explain": "..."}\n'
                '- {"tool": "list_directory", "path": "...", "recursive": true|false, "pattern": "glob", "explain": "..."}\n'
                '- {"tool": "copy_file", "source": "...", "destination": "...", "overwrite": true|false, "explain": "..."}\n'
                '- {"tool": "delete_file", "path": "...", "backup": true|false, "explain": "..."}\n\n'
                "### Plan & Communication\n"
                '- {"tool": "update_plan_step", "step_number": N, "status": "completed|failed|skipped", "result": "description"}\n'
                '- {"tool": "ask_user", "question": "..."}  (NOT available in autonomous mode)\n\n'
                "### Completion\n"
                '- {"tool": "finish", "summary": "detailed summary of what was achieved"}\n'
                "  NOTE: When you call 'finish', a Deep Analysis Sub-Agent will automatically\n"
                "  review ALL sources from this session (commands, outputs, files, searches, plan)\n"
                "  and generate a comprehensive final report. Your 'summary' field should be\n"
                "  a thorough description of what was done and achieved.\n\n"
                "## ERROR HANDLING (for bash commands)\n"
                "After each command, analyze exit_code:\n"
                "- exit_code=0: SUCCESS → mark step completed, continue to next\n"
                "- exit_code≠0: FAILURE → decide action:\n"
                "  - RETRY: transient error (timeout, network) → retry same/modified command\n"
                "  - FIX: wrong command (syntax, missing file) → fix and retry\n"
                "  - SKIP: non-critical error → skip and continue\n"
                "  - FAIL: critical error → mark failed, ask user or stop\n\n"
                "## CONSTRAINTS\n"
                "- Each command runs in a separate shell process; 'cd' does not persist between commands\n"
                "- Never use interactive commands: nano, vi, vim, less, more, top, htop, mc, passwd\n"
                "- In autonomous mode: DO NOT use 'ask_user', make decisions yourself\n"
                "- Always include 'tool' field in every response\n"
                "- Provide detailed summary in 'finish' explaining achievements and issues\n\n"
                "## RESPONSE FORMAT\n"
                "Reply ONLY with a valid JSON object (no explanations outside JSON):\n"
                '{"tool": "bash", "command": "ls -la", "explain": "List files in current directory"}'
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
        self.plan_manager = ActionPlanManager(terminal=terminal, ai_handler=self.ai_handler,linux_distro=self.linux_distro, linux_version=self.linux_version, logger=self.logger)
        
        # Initialize enhanced JSON validator if available
        self.json_validator = None
        if JSON_VALIDATOR_AVAILABLE:
            try:
                self.json_validator = create_validator("flexible")  # Use flexible mode for maximum compatibility
                self.logger.info("Enhanced JSON validator initialized successfully")
            except Exception as e:
                self.logger.warning(f"Failed to initialize enhanced JSON validator: {e}")
                self.json_validator = None
        # Configurable max steps limit (prevents infinite loops)
        self.max_steps = max_steps if max_steps is not None else self.MAX_STEPS_DEFAULT

        # Initialize WebSearchAgent as singleton (avoids re-creating per call)
        self.web_search_agent = None
        if WEB_SEARCH_AGENT_AVAILABLE:
            try:
                self.web_search_agent = WebSearchAgent(
                    ai_handler=self.ai_handler,
                    logger=self.logger
                )
                self.logger.info("WebSearchAgent initialized successfully")
            except Exception as e:
                self.logger.warning(f"Failed to initialize WebSearchAgent: {e}")
        else:
            self.logger.warning("WebSearchAgent not available (missing dependencies)")

        # Initialize FinishSubAgent for deep task completion analysis
        self.finish_sub_agent = None
        if FINISH_SUB_AGENT_AVAILABLE:
            try:
                self.finish_sub_agent = FinishSubAgent(
                    terminal=terminal,
                    ai_handler=self.ai_handler,
                    logger=self.logger
                )
                self.logger.info("FinishSubAgent initialized successfully")
            except Exception as e:
                self.logger.warning(f"Failed to initialize FinishSubAgent: {e}")
        else:
            self.logger.warning("FinishSubAgent not available")


    def _cleanup_request_history(self, max_entries: int = 1000):
        """
        Clean up request history to prevent memory leaks.
        Keep only the most recent entries.
        """
        self.context_manager.cleanup_request_history(max_entries)

    def _get_ai_reply_with_retry(self, terminal, system_prompt, user_prompt, retries=3):
        """
        Get AI reply with retry logic.
        Delegates to ai_handler.send_request for actual communication.
        
        Args:
            terminal: Terminal instance (kept for interface compatibility)
            system_prompt: System instructions for the AI
            user_prompt: User prompt content
            retries: Number of retry attempts (not directly used, handled by ai_handler)
            
        Returns:
            AI response string or None on failure
        """
        return self.ai_handler.send_request(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_format="text"  # Summarization doesn't need JSON
        )

    def _get_user_input(self, prompt_text: str, multiline: bool = False) -> str:
        return self.user_interaction_handler._get_user_input(prompt_text, multiline)

    def _initialize_plan(self):
        """
        Initialize action plan based on user goal.
        Asks AI to create initial plan or creates a simple default plan.
        In interactive mode, asks user to accept or modify the plan.
        """
        terminal = self.terminal
        
        # Try to create plan with AI
        try:
            terminal.print_console("\nCreating action plan...")
            steps = self.plan_manager.create_plan_with_ai(self.user_goal)
            
            if steps:
                terminal.print_console(f"[OK] Created plan with {len(steps)} steps")
                self.plan_manager.display_plan()
                
                # In interactive mode, ask for plan acceptance
                if not terminal.auto_accept:
                    self._interactive_plan_acceptance()
                
                # Add plan to AI context
                plan_context = self.plan_manager.get_context_for_ai()
                self.context_manager.add_system_message(
                    f"You have the following action plan available. "
                    f"Execute steps sequentially and update the status of each step after completion.\n\n{plan_context}"
                )
            else:
                # If AI didn't return a plan, create a simple default plan
                self._create_default_plan()
                
        except Exception as e:
            self.logger.warning(f"Failed to create plan with AI: {e}")
            self._create_default_plan()

    def _interactive_plan_acceptance(self):
        """
        Interactive loop for plan acceptance and modification.
        Asks user to accept (y), reject (n), or edit (e) the plan.
        """
        terminal = self.terminal
        
        while True:
            # Ask for acceptance
            choice = self._get_user_input(
                "\nAccept this plan? [y/n/e(edit)]: ",
                multiline=False
            ).lower().strip()
            
            if choice == 'y':
                terminal.print_console("[OK] Plan accepted. Starting execution...")
                return
            
            elif choice in ('n', 'e'):
                # Get user's change requests
                terminal.print_console("\nDescribe what you want to change in the plan:")
                terminal.print_console("(e.g., 'Add backup step before changes', 'Remove step 3', 'Change step 2 command to...')")
                changes = self._get_user_input(
                    "Your changes: ",
                    multiline=True
                ).strip()
                
                if not changes:
                    terminal.print_console("[WARN] No changes specified. Keeping current plan.")
                    continue
                
                # Ask AI to revise the plan
                terminal.print_console("\nRevising plan based on your feedback...")
                
                # Create revision prompt
                current_plan = self.plan_manager.get_context_for_ai()
                revision_prompt = (
                    f"Current plan:\n{current_plan}\n\n"
                    f"User requested changes: {changes}\n\n"
                    f"Please generate a revised action plan incorporating these changes. "
                    f"Return the plan in the same JSON format: {{'steps': [{{'description': '...', 'command': '...'}}, ...]}}"
                )
                
                try:
                    # Get revised plan from AI
                    response = self.ai_handler.send_request(
                        system_prompt="You are a task planner. Revise the action plan based on user feedback. Return only valid JSON.",
                        user_prompt=revision_prompt,
                        request_format="json"
                    )
                    
                    if response:
                        data = json.loads(response)
                        new_steps = data.get('steps', [])
                        
                        if new_steps:
                            # Clear old plan and create new one
                            self.plan_manager.clear()
                            self.plan_manager.create_plan(self.user_goal, new_steps)
                            terminal.print_console("\n[OK] Plan revised:")
                            self.plan_manager.display_plan()
                        else:
                            terminal.print_console("[WARN] Could not revise plan. Keeping current plan.")
                    else:
                        terminal.print_console("[WARN] No response from AI. Keeping current plan.")
                        
                except Exception as e:
                    terminal.print_console(f"[ERROR] Failed to revise plan: {e}")
                    terminal.print_console("[WARN] Keeping current plan.")
            
            else:
                terminal.print_console("[WARN] Invalid choice. Please enter 'y', 'n', or 'e'.")

    def _create_default_plan(self):
        """Create default plan with general steps."""
        default_steps = [
            {"description": "Analyze goal and requirements", "command": None},
            {"description": "Execute necessary operations", "command": None},
            {"description": "Verify results", "command": None},
            {"description": "Summarize task", "command": None},
        ]
        self.plan_manager.create_plan(self.user_goal, default_steps)
        self.terminal.print_console("[WARN] Using default plan")

    def _update_plan_progress(self, action_description: str, success: bool = True):
        """
        Update plan progress after action execution.
        
        Args:
            action_description: Description of executed action
            success: Whether action completed successfully
        """
        if not self.plan_manager.steps:
            return
        
        # Find first pending or in-progress step
        current_step = self.plan_manager.get_current_step()
        if current_step:
            if success:
                self.plan_manager.mark_step_done(current_step.number, action_description)
            else:
                self.plan_manager.mark_step_failed(current_step.number, action_description)
        else:
            # If no step in progress, mark next pending one
            next_step = self.plan_manager.get_next_pending_step()
            if next_step:
                if success:
                    self.plan_manager.mark_step_done(next_step.number, action_description)
                else:
                    self.plan_manager.mark_step_failed(next_step.number, action_description)
        
        # Display compact progress
        self.plan_manager.display_compact()

    def _get_plan_status_for_ai(self) -> str:
        """
        Get a concise plan status summary for AI context.
        
        Returns:
            String with current plan status
        """
        if not self.plan_manager.steps:
            return ""
        
        progress = self.plan_manager.get_progress()
        lines = ["PLAN STATUS:"]
        lines.append(f"Progress: {progress['completed']}/{progress['total']} ({progress['percentage']}%)")
        
        # Show next pending step
        next_step = self.plan_manager.get_next_pending_step()
        if next_step:
            lines.append(f"Next step to complete: Step {next_step.number}: {next_step.description}")
        
        # Show warning if plan not complete
        if progress['pending'] > 0:
            lines.append(f"[WARN] You still have {progress['pending']} pending step(s) to complete before finishing.")
        
        return "\n".join(lines)

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
                # Successfully parsed with enhanced validator - always serialize to JSON string
                ai_reply_json_string = json.dumps(data, ensure_ascii=False)
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
                        # Uses encapsulated method instead of direct deque manipulation
                        self.context_manager.remove_last_n_messages(2)
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

        # Create initial plan based on user goal
        self._initialize_plan()

        while keep_running:
            task_finished_successfully = False
            agent_should_stop_this_turn = False

            for step_count in range(self.max_steps):  # Configurable step limit
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
                    
                    if tool is None:
                        terminal.print_console(f"[WARN] AI response missing 'tool' field: {action_item}")
                        self.context_manager.add_user_message(
                            "Your response is missing the required 'tool' field. "
                            "Valid tools are: 'bash', 'ask_user', 'write_file', 'edit_file', 'update_plan_step', 'finish'. "
                            "Please provide a valid JSON response with the correct structure."
                        )
                        continue
                    

                    if tool == "finish":
                        summary_text = action_item.get("summary", "Agent reported task finished.")
                        
                        # Check if all plan steps are completed before allowing finish
                        progress = self.plan_manager.get_progress()
                        if progress['pending'] > 0 or progress['in_progress'] > 0:
                            incomplete_steps = progress['pending'] + progress['in_progress']
                            terminal.print_console(f"\n[WARN] Agent tried to finish but {incomplete_steps} plan step(s) are still pending.")
                            self.context_manager.add_user_message(
                                f"You tried to finish the task, but the action plan is not complete. "
                                f"You still have {incomplete_steps} step(s) pending or in progress. "
                                f"Please complete all plan steps before calling 'finish'. "
                                f"If a step cannot be completed, mark it as failed with a reason. "
                                f"Current plan status: {progress['completed']}/{progress['total']} completed."
                            )
                            continue
                        
                        terminal.print_console(f"\nVaultAI> Agent finished its task.\nSummary: {summary_text}")
                        self.summary = summary_text
                        task_finished_successfully = True
                        agent_should_stop_this_turn = True
                        try:
                            # Log finish along with the request id for traceability
                            self.logger.info("Agent signaled finish with summary: %s; request_id=%s", summary_text, request_id)
                        except Exception:
                            pass

                        # --- FinishSubAgent: Deep Analysis ---
                        # Ask user whether to run the deep analysis sub-agent
                        if self.finish_sub_agent is not None:
                            run_analysis = self._get_user_input(
                                "\nVaultAI> Run Deep Analysis Sub-Agent for a detailed session report? [y/N]: ",
                                multiline=False
                            ).lower().strip()

                            if run_analysis == 'y':
                                try:
                                    self.finish_sub_agent.run(
                                        user_goal=self.user_goal,
                                        agent_summary=summary_text,
                                        context_manager=self.context_manager,
                                        plan_manager=self.plan_manager,
                                        steps=self.steps,
                                    )
                                except Exception as e:
                                    terminal.print_console(f"\n[WARN] Deep Analysis Sub-Agent encountered an error: {e}")
                                    self.logger.warning("FinishSubAgent.run failed: %s", e)
                            else:
                                terminal.print_console("[dim]Deep Analysis skipped.[/dim]")
                        # --- End FinishSubAgent ---

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
                                confirm_prompt_text = f"\nVaultAI> Agent suggests to run command: '{command}' which is intended to: {explain}. Execute? [y/N]: "
                            else:
                                confirm_prompt_text = f"\nVaultAI> Agent suggests to run command: '{command}'. Execute? [y/N]: "

                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nVaultAI> Provide justification for refusing the command and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nVaultAI> Command refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to execute command '{command}' with justification: {justification}. Based on this, what should be the next step?")
                                continue

                        terminal.print_console(f"\nVaultAI> Executing: {command}")
                        try:
                            self.logger.info("\nVaultAI> Executing bash command: %s; request_id=%s", command, request_id)
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
                        #terminal.print_console(f"Result (exit code: {code}):\n{out}")
                        terminal.print_console(f"\n{out}")
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

                        # Build smart feedback based on exit code
                        if code == 0:
                            user_feedback_content = f"Command '{command}' executed successfully with exit code 0.\n" \
                                                    f"Output:\n```\n{out}\n```\n" \
                                                    "The command succeeded. You can mark this step as completed and proceed to the next step."
                        else:
                            user_feedback_content = f"Command '{command}' failed with exit code {code}.\n" \
                                                    f"Output:\n```\n{out}\n```\n" \
                                                    f"The command failed. Analyze the error and decide:\n" \
                                                    f"- RETRY: If it's a transient error (timeout, network, temporary), retry with same or modified command\n" \
                                                    f"- FIX: If the command was wrong (bad syntax, missing args), fix and retry with corrected command\n" \
                                                    f"- SKIP: If this step is non-critical and you can proceed without it\n" \
                                                    f"- FAIL: If this is a critical error that blocks progress\n" \
                                                    f"What is your decision?"

                        if not agent_should_stop_this_turn:
                            if len(actions_to_process) > 1 and action_item_idx < len(actions_to_process) - 1:
                                user_feedback_content += "\nI will now proceed to the next action you provided."
                        
                        # Update plan progress first
                        action_desc = f"Executed: {command} (exit code: {code})"
                        self._update_plan_progress(action_desc, success=(code == 0))
                        
                        # Add plan status to feedback
                        plan_status = self._get_plan_status_for_ai()
                        user_feedback_content += f"\n\n{plan_status}"
                        
                        self.context_manager.add_user_message(user_feedback_content)

                    elif tool == "ask_user":
                        # Block ask_user in autonomous mode
                        if terminal.auto_accept:
                            terminal.print_console("[WARN] Agent tried to use 'ask_user' in autonomous mode. Request rejected.")
                            self.context_manager.add_user_message(
                                "You tried to use the 'ask_user' tool, but you are running in AUTONOMOUS MODE. "
                                "In autonomous mode, you must NOT ask the user questions. "
                                "Instead, make decisions yourself based on available information and proceed with the best course of action. "
                                "Use your best judgment and continue with the task."
                            )
                            continue
                        
                        # Normal ask_user handling in interactive mode
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
                    
                    elif tool == "read_file":
                        file_path = action_item.get("path")
                        start_line = action_item.get("start_line")
                        end_line = action_item.get("end_line")
                        explain = action_item.get("explain", "")
                        
                        if not file_path:
                            terminal.print_console(f"Missing 'path' in read_file action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided a 'read_file' tool action but no 'path': {action_item}. I am skipping it.")
                            continue
                        
                        if not terminal.auto_accept:
                            line_info = ""
                            if start_line or end_line:
                                line_info = f" (lines {start_line or 'start'} to {end_line or 'end'})"
                            confirm_prompt_text = f"\nVaultAI> Agent suggests to read file: '{file_path}'{line_info}. This is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nVaultAI> Provide justification for refusing to read the file and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nVaultAI> File read refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to read file '{file_path}' with justification: {justification}. Based on this, what should be the next step?")
                                continue
                        
                        result = self.file_operator.read_file(file_path, start_line, end_line, explain)
                        if result.get("success"):
                            content = result.get("content", "")
                            total_lines = result.get("total_lines", "unknown")
                            lines_read = result.get("lines_count", 0)
                            
                            # Truncate very long content for context
                            max_content_len = 10000
                            if len(content) > max_content_len:
                                content_display = content[:max_content_len] + f"\n... (truncated, {len(content)} total characters)"
                            else:
                                content_display = content
                            
                            terminal.print_console(f"\n[OK] File '{file_path}' read successfully ({lines_read} lines).")
                            
                            feedback = f"File '{file_path}' read successfully.\n"
                            feedback += f"Total lines: {total_lines}, Lines read: {lines_read}\n\n"
                            feedback += f"Content:\n```\n{content_display}\n```"
                            
                            self._update_plan_progress(f"Read file: {file_path}", success=True)
                            self.context_manager.add_user_message(feedback)
                        else:
                            error = result.get("error", "Unknown error")
                            terminal.print_console(f"\n[ERROR] Failed to read file '{file_path}': {error}")
                            self._update_plan_progress(f"Failed to read file: {file_path}", success=False)
                            self.context_manager.add_user_message(f"Failed to read file '{file_path}': {error}")
                        continue

                    elif tool == "write_file":
                        file_path = action_item.get("path")
                        explain = action_item.get("explain", "")
                        file_content = action_item.get("content")
                        if not file_path or file_content is None:
                            terminal.print_console(f"Missing 'path' or 'content' in write_file action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided a 'write_file' tool action but no 'path' or 'content': {action_item}. I am skipping it.")
                            continue

                        if not terminal.auto_accept:
                            confirm_prompt_text = f"\nVaultAI> Agent suggests to write file: '{file_path}' which is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nVaultAI> Provide justification for refusing to write the file and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nVaultAI> File write refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to write file '{file_path}' with justification: {justification}. Based on this, what should be the next step?")
                                continue

                        success = self.file_operator.write_file(file_path, file_content, explain)
                        if success:
                            self.context_manager.add_user_message(f"File '{file_path}' written successfully.")
                            # Update plan progress
                            self._update_plan_progress(f"Created file: {file_path}", success=True)
                        else:
                            self.context_manager.add_user_message(f"Failed to write file '{file_path}'.")
                            self._update_plan_progress(f"Failed to create file: {file_path}", success=False)
                        continue

                    elif tool == "list_directory":
                        dir_path = action_item.get("path")
                        recursive = action_item.get("recursive", False)
                        pattern = action_item.get("pattern")
                        explain = action_item.get("explain", "")
                        
                        if not dir_path:
                            terminal.print_console(f"Missing 'path' in list_directory action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided a 'list_directory' tool action but no 'path': {action_item}. I am skipping it.")
                            continue
                        
                        if not terminal.auto_accept:
                            pattern_info = f" (pattern: {pattern})" if pattern else ""
                            recursive_info = " recursively" if recursive else ""
                            confirm_prompt_text = f"\nVaultAI> Agent suggests to list directory: '{dir_path}'{recursive_info}{pattern_info}. This is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nVaultAI> Provide justification for refusing and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nVaultAI> Directory listing refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to list directory '{dir_path}' with justification: {justification}. Based on this, what should be the next step?")
                                continue
                        
                        result = self.file_operator.list_directory(dir_path, recursive, pattern, explain)
                        if result.get("success"):
                            entries = result.get("entries", [])
                            total_count = result.get("total_count", 0)
                            
                            terminal.print_console(f"\n[OK] Directory '{dir_path}' listed ({total_count} entries).")
                            
                            # Format for display
                            feedback = f"Directory '{dir_path}' contents ({total_count} entries):\n\n"
                            
                            # Limit entries in context to avoid token overflow
                            max_entries = 100
                            display_entries = entries[:max_entries]
                            
                            for entry in display_entries:
                                entry_type = "📁" if entry["type"] == "directory" else "📄"
                                size_info = f" ({entry.get('size', 0)} bytes)" if entry["type"] == "file" else ""
                                feedback += f"{entry_type} {entry['name']}{size_info}\n"
                            
                            if len(entries) > max_entries:
                                feedback += f"\n... and {len(entries) - max_entries} more entries"
                            
                            self._update_plan_progress(f"Listed directory: {dir_path}", success=True)
                            self.context_manager.add_user_message(feedback)
                        else:
                            error = result.get("error", "Unknown error")
                            terminal.print_console(f"\n[ERROR] Failed to list directory '{dir_path}': {error}")
                            self._update_plan_progress(f"Failed to list directory: {dir_path}", success=False)
                            self.context_manager.add_user_message(f"Failed to list directory '{dir_path}': {error}")
                        continue

                    elif tool == "copy_file":
                        source = action_item.get("source")
                        destination = action_item.get("destination")
                        overwrite = action_item.get("overwrite", False)
                        explain = action_item.get("explain", "")
                        
                        if not source or not destination:
                            terminal.print_console(f"Missing 'source' or 'destination' in copy_file action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided a 'copy_file' tool action but missing 'source' or 'destination': {action_item}. I am skipping it.")
                            continue
                        
                        if not terminal.auto_accept:
                            overwrite_info = " (overwrite)" if overwrite else ""
                            confirm_prompt_text = f"\nVaultAI> Agent suggests to copy '{source}' to '{destination}'{overwrite_info}. This is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nVaultAI> Provide justification for refusing and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nVaultAI> Copy operation refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to copy '{source}' to '{destination}' with justification: {justification}. Based on this, what should be the next step?")
                                continue
                        
                        result = self.file_operator.copy_file(source, destination, overwrite, explain)
                        if result.get("success"):
                            terminal.print_console(f"\n[OK] Copied '{source}' to '{destination}'.")
                            self._update_plan_progress(f"Copied: {source} -> {destination}", success=True)
                            self.context_manager.add_user_message(f"Successfully copied '{source}' to '{destination}'.")
                        else:
                            error = result.get("error", "Unknown error")
                            terminal.print_console(f"\n[ERROR] Failed to copy: {error}")
                            self._update_plan_progress(f"Failed to copy: {source} -> {destination}", success=False)
                            self.context_manager.add_user_message(f"Failed to copy '{source}' to '{destination}': {error}")
                        continue

                    elif tool == "delete_file":
                        file_path = action_item.get("path")
                        backup = action_item.get("backup", False)
                        explain = action_item.get("explain", "")
                        
                        if not file_path:
                            terminal.print_console(f"Missing 'path' in delete_file action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided a 'delete_file' tool action but no 'path': {action_item}. I am skipping it.")
                            continue
                        
                        if not terminal.auto_accept:
                            backup_info = " (with backup)" if backup else ""
                            confirm_prompt_text = f"\nVaultAI> Agent suggests to delete '{file_path}'{backup_info}. This is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nVaultAI> Provide justification for refusing and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nVaultAI> Delete operation refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to delete '{file_path}' with justification: {justification}. Based on this, what should be the next step?")
                                continue
                        
                        result = self.file_operator.delete_file(file_path, backup, explain)
                        if result.get("success"):
                            backup_path = result.get("backup_path")
                            terminal.print_console(f"\n[OK] Deleted '{file_path}'.")
                            if backup_path:
                                terminal.print_console(f"Backup created: {backup_path}")
                                self._update_plan_progress(f"Deleted: {file_path} (backup: {backup_path})", success=True)
                                self.context_manager.add_user_message(f"Successfully deleted '{file_path}'. Backup created at: {backup_path}")
                            else:
                                self._update_plan_progress(f"Deleted: {file_path}", success=True)
                                self.context_manager.add_user_message(f"Successfully deleted '{file_path}'.")
                        else:
                            error = result.get("error", "Unknown error")
                            terminal.print_console(f"\n[ERROR] Failed to delete: {error}")
                            self._update_plan_progress(f"Failed to delete: {file_path}", success=False)
                            self.context_manager.add_user_message(f"Failed to delete '{file_path}': {error}")
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
                            confirm_prompt_text = f"\nVaultAI> Agent suggests to edit file '{file_path}' with action: {desc}. This is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nVaultAI> Provide justification for refusing to edit the file and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nVaultAI> File edit refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to edit file '{file_path}' with justification: {justification}. Based on this, what should be the next step?")
                                continue

                        success = self.file_operator.edit_file(file_path, action, search, replace, line, explain)
                        if success:
                            self.context_manager.add_user_message(f"File '{file_path}' edited successfully.")
                            # Update plan progress
                            self._update_plan_progress(f"Edited file: {file_path} ({action})", success=True)
                        else:
                            self.context_manager.add_user_message(f"Failed to edit file '{file_path}'.")
                            self._update_plan_progress(f"Failed to edit file: {file_path}", success=False)
                        continue

                    elif tool == "update_plan_step":
                        step_number = action_item.get("step_number")
                        status = action_item.get("status")
                        result = action_item.get("result", "")
                        
                        # Validate parameters
                        if step_number is None or status is None:
                            terminal.print_console(f"Missing 'step_number' or 'status' in update_plan_step action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided 'update_plan_step' but missing 'step_number' or 'status': {action_item}. I am skipping it.")
                            continue
                        
                        # Validate status value
                        valid_statuses = ["completed", "failed", "skipped", "in_progress"]
                        if status not in valid_statuses:
                            terminal.print_console(f"Invalid status '{status}' in update_plan_step. Valid: {valid_statuses}. Skipping.")
                            self.context_manager.add_user_message(f"Invalid status '{status}'. Valid statuses are: {', '.join(valid_statuses)}. I am skipping it.")
                            continue
                        
                        # Convert status string to StepStatus enum (already imported at module level)
                        status_map = {
                            "completed": StepStatus.COMPLETED,
                            "failed": StepStatus.FAILED,
                            "skipped": StepStatus.SKIPPED,
                            "in_progress": StepStatus.IN_PROGRESS
                        }
                        step_status = status_map[status]
                        
                        # Update the plan step
                        success = self.plan_manager.mark_step_status(step_number, step_status, result)
                        if success:
                            terminal.print_console(f"[OK] Plan step {step_number} marked as {status}")
                            self.context_manager.add_user_message(f"Plan step {step_number} successfully marked as {status}. Result: {result}")
                            # Display updated plan
                            self.plan_manager.display_compact()
                        else:
                            terminal.print_console(f"[WARN] Failed to update plan step {step_number}")
                            self.context_manager.add_user_message(f"Failed to update plan step {step_number}. Step may not exist in the plan.")
                        continue

                    elif tool == "web_search_agent":
                        # Web search agent tool for internet research
                        query = action_item.get("query")
                        engine = action_item.get("engine", "duckduckgo")
                        max_sources = action_item.get("max_sources", 5)
                        deep_search = action_item.get("deep_search", True)
                        explain = action_item.get("explain", "")
                        
                        if not query:
                            terminal.print_console(f"No query provided in web_search_agent action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided a 'web_search_agent' tool action but no query: {action_item}. I am skipping it.")
                            continue
                        
                        # Check if WebSearchAgent is available
                        if not WEB_SEARCH_AGENT_AVAILABLE:
                            terminal.print_console("[ERROR] WebSearchAgent is not available. Please install required dependencies: pip install duckduckgo-search beautifulsoup4 lxml")
                            self.context_manager.add_user_message(
                                "The 'web_search_agent' tool is not available because required dependencies are missing. "
                                "Install them with: pip install duckduckgo-search beautifulsoup4 lxml. "
                                "Try an alternative approach to complete this step."
                            )
                            continue
                        
                        if not terminal.auto_accept:
                            confirm_prompt_text = f"\nVaultAI> Agent suggests to search web for: '{query}' using {engine}. This is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nVaultAI> Provide justification for refusing the search and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nVaultAI> Web search refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to search for '{query}' with justification: {justification}. Based on this, what should be the next step?")
                                continue
                        
                        terminal.print_console(f"\nVaultAI> Executing web search: {query}")
                        try:
                            self.logger.info("Executing web search: query='%s', engine=%s; request_id=%s", query, engine, request_id)
                        except Exception:
                            pass
                        
                        try:
                            # Use singleton WebSearchAgent (initialized in __init__)
                            search_result = self.web_search_agent.execute(
                                query=query,
                                engine=engine,
                                max_sources=max_sources,
                                deep_search=deep_search
                            )
                            
                            if search_result.get('success'):
                                # Build feedback message
                                summary = search_result.get('summary', '')
                                sources = search_result.get('sources', [])
                                confidence = search_result.get('confidence', 0)
                                iterations = search_result.get('iterations_used', 0)
                                
                                terminal.print_console(f"\n[OK] Web search completed (confidence: {confidence:.0%}, {len(sources)} sources, {iterations} iterations)")
                                
                                # Format results for AI context
                                result_text = f"Web Search Results for: '{query}'\n\n"
                                result_text += f"Summary:\n{summary}\n\n"
                                result_text += f"Confidence: {confidence:.0%}\n"
                                result_text += f"Sources found: {len(sources)}\n\n"
                                
                                if sources:
                                    result_text += "Sources:\n"
                                    for i, source in enumerate(sources[:5], 1):
                                        result_text += f"{i}. {source.get('title', 'Untitled')}\n"
                                        result_text += f"   URL: {source.get('url', '')}\n"
                                        result_text += f"   Relevance: {source.get('relevance', 0):.0%}\n"
                                        content = source.get('content', '')
                                        if content:
                                            result_text += f"   Content: {content[:500]}{'...' if len(content) > 500 else ''}\n"
                                        result_text += "\n"
                                
                                # Update plan progress
                                self._update_plan_progress(f"Web search: {query}", success=True)
                                
                                self.context_manager.add_user_message(result_text)
                            else:
                                error_msg = search_result.get('summary', 'Unknown error')
                                terminal.print_console(f"\n[ERROR] Web search failed: {error_msg}")
                                self._update_plan_progress(f"Web search failed: {query}", success=False)
                                self.context_manager.add_user_message(f"Web search for '{query}' failed: {error_msg}. Try an alternative approach.")
                                
                        except Exception as e:
                            terminal.print_console(f"\n[ERROR] Web search exception: {e}")
                            self.logger.error(f"Web search exception: {e}")
                            self._update_plan_progress(f"Web search error: {query}", success=False)
                            self.context_manager.add_user_message(f"Web search for '{query}' encountered an error: {str(e)}. Try an alternative approach.")
                        continue

                    else: 
                        terminal.print_console(f"AI response contained an invalid 'tool': '{tool}' in action: {action_item}.")
                        user_feedback_invalid_tool = (
                            f"Your response included an action with an invalid tool: '{tool}' in {action_item}. "
                            f"Valid tools are: 'bash', 'read_file', 'write_file', 'edit_file', 'list_directory', 'copy_file', 'delete_file', 'update_plan_step', 'ask_user', 'web_search_agent', and 'finish'. "
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
                # Display final plan
                self.terminal.print_console("\nFinal Action Plan:")
                self.plan_manager.display_plan(show_details=True)
                
                continue_choice = self._get_user_input("\nVaultAI> Do you want continue this thread? [y/N]: ", multiline=False).lower().strip()
                if continue_choice == 'y':
                    terminal.console.print("\nVaultAI> Prompt your next goal and press [cyan]Ctrl+S[/] to start!")
                    user_input = self._get_user_input(f"{self.input_text}> ", multiline=True)
                    new_instruction = terminal.process_input(user_input)

                    # Append to existing context instead of resetting to preserve conversation history
                    self.context_manager.add_assistant_message(f"Previous task summary: {self.summary}")
                    self.context_manager.add_user_message(f"New instruction (this takes priority): {new_instruction}")

                    self.steps = []
                    self.summary = ""
                    # Update the goal and reset plan for the new task
                    self.user_goal = new_instruction
                    self.plan_manager.clear()
                    # Create a new plan for the new goal
                    self._initialize_plan()
                    # Continue the while loop
                else:
                    keep_running = False
            else:
                # If the loop broke for any other reason (error, user cancellation), stop.
                keep_running = False
