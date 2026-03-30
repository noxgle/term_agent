import json
import os
import re
import tempfile
import shutil
import subprocess
import time
import uuid
import hashlib
from datetime import datetime
from typing import Dict, Optional, Any, List, Tuple
from user.UserInteractionHandler import UserInteractionHandler
from security.SecurityValidator import SecurityValidator
from context.ContextManager import ContextManager
from ai.AICommunicationHandler import AICommunicationHandler
from ai.PromptFilter import compress_prompt, estimate_token_savings
from ai.LogCompressor import LogCompressor, DynamicLogCompressor, should_compress,should_compress_adaptive
from ai.detect_output_type import detect_output_type, summarize_table 
from ai.stacktrace_summarize import summarize_stacktrace
from ai.kv_summarize import summarize_kv
from ai.json_summarize import summarize_json
import logging
from file_operator.FileOperator import FileOperator
from plan.ActionPlanManager import ActionPlanManager, StepStatus, create_simple_plan
from prompts import get_agent_system_prompt, SYSTEM_PROMPT_COMPACT_SINGLE, SYSTEM_PROMPT_COMPACT_REPAIR, SYSTEM_PROMPT_COMPACT_FINAL

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

# Import CriticSubAgent for answer correctness scoring
try:
    from critic.CriticSubAgent import CriticSubAgent
    CRITIC_SUB_AGENT_AVAILABLE = True
