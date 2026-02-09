"""
ActionPlanManager - Task planning module for the terminal AI agent.

Creates, updates, and displays action plans with progress tracking.
"""

import json
import os
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box


class StepStatus(Enum):
    """Plan step statuses."""
    PENDING = "pending"         # ⬜ Pending
    IN_PROGRESS = "in_progress" # ⏳ In progress
    COMPLETED = "completed"     # ✅ Completed
    FAILED = "failed"           # ❌ Failed
    SKIPPED = "skipped"         # ⏭️ Skipped


@dataclass
class PlanStep:
    """Single plan step."""
    number: int
    description: str
    command: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    timestamp_start: Optional[str] = None
    timestamp_end: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary."""
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlanStep':
        """Create step from dictionary."""
        data = data.copy()
        data['status'] = StepStatus(data.get('status', 'pending'))
        return cls(**data)


class ActionPlanManager:
    """
    Class for managing the terminal AI agent's action plan.
    
    Features:
    - Creating a plan based on user goal
    - Updating step statuses
    - Displaying progress
    - Saving/loading plan to/from file
    - Integration with AI context
    """

    # Status icons (text-based)
    STATUS_ICONS = {
        StepStatus.PENDING: "[ ]",
        StepStatus.IN_PROGRESS: "[~]",
        StepStatus.COMPLETED: "[X]",
        StepStatus.FAILED: "[!]",
        StepStatus.SKIPPED: ">",
    }

    # Colors for Rich
    STATUS_COLORS = {
        StepStatus.PENDING: "white",
        StepStatus.IN_PROGRESS: "yellow",
        StepStatus.COMPLETED: "green",
        StepStatus.FAILED: "red",
        StepStatus.SKIPPED: "dim",
    }

    def __init__(self, terminal=None, ai_handler=None, plan_file: Optional[str] = None):
        """
        Initialize plan manager.
        
        Args:
            terminal: Terminal object for display (optional)
            ai_handler: Handler for AI communication (optional)
            plan_file: Path to plan file (optional)
        """
        self.terminal = terminal
        self.ai_handler = ai_handler
        self.plan_file = plan_file
        self.steps: List[PlanStep] = []
        self.goal: Optional[str] = None
        self.created_at: Optional[str] = None
        self.updated_at: Optional[str] = None
        self.console = Console() if terminal is None else terminal.console
        
        # If plan file is provided, try to load it
        if plan_file and os.path.exists(plan_file):
            self.load_from_file(plan_file)

    def create_plan(self, goal: str, steps_data: List[Dict[str, Any]]) -> List[PlanStep]:
        """
        Create a new action plan.
        
        Args:
            goal: User goal
            steps_data: List of dictionaries with step data (description, command optional)
            
        Returns:
            List of created steps
        """
        self.goal = goal
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.steps = []
        
        for idx, step_data in enumerate(steps_data, start=1):
            step = PlanStep(
                number=idx,
                description=step_data.get('description', ''),
                command=step_data.get('command'),
                status=StepStatus.PENDING
            )
            self.steps.append(step)
        
        self._log(f"Created plan with {len(self.steps)} steps for goal: {goal}")
        return self.steps

    def create_plan_with_ai(self, goal: str, system_prompt: Optional[str] = None) -> List[PlanStep]:
        """
        Create action plan with AI assistance.
        
        Args:
            goal: User goal
            system_prompt: Optional system prompt for AI
            
        Returns:
            List of created steps
        """
        if self.ai_handler is None:
            raise ValueError("AI handler was not provided during initialization")
        
        default_prompt = (
            "You are a task planner. Based on the user's goal, create a detailed action plan. "
            "Return response in JSON format with list of steps. "
            "Each step should have fields: 'description' and optionally 'command'. "
            "Response must be in format: {'steps': [{'description': '...', 'command': '...'}, ...]}"
        )
        
        prompt = system_prompt or default_prompt
        user_prompt = f"Create an action plan for the following goal: {goal}"
        
        try:
            response = self.ai_handler.send_request(
                system_prompt=prompt,
                user_prompt=user_prompt,
                request_format="json"
            )
            
            if response:
                data = json.loads(response)
                steps_data = data.get('steps', [])
                return self.create_plan(goal, steps_data)
            else:
                self._log("Error: No response from AI", level="error")
                return []
                
        except Exception as e:
            self._log(f"Error creating plan with AI: {e}", level="error")
            return []

    def mark_step_status(self, step_number: int, status: StepStatus, result: Optional[str] = None) -> bool:
        """
        Change plan step status.
        
        Args:
            step_number: Step number (1-based)
            status: New status
            result: Optional result/message
            
        Returns:
            True if updated, False if step doesn't exist
        """
        for step in self.steps:
            if step.number == step_number:
                step.status = status
                
                if status == StepStatus.IN_PROGRESS:
                    step.timestamp_start = datetime.now().isoformat()
                elif status in [StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED]:
                    step.timestamp_end = datetime.now().isoformat()
                
                if result:
                    step.result = result
                
                self.updated_at = datetime.now().isoformat()
                self._log(f"Step {step_number}: {status.value}")
                return True
        
        self._log(f"Step {step_number} does not exist", level="warning")
        return False

    def mark_step_done(self, step_number: int, result: Optional[str] = None) -> bool:
        """Mark step as completed."""
        return self.mark_step_status(step_number, StepStatus.COMPLETED, result)

    def mark_step_in_progress(self, step_number: int) -> bool:
        """Mark step as in progress."""
        return self.mark_step_status(step_number, StepStatus.IN_PROGRESS)

    def mark_step_failed(self, step_number: int, error_message: Optional[str] = None) -> bool:
        """Mark step as failed."""
        return self.mark_step_status(step_number, StepStatus.FAILED, error_message)

    def mark_step_skipped(self, step_number: int, reason: Optional[str] = None) -> bool:
        """Mark step as skipped."""
        return self.mark_step_status(step_number, StepStatus.SKIPPED, reason)

    def get_next_pending_step(self) -> Optional[PlanStep]:
        """Return first pending step."""
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                return step
        return None

    def get_current_step(self) -> Optional[PlanStep]:
        """Return step currently in progress."""
        for step in self.steps:
            if step.status == StepStatus.IN_PROGRESS:
                return step
        return None

    def get_progress(self) -> Dict[str, int]:
        """Return plan progress statistics."""
        total = len(self.steps)
        if total == 0:
            return {"total": 0, "completed": 0, "failed": 0, "pending": 0, "in_progress": 0, "percentage": 0}
        
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in self.steps if s.status == StepStatus.FAILED)
        pending = sum(1 for s in self.steps if s.status == StepStatus.PENDING)
        in_progress = sum(1 for s in self.steps if s.status == StepStatus.IN_PROGRESS)
        percentage = int((completed / total) * 100)
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "in_progress": in_progress,
            "percentage": percentage
        }

    def display_plan(self, show_details: bool = False):
        """
        Display action plan as a table.
        
        Args:
            show_details: Whether to show details (commands, results)
        """
        if not self.steps:
            self.console.print("[yellow]Plan is empty.[/]")
            return
        
        # Header with goal
        header = f"PLAN: {self.goal or 'No goal'}"
        self.console.print(f"\n[bold cyan]{header}[/]")
        self.console.print("-" * min(len(header) + 5, 80))
        
        # Steps table
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Status", width=4)
        table.add_column("Nr", width=4, justify="right")
        table.add_column("Description", min_width=40)
        
        if show_details:
            table.add_column("Command", min_width=20)
            table.add_column("Result", min_width=20)
        
        for step in self.steps:
            icon = self.STATUS_ICONS.get(step.status, "[ ]")
            color = self.STATUS_COLORS.get(step.status, "white")
            
            row = [
                f"[{color}]{icon}[/{color}]",
                f"[{color}]{step.number}.[/{color}]",
                f"[{color}]{step.description}[/{color}]"
            ]
            
            if show_details:
                cmd = step.command or "-"
                result = step.result or "-"
                row.extend([f"[dim]{cmd}[/]", f"[dim]{result[:50]}...[/]" if len(str(result)) > 50 else f"[dim]{result}[/]"])
            
            table.add_row(*row)
        
        self.console.print(table)
        
        # Progress bar
        progress = self.get_progress()
        bar_width = 40
        filled = int((progress['completed'] / progress['total']) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        self.console.print(f"\n[bold]Progress:[/] [{bar}] {progress['percentage']}%")
        self.console.print(f"[green][OK] {progress['completed']} completed[/] | "
                          f"[red][FAIL] {progress['failed']} failed[/] | "
                          f"[yellow][~] {progress['in_progress']} in progress[/] | "
                          f"[white][ ] {progress['pending']} pending[/]")
        self.console.print()

    def display_compact(self):
        """Display compact plan view (only progress)."""
        progress = self.get_progress()
        if progress['total'] == 0:
            return
        
        bar_width = 20
        filled = int((progress['completed'] / progress['total']) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        self.console.print(f"[dim]Plan: [{bar}] {progress['completed']}/{progress['total']} ({progress['percentage']}%)[/]")

    def to_dict(self) -> Dict[str, Any]:
        """Convert entire plan to dictionary."""
        return {
            "goal": self.goal,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": [step.to_dict() for step in self.steps]
        }

    def from_dict(self, data: Dict[str, Any]):
        """Load plan from dictionary."""
        self.goal = data.get('goal')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')
        self.steps = [PlanStep.from_dict(s) for s in data.get('steps', [])]

    def to_json(self) -> str:
        """Return plan as JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save_to_file(self, filepath: Optional[str] = None) -> bool:
        """
        Save plan to JSON file.
        
        Args:
            filepath: File path (if None, uses self.plan_file)
            
        Returns:
            True if saved successfully
        """
        filepath = filepath or self.plan_file
        if not filepath:
            self._log("No file path provided", level="error")
            return False
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            self._log(f"Plan saved to: {filepath}")
            return True
        except Exception as e:
            self._log(f"Error saving plan: {e}", level="error")
            return False

    def load_from_file(self, filepath: Optional[str] = None) -> bool:
        """
        Load plan from JSON file.
        
        Args:
            filepath: File path (if None, uses self.plan_file)
            
        Returns:
            True if loaded successfully
        """
        filepath = filepath or self.plan_file
        if not filepath or not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.from_dict(data)
            self.plan_file = filepath
            self._log(f"Plan loaded from: {filepath}")
            return True
        except Exception as e:
            self._log(f"Error loading plan: {e}", level="error")
            return False

    def get_context_for_ai(self) -> str:
        """
        Generate text description of plan for AI context.
        
        Returns:
            String with plan description ready to send to AI
        """
        lines = ["Current action plan:"]
        lines.append(f"Goal: {self.goal or 'Undefined'}")
        lines.append("")
        
        for step in self.steps:
            icon = self.STATUS_ICONS.get(step.status, "[ ]")
            status_text = step.status.value.upper()
            lines.append(f"{icon} Step {step.number}: {step.description} [{status_text}]")
            if step.command:
                lines.append(f"   Command: {step.command}")
            if step.result:
                lines.append(f"   Result: {step.result[:200]}..." if len(str(step.result)) > 200 else f"   Result: {step.result}")
        
        progress = self.get_progress()
        lines.append("")
        lines.append(f"Progress: {progress['completed']}/{progress['total']} ({progress['percentage']}%)")
        
        return "\n".join(lines)

    def add_step(self, description: str, command: Optional[str] = None, position: Optional[int] = None) -> PlanStep:
        """
        Add new step to plan.
        
        Args:
            description: Step description
            command: Optional command
            position: Insert position (None = at the end)
            
        Returns:
            Created step
        """
        if position is None:
            number = len(self.steps) + 1
        else:
            number = position
            # Renumber remaining steps
            for step in self.steps:
                if step.number >= number:
                    step.number += 1
        
        step = PlanStep(
            number=number,
            description=description,
            command=command,
            status=StepStatus.PENDING
        )
        
        self.steps.append(step)
        self.steps.sort(key=lambda s: s.number)
        self.updated_at = datetime.now().isoformat()
        
        self._log(f"Added step {number}: {description}")
        return step

    def remove_step(self, step_number: int) -> bool:
        """
        Remove step from plan.
        
        Args:
            step_number: Step number to remove
            
        Returns:
            True if removed
        """
        for i, step in enumerate(self.steps):
            if step.number == step_number:
                self.steps.pop(i)
                # Renumber remaining
                for s in self.steps:
                    if s.number > step_number:
                        s.number -= 1
                self.updated_at = datetime.now().isoformat()
                self._log(f"Removed step {step_number}")
                return True
        return False

    def clear(self):
        """Clear entire plan."""
        self.steps = []
        self.goal = None
        self.created_at = None
        self.updated_at = None
        self._log("Plan cleared")

    def _log(self, message: str, level: str = "info"):
        """Internal logging."""
        if self.terminal and hasattr(self.terminal, 'logger'):
            logger = getattr(self.terminal, 'logger')
            if hasattr(logger, level):
                getattr(logger, level)(f"[ActionPlanManager] {message}")


