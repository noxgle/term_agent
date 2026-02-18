"""
FinishSubAgent - Deep analysis sub-agent for the Vault 3000 AI terminal agent.

When the main agent signals task completion (tool: finish), this sub-agent
performs a comprehensive analysis of all sources collected during the session:
- Full conversation history
- Executed bash commands and their outputs
- Web search results
- File operations
- Action plan steps with statuses
- Agent's own summary

The sub-agent generates a structured, in-depth final report in the context
of the user's original goal.
"""

import json
from typing import Optional, List, Dict, Any
from rich.panel import Panel
from rich.markdown import Markdown
from rich.console import Console
from rich import box


class FinishSubAgent:
    """
    Sub-agent performing deep analysis of all data sources collected
    by the main agent during task execution.

    This class is invoked when the main agent calls the 'finish' tool.
    Instead of simply displaying the summary, it gathers ALL available
    data sources (conversation history, executed commands, plan steps,
    file operations, web search results) and sends them to the AI for
    a comprehensive, structured analysis aligned with the user's original goal.
    """

    ANALYST_SYSTEM_PROMPT = (
        "You are an expert AI analyst specializing in post-task analysis and reporting.\n"
        "Your role is to perform a DEEP, COMPREHENSIVE analysis of all data collected during an AI agent's task execution.\n\n"
        "## YOUR MISSION\n"
        "Analyze ALL provided sources — conversation history, executed commands, file operations, "
        "web searches, and the action plan — then generate a structured, professional final report.\n\n"
        "## REPORT STRUCTURE (use this exact format)\n\n"
        "### GOAL ACHIEVEMENT ASSESSMENT\n"
        "- Was the user's goal fully achieved? (Yes / Partially / No)\n"
        "- What was achieved vs. what was not\n"
        "- Overall success rating (1-10)\n\n"
        "### EXECUTION SUMMARY\n"
        "- Total steps in plan vs. completed\n"
        "- Key actions performed\n"
        "- Critical decisions made by the agent\n\n"
        "### WHAT WORKED WELL\n"
        "- Successful operations with specific details\n"
        "- Effective strategies used\n\n"
        "### PROBLEMS & FAILURES\n"
        "- Failed commands with root cause analysis\n"
        "- Errors encountered and how (or if) they were resolved\n"
        "- Workarounds applied\n\n"
        "### DEEP TECHNICAL ANALYSIS\n"
        "- Analysis of key outputs and their implications\n"
        "- System state changes\n"
        "- Configuration changes made\n"
        "- Security considerations (if applicable)\n\n"
        "### RECOMMENDATIONS\n"
        "- What should be done next\n"
        "- Improvements to the approach\n"
        "- Potential risks or issues to monitor\n\n"
        "### FINAL VERDICT\n"
        "- Concise conclusion (2-3 sentences)\n"
        "- Task status: COMPLETED / PARTIALLY COMPLETED / FAILED\n\n"
        "Be thorough, precise, and base your analysis ONLY on the provided data. "
        "Reference specific commands, outputs, and steps where relevant. "
        "Use markdown formatting for clarity."
    )

    def __init__(self, terminal, ai_handler, logger=None):
        """
        Initialize FinishSubAgent.

        Args:
            terminal: Terminal instance for display and configuration
            ai_handler: AICommunicationHandler for AI requests
            logger: Logger instance (optional)
        """
        self.terminal = terminal
        self.ai_handler = ai_handler
        self.logger = logger or self._create_dummy_logger()
        self.console = getattr(terminal, 'console', Console())

    def run(
        self,
        user_goal: str,
        agent_summary: str,
        context_manager,
        plan_manager,
        steps: List[str],
    ) -> str:
        """
        Execute the deep analysis sub-agent.

        Collects all available data sources from the main agent session
        and generates a comprehensive analysis report.

        Args:
            user_goal: Original goal provided by the user
            agent_summary: Summary provided by the agent in the 'finish' tool call
            context_manager: ContextManager instance with full conversation history
            plan_manager: ActionPlanManager instance with plan steps and statuses
            steps: List of executed step descriptions (bash commands, file ops, etc.)

        Returns:
            str: Comprehensive analysis report text
        """
        self.terminal.print_console(
            "\nVault 3000 Deep Analysis Sub-Agent initializing..."
        )
        self.logger.info("FinishSubAgent: Starting deep analysis for goal: %s", user_goal)

        # Step 1: Collect and structure all sources
        sources = self._collect_sources(
            user_goal=user_goal,
            agent_summary=agent_summary,
            context_manager=context_manager,
            plan_manager=plan_manager,
            steps=steps,
        )

        # Step 2: Build the analysis prompt
        analysis_prompt = self._build_analysis_prompt(sources)

        # Step 3: Send to AI for deep analysis
        self.terminal.print_console(
            "Sub-agent analyzing all available sources..."
        )
        self.logger.info("FinishSubAgent: Sending %d chars of context to AI for analysis", len(analysis_prompt))

        analysis_result = self.ai_handler.send_request(
            system_prompt=self.ANALYST_SYSTEM_PROMPT,
            user_prompt=analysis_prompt,
            request_format="text"
        )

        if not analysis_result:
            self.logger.warning("FinishSubAgent: AI returned no analysis result")
            analysis_result = (
                "## Analysis Unavailable\n\n"
                "The deep analysis sub-agent could not generate a report "
                "(AI returned no response).\n\n"
                f"**Agent Summary:** {agent_summary}"
            )

        # Step 4: Display the analysis result
        self._display_analysis(analysis_result, user_goal)

        self.logger.info("FinishSubAgent: Deep analysis complete.")
        return analysis_result

    def _collect_sources(
        self,
        user_goal: str,
        agent_summary: str,
        context_manager,
        plan_manager,
        steps: List[str],
    ) -> Dict[str, Any]:
        """
        Collect and structure all available data sources.

        Gathers: conversation history, plan steps, executed commands,
        agent summary, and metadata.

        Args:
            user_goal: Original user goal
            agent_summary: Agent's own summary from 'finish' tool
            context_manager: ContextManager with full message history
            plan_manager: ActionPlanManager with plan data
            steps: List of executed step strings

        Returns:
            dict: Structured sources dictionary
        """
        sources = {
            "user_goal": user_goal,
            "agent_summary": agent_summary,
            "plan": None,
            "plan_progress": None,
            "executed_steps": steps or [],
            "conversation_messages": [],
            "web_searches": [],
            "file_operations": [],
            "bash_commands": [],
        }

        # Collect plan data
        try:
            if plan_manager and plan_manager.steps:
                sources["plan"] = plan_manager.get_context_for_ai()
                sources["plan_progress"] = plan_manager.get_progress()
                # Extract individual step details
                sources["plan_steps_detail"] = [
                    {
                        "number": s.number,
                        "description": s.description,
                        "status": s.status.value,
                        "result": s.result,
                        "command": s.command,
                    }
                    for s in plan_manager.steps
                ]
        except Exception as e:
            self.logger.warning("FinishSubAgent: Could not collect plan data: %s", e)

        # Collect conversation history from context manager
        try:
            all_messages = list(getattr(context_manager, '_messages', []))
            if not all_messages:
                # Try alternative attribute names
                all_messages = list(getattr(context_manager, 'messages', []))

            for msg in all_messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if not content:
                    continue

                sources["conversation_messages"].append({
                    "role": role,
                    "content": content[:3000]  # Limit individual message size
                })

                # Categorize messages by type
                if role == "user":
                    content_lower = content.lower()
                    # Detect web search results
                    if "web search results for" in content_lower or "sources found:" in content_lower:
                        sources["web_searches"].append(content[:2000])
                    # Detect file operations
                    elif any(op in content_lower for op in [
                        "file '", "written successfully", "read successfully",
                        "copied '", "deleted '", "edited successfully"
                    ]):
                        sources["file_operations"].append(content[:1000])
                    # Detect bash outputs
                    elif ("exit code" in content_lower or
                          "executed successfully" in content_lower or
                          "command '" in content_lower):
                        sources["bash_commands"].append(content[:2000])

        except Exception as e:
            self.logger.warning("FinishSubAgent: Could not collect conversation history: %s", e)

        self.logger.info(
            "FinishSubAgent: Sources collected — %d messages, %d web searches, "
            "%d file ops, %d bash results, %d plan steps",
            len(sources["conversation_messages"]),
            len(sources["web_searches"]),
            len(sources["file_operations"]),
            len(sources["bash_commands"]),
            len(sources.get("plan_steps_detail", [])),
        )
        return sources

    def _build_analysis_prompt(self, sources: Dict[str, Any]) -> str:
        """
        Build the analysis prompt from collected sources.

        Creates a structured prompt combining all data sources for
        comprehensive AI analysis.

        Args:
            sources: Dictionary of collected data sources

        Returns:
            str: Formatted analysis prompt
        """
        sections = []

        # Header
        sections.append("=" * 70)
        sections.append("DEEP ANALYSIS REQUEST — ALL AVAILABLE SOURCES")
        sections.append("=" * 70)

        # User goal
        sections.append("\n## USER'S ORIGINAL GOAL")
        sections.append(sources.get("user_goal", "Unknown"))

        # Agent's summary
        sections.append("\n## AGENT'S OWN SUMMARY")
        sections.append(sources.get("agent_summary", "No summary provided"))

        # Action plan
        if sources.get("plan"):
            sections.append("\n## ACTION PLAN (with statuses)")
            sections.append(sources["plan"])

        # Plan progress stats
        if sources.get("plan_progress"):
            prog = sources["plan_progress"]
            sections.append("\n## PLAN PROGRESS STATISTICS")
            sections.append(
                f"Total: {prog.get('total', 0)} | "
                f"Completed: {prog.get('completed', 0)} | "
                f"Failed: {prog.get('failed', 0)} | "
                f"Skipped: {prog.get('skipped', prog.get('total', 0) - prog.get('completed', 0) - prog.get('failed', 0) - prog.get('pending', 0) - prog.get('in_progress', 0))} | "
                f"Pending: {prog.get('pending', 0)} | "
                f"Success rate: {prog.get('percentage', 0)}%"
            )

        # Executed steps log
        if sources.get("executed_steps"):
            sections.append("\n## EXECUTED STEPS LOG")
            for step_str in sources["executed_steps"]:
                sections.append(f"  • {step_str}")

        # Bash command results (most recent / most relevant)
        if sources.get("bash_commands"):
            sections.append("\n## BASH COMMAND RESULTS")
            # Include up to 20 most recent bash results
            bash_items = sources["bash_commands"][-20:]
            for i, cmd_output in enumerate(bash_items, 1):
                sections.append(f"\n--- Command Result {i} ---")
                sections.append(cmd_output[:1500])

        # File operations
        if sources.get("file_operations"):
            sections.append("\n## FILE OPERATIONS PERFORMED")
            for i, file_op in enumerate(sources["file_operations"], 1):
                sections.append(f"\n--- File Operation {i} ---")
                sections.append(file_op[:800])

        # Web search results
        if sources.get("web_searches"):
            sections.append("\n## WEB SEARCH RESULTS GATHERED")
            for i, search_result in enumerate(sources["web_searches"], 1):
                sections.append(f"\n--- Web Search {i} ---")
                sections.append(search_result[:1500])

        # Full conversation context (limited to most relevant recent messages)
        conversation = sources.get("conversation_messages", [])
        if conversation:
            sections.append("\n## CONVERSATION HISTORY (key exchanges)")
            sections.append("(Showing up to last 30 significant messages)")
            # Filter out system messages, show user/assistant exchanges
            significant = [
                m for m in conversation
                if m["role"] in ("user", "assistant") and len(m["content"]) > 20
            ]
            # Take last 30 significant messages
            for msg in significant[-30:]:
                role_label = "AGENT" if msg["role"] == "assistant" else "SYSTEM/RESULT"
                sections.append(f"\n[{role_label}]")
                sections.append(msg["content"][:1000])

        # Footer instruction
        sections.append("\n" + "=" * 70)
        sections.append("ANALYSIS REQUEST")
        sections.append("=" * 70)
        sections.append(
            "Based on ALL the sources provided above, please generate a comprehensive "
            "deep analysis report following the structure defined in your system prompt. "
            "Be specific, reference actual commands/outputs/steps where relevant, "
            "and provide actionable insights and recommendations."
        )

        return "\n".join(sections)

    def _display_analysis(self, analysis: str, user_goal: str):
        """
        Display the analysis result with Vault-Tec themed formatting.

        Args:
            analysis: The analysis report text from AI
            user_goal: Original user goal (for panel title)
        """
        self.console.print("\n")
        self.console.print(
            Panel(
                f"VAULT 3000 — DEEP ANALYSIS COMPLETE\n"
                f"Goal: {user_goal[:80]}{'...' if len(user_goal) > 80 else ''}",
                border_style="cyan",
                box=box.DOUBLE,
            )
        )

        # Try to render as Markdown for rich formatting
        try:
            self.console.print(Markdown(analysis))
        except Exception:
            # Fallback to plain text
            self.console.print(analysis)

        self.console.print(
            Panel(
                "Analysis by Vault 3000 Deep Analysis Sub-Agent\n"
                "Vault-Tec reminds you: Knowledge is your greatest weapon!",
                border_style="cyan",
                box=box.SIMPLE,
            )
        )

    def _create_dummy_logger(self):
        """Fallback logger if none provided."""
        class DummyLogger:
            def log(self, *args, **kwargs): pass
            def debug(self, *args, **kwargs): pass
            def info(self, *args, **kwargs): pass
            def warning(self, *args, **kwargs): pass
            def error(self, *args, **kwargs): pass
            def exception(self, *args, **kwargs): pass
        return DummyLogger()