except ImportError:
    CRITIC_SUB_AGENT_AVAILABLE = False

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
                max_steps=None,
                compact_mode: Optional[bool] = None,
                hybrid_mode: Optional[bool] = None
                ):
        
        self.dir_app = os.path.dirname(os.path.abspath(__file__))

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
        self.force_plan = False  # Flag to force plan creation (set via --plan or [plan] keyword)
        
        # Get current date and time for context
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        user_prvileges = terminal.check_user_privileges()

        if system_prompt_agent is None:
            # Use the prompts module to generate the system prompt
            is_root = (user == "root")
            self.system_prompt_agent = get_agent_system_prompt(
                current_datetime=current_datetime,
                workspace=terminal.workspace,
                linux_distro=self.linux_distro,
                linux_version=self.linux_version,
                is_root=is_root,
                auto_explain_command=terminal.auto_explain_command,
                user_prvileges=user_prvileges
            )
        else:
            self.system_prompt_agent = system_prompt_agent

        # Compact pipeline defaults (can be overridden by env or explicit param)
        env_raw = os.getenv("AGENT_MODE")
        if env_raw is None:
            env_raw = os.getenv("COMPACT_MODE", "hybrid")
        env_value = env_raw.strip().lower()
        env_mode = "hybrid"
        if env_value in ("0", "false", "no", "off", "normal"):
            env_mode = "normal"
        elif env_value in ("1", "true", "yes", "on", "compact"):
            env_mode = "compact"
        elif env_value in ("auto", "hybrid"):
            env_mode = "hybrid"

        self.hybrid_mode = env_mode == "hybrid"
        self.compact_mode = env_mode != "normal"

        if compact_mode is not None:
            self.compact_mode = bool(compact_mode)
            if not self.compact_mode:
                self.hybrid_mode = False

        if hybrid_mode is not None:
            self.hybrid_mode = bool(hybrid_mode)
            if self.hybrid_mode:
                self.compact_mode = True
        self.compact_max_output_chars = 800
        self.compact_max_display_chars = 6000
        self.compact_max_output_tokens = 1500
        self.compact_max_summary_tokens = 1200

        # Use imported compact mode prompts from prompts module
        self.system_prompt_compact_single = SYSTEM_PROMPT_COMPACT_SINGLE
        self.system_prompt_compact_repair = SYSTEM_PROMPT_COMPACT_REPAIR
        self.system_prompt_compact_final = SYSTEM_PROMPT_COMPACT_FINAL

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

        # Initialize ContextManager for conversation context and sliding window functionality
        self.context_manager = ContextManager(window_size=window_size, logger=self.logger, runner=self)

        # Initialize context with system prompt and user goal
        self.context_manager.add_system_message(self.system_prompt_agent)

        # Filter user goal and log savings (moved after prompt_filter_stats init)
        
        filtered_goal = compress_prompt(user_goal)
        self.context_manager.add_user_message(f"Your goal: {filtered_goal}.")

        self.steps = []
        self.summary = ""
        self.goal_success = False
        self.critic_rating = 0
        self.critic_verdict = ""
        self.critic_rationale = ""
        self.summary_model_creator = "unknown"  # Track which model created the summary
        self.compact_state = self._init_compact_state()

        # Performance summary visibility (controlled via .env)
        self.show_performance_summary = (
            os.getenv("SHOW_PERFORMANCE_SUMMARY", "false").lower() == "true"
        )
        # Critic Sub-Agent toggle (controlled via .env)
        self.enable_critic_sub_agent = (
            os.getenv("ENABLE_CRITIC_SUB_AGENT", "true").lower() == "true"
        )
        # Critic finish gate toggle (controlled via .env)
        self.loop_critic_sub_agent = (
            os.getenv("LOOP_CRITIC_SUB_AGENT", "false").lower() == "true"
        )

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
                    logger=self.logger,
                    terminal=terminal
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

        # Initialize CriticSubAgent for correctness scoring on successful completion
        self.critic_sub_agent = None
        if CRITIC_SUB_AGENT_AVAILABLE and self.enable_critic_sub_agent:
            try:
                self.critic_sub_agent = CriticSubAgent(
                    terminal=terminal,
                    ai_handler=self.ai_handler,
                    logger=self.logger
                )
                self.logger.info("CriticSubAgent initialized successfully")
            except Exception as e:
                self.logger.warning(f"Failed to initialize CriticSubAgent: {e}")
        elif CRITIC_SUB_AGENT_AVAILABLE and not self.enable_critic_sub_agent:
            self.logger.info("CriticSubAgent disabled by ENABLE_CRITIC_SUB_AGENT")
        else:
            self.logger.warning("CriticSubAgent not available")

        # Initialize timing tracking for performance monitoring
        self.timings: Dict[str, Dict[str, float]] = {}
        self._timing_starts: Dict[str, float] = {}
        
        # Initialize token usage tracking
        self.token_usage: Dict[str, Dict[str, int]] = {}
        
        # Initialize prompt filter savings tracking
        self.prompt_filter_stats: Dict[str, int] = {
            "total_original_chars": 0,
            "total_compressed_chars": 0,
            "total_saved_chars": 0,
            "total_original_tokens_est": 0,
            "total_compressed_tokens_est": 0,
            "total_saved_tokens_est": 0,
            "filter_count": 0
        }
        
        # Initialize summarize_* statistics tracking (json, stacktrace, table, kv)
        self.summarize_stats: Dict[str, Any] = {
            "json": {"original": 0, "summarized": 0, "count": 0},
            "stacktrace": {"original": 0, "summarized": 0, "count": 0},
            "table": {"original": 0, "summarized": 0, "count": 0},
            "kv": {"original": 0, "summarized": 0, "count": 0},
            "total_original": 0,
            "total_summarized": 0,
            "total_saved": 0,
            "total_count": 0
        }
        
        # Log savings from user goal filtering (after stats init)
        self._log_prompt_filter_savings(user_goal, filtered_goal)

    def _start_timing(self, action_name: str) -> str:
        """
        Start timing for an action and return a unique timing ID.
        
        Args:
            action_name: Descriptive name of the action being timed
            
        Returns:
            Unique timing ID for this timing session
        """
        timing_id = f"{action_name}_{time.perf_counter():.6f}"
        self._timing_starts[timing_id] = time.perf_counter()
        return timing_id

    def _end_timing(self, timing_id: str, action_name: str, success: bool = True) -> float:
        """
        End timing for an action and log the duration.
        
        Args:
            timing_id: Unique timing ID returned by _start_timing
            action_name: Descriptive name of the action
            success: Whether the action completed successfully
            
        Returns:
            Duration in seconds
        """
        if timing_id not in self._timing_starts:
            self.logger.warning(f"Timing ID {timing_id} not found for action '{action_name}'")
            return 0.0
            
        start_time = self._timing_starts.pop(timing_id)
        duration = time.perf_counter() - start_time
        
        # Store timing data
        if action_name not in self.timings:
            self.timings[action_name] = {
                "total_time": 0.0,
                "call_count": 0,
                "min_time": float('inf'),
                "max_time": 0.0,
                "success_count": 0,
                "last_duration": 0.0
            }
        
        stats = self.timings[action_name]
        stats["total_time"] += duration
        stats["call_count"] += 1
        stats["min_time"] = min(stats["min_time"], duration)
        stats["max_time"] = max(stats["max_time"], duration)
        stats["last_duration"] = duration
        if success:
            stats["success_count"] += 1
        
        # Log timing information
        status = "SUCCESS" if success else "FAILED"
        self.logger.debug(f"Timing: {action_name} {status} - {duration:.3f}s (avg: {stats['total_time']/stats['call_count']:.3f}s)")
        
        return duration

    def _get_timing_summary(self) -> str:
        """
        Get a summary of all timing statistics.
        
        Returns:
            Formatted string with timing statistics
        """
        if not self.timings:
            return "No timing data available."
        
        summary_lines = ["\n=== TIMING SUMMARY ==="]
        for action_name, stats in self.timings.items():
            avg_time = stats["total_time"] / stats["call_count"]
            success_rate = (stats["success_count"] / stats["call_count"]) * 100
            summary_lines.append(
                f"{action_name}: {stats['call_count']} calls, "
                f"avg: {avg_time:.3f}s, min: {stats['min_time']:.3f}s, "
                f"max: {stats['max_time']:.3f}s, success: {success_rate:.1f}%"
            )
        
        return "\n".join(summary_lines)

    def _display_timing_summary(self):
        """
        Display timing summary to the user and log it.
        """
        timing_summary = self._get_timing_summary()
        self.terminal.print_console(timing_summary)
        self.logger.info("Timing summary: %s", timing_summary)

    def _get_token_summary(self) -> str:
        """
        Get a summary of all token usage statistics.
        
        Returns:
            Formatted string with token usage statistics
        """
        if not hasattr(self.ai_handler, 'token_usage') or not self.ai_handler.token_usage:
            return "No token usage data available."
        
        token_data = self.ai_handler.token_usage
        summary_lines = ["\n=== TOKEN USAGE SUMMARY ==="]
        
        # Overall statistics
        summary_lines.append(f"Total Input Tokens: {token_data['total_input_tokens']:,}")
        summary_lines.append(f"Total Output Tokens: {token_data['total_output_tokens']:,}")
        summary_lines.append(f"Total Tokens Used: {token_data['total_tokens']:,}")
        
        # Calculate average tokens per operation
        if token_data['operations']:
            avg_input = token_data['total_input_tokens'] / len(token_data['operations'])
            avg_output = token_data['total_output_tokens'] / len(token_data['operations'])
            avg_total = token_data['total_tokens'] / len(token_data['operations'])
            
            summary_lines.append(f"Average Input Tokens per Request: {avg_input:.1f}")
            summary_lines.append(f"Average Output Tokens per Request: {avg_output:.1f}")
            summary_lines.append(f"Average Total Tokens per Request: {avg_total:.1f}")
        
        # Operation breakdown
        if token_data['operations']:
            summary_lines.append("\nOperation Breakdown:")
            
            # Categorize operations for better analysis
            operation_categories = {}
            for op in token_data['operations']:
                category = op['operation']
                if category not in operation_categories:
                    operation_categories[category] = []
                operation_categories[category].append(op)
            
            # Show categorized operations with counts
            for category, ops in operation_categories.items():
                total_input = sum(op['input_tokens'] for op in ops)
                total_output = sum(op['output_tokens'] for op in ops)
                total_tokens = sum(op['total_tokens'] for op in ops)
                count = len(ops)
                
                if count == 1:
                    summary_lines.append(
                        f"  {category}: Input: {total_input:,}, Output: {total_output:,}, Total: {total_tokens:,}"
                    )
                else:
                    avg_input = total_input // count
                    avg_output = total_output // count
                    summary_lines.append(
                        f"  {category} ({count} calls): Input: {total_input:,} (avg: {avg_input:,}), "
                        f"Output: {total_output:,} (avg: {avg_output:,}), Total: {total_tokens:,}"
                    )
            
            # Add efficiency analysis
            summary_lines.append("\nEfficiency Analysis:")
            
            # Find most and least efficient operations
            if len(token_data['operations']) > 1:
                most_efficient = min(token_data['operations'], key=lambda x: x['total_tokens'])
                least_efficient = max(token_data['operations'], key=lambda x: x['total_tokens'])
                
                summary_lines.append(
                    f"  Most Efficient: {most_efficient['operation']} - {most_efficient['total_tokens']:,} tokens"
                )
                summary_lines.append(
                    f"  Least Efficient: {least_efficient['operation']} - {least_efficient['total_tokens']:,} tokens"
                )
                efficiency_ratio = least_efficient['total_tokens'] / most_efficient['total_tokens'] if most_efficient['total_tokens'] > 0 else 0
                summary_lines.append(
                    f"  Efficiency Ratio: {efficiency_ratio:.1f}x difference"
                )
        
        # Cost estimation (using rough estimates)
        # Assuming $0.0005 per 1000 input tokens and $0.0015 per 1000 output tokens (GPT-4o rates)
        input_cost = (token_data['total_input_tokens'] / 1000) * 0.0005
        output_cost = (token_data['total_output_tokens'] / 1000) * 0.0015
        total_cost = input_cost + output_cost
        
        summary_lines.append(f"\nEstimated Cost: ${total_cost:.4f}")
        summary_lines.append(f"  Input tokens cost: ${input_cost:.4f}")
        summary_lines.append(f"  Output tokens cost: ${output_cost:.4f}")
        
        return "\n".join(summary_lines)

    def _display_token_summary(self):
        """
        Display token usage summary to the user and log it.
        """
        token_summary = self._get_token_summary()
        self.terminal.print_console(token_summary)
        self.logger.info("Token usage summary: %s", token_summary)

    def _get_cost_optimization_recommendations(self) -> str:
        """
        Generate cost optimization recommendations based on token usage patterns.
        
        Returns:
            Formatted string with optimization recommendations
        """
        if not hasattr(self.ai_handler, 'token_usage') or not self.ai_handler.token_usage:
            return "No token usage data available for optimization recommendations."
        
        token_data = self.ai_handler.token_usage
        recommendations = ["\n=== COST OPTIMIZATION RECOMMENDATIONS ==="]
        
        # Analyze token efficiency
        if token_data['operations']:
            avg_input = token_data['total_input_tokens'] / len(token_data['operations'])
            avg_output = token_data['total_output_tokens'] / len(token_data['operations'])
            
            # Check for high input token usage
            if avg_input > 5000:
                recommendations.append(
                    "HIGH INPUT TOKEN USAGE: Average input tokens per request is high."
                    "\n   - Consider shortening system prompts"
                    "\n   - Use more concise user queries"
                    "\n   - Implement context window management"
                    "\n   - Remove unnecessary context from requests"
                )
            
            # Check for high output token usage
            if avg_output > 2000:
                recommendations.append(
                    "HIGH OUTPUT TOKEN USAGE: Average output tokens per request is high."
                    "\n   - Request more concise responses"
                    "\n   - Use bullet points instead of paragraphs"
                    "\n   - Set max_tokens limits when possible"
                    "\n   - Ask for summaries instead of detailed explanations"
                )
            
            # Check for inefficient operations
            if len(token_data['operations']) > 10:
                # Look for patterns that might be inefficient
                operation_types = [op['operation'] for op in token_data['operations']]
                ai_requests = [op for op in operation_types if 'ai_request' in op]
                
                if len(ai_requests) > len(set(ai_requests)):
                    recommendations.append(
                        "POTENTIAL REDUNDANCY: Multiple similar AI requests detected."
                        "\n   - Consider batching similar requests"
                        "\n   - Cache responses for repeated queries"
                        "\n   - Use more specific prompts to reduce iterations"
                    )
        
        # General recommendations
        recommendations.extend([
            "\nGENERAL OPTIMIZATION TIPS:",
            "   - Use cheaper models for simple tasks (e.g., GPT-3.5 vs GPT-4)",
            "   - Implement early stopping for long-running tasks",
            "   - Use streaming responses when possible",
            "   - Cache frequently used responses",
            "   - Monitor token usage regularly",
            "   - Set budget alerts for high-usage scenarios"
        ])
        
        # Calculate potential savings
        current_cost = (token_data['total_input_tokens'] / 1000) * 0.0005 + (token_data['total_output_tokens'] / 1000) * 0.0015
        
        # Estimate optimized cost (assuming 30% reduction with optimizations)
        optimized_cost = current_cost * 0.7
        potential_savings = current_cost - optimized_cost
        
        recommendations.append(f"\nPOTENTIAL SAVINGS: ${potential_savings:.4f} per session (30% reduction)")
        recommendations.append(f"   Current cost: ${current_cost:.4f}")
        recommendations.append(f"   Optimized cost: ${optimized_cost:.4f}")
        
        return "\n".join(recommendations)

    def _display_cost_optimization_recommendations(self):
        """
        Display cost optimization recommendations to the user and log them.
        """
        recommendations = self._get_cost_optimization_recommendations()
        self.terminal.print_console(recommendations)
        self.logger.info("Cost optimization recommendations: %s", recommendations)

    def _log_prompt_filter_savings(self, original_text: str, compressed_text: str) -> None:
        """
        Log token savings from prompt filtering and update cumulative stats.
        
        Args:
            original_text: Original text before compression
            compressed_text: Text after compression
        """
        savings = estimate_token_savings(original_text, compressed_text)
        
        # Update cumulative stats
        self.prompt_filter_stats["total_original_chars"] += savings["original_chars"]
        self.prompt_filter_stats["total_compressed_chars"] += savings["compressed_chars"]
        self.prompt_filter_stats["total_saved_chars"] += savings["saved_chars"]
        self.prompt_filter_stats["total_original_tokens_est"] += savings["original_tokens_est"]
        self.prompt_filter_stats["total_compressed_tokens_est"] += savings["compressed_tokens_est"]
        self.prompt_filter_stats["total_saved_tokens_est"] += savings["saved_tokens_est"]
        self.prompt_filter_stats["filter_count"] += 1
        
        # Log per-call stats at DEBUG level
        self.logger.debug(
            f"Prompt filter: {savings['original_chars']}→{savings['compressed_chars']} chars "
            f"({savings['saved_chars']} saved, {savings['compression_ratio']:.1%} ratio), "
            f"~{savings['saved_tokens_est']} tokens saved"
        )

    def _get_prompt_filter_summary(self) -> str:
        """
        Get a comprehensive summary of prompt filter savings statistics.
        
        Returns:
            Formatted string with detailed filter savings statistics and insights
        """
        stats = self.prompt_filter_stats
        if stats["filter_count"] == 0:
            return "No prompt filters applied."
        
        # Calculate basic metrics
        compression_ratio = (
            stats["total_compressed_chars"] / stats["total_original_chars"]
            if stats["total_original_chars"] > 0 else 1.0
        )
        savings_pct = (1 - compression_ratio) * 100
        avg_savings_per_filter = (
            stats["total_saved_chars"] / stats["filter_count"]
            if stats["filter_count"] > 0 else 0
        )
        avg_tokens_saved_per_filter = (
            stats["total_saved_tokens_est"] / stats["filter_count"]
            if stats["filter_count"] > 0 else 0
        )
        
        # Calculate cost savings (using rough estimates)
        # Assuming $0.0005 per 1000 input tokens and $0.0015 per 1000 output tokens (GPT-4o rates)
        input_cost_savings = (stats["total_saved_tokens_est"] / 1000) * 0.0010  # Conservative estimate
        output_cost_savings = (stats["total_saved_tokens_est"] / 1000) * 0.0020  # Conservative estimate
        total_cost_savings = input_cost_savings + output_cost_savings
        
        # Calculate efficiency metrics
        efficiency_score = min(100, savings_pct * 2)  # Scale efficiency score
        
        summary_lines = ["\n=== PROMPT FILTER COMPRESSION ANALYSIS ==="]
        
        # Basic statistics
        summary_lines.append("\nCOMPRESSION STATISTICS:")
        summary_lines.append(f"   Total filters applied: {stats['filter_count']:,}")
        summary_lines.append(f"   Original characters: {stats['total_original_chars']:,}")
        summary_lines.append(f"   Compressed characters: {stats['total_compressed_chars']:,}")
        summary_lines.append(f"   Characters saved: {stats['total_saved_chars']:,}")
        
        # Token analysis
        summary_lines.append("\nTOKEN ANALYSIS:")
        summary_lines.append(f"   Original tokens (est): {stats['total_original_tokens_est']:,}")
        summary_lines.append(f"   Compressed tokens (est): {stats['total_compressed_tokens_est']:,}")
        summary_lines.append(f"   Tokens saved (est): {stats['total_saved_tokens_est']:,}")
        summary_lines.append(f"   Average tokens saved per filter: {avg_tokens_saved_per_filter:.1f}")
        
        # Compression effectiveness
        summary_lines.append("\nCOMPRESSION EFFECTIVENESS:")
        summary_lines.append(f"   Compression ratio: {compression_ratio:.1%}")
        summary_lines.append(f"   Space savings: {savings_pct:.1f}%")
        summary_lines.append(f"   Average chars saved per filter: {avg_savings_per_filter:.1f}")
        summary_lines.append(f"   Efficiency score: {efficiency_score:.1f}/100")
        
        # Cost analysis
        summary_lines.append("\nCOST IMPACT:")
        summary_lines.append(f"   Estimated cost savings: ${total_cost_savings:.4f}")
        summary_lines.append(f"   Input cost savings: ${input_cost_savings:.4f}")
        summary_lines.append(f"   Output cost savings: ${output_cost_savings:.4f}")
        
        # Performance insights
        summary_lines.append("\nPERFORMANCE INSIGHTS:")
        if savings_pct > 50:
            summary_lines.append("Excellent compression rate - significant savings achieved!")
        elif savings_pct > 30:
            summary_lines.append("Good compression rate - effective token reduction.")
        elif savings_pct > 10:
            summary_lines.append("Moderate compression - room for improvement.")
        else:
            summary_lines.append("Low compression rate - consider reviewing filter settings.")
        
        if avg_tokens_saved_per_filter > 100:
            summary_lines.append("High impact per filter - excellent optimization!")
        elif avg_tokens_saved_per_filter > 50:
            summary_lines.append("Good impact per filter - effective filtering.")
        elif avg_tokens_saved_per_filter > 10:
            summary_lines.append("Moderate impact per filter - acceptable performance.")
        else:
            summary_lines.append("Low impact per filter - may need optimization.")
        
        # Additional metrics
        summary_lines.append(f"\n   Filter efficiency: {stats['filter_count']} filters processed")
        summary_lines.append(f"   Total data processed: {stats['total_original_chars']:,} characters")
        summary_lines.append(f"   Data reduction: {stats['total_saved_chars']:,} characters removed")
        
        # Show detailed breakdown if enabled
        if os.getenv("SHOW_PROMPT_FILTER_DETAILS", "false").lower() == "true":
            summary_lines.append("\nDETAILED BREAKDOWN:")
            summary_lines.append(f"   Original → Compressed → Saved")
            summary_lines.append(f"   {stats['total_original_chars']:,} → {stats['total_compressed_chars']:,} → {stats['total_saved_chars']:,}")
            summary_lines.append(f"   {stats['total_original_tokens_est']:,} → {stats['total_compressed_tokens_est']:,} → {stats['total_saved_tokens_est']:,}")
        
        return "\n".join(summary_lines)

    def _display_prompt_filter_summary(self):
        """
        Display prompt filter savings summary to the user and log it.
        """
        filter_summary = self._get_prompt_filter_summary()
        self.terminal.print_console(filter_summary)
        self.logger.info("Prompt filter summary: %s", filter_summary)

    def _get_summarize_stats_summary(self) -> str:
        """
        Get a summary of summarize_* statistics (json, stacktrace, table, kv).
        
        Returns:
            Formatted string with summarize statistics
        """
        stats = self.summarize_stats
        if stats["total_count"] == 0:
            return "\n=== BASH SUMMARIZE OPERATIONS SUMMARY ===\n   No summarize operations performed."
        
        # Calculate compression ratio
        compression_ratio = (
            stats["total_summarized"] / stats["total_original"]
            if stats["total_original"] > 0 else 1.0
        )
        savings_pct = (1 - compression_ratio) * 100
        
        summary_lines = ["\n=== BASH SUMMARIZE OPERATIONS SUMMARY ==="]
        
        # Overall statistics
        summary_lines.append("\nOVERALL STATISTICS:")
        summary_lines.append(f"   Total operations: {stats['total_count']:,}")
        summary_lines.append(f"   Original characters: {stats['total_original']:,}")
        summary_lines.append(f"   Summarized characters: {stats['total_summarized']:,}")
        summary_lines.append(f"   Characters saved: {stats['total_saved']:,}")
        summary_lines.append(f"   Compression ratio: {compression_ratio:.1%}")
        summary_lines.append(f"   Space savings: {savings_pct:.1f}%")
        
        # Per-type breakdown
        summary_lines.append("\nBREAKDOWN BY TYPE:")
        
        for type_name in ["json", "stacktrace", "table", "kv"]:
            type_stats = stats[type_name]
            if type_stats["count"] > 0:
                type_ratio = type_stats["summarized"] / type_stats["original"] if type_stats["original"] > 0 else 1.0
                type_savings = (1 - type_ratio) * 100
                type_saved = type_stats["original"] - type_stats["summarized"]
                
                summary_lines.append(f"\n   {type_name.upper()}:")
                summary_lines.append(f"      Count: {type_stats['count']:,}")
                summary_lines.append(f"      Original: {type_stats['original']:,} chars")
                summary_lines.append(f"      Summarized: {type_stats['summarized']:,} chars")
                summary_lines.append(f"      Saved: {type_saved:,} chars ({type_savings:.1f}%)")
        
        # Performance insights
        summary_lines.append("\nPERFORMANCE INSIGHTS:")
        if savings_pct > 50:
            summary_lines.append("Excellent summarization rate - significant reduction achieved!")
        elif savings_pct > 30:
            summary_lines.append("Good summarization rate - effective output reduction.")
        elif savings_pct > 10:
            summary_lines.append("Moderate summarization - room for improvement.")
        else:
            summary_lines.append("Low summarization rate - output may be already concise.")
        
        return "\n".join(summary_lines)

    def _display_summarize_stats_summary(self):
        """
        Display summarize stats summary to the user and log it.
        """
        summarize_summary = self._get_summarize_stats_summary()
        self.terminal.print_console(summarize_summary)
        self.logger.info("Summarize stats summary: %s", summarize_summary)

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

    def _validate_analysis_data_arguments(
        self, action_item: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Validate and normalize arguments for the analysis_data tool.

        Args:
            action_item: Raw tool action dictionary received from the model.

        Returns:
            Tuple[bool, Optional[Dict[str, Any]], str]:
                - validation success
                - normalized args on success, otherwise None
                - error description on failure
        """
        allowed_types = {
            "calculate",
            "extract",
            "summarize",
            "compare",
            "trend",
            "classify",
            "validate",
            "transform",
        }
        allowed_output_formats = {"json", "text", "number"}
        allowed_precision = {"low", "medium", "high"}

        arguments = action_item.get("arguments")
        if not isinstance(arguments, dict):
            return False, None, "Missing or invalid 'arguments' object"

        analysis_type = arguments.get("type")
        if not isinstance(analysis_type, str):
            return False, None, "Missing or invalid 'arguments.type' (must be string)"
        analysis_type = analysis_type.strip().lower()
        if analysis_type not in allowed_types:
            return (
                False,
                None,
                "Invalid 'arguments.type'. Allowed: calculate|extract|summarize|compare|"
                "trend|classify|validate|transform",
            )

        analysis_input = arguments.get("input")
        if analysis_input is None:
            return False, None, "Missing required 'arguments.input'"
        if isinstance(analysis_input, (dict, list)):
            input_text = json.dumps(analysis_input, ensure_ascii=False)
        else:
            input_text = str(analysis_input)
        if not input_text.strip():
            return False, None, "Empty 'arguments.input'"

        instructions = arguments.get("instructions", "")
        if isinstance(instructions, (dict, list)):
            instructions_text = json.dumps(instructions, ensure_ascii=False)
        else:
            instructions_text = str(instructions) if instructions is not None else ""

        context = arguments.get("context", "")
        if isinstance(context, (dict, list)):
            context_text = json.dumps(context, ensure_ascii=False)
        else:
            context_text = str(context) if context is not None else ""

        output_format = arguments.get("output_format", "text")
        if not isinstance(output_format, str):
            return False, None, "Invalid 'arguments.output_format' (must be string)"
        output_format = output_format.strip().lower()
        if output_format not in allowed_output_formats:
            return False, None, "Invalid 'arguments.output_format'. Allowed: json|text|number"

        constraints = arguments.get("constraints", {})
        if constraints is None:
            constraints = {}
        if not isinstance(constraints, dict):
            return False, None, "Invalid 'arguments.constraints' (must be object)"

        raw_max_tokens = constraints.get("max_tokens", 300)
        try:
            max_tokens = int(raw_max_tokens)
        except Exception:
            return False, None, "Invalid 'arguments.constraints.max_tokens' (must be integer)"
        if max_tokens <= 0:
            return False, None, "Invalid 'arguments.constraints.max_tokens' (must be > 0)"

        precision = constraints.get("precision", "medium")
        if not isinstance(precision, str):
            return False, None, "Invalid 'arguments.constraints.precision' (must be string)"
        precision = precision.strip().lower()
        if precision not in allowed_precision:
            return False, None, "Invalid 'arguments.constraints.precision'. Allowed: low|medium|high"

        normalized_args = {
            "type": analysis_type,
            "input": input_text,
            "instructions": instructions_text,
            "context": context_text,
            "output_format": output_format,
            "constraints": {
                "max_tokens": max_tokens,
                "precision": precision,
            },
        }
        return True, normalized_args, ""

    def _build_analysis_data_prompts(self, arguments: Dict[str, Any]) -> Tuple[str, str]:
        """
        Build system and user prompts for analysis_data tool execution.

        Args:
            arguments: Normalized arguments from _validate_analysis_data_arguments.

        Returns:
            Tuple of (system_prompt, user_prompt).
        """
        analysis_type = arguments["type"]
        analysis_input = arguments["input"]
        instructions = arguments.get("instructions", "")
        context = arguments.get("context", "")
        output_format = arguments.get("output_format", "text")
        constraints = arguments.get("constraints", {})
        precision = constraints.get("precision", "medium")
        max_tokens = constraints.get("max_tokens", 300)

        output_guidance = {
            "json": "Return ONLY valid JSON (object or array), no extra text.",
            "number": "Return ONLY a single numeric value, no units or explanation.",
            "text": "Return concise plain text summary with actionable insights.",
        }.get(output_format, "Return concise plain text.")

        # Keep system prompt empty for tool sub-calls to avoid coupling
        # with the main agent system prompt semantics.
        system_prompt = ""
        user_prompt = (
            "ROLE: precise data analysis assistant.\n"
            "Follow requested analysis type and constraints.\n"
            "Avoid unrelated content.\n\n"
            f"ANALYSIS_TYPE: {analysis_type}\n"
            f"OUTPUT_FORMAT: {output_format}\n"
            f"PRECISION: {precision}\n"
            f"MAX_TOKENS_BUDGET: {max_tokens}\n"
            f"INSTRUCTIONS: {instructions or 'None'}\n"
            f"CONTEXT: {context or 'None'}\n"
            f"INPUT:\n{analysis_input}\n\n"
            f"OUTPUT RULE: {output_guidance}"
        )
        return system_prompt, user_prompt

    def _extract_first_number(self, text: str) -> Optional[str]:
        """
        Extract the first numeric token from text output.

        Args:
            text: Raw model output

        Returns:
            Numeric string if found, otherwise None.
        """
        if text is None:
            return None
        raw = str(text).strip()
        if not raw:
            return None

        # Fast path: output is already a pure number.
        try:
            float(raw)
            return raw
        except Exception:
            pass

        match = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", raw)
        if not match:
            return None
        return match.group(0)

    def _local_calculate_analysis_data(self, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Best-effort local calculator for analysis_data(type=calculate) when model output is empty.
        """
        raw_input = str(arguments.get("input", "") or "")
        if not raw_input.strip():
            return None

        def _to_float(value: str) -> Optional[float]:
            try:
                return float(value.replace(",", "").strip())
            except Exception:
                return None

        def _parse_number(pattern: str) -> Optional[float]:
            m = re.search(pattern, raw_input, re.IGNORECASE)
            if not m:
                return None
            return _to_float(m.group(1))

        def _parse_abbrev_number(pattern: str) -> Optional[float]:
            m = re.search(pattern, raw_input, re.IGNORECASE)
            if not m:
                return None
            num = _to_float(m.group(1))
            if num is None:
                return None
            suffix = (m.group(2) or "").upper()
            if suffix == "K":
                return num * 1_000
            if suffix == "M":
                return num * 1_000_000
            if suffix == "B":
                return num * 1_000_000_000
            return num

        price = _parse_number(r"\bPrice:\s*([-+]?\d[\d,]*\.?\d*)")
        high_52w = _parse_number(r"\b52W\s*High:\s*([-+]?\d[\d,]*\.?\d*)")
        low_from_range = None
        range_match = re.search(
            r"\b52W\s*Range:\s*([-+]?\d[\d,]*\.?\d*)\s*-\s*([-+]?\d[\d,]*\.?\d*)",
            raw_input,
            re.IGNORECASE,
        )
        if range_match:
            low_from_range = _to_float(range_match.group(1))
            if high_52w is None:
                high_52w = _to_float(range_match.group(2))
        low_52w_explicit = _parse_number(r"\b52W\s*Low:\s*([-+]?\d[\d,]*\.?\d*)")
        low_52w = low_from_range if low_from_range is not None else low_52w_explicit

        sma20_pct = _parse_number(r"\bSMA20:\s*([-+]?\d+(?:\.\d+)?)%")
        sma50_pct = _parse_number(r"\bSMA50:\s*([-+]?\d+(?:\.\d+)?)%")
        sma200_pct = _parse_number(r"\bSMA200:\s*([-+]?\d+(?:\.\d+)?)%")
        atr = _parse_number(r"\bATR\s*\(14\):\s*([-+]?\d[\d,]*\.?\d*)")
        volume = _parse_abbrev_number(r"\bVolume:\s*([-+]?\d[\d,]*\.?\d*)\s*([KMB]?)")
        avg_volume = _parse_abbrev_number(r"\bAvg\s*Volume:\s*([-+]?\d[\d,]*\.?\d*)\s*([KMB]?)")
        rel_volume = _parse_number(r"\bRel\s*Volume:\s*([-+]?\d+(?:\.\d+)?)")

        if price is None:
            return None

        result: Dict[str, Any] = {
            "source": "local_calculate_fallback",
            "price": round(price, 4),
            "metrics": {},
        }
        metrics = result["metrics"]

        if sma20_pct is not None:
            metrics["distance_from_sma20_pct"] = round(sma20_pct, 4)
        if sma50_pct is not None:
            metrics["distance_from_sma50_pct"] = round(sma50_pct, 4)
        if sma200_pct is not None:
            metrics["distance_from_sma200_pct"] = round(sma200_pct, 4)

        if high_52w is not None:
            metrics["distance_from_52w_high_abs"] = round(price - high_52w, 4)
        if low_52w is not None:
            metrics["distance_from_52w_low_abs"] = round(price - low_52w, 4)
        if atr is not None and price != 0:
            metrics["atr_as_pct_of_price"] = round((atr / price) * 100.0, 4)
        if volume is not None and avg_volume and avg_volume > 0:
            metrics["volume_vs_avg_volume_ratio"] = round(volume / avg_volume, 4)
        elif rel_volume is not None:
            metrics["volume_vs_avg_volume_ratio"] = round(rel_volume, 4)

        if low_52w is not None and high_52w is not None and high_52w != low_52w:
            pos = ((price - low_52w) / (high_52w - low_52w)) * 100.0
            metrics["position_in_52w_range_pct"] = round(max(0.0, min(100.0, pos)), 4)

        return result if metrics else None

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
                
                # Add plan to AI context - THIS IS CRITICAL
                plan_context = self.plan_manager.get_context_for_ai()
                self.context_manager.add_system_message(
                    f"You have the following action plan available. "
                    f"Execute steps sequentially and update the status of each step after completion.\n\n{plan_context}"
                )
                self.logger.info(f"[PLAN ADDED TO CONTEXT] Plan with {len(steps)} steps added to AI context")
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
        Update plan progress after action execution using ActionPlanManager.
        
        Args:
            action_description: Description of executed action
            success: Whether action completed successfully
        """
        if not self.plan_manager.steps:
            return
        
        # Find first pending or in-progress step
        current_step = self.plan_manager.get_current_step()
        if current_step:
            # Use the proper ActionPlanManager method
            status = StepStatus.COMPLETED if success else StepStatus.FAILED
            self.plan_manager.mark_step_status(current_step.number, status, action_description)
        else:
            # If no step in progress, mark next pending one
            next_step = self.plan_manager.get_next_pending_step()
            if next_step:
                # Use the proper ActionPlanManager method
                status = StepStatus.COMPLETED if success else StepStatus.FAILED
                self.plan_manager.mark_step_status(next_step.number, status, action_description)
        
        # Display compact progress
        self.plan_manager.display_compact()

    def _plan_exists(self) -> bool:
        """
        Check if an action plan exists and has steps.
        
        Returns:
            True if plan exists and has steps, False otherwise
        """
        return bool(self.plan_manager.steps)

    def _get_plan_status_for_ai(self) -> str:
        """
        Get a concise plan status summary for AI context.
        
        Returns:
            String with current plan status
        """
        if not self._plan_exists():
            return ""
        
        progress = self.plan_manager.get_progress()
        lines = ["PLAN STATUS:"]
        lines.append("Progress: {}/{} ({}%)".format(progress['completed'], progress['total'], progress['percentage']))
        
        # Show next pending step
        next_step = self.plan_manager.get_next_pending_step()
        if next_step:
            lines.append("Next step to complete: Step {}: {}".format(next_step.number, next_step.description))
        
        # Show warning if plan not complete
        if progress['pending'] > 0:
            lines.append("[WARN] You still have {} pending step(s) to complete before finishing.".format(progress['pending']))
        
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

    # ------------------------------------------------------------------
    # Compact pipeline helpers
    # ------------------------------------------------------------------

    def _init_compact_state(self) -> Dict[str, Any]:
        return {
            "task_id": uuid.uuid4().hex,
            "goal": self.user_goal,
            "mode": "compact",
            "budget": {
                "max_calls": 3,
                "calls_used": 0,
                "max_state_chars": 4000,
                "max_actions": 5,
            },
            "facts": [],
            "actions": [],
            "results": [],
            "errors": [],
            "status": "new",
            "final": {"summary": "", "goal_success": False},
        }

    def _cap_state_size(self, state: Dict[str, Any]) -> Dict[str, Any]:
        max_chars = int(state.get("budget", {}).get("max_state_chars", 2000))
        if max_chars <= 0:
            return state

        def state_len() -> int:
            try:
                return len(json.dumps(state, ensure_ascii=False))
            except Exception:
                return len(str(state))

        while state_len() > max_chars:
            if state.get("results"):
                state["results"].pop(0)
                continue
            if state.get("facts"):
                state["facts"].pop(0)
                continue
            if state.get("errors"):
                state["errors"].pop(0)
                continue
            break
        return state

    def _compress_output(self, text: Any, max_chars: Optional[int] = None) -> Tuple[str, str]:
        if max_chars is None:
            max_chars = self.compact_max_output_chars
        raw = "" if text is None else str(text)
        truncated = raw if len(raw) <= max_chars else raw[:max_chars]
        digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()
        return truncated, f"sha256:{digest}"

    def _compact_state_json(self, state: Dict[str, Any]) -> str:
        self._cap_state_size(state)
        return json.dumps(state, ensure_ascii=False, sort_keys=True)

    def _compact_apply_state_update(self, state: Dict[str, Any], update: Any) -> None:
        if not isinstance(update, dict):
            return
        for k, v in update.items():
            if k in ("actions", "results", "errors", "facts"):
                if isinstance(v, list):
                    state[k] = v
                else:
                    continue
            elif k in ("budget", "final"):
                if isinstance(v, dict):
                    state[k] = v
                else:
                    continue
            elif k == "status":
                if isinstance(v, str):
                    state[k] = v
            elif k == "goal":
                if isinstance(v, str):
                    state[k] = v
            else:
                state[k] = v

    def _compact_build_prompt_single(self, state: Dict[str, Any]) -> str:
        return (
            f"TASK: {self.user_goal}\n"
            f"STATE: {self._compact_state_json(state)}\n\n"
            "Return one of:\n"
            '1) {"kind":"final","summary":"...","goal_success":true|false,"state_update":{...}}\n'
            '2) {"kind":"actions","actions":[...],"state_update":{...}}\n\n'
            "Action schema:\n"
            '{"tool":"bash|read_file|write_file|edit_file|list_directory|search_in_file|copy_file|delete_file","command_or_path":"...","timeout":30,"explain":"..."}'
        )

    def _compact_build_prompt_repair(
        self,
        state: Dict[str, Any],
        errors: List[str],
        results: List[Dict[str, Any]],
    ) -> str:
        errors_json = json.dumps(errors, ensure_ascii=False)
        results_json = json.dumps(results, ensure_ascii=False)
        return (
            f"TASK: {self.user_goal}\n"
            f"STATE: {self._compact_state_json(state)}\n"
            f"ERRORS: {errors_json}\n"
            f"LAST_RESULTS: {results_json}\n\n"
            "Return one of:\n"
            '1) {"kind":"final","summary":"...","goal_success":false,"state_update":{...}}\n'
            '2) {"kind":"actions","actions":[...],"state_update":{...}}'
        )

    def _compact_build_prompt_final(self, state: Dict[str, Any]) -> str:
        return (
            f"TASK: {self.user_goal}\n"
            f"STATE: {self._compact_state_json(state)}\n\n"
            "Return:\n"
            '{"summary":"...","goal_success":true|false,"key_results":["..."],"followups":["..."],"state_update":{...}}'
        )

    def _compact_llm_json_call(
        self,
        system_prompt: str,
        user_prompt: str,
        operation: str,
        max_tokens: int,
        state: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        budget = state.get("budget", {})
        max_calls = int(budget.get("max_calls", 3))
        calls_used = int(budget.get("calls_used", 0))
        if calls_used >= max_calls:
            return None

        budget["calls_used"] = calls_used + 1
        state["budget"] = budget

        response = self.ai_handler.send_request(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_format="json",
            operation=operation,
            max_tokens=max_tokens,
        )
        if response is None:
            return None
        try:
            data = json.loads(response)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        return data

    def _compact_record_action(self, state: Dict[str, Any], tool: str, input_text: str, timeout: int) -> str:
        if not isinstance(state.get("actions"), list):
            state["actions"] = []
        action_id = f"a{len(state.get('actions', [])) + 1}"
        state.setdefault("actions", []).append({
            "id": action_id,
            "tool": tool,
            "input": input_text,
            "timeout": timeout,
        })
        return action_id

    def _compact_record_result(self, state: Dict[str, Any], action_id: str, code: int, out: str, out_hash: str, tool: str) -> None:
        if not isinstance(state.get("results"), list):
            state["results"] = []
        state.setdefault("results", []).append({
            "id": action_id,
            "tool": tool,
            "code": code,
            "out": out,
            "out_hash": out_hash,
        })

    def _compact_execute_single_action(self, action: Dict[str, Any], state: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        terminal = self.terminal
        tool = action.get("tool")
        allowed_tools = {
            "bash",
            "read_file",
            "write_file",
            "edit_file",
            "list_directory",
            "copy_file",
            "delete_file",
        }
        if tool not in allowed_tools:
            return False, f"Invalid tool: {tool}"

        timeout = action.get("timeout") or 30
        try:
            timeout = int(timeout)
        except Exception:
            timeout = 30

        if tool == "bash":
            command = action.get("command") or action.get("command_or_path") or action.get("input")
            explain = action.get("explain", "")
            if not command:
                return False, "Missing command for bash action"

            if terminal.block_dangerous_commands:
                is_valid, reason = self.security_validator.validate_command(command)
                if not is_valid:
                    return False, f"Command validation failed: {reason}"

            if not terminal.auto_accept:
                confirm_prompt_text = f"\nVaultAI> Execute command: '{command}'? [y/N]: "
                confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                if confirm != 'y':
                    return False, "User refused command execution"

            terminal.print_console(f"\nVaultAI> Executing: {command}")
            if terminal.ssh_connection:
                remote = f"{terminal.user}@{terminal.host}" if terminal.user and terminal.host else terminal.host
                password = getattr(terminal, "ssh_password", None)
                out, code = terminal.execute_remote_pexpect(command, remote, password=password, timeout=timeout)
            else:
                out, code = terminal.execute_local(command, timeout=timeout)

            out_str = out if isinstance(out, str) else str(out)
            terminal.print_console(f"\n{out_str}")

            out_compact, out_hash = self._compress_output(out_str)
            action_id = self._compact_record_action(state, tool, command, timeout)
            self._compact_record_result(state, action_id, int(code), out_compact, out_hash, tool)
            return code == 0, None if code == 0 else f"Command failed with exit code {code}"

        if tool == "read_file":
            path = action.get("path") or action.get("command_or_path")
            start_line = action.get("start_line")
            end_line = action.get("end_line")
            if not path:
                return False, "Missing path for read_file"

            if not terminal.auto_accept:
                confirm_prompt_text = f"\nVaultAI> Read file '{path}'? [y/N]: "
                confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                if confirm != 'y':
                    return False, "User refused file read"

            result = self.file_operator.read_file(path, start_line or None, end_line or None, "")
            if result.get("success"):
                content = result.get("content", "")
                display = content if len(content) <= self.compact_max_display_chars else (
                    content[: self.compact_max_display_chars] + "\n... (truncated)"
                )
                terminal.print_console(f"\n[OK] File '{path}' read successfully.")
                terminal.print_console(f"\n{display}")
                out_compact, out_hash = self._compress_output(content)
                action_id = self._compact_record_action(state, tool, path, timeout)
                self._compact_record_result(state, action_id, 0, out_compact, out_hash, tool)
                return True, None
            error = result.get("error", "Unknown error")
            action_id = self._compact_record_action(state, tool, path, timeout)
            out_compact, out_hash = self._compress_output(error)
            self._compact_record_result(state, action_id, 1, out_compact, out_hash, tool)
            return False, error

        if tool == "write_file":
            path = action.get("path") or action.get("command_or_path")
            content = action.get("content")
            if not path or content is None:
                return False, "Missing path or content for write_file"

            if not terminal.auto_accept:
                confirm_prompt_text = f"\nVaultAI> Write file '{path}'? [y/N]: "
                confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                if confirm != 'y':
                    return False, "User refused file write"

            success = self.file_operator.write_file(path, content, "")
            action_id = self._compact_record_action(state, tool, path, timeout)
            out_compact, out_hash = self._compress_output("ok" if success else "write failed")
            self._compact_record_result(state, action_id, 0 if success else 1, out_compact, out_hash, tool)
            return success, None if success else "Failed to write file"

        if tool == "edit_file":
            path = action.get("path") or action.get("command_or_path")
            edit_action = action.get("action")
            search = action.get("search")
            replace = action.get("replace")
            line = action.get("line")
            if not path or not edit_action:
                return False, "Missing path or action for edit_file"

            if not terminal.auto_accept:
                confirm_prompt_text = f"\nVaultAI> Edit file '{path}'? [y/N]: "
                confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                if confirm != 'y':
                    return False, "User refused file edit"

            success = self.file_operator.edit_file(path, edit_action, search, replace, line, "")
            action_id = self._compact_record_action(state, tool, path, timeout)
            out_compact, out_hash = self._compress_output("ok" if success else "edit failed")
            self._compact_record_result(state, action_id, 0 if success else 1, out_compact, out_hash, tool)
            return success, None if success else "Failed to edit file"

        if tool == "list_directory":
            path = action.get("path") or action.get("command_or_path")
            recursive = action.get("recursive", False)
            pattern = action.get("pattern")
            if not path:
                return False, "Missing path for list_directory"

            if not terminal.auto_accept:
                confirm_prompt_text = f"\nVaultAI> List directory '{path}'? [y/N]: "
                confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                if confirm != 'y':
                    return False, "User refused directory listing"

            result = self.file_operator.list_directory(path, recursive, pattern or None, "")
            if result.get("success"):
                entries = result.get("entries", [])
                total_count = result.get("total_count", len(entries))
                terminal.print_console(f"\n[OK] Directory '{path}' listed ({total_count} entries).")
                out_compact, out_hash = self._compress_output(json.dumps(entries[:50], ensure_ascii=False))
                action_id = self._compact_record_action(state, tool, path, timeout)
                self._compact_record_result(state, action_id, 0, out_compact, out_hash, tool)
                return True, None
            error = result.get("error", "Unknown error")
            action_id = self._compact_record_action(state, tool, path, timeout)
            out_compact, out_hash = self._compress_output(error)
            self._compact_record_result(state, action_id, 1, out_compact, out_hash, tool)
            return False, error

        if tool == "copy_file":
            source = action.get("source")
            destination = action.get("destination")
            overwrite = action.get("overwrite", False)
            if not source or not destination:
                spec = action.get("command_or_path") or action.get("input")
                if spec and "->" in spec:
                    parts = [p.strip() for p in spec.split("->", 1)]
                    if len(parts) == 2:
                        source, destination = parts[0], parts[1]
            if not source or not destination:
                return False, "Missing source or destination for copy_file"

            if not terminal.auto_accept:
                confirm_prompt_text = f"\nVaultAI> Copy '{source}' to '{destination}'? [y/N]: "
                confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                if confirm != 'y':
                    return False, "User refused copy"

            result = self.file_operator.copy_file(source, destination, overwrite, "")
            if result.get("success"):
                terminal.print_console(f"\n[OK] Copied '{source}' to '{destination}'.")
                action_id = self._compact_record_action(state, tool, f"{source} -> {destination}", timeout)
                out_compact, out_hash = self._compress_output("ok")
                self._compact_record_result(state, action_id, 0, out_compact, out_hash, tool)
                return True, None
            error = result.get("error", "Unknown error")
            action_id = self._compact_record_action(state, tool, f"{source} -> {destination}", timeout)
            out_compact, out_hash = self._compress_output(error)
            self._compact_record_result(state, action_id, 1, out_compact, out_hash, tool)
            return False, error

        if tool == "delete_file":
            path = action.get("path") or action.get("command_or_path")
            backup = action.get("backup", False)
            if not path:
                return False, "Missing path for delete_file"

            if not terminal.auto_accept:
                confirm_prompt_text = f"\nVaultAI> Delete '{path}'? [y/N]: "
                confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                if confirm != 'y':
                    return False, "User refused delete"

            result = self.file_operator.delete_file(path, backup, "")
            if result.get("success"):
                terminal.print_console(f"\n[OK] Deleted '{path}'.")
                action_id = self._compact_record_action(state, tool, path, timeout)
                out_compact, out_hash = self._compress_output("ok")
                self._compact_record_result(state, action_id, 0, out_compact, out_hash, tool)
                return True, None
            error = result.get("error", "Unknown error")
            action_id = self._compact_record_action(state, tool, path, timeout)
            out_compact, out_hash = self._compress_output(error)
            self._compact_record_result(state, action_id, 1, out_compact, out_hash, tool)
            return False, error

        return False, f"Unhandled tool: {tool}"

    def _compact_execute_actions(self, actions: List[Dict[str, Any]], state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        max_actions = int(state.get("budget", {}).get("max_actions", 5))
        limited_actions = actions[:max_actions]
        if len(actions) > max_actions:
            errors.append(f"Truncated actions to max_actions={max_actions}")

        for action in limited_actions:
            if not isinstance(action, dict):
                errors.append("Invalid action item (not object)")
                continue
            ok, err = self._compact_execute_single_action(action, state)
            if not ok and err:
                errors.append(err)

        state.setdefault("errors", []).extend(errors)
        self._cap_state_size(state)
        return len(errors) == 0, errors

    def _compact_local_summary(self, state: Dict[str, Any]) -> Tuple[str, bool]:
        total_actions = len(state.get("actions", []))
        total_errors = len(state.get("errors", []))
        goal_success = total_errors == 0 and total_actions > 0
        summary = (
            f"Compact pipeline completed with {total_actions} action(s). "
            f"Errors: {total_errors}."
        )
        return summary, goal_success

    def _compact_should_fallback(self) -> bool:
        if self.goal_success:
            errors = self.compact_state.get("errors") if isinstance(self.compact_state, dict) else None
            if isinstance(errors, list) and len(errors) == 0:
                return False
        status = None
        if isinstance(self.compact_state, dict):
            status = self.compact_state.get("status")
        return status in (None, "blocked") or not self.goal_success

    def _run_compact_pipeline(self) -> None:
        terminal = self.terminal
        state = self.compact_state or self._init_compact_state()
        state["goal"] = self.user_goal
        state["status"] = "running"
        state["errors"] = []
        state["actions"] = []
        state["results"] = []
        state.setdefault("budget", {}).setdefault("max_calls", 3)
        state.setdefault("budget", {}).setdefault("max_actions", 5)
        state.setdefault("budget", {}).setdefault("max_state_chars", 4000)
        state["budget"]["calls_used"] = 0
        self.compact_state = state

        # Call 1: single-call decision or actions
        single_prompt = self._compact_build_prompt_single(state)
        single_response = self._compact_llm_json_call(
            self.system_prompt_compact_single,
            single_prompt,
            operation="compact_single",
            max_tokens=self.compact_max_output_tokens,
            state=state,
        )

        if single_response is None:
            summary, goal_success = self._compact_local_summary(state)
            self.summary = summary
            self.goal_success = goal_success
            state["final"] = {"summary": summary, "goal_success": goal_success}
            state["status"] = "done"
            return

        self._compact_apply_state_update(state, single_response.get("state_update"))

        if single_response.get("kind") == "final":
            summary = single_response.get("summary", "")
            goal_success = bool(single_response.get("goal_success", False))
            self.summary = summary
            self.goal_success = goal_success
            state["final"] = {"summary": summary, "goal_success": goal_success}
            state["status"] = "done"
            return

        if single_response.get("kind") != "actions":
            state.setdefault("errors", []).append("Invalid response kind")
        else:
            actions = single_response.get("actions", [])
            if isinstance(actions, list):
                success, errors = self._compact_execute_actions(actions, state)
                state["status"] = "running" if success else "blocked"
            else:
                success, errors = False, ["Actions is not a list"]
                state.setdefault("errors", []).extend(errors)
                state["status"] = "blocked"

            # Repair pass if needed and budget allows
            if not success:
                repair_prompt = self._compact_build_prompt_repair(
                    state,
                    state.get("errors", []),
                    state.get("results", []),
                )
                repair_response = self._compact_llm_json_call(
                    self.system_prompt_compact_repair,
                    repair_prompt,
                    operation="compact_repair",
                    max_tokens=self.compact_max_output_tokens,
                    state=state,
                )
                if repair_response:
                    self._compact_apply_state_update(state, repair_response.get("state_update"))
                    if repair_response.get("kind") == "final":
                        summary = repair_response.get("summary", "")
                        goal_success = bool(repair_response.get("goal_success", False))
                        self.summary = summary
                        self.goal_success = goal_success
                        state["final"] = {"summary": summary, "goal_success": goal_success}
                        state["status"] = "done"
                        return
                    if repair_response.get("kind") == "actions":
                        actions = repair_response.get("actions", [])
                        if isinstance(actions, list):
                            success, _ = self._compact_execute_actions(actions, state)
                            state["status"] = "running" if success else "blocked"
                        else:
                            state.setdefault("errors", []).append("Repair actions is not a list")
                            state["status"] = "blocked"

        # Final summary call if budget allows
        final_prompt = self._compact_build_prompt_final(state)
        final_response = self._compact_llm_json_call(
            self.system_prompt_compact_final,
            final_prompt,
            operation="compact_final",
            max_tokens=self.compact_max_summary_tokens,
            state=state,
        )

        if final_response and "summary" in final_response:
            summary = final_response.get("summary", "")
            goal_success = bool(final_response.get("goal_success", False))
            self.summary = summary
            self.goal_success = goal_success
            state["final"] = {"summary": summary, "goal_success": goal_success}
            state["status"] = "done"
            self._compact_apply_state_update(state, final_response.get("state_update"))
        else:
            summary, goal_success = self._compact_local_summary(state)
            self.summary = summary
            self.goal_success = goal_success
            state["final"] = {"summary": summary, "goal_success": goal_success}
            state["status"] = "done"

    def _parse_ai_response_with_enhanced_validator(self, ai_reply: str, request_id: str) -> tuple:
        """
        Parse AI response using the enhanced JSON validator for better error recovery.
        
        Args:
            ai_reply: Raw AI response string
            request_id: Request ID for logging
            
        Returns:
            tuple: (success, data, ai_reply_json_string, corrected_successfully, error_message)
        """
        # Start timing JSON validation
        json_timing_id = self._start_timing("JSON_VALIDATION")
        
        if not self.json_validator:
            # Fallback to original parsing if enhanced validator is not available
            result = self._parse_ai_response_original(ai_reply, request_id)
            # End timing JSON validation (fallback path)
            self._end_timing(json_timing_id, "JSON_VALIDATION", result[0])
            return result
        
        try:
            success, data, error = self.json_validator.validate_response(ai_reply)
            
            if success:
                # Successfully parsed with enhanced validator - always serialize to JSON string
                ai_reply_json_string = json.dumps(data, ensure_ascii=False)
                self.logger.debug(f"Enhanced JSON validator successfully parsed response. request_id={request_id}")
                # End timing JSON validation (success with enhanced validator)
                self._end_timing(json_timing_id, "JSON_VALIDATION", True)
                return True, data, ai_reply_json_string, False, ""
            else:
                # Enhanced validator failed, try original parsing as fallback
                self.logger.warning(f"Enhanced JSON validator failed: {error}. Trying original parsing. request_id={request_id}")
                result = self._parse_ai_response_original(ai_reply, request_id)
                # End timing JSON validation (fallback path)
                self._end_timing(json_timing_id, "JSON_VALIDATION", result[0])
                return result
                
        except Exception as e:
            self.logger.error(f"Error in enhanced JSON validation: {e}. Falling back to original parsing. request_id={request_id}")
            result = self._parse_ai_response_original(ai_reply, request_id)
            # End timing JSON validation (exception path)
            self._end_timing(json_timing_id, "JSON_VALIDATION", result[0])
            return result

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

                # Start timing JSON correction attempt
                correction_timing_id = self._start_timing("JSON_CORRECTION")
                
                corrected_ai_reply = self.ai_handler.send_request(
                    system_prompt=self.system_prompt_agent, 
                    user_prompt=correction_llm_prompt_text,
                    request_format="json"
                )

                # End timing JSON correction attempt
                self._end_timing(correction_timing_id, "JSON_CORRECTION", corrected_ai_reply is not None)

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

    def _compress_with_fallback(self, text: str, logger) -> str:
        """
        Compress text with configurable compressor selection based on LOG_COMPRESSOR_MODE.
        
        Args:
            text: Text to compress
            logger: Logger instance for error logging
            
        Returns:
            Compressed text, or original text if both compressors fail
        """
        # Get compressor mode from environment variable
        compressor_mode = os.getenv("LOG_COMPRESSOR_MODE", "auto").lower().strip()
        
        if compressor_mode == "simple":
            # Force use of LogCompressor only
            try:
                compressor = LogCompressor()
                compressed_out = compressor.compress(text)
                logger.debug(f"LogCompressor (simple mode) successfully compressed output from {len(text)} chars to {len(compressed_out)} chars")
                return compressed_out
            except Exception as e:
                logger.error(f"LogCompressor failed in simple mode: {e}. Using original text.")
                return text
        
        elif compressor_mode == "dynamic":
            # Force use of DynamicLogCompressor only (no fallback)
            try:
                
                # Get HF token and cache path from environment
                hf_token = os.getenv("HF_TOKEN")
                compressor = DynamicLogCompressor(dir_app=self.dir_app,logger=self.logger)
                compressed_out = compressor.compress(text)
                logger.debug(f"DynamicLogCompressor (dynamic mode) successfully compressed output from {len(text)} chars to {len(compressed_out)} chars")
                return compressed_out
            except Exception as e:
                logger.error(f"DynamicLogCompressor failed in dynamic mode: {e}. Using original text.")
                return text
        
        else:  # compressor_mode == "auto" or any other value
            # Auto mode: try DynamicLogCompressor first, then fallback to LogCompressor
            try:
                # Get HF token and cache path from environment
                hf_token = os.getenv("HF_TOKEN")
                compressor = DynamicLogCompressor(dir_app=self.dir_app,logger=self.logger)
                compressed_out = compressor.compress(text)
                logger.debug(f"DynamicLogCompressor (auto mode) successfully compressed output from {len(text)} chars to {len(compressed_out)} chars")
                return compressed_out
            except Exception as e:
                logger.warning(f"DynamicLogCompressor failed in auto mode: {e}. Falling back to LogCompressor.")
                
                # Fallback to LogCompressor (simpler but more reliable)
                try:
                    compressor = LogCompressor()
                    compressed_out = compressor.compress(text)
                    logger.debug(f"LogCompressor (auto mode fallback) successfully compressed output from {len(text)} chars to {len(compressed_out)} chars")
                    return compressed_out
                except Exception as e2:
                    logger.error(f"LogCompressor also failed in auto mode: {e2}. Using original text.")
                    return text

    def run(self):
        terminal = self.terminal
        keep_running = True

        if self.force_plan:
            self.compact_mode = False
            self.hybrid_mode = False

        if self.compact_mode:
            self._run_compact_pipeline()
            compact_finish_blocked_by_critic = False

            # Apply critic scoring/gate in compact pipeline before final return.
            if (
                self.goal_success
                and self.enable_critic_sub_agent
                and self.critic_sub_agent is not None
            ):
                try:
                    # Pass compact state results to critic for better evaluation
                    agent_results = self.compact_state.get("results", []) if isinstance(self.compact_state, dict) else None
                    critic_result = self.critic_sub_agent.run(
                        user_goal=self.user_goal,
                        agent_summary=self.summary or "Agent reported task finished.",
                        agent_results=agent_results,
                    )
                    self.critic_rating = critic_result.get("rating", 0)
                    self.critic_verdict = critic_result.get("verdict", "")
                    self.critic_rationale = critic_result.get("rationale", "")
                except Exception as e:
                    terminal.print_console(f"\n[WARN] Critic Sub-Agent encountered an error: {e}")
                    self.logger.warning("CriticSubAgent.run failed in compact pipeline: %s", e)
            elif (
                self.goal_success
                and self.enable_critic_sub_agent
                and self.loop_critic_sub_agent
                and self.critic_sub_agent is None
            ):
                self.logger.warning(
                    "LOOP_CRITIC_SUB_AGENT is enabled but CriticSubAgent is unavailable "
                    "in compact pipeline; continuing without critic gate."
                )

            if (
                self.goal_success
                and self.enable_critic_sub_agent
                and self.loop_critic_sub_agent
                and self.critic_sub_agent is not None
                and self.critic_verdict.strip() != "Correct"
            ):
                compact_finish_blocked_by_critic = True
                critic_verdict = self.critic_verdict.strip() or "Unknown"
                terminal.print_console(
                    "\n[WARN] Compact finish blocked by Critic Sub-Agent verdict "
                    f"'{critic_verdict}'."
                )
                self.context_manager.add_user_message(
                    "Your compact final answer was rejected by CriticSubAgent. "
                    f"Critic rating: {self.critic_rating}/10. "
                    f"Verdict: {critic_verdict}. "
                    f"Rationale: {self.critic_rationale or 'No rationale provided.'} "
                    "Please continue working and provide a corrected final answer."
                )
                try:
                    self.logger.info(
                        "Compact finish rejected by critic verdict=%s rating=%s",
                        critic_verdict,
                        self.critic_rating,
                    )
                except Exception:
                    pass
                self.summary = ""
                self.goal_success = False

            if not compact_finish_blocked_by_critic and (
                not self.hybrid_mode or not self._compact_should_fallback()
            ):
                summary_text = self.summary or "Agent reported task finished."
                self.terminal.print_console(
                    f"\nVaultAI> Agent finished its task.\nSummary: {summary_text}"
                )
                if self.show_performance_summary and (
                    self.timings
                    or (hasattr(self.ai_handler, 'token_usage') and self.ai_handler.token_usage)
                ):
                    self.terminal.print_console("\n" + "="*60)
                    self.terminal.print_console("PERFORMANCE SUMMARY")
                    self.terminal.print_console("="*60)
                    if hasattr(self.ai_handler, 'token_usage') and self.ai_handler.token_usage:
                        self._display_cost_optimization_recommendations()
                    if self.timings:
                        self._display_timing_summary()
                    if hasattr(self.ai_handler, 'token_usage') and self.ai_handler.token_usage:
                        self._display_token_summary()
                    # Display summarize operations summary
                    self._display_summarize_stats_summary()
                    self.terminal.print_console("="*60)
                return
            self.terminal.print_console("\n VaultAI> Compact mode fallback to normal mode.")
            self.summary = ""
            self.goal_success = False

        try:
            self.logger.info("Starting VaultAIAgentRunner.run for goal: %s", self.user_goal)
        except Exception:
            pass

        # Check if plan should be forced (via --plan flag or [plan] keyword)
        if self.force_plan:
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
                
                # Add current plan status to the prompt if plan exists
                # This ensures AI is always aware of plan progress
                if self._plan_exists():
                    plan_status = self._get_plan_status_for_ai()
                    if plan_status:
                        prompt_text_parts.append(f"system: {plan_status}")
                
                prompt_text = "\n".join(prompt_text_parts)

                # Start timing AI response generation
                ai_timing_id = self._start_timing("AI_RESPONSE_GENERATION")
                
                ai_reply = self.ai_handler.send_request(
                    system_prompt=self.system_prompt_agent, 
                    user_prompt=prompt_text,
                    request_format="json"
                )
                
                # End timing AI response generation
                ai_duration = self._end_timing(ai_timing_id, "AI_RESPONSE_GENERATION", ai_reply is not None)

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
                    # Backward compatibility alias
                    if tool == "analyze_data":
                        tool = "analysis_data"
                        action_item["tool"] = "analysis_data"
                    elif tool == "final":
                        tool = "finish"
                        action_item["tool"] = "finish"
                        if "summary" not in action_item and "answer" in action_item:
                            action_item["summary"] = action_item.get("answer")
                        if "goal_success" not in action_item:
                            action_item["goal_success"] = True
                    
                    if tool is None:
                        terminal.print_console(f"[WARN] AI response missing 'tool' field: {action_item}")
                        self.context_manager.add_user_message(
                            "Your response is missing the required 'tool' field. "
                            "Valid tools are: 'create_action_plan', 'bash', 'read_file', 'write_file', 'edit_file', "
                            "'list_directory', 'search_in_file', 'copy_file', 'delete_file', 'analysis_data', "
                            "'update_plan_step', 'ask_user', 'web_search_agent', 'finish'. "
                            "Please provide a valid JSON response with the correct structure."
                        )
                        continue
                    

                    if tool == "create_action_plan":
                        # Create action plan tool - agent decides when task is complex
                        goal = action_item.get("goal", self.user_goal)
                        explain = action_item.get("explain", "")
                        
                        terminal.print_console(f"\nVaultAI> Creating action plan for: {goal}")
                        if explain:
                            terminal.print_console(f"Reason: {explain}")
                        
                        # Start timing plan creation
                        plan_timing_id = self._start_timing(f"PLAN_CREATION_{goal[:50]}")
                        
                        # Check if plan already exists
                        if self.plan_manager.steps:
                            terminal.print_console("[WARN] A plan already exists. Clearing old plan.")
                            self.plan_manager.clear()
                        
                        try:
                            steps = self.plan_manager.create_plan_with_ai(goal)
                            
                            if steps:
                                terminal.print_console(f"[OK] Created plan with {len(steps)} steps")
                                self.plan_manager.display_plan()
                                
                                # In interactive mode, ask for plan acceptance
                                if not terminal.auto_accept:
                                    self._interactive_plan_acceptance()
                                
                                # Add plan to AI context - THIS IS CRITICAL FOR AI TO SEE THE PLAN
                                plan_context = self.plan_manager.get_context_for_ai()
                                self.context_manager.add_system_message(
                                    f"Action plan created successfully. "
                                    f"Execute steps sequentially and update the status of each step after completion.\n\n{plan_context}"
                                )
                                self.context_manager.add_user_message(
                                    f"Action plan created with {len(steps)} steps. Begin execution with step 1."
                                )
                                self.logger.info(f"[PLAN ADDED TO CONTEXT] Dynamic plan with {len(steps)} steps added to AI context during execution")
                                
                                # End timing plan creation (success)
                                self._end_timing(plan_timing_id, f"PLAN_CREATION_{goal[:50]}", True)
                            else:
                                terminal.print_console("[WARN] Failed to create action plan. Proceeding without plan.")
                                self.context_manager.add_user_message(
                                    "Failed to create action plan. You can proceed without a plan or try again. "
                                    "For simple tasks, just execute commands directly."
                                )
                                
                                # End timing plan creation (failed)
                                self._end_timing(plan_timing_id, f"PLAN_CREATION_{goal[:50]}", False)
                        except Exception as e:
                            terminal.print_console(f"[ERROR] Failed to create action plan: {e}")
                            self.context_manager.add_user_message(
                                f"Failed to create action plan due to error: {e}. "
                                "You can proceed without a plan for simple tasks."
                            )
                            
                            # End timing plan creation (exception)
                            self._end_timing(plan_timing_id, f"PLAN_CREATION_{goal[:50]}", False)
                        continue

                    elif tool == "finish":
                        summary_text = action_item.get("summary", "Agent reported task finished.")
                        goal_success = action_item.get("goal_success", False)
                        if isinstance(goal_success, bool):
                            self.goal_success = goal_success
                        else:
                            self.logger.warning(f"Invalid or missing 'goal_success' value in finish tool: {goal_success}. Expected a boolean. Defaulting to False. request_id={request_id}")
                            self.goal_success = False
                        
                        # Check if plan exists and if all steps are completed before allowing finish
                        if self.plan_manager.steps:
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
                        # If no plan exists, allow finish without checking plan status

                        should_gate_finish_with_critic = (
                            self.goal_success
                            and self.enable_critic_sub_agent
                            and self.loop_critic_sub_agent
                            and self.critic_sub_agent is not None
                        )
                        if (
                            self.goal_success
                            and self.enable_critic_sub_agent
                            and self.critic_sub_agent is None
                            and self.loop_critic_sub_agent
                        ):
                            self.logger.warning(
                                "LOOP_CRITIC_SUB_AGENT is enabled but CriticSubAgent is unavailable; "
                                "continuing without critic gate."
                            )

                        # --- CriticSubAgent: Correctness Score / optional finish gate ---
                        if (
                            self.goal_success
                            and self.enable_critic_sub_agent
                            and self.critic_sub_agent is not None
                        ):
                            try:
                                critic_result = self.critic_sub_agent.run(
                                    user_goal=self.user_goal,
                                    agent_summary=summary_text,
                                )
                                self.critic_rating = critic_result.get("rating", 0)
                                self.critic_verdict = critic_result.get("verdict", "")
                                self.critic_rationale = critic_result.get("rationale", "")
                            except Exception as e:
                                terminal.print_console(f"\n[WARN] Critic Sub-Agent encountered an error: {e}")
                                self.logger.warning("CriticSubAgent.run failed: %s", e)
                        # --- End CriticSubAgent ---

                        if should_gate_finish_with_critic:
                            critic_verdict = self.critic_verdict.strip()
                            if critic_verdict != "Correct":
                                terminal.print_console(
                                    "\n[WARN] Finish blocked by Critic Sub-Agent verdict "
                                    f"'{critic_verdict or 'Unknown'}'."
                                )
                                self.context_manager.add_user_message(
                                    "Your 'finish' action was rejected by CriticSubAgent. "
                                    f"Critic rating: {self.critic_rating}/10. "
                                    f"Verdict: {critic_verdict or 'Unknown'}. "
                                    f"Rationale: {self.critic_rationale or 'No rationale provided.'} "
                                    "Please continue working and call 'finish' only after fully addressing "
                                    "the user goal."
                                )
                                try:
                                    self.logger.info(
                                        "Finish rejected by critic verdict=%s rating=%s request_id=%s",
                                        critic_verdict or "Unknown",
                                        self.critic_rating,
                                        request_id,
                                    )
                                except Exception:
                                    pass
                                continue

                        # Track which model created the summary
                        model_used = getattr(self.ai_handler, 'ai_engines', [getattr(self.ai_handler, 'ai_engine', 'unknown')])[0]
                        self.summary_model_creator = model_used

                        terminal.print_console(f"\nVaultAI> Agent finished its task.\nSummary: {summary_text}")
                        self.summary = summary_text
                        task_finished_successfully = True
                        agent_should_stop_this_turn = True
                        try:
                            # Log finish along with the request id for traceability
                            self.logger.info("Agent signaled finish with summary: %s; request_id=%s; model=%s", summary_text, request_id, model_used)
                        except Exception:
                            pass

                        # Display model information in summary
                        terminal.print_console(f"Summary created by: {model_used}")

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
                                terminal.print_console("Deep Analysis skipped.")
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
                        
                        # Start timing command execution
                        cmd_timing_id = self._start_timing(f"COMMAND_EXECUTION_{command[:50]}")
                        
                        out, code = "", 1
                        if self.terminal.ssh_connection:
                            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
                            password = getattr(self.terminal, "ssh_password", None)
                            out, code = self.terminal.execute_remote_pexpect(command, remote, password=password, timeout=timeout)
                        else:
                            out, code = self.terminal.execute_local(command, timeout=timeout) # Corrected method call
                        
                        # End timing command execution
                        cmd_duration = self._end_timing(cmd_timing_id, f"COMMAND_EXECUTION_{command[:50]}", code == 0)

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

                        output_type = detect_output_type(out, command)
                        if output_type == "empty":
                            original_feedback = (
                                f"Command '{command}' executed with exit code {code} and no output.\n"
                                f"The command {'succeeded' if code == 0 else 'failed'} with no output. "
                                f"You can mark this step as {'completed' if code == 0 else 'failed'} and proceed to the next step."
                            )
                        elif output_type == "json":
                            # pretty / truncate JSON output for feedback
                            original_len = len(out)
                            summarized_json_out = summarize_json(out)
                            summarized_len = len(summarized_json_out)
                            # Track summarize stats
                            self.summarize_stats["json"]["original"] += original_len
                            self.summarize_stats["json"]["summarized"] += summarized_len
                            self.summarize_stats["json"]["count"] += 1
                            self.summarize_stats["total_original"] += original_len
                            self.summarize_stats["total_summarized"] += summarized_len
                            self.summarize_stats["total_saved"] += (original_len - summarized_len)
                            self.summarize_stats["total_count"] += 1
                            self.logger.debug(f"JSON Command output from {original_len} chars to {summarized_len} chars for feedback (saved {original_len - summarized_len})")
                            if code == 0:
                                original_feedback = (
                                    f"Command '{command}' executed successfully with exit code 0 and produced JSON output.\n"
                                    f"Output:\n\n{summarized_json_out}\n\n"
                                    "The command succeeded. You can mark this step as completed and proceed to the next step."
                                )
                            else:
                                    original_feedback = (
                                        f"Command '{command}' failed with exit code {code} but produced JSON output.\n"
                                        f"Output:\n\n{summarized_json_out}\n\n"
                                        f"The command failed. Analyze the error and decide:\n"
                                        f"- RETRY: If it's a transient error (timeout, network, temporary), retry with same or modified command\n"
                                        f"- FIX: If the command was wrong (bad syntax, missing args), fix and retry with corrected command\n"
                                        f"- SKIP: If this step is non-critical and you can proceed without it\n"
                                        f"- FAIL: If this is a critical error that blocks progress\n"
                                        f"What is your decision?"
                                    )
                        elif output_type == "stacktrace":
                            original_len = len(out)
                            summarized_stacktrace_out = summarize_stacktrace(out)
                            summarized_len = len(summarized_stacktrace_out)
                            # Track summarize stats
                            self.summarize_stats["stacktrace"]["original"] += original_len
                            self.summarize_stats["stacktrace"]["summarized"] += summarized_len
                            self.summarize_stats["stacktrace"]["count"] += 1
                            self.summarize_stats["total_original"] += original_len
                            self.summarize_stats["total_summarized"] += summarized_len
                            self.summarize_stats["total_saved"] += (original_len - summarized_len)
                            self.summarize_stats["total_count"] += 1
                            self.logger.debug(f"Stacktrace Command output from {original_len} chars to {summarized_len} chars for feedback (saved {original_len - summarized_len})")
                            if code == 0:
                                original_feedback = (
                                    f"Command '{command}' executed successfully with exit code 0 but produced a stacktrace output.\n"
                                    f"Output:\n\n{summarized_stacktrace_out}\n\n"
                                    "The command succeeded but produced a stacktrace. Analyze the output to determine if there are any warnings or non-critical errors. You can mark this step as completed and proceed to the next step if the stacktrace does not indicate a critical issue."
                                )
                            else:
                                original_feedback = (
                                    f"Command '{command}' failed with exit code {code} and produced a stacktrace output.\n"
                                    f"Output:\n\n{summarized_stacktrace_out}\n\n"
                                    f"The command failed and produced a stacktrace. Analyze the stacktrace to identify the error. Based on the analysis, decide:\n"
                                    f"- RETRY: If it's a transient error (timeout, network, temporary), retry with same or modified command\n"
                                    f"- FIX: If the command was wrong (bad syntax, missing args), fix and retry with corrected command\n"
                                    f"- SKIP: If this step is non-critical and you can proceed without it\n"
                                    f"- FAIL: If this is a critical error that blocks progress\n"
                                    f"What is your decision?"
                                )
                        elif output_type == "log":
                            if  should_compress_adaptive(out):
                                compressed_out = self._compress_with_fallback(out, self.logger)
                                self.logger.debug(f"Compressed command output from {len(out)} chars to {len(compressed_out)} chars for command: {command}")
                                out = compressed_out
                                text_for_feedback = f"Compressed Output:\n\n{out}\n\n"
                            else:
                                text_for_feedback = f"Output:\n\n{out}\n\n"
                            if code == 0:
                                original_feedback = (
                                    f"Command '{command}' executed successfully with exit code 0 and produced log output.\n"
                                    f"{text_for_feedback}"
                                    "The command succeeded. You can mark this step as completed and proceed to the next step."
                                )
                            else:
                                original_feedback = (
                                    f"Command '{command}' failed with exit code {code} but produced log output.\n"
                                    f"{text_for_feedback}"
                                    f"The command failed. Analyze the log output to identify any error messages or warnings. Based on the analysis, decide:\n"
                                    f"- RETRY: If it's a transient error (timeout, network, temporary), retry with same or modified command\n"
                                    f"- FIX: If the command was wrong (bad syntax, missing args), fix and retry with corrected command\n"
                                    f"- SKIP: If this step is non-critical and you can proceed without it\n"
                                    f"- FAIL: If this is a critical error that blocks progress\n"
                                    f"What is your decision?"
                                )
                        elif output_type == "table":
                            # Summarize table output using the new summarization functions
                            try:
                                original_len = len(out)
                                summarized_output = summarize_table(out)
                                summarized_len = len(summarized_output)
                                # Track summarize stats
                                self.summarize_stats["table"]["original"] += original_len
                                self.summarize_stats["table"]["summarized"] += summarized_len
                                self.summarize_stats["table"]["count"] += 1
                                self.summarize_stats["total_original"] += original_len
                                self.summarize_stats["total_summarized"] += summarized_len
                                self.summarize_stats["total_saved"] += (original_len - summarized_len)
                                self.summarize_stats["total_count"] += 1
                                self.logger.debug(f"Table Command output from {original_len} chars to {summarized_len} chars for feedback (saved {original_len - summarized_len})")
                                if code == 0:
                                    original_feedback = (
                                        f"Command '{command}' executed successfully with exit code 0 and produced table output.\n"
                                        f"Summary:\n{summarized_output}\n"
                                        "The command succeeded. You can mark this step as completed and proceed to the next step."
                                    )
                                else:
                                    original_feedback = (
                                        f"Command '{command}' failed with exit code {code} but produced table output.\n"
                                        f"Summary:\n{summarized_output}\n"
                                        f"The command failed. Analyze the table output to identify any error messages or warnings. Based on the analysis, decide:\n"
                                        f"- RETRY: If it's a transient error (timeout, network, temporary), retry with same or modified command\n"
                                        f"- FIX: If the command was wrong (bad syntax, missing args), fix and retry with corrected command\n"
                                        f"- SKIP: If this step is non-critical and you can proceed without it\n"
                                        f"- FAIL: If this is a critical error that blocks progress\n"
                                        f"What is your decision?"
                                    )
                            except Exception as e:
                                # Fallback to original behavior if summarization fails
                                self.logger.warning(f"Table summarization failed for command '{command}': {e}")
                                if code == 0:
                                    original_feedback = (
                                        f"Command '{command}' executed successfully with exit code 0 and produced table output.\n"
                                        f"Output:\n\n{out}\n\n"
                                        "The command succeeded. You can mark this step as completed and proceed to the next step."
                                    )
                                else:
                                    original_feedback = (
                                        f"Command '{command}' failed with exit code {code} but produced table output.\n"
                                        f"Output:\n\n{out}\n\n"
                                        f"The command failed. Analyze the table output to identify any error messages or warnings. Based on the analysis, decide:\n"
                                        f"- RETRY: If it's a transient error (timeout, network, temporary), retry with same or modified command\n"
                                        f"- FIX: If the command was wrong (bad syntax, missing args), fix and retry with corrected command\n"
                                        f"- SKIP: If this step is non-critical and you can proceed without it\n"
                                        f"- FAIL: If this is a critical error that blocks progress\n"
                                        f"What is your decision?"
                                    )
                        elif output_type == "kv":
                            original_len = len(out)
                            summarize_kv_out = summarize_kv(out)
                            summarized_len = len(summarize_kv_out)
                            # Track summarize stats
                            self.summarize_stats["kv"]["original"] += original_len
                            self.summarize_stats["kv"]["summarized"] += summarized_len
                            self.summarize_stats["kv"]["count"] += 1
                            self.summarize_stats["total_original"] += original_len
                            self.summarize_stats["total_summarized"] += summarized_len
                            self.summarize_stats["total_saved"] += (original_len - summarized_len)
                            self.summarize_stats["total_count"] += 1
                            self.logger.debug(f"KV Command output from {original_len} chars to {summarized_len} chars for feedback (saved {original_len - summarized_len})")
                            if code == 0:
                                original_feedback = (
                                    f"Command '{command}' executed successfully with exit code 0 and produced key-value output.\n"
                                    f"Output:\n\n{summarize_kv_out}\n\n"
                                    "The command succeeded. You can mark this step as completed and proceed to the next step."
                                )
                            else:
                                original_feedback = (
                                    f"Command '{command}' failed with exit code {code} but produced key-value output.\n"
                                    f"Output:\n\n{summarize_kv_out}\n\n"
                                    f"The command failed. Analyze the key-value output to identify any error messages or warnings. Based on the analysis, decide:\n"
                                    f"- RETRY: If it's a transient error (timeout, network, temporary), retry with same or modified command\n"
                                    f"- FIX: If the command was wrong (bad syntax, missing args), fix and retry with corrected command\n"
                                    f"- SKIP: If this step is non-critical and you can proceed without it\n"
                                    f"- FAIL: If this is a critical error that blocks progress\n"
                                    f"What is your decision?"
                                )
                        elif output_type == "single_line":
                            if code == 0:
                                original_feedback = (
                                    f"Command '{command}' executed successfully with exit code 0 and produced single-line output.\n"
                                    f"Output: {out}\n\n"
                                    "The command succeeded. You can mark this step as completed and proceed to the next step."
                                )
                            else:
                                original_feedback = (
                                    f"Command '{command}' failed with exit code {code} but produced single-line output.\n"
                                    f"Output: {out}\n\n"
                                    f"The command failed. Analyze the output to identify any error messages or warnings. Based on the analysis, decide:\n"
                                    f"- RETRY: If it's a transient error (timeout, network, temporary), retry with same or modified command\n"
                                    f"- FIX: If the command was wrong (bad syntax, missing args), fix and retry with corrected command\n"
                                    f"- SKIP: If this step is non-critical and you can proceed without it\n"
                                    f"- FAIL: If this is a critical error that blocks progress\n"
                                    f"What is your decision?"
                                )
                        elif output_type == "text" or output_type == "unknown":
                            # truncate if too long
                            if code == 0:
                                original_feedback = (
                                    f"Command '{command}' executed successfully with exit code 0 and produced text output.\n"
                                    f"Output:\n\n{out}\n\n"
                                    "The command succeeded. You can mark this step as completed and proceed to the next step."
                                )
                            else:
                                original_feedback = (
                                    f"Command '{command}' failed with exit code {code} and produced text output.\n"
                                    f"Output:\n\n{out}\n\n"
                                    f"The command failed. Analyze the output to identify any error messages or warnings. Based on the analysis, decide:\n"
                                    f"- RETRY: If it's a transient error (timeout, network, temporary), retry with same or modified command\n"
                                    f"- FIX: If the command was wrong (bad syntax, missing args), fix and retry with corrected command\n"
                                    f"- SKIP: If this step is non-critical and you can proceed without it\n"
                                    f"- FAIL: If this is a critical error that blocks progress\n"
                                    f"What is your decision?"
                                )
                                
                        user_feedback_content = compress_prompt(original_feedback)
                        self._log_prompt_filter_savings(original_feedback, user_feedback_content)

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

                    elif tool == "analysis_data":
                        explain = action_item.get("explain", "")
                        is_valid, analysis_args, validation_error = self._validate_analysis_data_arguments(action_item)
                        if not is_valid:
                            self.logger.warning(
                                "analysis_data validation failed: %s; action=%s; request_id=%s",
                                validation_error,
                                action_item,
                                request_id,
                            )
                            terminal.print_console(
                                f"[WARN] Invalid analysis_data action: {validation_error}. Skipping."
                            )
                            self.context_manager.add_user_message(
                                f"You provided an invalid 'analysis_data' action: {validation_error}. "
                                f"Action: {action_item}. I am skipping it."
                            )
                            self._update_plan_progress("analysis_data validation failed", success=False)
                            continue

                        analysis_type = analysis_args["type"]
                        output_format = analysis_args["output_format"]
                        self.logger.info(
                            "analysis_data requested: type=%s format=%s request_id=%s",
                            analysis_type,
                            output_format,
                            request_id,
                        )
                        requested_max_tokens = analysis_args["constraints"]["max_tokens"]
                        max_tokens = requested_max_tokens
                        # Some reasoning models may spend small budgets on hidden reasoning only.
                        # Keep practical lower bounds so structured outputs are actually returned.
                        if output_format == "json":
                            json_min_tokens = 3000 if analysis_type == "calculate" else 1200
                            if max_tokens < json_min_tokens:
                                max_tokens = json_min_tokens
                        elif output_format == "number" and max_tokens < 512:
                            max_tokens = 512

                        if not terminal.auto_accept:
                            if self.terminal.auto_explain_command and explain:
                                confirm_prompt_text = (
                                    f"\nVaultAI> Agent suggests to run analysis_data "
                                    f"(type='{analysis_type}', format='{output_format}') "
                                    f"which is intended to: {explain}. Execute? [y/N]: "
                                )
                            else:
                                confirm_prompt_text = (
                                    f"\nVaultAI> Agent suggests to run analysis_data "
                                    f"(type='{analysis_type}', format='{output_format}'). "
                                    f"Execute? [y/N]: "
                                )
                            confirm = self._get_user_input(
                                f"{confirm_prompt_text}", multiline=False
                            ).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(
                                    f"\nVaultAI> Provide justification for refusing analysis_data and press Ctrl+S to submit.\n{self.input_text}>  ",
                                    multiline=True,
                                ).strip()
                                self.logger.info(
                                    "analysis_data refused by user: type=%s format=%s justification=%s request_id=%s",
                                    analysis_type,
                                    output_format,
                                    justification,
                                    request_id,
                                )
                                terminal.print_console(
                                    f"\nVaultAI> analysis_data refused by user. Justification: {justification}\n"
                                )
                                self.context_manager.add_user_message(
                                    "User refused to execute analysis_data "
                                    f"(type='{analysis_type}', format='{output_format}') "
                                    f"with justification: {justification}. "
                                    "Based on this, what should be the next step?"
                                )
                                continue

                        terminal.print_console(
                            f"\nVaultAI> Executing analysis_data: type={analysis_type}, "
                            f"format={output_format}"
                        )
                        analysis_timing_id = self._start_timing(
                            f"ANALYSIS_DATA_{analysis_type.upper()}"
                        )

                        request_format = "json" if output_format == "json" else "text"
                        prompt_args = dict(analysis_args)
                        prompt_constraints = dict(analysis_args.get("constraints", {}))
                        prompt_constraints["max_tokens"] = max_tokens
                        prompt_args["constraints"] = prompt_constraints
                        analysis_system_prompt, analysis_user_prompt = self._build_analysis_data_prompts(
                            prompt_args
                        )
                        analysis_result = self.ai_handler.send_request(
                            system_prompt=analysis_system_prompt,
                            user_prompt=analysis_user_prompt,
                            request_format=request_format,
                            operation=f"analysis_data_tool_{analysis_type}",
                            max_tokens=max_tokens,
                        )
                        self.logger.debug(
                            "analysis_data primary call done: type=%s format=%s has_result=%s request_id=%s",
                            analysis_type,
                            output_format,
                            analysis_result is not None,
                            request_id,
                        )
                        used_lightweight_fallback = False
                        used_local_calculate_fallback = False

                        self._end_timing(
                            analysis_timing_id,
                            f"ANALYSIS_DATA_{analysis_type.upper()}",
                            analysis_result is not None,
                        )

                        if analysis_result is None:
                            # Some models can consume the whole budget on hidden reasoning for large
                            # calculate tasks and return empty output. Retry with a lighter text-only
                            # variant to keep the workflow moving.
                            if analysis_type == "calculate":
                                self.logger.warning(
                                    "analysis_data empty response on calculate, starting fallback flow; request_id=%s",
                                    request_id,
                                )
                                terminal.print_console(
                                    "[WARN] analysis_data returned no response for calculate; "
                                    "trying lightweight text fallback."
                                )
                                lightweight_system = ""
                                lightweight_user = (
                                    "ROLE: precise data analysis assistant.\n"
                                    "Return final answer directly without preamble.\n\n"
                                    f"ANALYSIS_TYPE: {analysis_type}\n"
                                    "OUTPUT_FORMAT: text\n"
                                    f"PRECISION: {analysis_args['constraints'].get('precision', 'medium')}\n"
                                    "MAX_TOKENS_BUDGET: 900\n"
                                    f"INSTRUCTIONS: {analysis_args.get('instructions') or 'None'}\n"
                                    f"CONTEXT: {analysis_args.get('context') or 'None'}\n"
                                    f"INPUT:\n{analysis_args.get('input', '')}\n\n"
                                    "OUTPUT RULE: Return concise final answer only. "
                                    "No reasoning trace."
                                )
                                fallback_result = self.ai_handler.send_request(
                                    system_prompt=lightweight_system,
                                    user_prompt=lightweight_user,
                                    request_format="text",
                                    operation=f"analysis_data_tool_{analysis_type}_fallback_text",
                                    max_tokens=900,
                                )
                                if fallback_result is not None:
                                    analysis_result = fallback_result
                                    used_lightweight_fallback = True
                                    self.logger.info(
                                        "analysis_data lightweight fallback succeeded: type=%s request_id=%s",
                                        analysis_type,
                                        request_id,
                                    )
                                else:
                                    local_fallback = self._local_calculate_analysis_data(analysis_args)
                                    if local_fallback is not None:
                                        analysis_result = json.dumps(local_fallback, ensure_ascii=False)
                                        used_local_calculate_fallback = True
                                        self.logger.info(
                                            "analysis_data local calculate fallback succeeded: type=%s request_id=%s",
                                            analysis_type,
                                            request_id,
                                        )
                            else:
                                self.logger.warning(
                                    "analysis_data empty response, starting lightweight fallback: type=%s request_id=%s",
                                    analysis_type,
                                    request_id,
                                )
                                terminal.print_console(
                                    "[WARN] analysis_data returned no response; "
                                    "trying lightweight text fallback."
                                )
                                lightweight_system = ""
                                lightweight_user = (
                                    "ROLE: precise data analysis assistant.\n"
                                    "Return concise final answer only.\n\n"
                                    f"ANALYSIS_TYPE: {analysis_type}\n"
                                    "OUTPUT_FORMAT: text\n"
                                    f"PRECISION: {analysis_args['constraints'].get('precision', 'medium')}\n"
                                    "MAX_TOKENS_BUDGET: 700\n"
                                    f"INSTRUCTIONS: {analysis_args.get('instructions') or 'None'}\n"
                                    f"CONTEXT: {analysis_args.get('context') or 'None'}\n"
                                    f"INPUT:\n{analysis_args.get('input', '')}\n\n"
                                    "OUTPUT RULE: Return concise final answer only. "
                                    "No reasoning trace."
                                )
                                fallback_result = self.ai_handler.send_request(
                                    system_prompt=lightweight_system,
                                    user_prompt=lightweight_user,
                                    request_format="text",
                                    operation=f"analysis_data_tool_{analysis_type}_fallback_text",
                                    max_tokens=700,
                                )
                                if fallback_result is not None:
                                    analysis_result = fallback_result
                                    used_lightweight_fallback = True
                                    self.logger.info(
                                        "analysis_data lightweight fallback succeeded: type=%s request_id=%s",
                                        analysis_type,
                                        request_id,
                                    )

                        if analysis_result is None:
                            self.logger.error(
                                "analysis_data failed: no AI response after fallbacks; type=%s format=%s request_id=%s",
                                analysis_type,
                                output_format,
                                request_id,
                            )
                            terminal.print_console(
                                "[ERROR] analysis_data failed: no response from AI."
                            )
                            self._update_plan_progress(
                                f"analysis_data failed: {analysis_type}", success=False
                            )
                            self.context_manager.add_user_message(
                                f"analysis_data failed for type '{analysis_type}': no AI response."
                            )
                            continue

                        raw_result = analysis_result if isinstance(analysis_result, str) else str(analysis_result)
                        self.logger.debug(
                            "analysis_data raw response stats: type=%s format=%s len=%d",
                            analysis_type,
                            output_format,
                            len(raw_result),
                        )
                        result_for_context = raw_result
                        result_for_display = raw_result
                        number_fallback_note = ""
                        strict_json_retry_used = False
                        strict_json_fallback_used = False
                        lightweight_json_wrap_used = False

                        if output_format == "json":
                            if used_lightweight_fallback:
                                fallback_obj = {
                                    "fallback": "analysis_data_calculate_lightweight_text",
                                    "analysis_type": analysis_type,
                                    "result_text": raw_result[:4000],
                                }
                                result_for_display = json.dumps(
                                    fallback_obj, ensure_ascii=False, indent=2
                                )
                                result_for_context = json.dumps(
                                    fallback_obj, ensure_ascii=False
                                )
                                lightweight_json_wrap_used = True
                            try:
                                if not used_lightweight_fallback:
                                    parsed_json = json.loads(raw_result)
                                    result_for_display = json.dumps(
                                        parsed_json, ensure_ascii=False, indent=2
                                    )
                                    result_for_context = json.dumps(
                                        parsed_json, ensure_ascii=False
                                    )
                            except Exception:
                                self.logger.warning(
                                    "analysis_data returned non-JSON output, retrying with strict JSON constraints. "
                                    "type=%s len=%d request_id=%s",
                                    analysis_type,
                                    len(raw_result),
                                    request_id,
                                )
                                strict_retry_prompt = (
                                    f"{analysis_user_prompt}\n\n"
                                    "CRITICAL OUTPUT CONSTRAINT:\n"
                                    "Return ONLY valid JSON (object or array). Do NOT include any text, markdown, "
                                    "code fences, explanations, or reasoning."
                                )
                                strict_retry_max_tokens = max(max_tokens, 1200)
                                strict_retry_result = self.ai_handler.send_request(
                                    system_prompt=analysis_system_prompt,
                                    user_prompt=strict_retry_prompt,
                                    request_format="text",
                                    operation=f"analysis_data_tool_{analysis_type}_strict_json_retry",
                                    max_tokens=strict_retry_max_tokens,
                                )
                                strict_json_retry_used = True

                                if strict_retry_result is not None:
                                    strict_raw = (
                                        strict_retry_result
                                        if isinstance(strict_retry_result, str)
                                        else str(strict_retry_result)
                                    )
                                    try:
                                        parsed_json = json.loads(strict_raw)
                                        result_for_display = json.dumps(
                                            parsed_json, ensure_ascii=False, indent=2
                                        )
                                        result_for_context = json.dumps(
                                            parsed_json, ensure_ascii=False
                                        )
                                    except Exception:
                                        strict_json_fallback_used = True
                                        fallback_obj = {
                                            "error": "analysis_data_invalid_json_response",
                                            "analysis_type": analysis_type,
                                            "output_format": output_format,
                                            "raw_response": strict_raw[:1200],
                                        }
                                        result_for_display = json.dumps(
                                            fallback_obj, ensure_ascii=False, indent=2
                                        )
                                        result_for_context = json.dumps(
                                            fallback_obj, ensure_ascii=False
                                        )
                                else:
                                    strict_json_fallback_used = True
                                    fallback_obj = {
                                        "error": "analysis_data_invalid_json_response",
                                        "analysis_type": analysis_type,
                                        "output_format": output_format,
                                        "raw_response": raw_result[:1200],
                                    }
                                    result_for_display = json.dumps(
                                        fallback_obj, ensure_ascii=False, indent=2
                                    )
                                    result_for_context = json.dumps(
                                        fallback_obj, ensure_ascii=False
                                    )
                        elif output_format == "number":
                            extracted_number = self._extract_first_number(raw_result)
                            if extracted_number is None:
                                number_fallback_note = (
                                    "Expected numeric output but received non-numeric text. "
                                    "Using raw response as fallback."
                                )
                            else:
                                result_for_display = extracted_number
                                result_for_context = extracted_number

                        terminal.print_console(
                            f"\n[OK] analysis_data completed (type={analysis_type}, format={output_format})."
                        )
                        terminal.print_console(f"\n{result_for_display}")
                        if number_fallback_note:
                            terminal.print_console(f"[WARN] {number_fallback_note}")
                        if strict_json_fallback_used:
                            terminal.print_console(
                                "[WARN] analysis_data did not return valid JSON after strict retry. "
                                "Stored fallback JSON object."
                            )
                        if lightweight_json_wrap_used:
                            terminal.print_console(
                                "[WARN] Wrapped lightweight text fallback into JSON object."
                            )
                        if used_lightweight_fallback:
                            terminal.print_console(
                                "[WARN] Used lightweight calculate fallback due to empty primary response."
                            )
                        if used_local_calculate_fallback:
                            terminal.print_console(
                                "[WARN] Used local calculate fallback due to repeated empty AI responses."
                            )

                        feedback_lines = [
                            f"analysis_data completed successfully.",
                            f"Type: {analysis_type}",
                            f"Output format: {output_format}",
                        ]
                        if max_tokens != requested_max_tokens:
                            feedback_lines.append(
                                f"Adjusted max_tokens from {requested_max_tokens} to {max_tokens} to ensure usable output."
                            )
                        if number_fallback_note:
                            feedback_lines.append(number_fallback_note)
                        if strict_json_retry_used:
                            feedback_lines.append(
                                "A strict JSON retry was performed because the initial response was not valid JSON."
                            )
                        if strict_json_fallback_used:
                            feedback_lines.append(
                                "Strict JSON retry still produced invalid output; fallback JSON object was generated."
                            )
                        if lightweight_json_wrap_used:
                            feedback_lines.append(
                                "Lightweight text fallback output was wrapped into JSON for compatibility."
                            )
                        if used_lightweight_fallback:
                            feedback_lines.append(
                                "Primary calculate call returned empty output; lightweight text fallback was used."
                            )
                        if used_local_calculate_fallback:
                            feedback_lines.append(
                                "Both AI calculate attempts returned empty output; local calculate fallback was used."
                            )
                        feedback_lines.append(f"Result:\n{result_for_context}")
                        analysis_feedback = "\n".join(feedback_lines)

                        analysis_feedback_compact = compress_prompt(analysis_feedback)
                        self._log_prompt_filter_savings(
                            analysis_feedback, analysis_feedback_compact
                        )
                        self.context_manager.add_user_message(analysis_feedback_compact)
                        self._update_plan_progress(
                            f"analysis_data: {analysis_type} ({output_format})",
                            success=True,
                        )
                        self.logger.info(
                            "analysis_data completed: type=%s format=%s request_id=%s",
                            analysis_type,
                            output_format,
                            request_id,
                        )
                        continue

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
                        
                        # Start timing file read operation
                        read_timing_id = self._start_timing(f"FILE_READ_{file_path}")
                        
                        result = self.file_operator.read_file(file_path, start_line or None, end_line or None, explain)
                        if result.get("success"):
                            # End timing file read operation
                            self._end_timing(read_timing_id, f"FILE_READ_{file_path}", True)
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
                        
                        result = self.file_operator.list_directory(dir_path, recursive, pattern or None, explain)
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

                    elif tool == "search_in_file":
                        file_path = action_item.get("path")
                        query = action_item.get("query")
                        context_lines = action_item.get("context_lines", 3)
                        max_results = action_item.get("max_results", 10)
                        explain = action_item.get("explain", "")
                        
                        if not file_path or not query:
                            terminal.print_console(f"Missing 'path' or 'query' in search_in_file action: {action_item}. Skipping.")
                            self.context_manager.add_user_message(f"You provided a 'search_in_file' tool action but missing 'path' or 'query': {action_item}. I am skipping it.")
                            continue
                        
                        if not terminal.auto_accept:
                            confirm_prompt_text = f"\nVaultAI> Agent suggests to search in file '{file_path}' for '{query}'. This is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nVaultAI> Provide justification for refusing and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nVaultAI> Search operation refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to search in file '{file_path}' with justification: {justification}. Based on this, what should be the next step?")
                                continue
                        
                        # Start timing search operation
                        search_timing_id = self._start_timing(f"FILE_SEARCH_{file_path}")
                        
                        result = self.file_operator.search_in_file(file_path, query, context_lines, max_results, explain)
                        if result.get("success"):
                            # End timing search operation
                            self._end_timing(search_timing_id, f"FILE_SEARCH_{file_path}", True)
                            matches = result.get("matches", [])
                            total_matches = result.get("total_matches", 0)
                            
                            terminal.print_console(f"\n[OK] Search in '{file_path}' completed ({total_matches} matches found).")
                            
                            # Format search results for display
                            feedback = f"Search results in '{file_path}' for '{query}':\n\n"
                            feedback += f"Total matches: {total_matches}\n\n"
                            
                            if matches:
                                for i, match in enumerate(matches, 1):
                                    feedback += f"Match {i} (Line {match['line_number']}):\n"
                                    feedback += f"  Content: {match['content']}\n"
                                    if match.get('context_before'):
                                        feedback += f"  Before: {match['context_before']}\n"
                                    if match.get('context_after'):
                                        feedback += f"  After: {match['context_after']}\n"
                                    feedback += "\n"
                            
                            self._update_plan_progress(f"Search in file: {file_path} for '{query}'", success=True)
                            self.context_manager.add_user_message(feedback)
                        else:
                            error = result.get("error", "Unknown error")
                            terminal.print_console(f"\n[ERROR] Failed to search in file '{file_path}': {error}")
                            self._update_plan_progress(f"Failed to search in file: {file_path}", success=False)
                            self.context_manager.add_user_message(f"Failed to search in file '{file_path}': {error}")
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
                        
                        # Check if plan exists before attempting to update
                        if not self.plan_manager.steps:
                            terminal.print_console(f"[WARN] No action plan exists. Cannot update step {step_number}.")
                            self.context_manager.add_user_message(
                                f"You tried to update plan step {step_number}, but no action plan exists. "
                                f"Create a plan first using the 'create_action_plan' tool, or proceed without a plan."
                            )
                            continue
                        
                        # Update the plan step
                        success = self.plan_manager.mark_step_status(step_number, step_status, result)
                        if success:
                            terminal.print_console(f"[OK] Plan step {step_number} marked as {status}")
                            self.context_manager.add_user_message(f"Plan step {step_number} successfully marked as {status}. Result: {result}")
                            # Display updated plan
                            self.plan_manager.display_compact()
                        else:
                            terminal.print_console(f"[WARN] Failed to update plan step {step_number}. Step may not exist in the plan.")
                            self.context_manager.add_user_message(f"Failed to update plan step {step_number}. Step may not exist in the plan.")
                        continue

                    elif tool == "web_search_agent":
                        # Web search agent tool for internet research
                        query = action_item.get("query")
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
                            effective_engine = (
                                self.web_search_agent.config.get("engine") if self.web_search_agent else "duckduckgo"
                            )
                            confirm_prompt_text = f"\nVaultAI> Agent suggests to search web for: '{query}' using {effective_engine}. This is intended to: {explain}. Proceed? [y/N]: "
                            confirm = self._get_user_input(f"{confirm_prompt_text}", multiline=False).lower().strip()
                            if confirm != 'y':
                                justification = self._get_user_input(f"\nVaultAI> Provide justification for refusing the search and press Ctrl+S to submit.\n{self.input_text}>  ", multiline=True).strip()
                                terminal.print_console(f"\nVaultAI> Web search refused by user. Justification: {justification}\n")
                                self.context_manager.add_user_message(f"User refused to search for '{query}' with justification: {justification}. Based on this, what should be the next step?")
                                continue
                        
                        terminal.print_console(f"\nVaultAI> Executing web search: {query}")
                        try:
                            effective_engine = (
                                self.web_search_agent.config.get("engine") if self.web_search_agent else "duckduckgo"
                            )
                            self.logger.info("Executing web search: query='%s', engine=%s; request_id=%s", query, effective_engine, request_id)
                        except Exception:
                            pass
                        
                        # Start timing web search operation
                        search_timing_id = self._start_timing(f"WEB_SEARCH_{query[:50]}")
                        
                        try:
                            # Use singleton WebSearchAgent (initialized in __init__)
                            search_result = self.web_search_agent.execute(
                                query=query,
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
                                
                                # End timing web search operation
                                self._end_timing(search_timing_id, f"WEB_SEARCH_{query[:50]}", True)
                                
                                # Update plan progress
                                self._update_plan_progress(f"Web search: {query}", success=True)
                                
                                self.context_manager.add_user_message(result_text)
                            else:
                                # End timing web search operation (failed)
                                self._end_timing(search_timing_id, f"WEB_SEARCH_{query[:50]}", False)
                                
                                error_msg = search_result.get('summary', 'Unknown error')
                                terminal.print_console(f"\n[ERROR] Web search failed: {error_msg}")
                                self._update_plan_progress(f"Web search failed: {query}", success=False)
                                self.context_manager.add_user_message(f"Web search for '{query}' failed: {error_msg}. Try an alternative approach.")
                                
                        except Exception as e:
                            import traceback
                            error_msg = f"Web search exception: {e}\nStack trace: {traceback.format_exc()}"
                            # End timing web search operation (exception)
                            self._end_timing(search_timing_id, f"WEB_SEARCH_{query[:50]}", False)
                            
                            terminal.print_console(f"\n[ERROR] Web search exception: {e}")
                            self.logger.error(error_msg)
                            self._update_plan_progress(f"Web search error: {query}", success=False)
                            self.context_manager.add_user_message(f"Web search for '{query}' encountered an error: {str(e)}. Try an alternative approach.")
                        continue

                    else: 
                        terminal.print_console(f"AI response contained an invalid 'tool': '{tool}' in action: {action_item}.")
                        user_feedback_invalid_tool = (
                            f"Your response included an action with an invalid tool: '{tool}' in {action_item}. "
                            f"Valid tools are: 'create_action_plan', 'bash', 'read_file', 'write_file', "
                            f"'edit_file', 'list_directory', 'search_in_file', 'copy_file', 'delete_file', "
                            f"'analysis_data', 'update_plan_step', 'ask_user', 'web_search_agent', and 'finish'. "
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
                #self.terminal.print_console("\nFinal Action Plan:")
                #self.plan_manager.display_plan(show_details=True)
                
                continue_choice = self._get_user_input("\nVaultAI> Do you want continue this thread? [y/N]: ", multiline=False).lower().strip()
                if continue_choice == 'y':
                    terminal.console.print("\nVaultAI> Prompt your next goal and press [cyan]Ctrl+S[/] to start!")
                    user_input = self._get_user_input(f"{self.input_text}> ", multiline=True)
                    new_instruction = terminal.process_input(user_input)

                    # Preserve completed plan history in context before clearing
                    completed_plan_context = self.plan_manager.get_context_for_ai()
                    self.context_manager.add_system_message(
                        f"[COMPLETED TASK]\n"
                        f"Goal: {self.user_goal}\n"
                        f"Summary: {self.summary}\n"
                        f"Plan that was executed:\n{completed_plan_context}\n"
                        f"[END COMPLETED TASK]\n\n"
                        f"The above task was fully completed. Now proceed with the new instruction."
                    )
                    self.context_manager.add_user_message(f"New instruction: {new_instruction}")

                    self.steps = []
                    self.summary = ""
                    self.critic_rating = 0
                    self.critic_verdict = ""
                    self.critic_rationale = ""
                    # Update the goal and reset plan for the new task
                    self.user_goal = new_instruction
                    self.plan_manager.clear()
                    # Create a new plan for the new goal
                    #self._initialize_plan()
                    # Continue the while loop
                else:
                    keep_running = False
            else:
                # If the loop broke for any other reason (error, user cancellation), stop.
                keep_running = False

        # Display comprehensive performance summary at the end of each task
        if self.show_performance_summary and (
            self.timings
            or (hasattr(self.ai_handler, 'token_usage') and self.ai_handler.token_usage)
        ):
            self.terminal.print_console("\n" + "="*60)
            self.terminal.print_console("PERFORMANCE SUMMARY")
            self.terminal.print_console("="*60)
            
            # Display cost optimization recommendations
            if hasattr(self.ai_handler, 'token_usage') and self.ai_handler.token_usage:
                self._display_cost_optimization_recommendations()
            
            # Display timing summary
            if self.timings:
                self._display_timing_summary()
            
            # Display token usage summary
            if hasattr(self.ai_handler, 'token_usage') and self.ai_handler.token_usage:
                self._display_token_summary()
            
            # Display prompt filter summary
            self._display_prompt_filter_summary()
            
            # Display summarize operations summary
            self._display_summarize_stats_summary()
            
            # Display plan summary if available
            if self.plan_manager.steps:
                self.terminal.print_console("\n" + "="*60)
                self.terminal.print_console("TASK COMPLETION SUMMARY")
                self.terminal.print_console("="*60)
                progress = self.plan_manager.get_progress()
                self.terminal.print_console(f"Plan Progress: {progress['completed']}/{progress['total']} steps completed ({progress['percentage']}%)")
                if progress['failed'] > 0:
                    self.terminal.print_console(f"Failed Steps: {progress['failed']}")
                if progress['skipped'] > 0:
                    self.terminal.print_console(f"Skipped Steps: {progress['skipped']}")
                if progress['pending'] > 0:
                    self.terminal.print_console(f"Pending Steps: {progress['pending']}")
            
            self.terminal.print_console("="*60)