# Helper functions for quick plan creation

def create_simple_plan(goal: str, steps_descriptions: List[str]) -> List[Dict[str, Any]]:
    """
    Create simple list of steps from descriptions.
    
    Args:
        goal: Plan goal
        steps_descriptions: List of step descriptions
        
    Returns:
        List of dictionaries ready to use in create_plan
    """
    return [{"description": desc} for desc in steps_descriptions]


# Usage example
if __name__ == "__main__":
    # Example usage
    manager = ActionPlanManager()
    
    # Create plan
    steps = [
        {"description": "Update package list", "command": "apt update"},
        {"description": "Install Nginx", "command": "apt install nginx -y"},
        {"description": "Start Nginx service", "command": "systemctl start nginx"},
        {"description": "Enable autostart", "command": "systemctl enable nginx"},
        {"description": "Check status", "command": "systemctl status nginx"},
    ]
    
    manager.create_plan("Nginx server installation", steps)
    
    # Initial display
    manager.display_plan()
    
    # Simulate execution
    import time
    for step in manager.steps[:3]:
        manager.mark_step_in_progress(step.number)
        manager.display_compact()
        time.sleep(0.5)
        manager.mark_step_done(step.number, f"Completed successfully")
        time.sleep(0.3)
    
    # Final display
    manager.display_plan(show_details=True)
    
    # Save to file
    manager.save_to_file("/tmp/test_plan.json")
    print("\nContext for AI:")
    print(manager.get_context_for_ai())
