"""
ActionPlanManager - Moduł zarządzania planem działania agenta terminalowego.

Tworzy, aktualizuje i wyświetla plan działania z możliwością śledzenia postępu.
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
    """Statusy kroków planu."""
    PENDING = "pending"         # ⬜ Oczekujący
    IN_PROGRESS = "in_progress" # ⏳ W trakcie
    COMPLETED = "completed"     # ✅ Ukończony
    FAILED = "failed"           # ❌ Nieudany
    SKIPPED = "skipped"         # ⏭️ Pominięty


@dataclass
class PlanStep:
    """Pojedynczy krok planu."""
    number: int
    description: str
    command: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    timestamp_start: Optional[str] = None
    timestamp_end: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje krok do słownika."""
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlanStep':
        """Tworzy krok ze słownika."""
        data = data.copy()
        data['status'] = StepStatus(data.get('status', 'pending'))
        return cls(**data)


class ActionPlanManager:
    """
    Klasa zarządzająca planem działania agenta terminalowego.
    
    Funkcjonalności:
    - Tworzenie planu na podstawie celu użytkownika
    - Aktualizacja statusów kroków
    - Wyświetlanie postępu
    - Zapisywanie/odczytywanie planu z pliku
    - Integracja z kontekstem AI
    """

    # Ikony statusów
    STATUS_ICONS = {
        StepStatus.PENDING: "⬜",
        StepStatus.IN_PROGRESS: "⏳",
        StepStatus.COMPLETED: "✅",
        StepStatus.FAILED: "❌",
        StepStatus.SKIPPED: "⏭️",
    }

    # Kolory dla Rich
    STATUS_COLORS = {
        StepStatus.PENDING: "white",
        StepStatus.IN_PROGRESS: "yellow",
        StepStatus.COMPLETED: "green",
        StepStatus.FAILED: "red",
        StepStatus.SKIPPED: "dim",
    }

    def __init__(self, terminal=None, ai_handler=None, plan_file: Optional[str] = None):
        """
        Inicjalizacja managera planu.
        
        Args:
            terminal: Obiekt terminala do wyświetlania (opcjonalny)
            ai_handler: Handler do komunikacji z AI (opcjonalny)
            plan_file: Ścieżka do pliku planu (opcjonalna)
        """
        self.terminal = terminal
        self.ai_handler = ai_handler
        self.plan_file = plan_file
        self.steps: List[PlanStep] = []
        self.goal: Optional[str] = None
        self.created_at: Optional[str] = None
        self.updated_at: Optional[str] = None
        self.console = Console() if terminal is None else terminal.console
        
        # Jeśli podano plik planu, spróbuj go wczytać
        if plan_file and os.path.exists(plan_file):
            self.load_from_file(plan_file)

    def create_plan(self, goal: str, steps_data: List[Dict[str, Any]]) -> List[PlanStep]:
        """
        Tworzy nowy plan działania.
        
        Args:
            goal: Cel użytkownika
            steps_data: Lista słowników z danymi kroków (description, command opcjonalnie)
            
        Returns:
            Lista utworzonych kroków
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
        
        self._log(f"Utworzono plan z {len(self.steps)} krokami dla celu: {goal}")
        return self.steps

    def create_plan_with_ai(self, goal: str, system_prompt: Optional[str] = None) -> List[PlanStep]:
        """
        Tworzy plan działania z pomocą AI.
        
        Args:
            goal: Cel użytkownika
            system_prompt: Opcjonalny prompt systemowy dla AI
            
        Returns:
            Lista utworzonych kroków
        """
        if self.ai_handler is None:
            raise ValueError("AI handler nie został podany podczas inicjalizacji")
        
        default_prompt = (
            "Jesteś planerem zadań. Na podstawie celu użytkownika stwórz szczegółowy plan działania. "
            "Zwróć odpowiedź w formacie JSON z listą kroków. "
            "Każdy krok powinien mieć pola: 'description' (opis) i opcjonalnie 'command' (polecenie do wykonania). "
            "Odpowiedź musi być w formacie: {'steps': [{'description': '...', 'command': '...'}, ...]}"
        )
        
        prompt = system_prompt or default_prompt
        user_prompt = f"Stwórz plan działania dla następującego celu: {goal}"
        
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
                self._log("Błąd: Brak odpowiedzi od AI", level="error")
                return []
                
        except Exception as e:
            self._log(f"Błąd podczas tworzenia planu z AI: {e}", level="error")
            return []

    def mark_step_status(self, step_number: int, status: StepStatus, result: Optional[str] = None) -> bool:
        """
        Zmienia status kroku planu.
        
        Args:
            step_number: Numer kroku (1-based)
            status: Nowy status
            result: Opcjonalny wynik/wiadomość
            
        Returns:
            True jeśli zaktualizowano, False jeśli krok nie istnieje
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
                self._log(f"Krok {step_number}: {status.value}")
                return True
        
        self._log(f"Krok {step_number} nie istnieje", level="warning")
        return False

    def mark_step_done(self, step_number: int, result: Optional[str] = None) -> bool:
        """Oznacza krok jako ukończony."""
        return self.mark_step_status(step_number, StepStatus.COMPLETED, result)

    def mark_step_in_progress(self, step_number: int) -> bool:
        """Oznacza krok jako w trakcie wykonywania."""
        return self.mark_step_status(step_number, StepStatus.IN_PROGRESS)

    def mark_step_failed(self, step_number: int, error_message: Optional[str] = None) -> bool:
        """Oznacza krok jako nieudany."""
        return self.mark_step_status(step_number, StepStatus.FAILED, error_message)

    def mark_step_skipped(self, step_number: int, reason: Optional[str] = None) -> bool:
        """Oznacza krok jako pominięty."""
        return self.mark_step_status(step_number, StepStatus.SKIPPED, reason)

    def get_next_pending_step(self) -> Optional[PlanStep]:
        """Zwraca pierwszy oczekujący krok."""
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                return step
        return None

    def get_current_step(self) -> Optional[PlanStep]:
        """Zwraca krok aktualnie w trakcie wykonywania."""
        for step in self.steps:
            if step.status == StepStatus.IN_PROGRESS:
                return step
        return None

    def get_progress(self) -> Dict[str, int]:
        """Zwraca statystyki postępu planu."""
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
        Wyświetla plan działania w formie tabeli.
        
        Args:
            show_details: Czy pokazać szczegóły (komendy, wyniki)
        """
        if not self.steps:
            self.console.print("[yellow]Plan jest pusty.[/]")
            return
        
        # Nagłówek z celem
        header = f"📋 Plan działania: {self.goal or 'Brak celu'}"
        self.console.print(f"\n[bold cyan]{header}[/]")
        self.console.print("━" * min(len(header) + 5, 80))
        
        # Tabela kroków
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Status", width=4)
        table.add_column("Nr", width=4, justify="right")
        table.add_column("Opis", min_width=40)
        
        if show_details:
            table.add_column("Komenda", min_width=20)
            table.add_column("Wynik", min_width=20)
        
        for step in self.steps:
            icon = self.STATUS_ICONS.get(step.status, "⬜")
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
        
        # Pasek postępu
        progress = self.get_progress()
        bar_width = 40
        filled = int((progress['completed'] / progress['total']) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        self.console.print(f"\n[bold]Postęp:[/] [{bar}] {progress['percentage']}%")
        self.console.print(f"[green]✓ {progress['completed']} ukończone[/] | "
                          f"[red]✗ {progress['failed']} nieudane[/] | "
                          f"[yellow]⏳ {progress['in_progress']} w trakcie[/] | "
                          f"[white]⬜ {progress['pending']} oczekujące[/]")
        self.console.print()

    def display_compact(self):
        """Wyświetla skrócony widok planu (tylko postęp)."""
        progress = self.get_progress()
        if progress['total'] == 0:
            return
        
        bar_width = 20
        filled = int((progress['completed'] / progress['total']) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        self.console.print(f"[dim]Plan: [{bar}] {progress['completed']}/{progress['total']} ({progress['percentage']}%)[/]")

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje cały plan do słownika."""
        return {
            "goal": self.goal,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": [step.to_dict() for step in self.steps]
        }

    def from_dict(self, data: Dict[str, Any]):
        """Wczytuje plan ze słownika."""
        self.goal = data.get('goal')
        self.created_at = data.get('created_at')
        self.updated_at = data.get('updated_at')
        self.steps = [PlanStep.from_dict(s) for s in data.get('steps', [])]

    def to_json(self) -> str:
        """Zwraca plan jako JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save_to_file(self, filepath: Optional[str] = None) -> bool:
        """
        Zapisuje plan do pliku JSON.
        
        Args:
            filepath: Ścieżka do pliku (jeśli None, używa self.plan_file)
            
        Returns:
            True jeśli zapisano pomyślnie
        """
        filepath = filepath or self.plan_file
        if not filepath:
            self._log("Brak ścieżki do pliku", level="error")
            return False
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            self._log(f"Plan zapisano do: {filepath}")
            return True
        except Exception as e:
            self._log(f"Błąd zapisu planu: {e}", level="error")
            return False

    def load_from_file(self, filepath: Optional[str] = None) -> bool:
        """
        Wczytuje plan z pliku JSON.
        
        Args:
            filepath: Ścieżka do pliku (jeśli None, używa self.plan_file)
            
        Returns:
            True jeśli wczytano pomyślnie
        """
        filepath = filepath or self.plan_file
        if not filepath or not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.from_dict(data)
            self.plan_file = filepath
            self._log(f"Plan wczytano z: {filepath}")
            return True
        except Exception as e:
            self._log(f"Błąd wczytywania planu: {e}", level="error")
            return False

    def get_context_for_ai(self) -> str:
        """
        Generuje tekstowy opis planu dla kontekstu AI.
        
        Returns:
            String z opisem planu gotowym do wysłania do AI
        """
        lines = ["Aktualny plan działania:"]
        lines.append(f"Cel: {self.goal or 'Nieokreślony'}")
        lines.append("")
        
        for step in self.steps:
            icon = self.STATUS_ICONS.get(step.status, "⬜")
            status_text = step.status.value.upper()
            lines.append(f"{icon} Krok {step.number}: {step.description} [{status_text}]")
            if step.command:
                lines.append(f"   Komenda: {step.command}")
            if step.result:
                lines.append(f"   Wynik: {step.result[:200]}..." if len(str(step.result)) > 200 else f"   Wynik: {step.result}")
        
        progress = self.get_progress()
        lines.append("")
        lines.append(f"Postęp: {progress['completed']}/{progress['total']} ({progress['percentage']}%)")
        
        return "\n".join(lines)

    def add_step(self, description: str, command: Optional[str] = None, position: Optional[int] = None) -> PlanStep:
        """
        Dodaje nowy krok do planu.
        
        Args:
            description: Opis kroku
            command: Opcjonalna komenda
            position: Pozycja wstawienia (None = na końcu)
            
        Returns:
            Utworzony krok
        """
        if position is None:
            number = len(self.steps) + 1
        else:
            number = position
            # Przenumeruj pozostałe kroki
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
        
        self._log(f"Dodano krok {number}: {description}")
        return step

    def remove_step(self, step_number: int) -> bool:
        """
        Usuwa krok z planu.
        
        Args:
            step_number: Numer kroku do usunięcia
            
        Returns:
            True jeśli usunięto
        """
        for i, step in enumerate(self.steps):
            if step.number == step_number:
                self.steps.pop(i)
                # Przenumeruj pozostałe
                for s in self.steps:
                    if s.number > step_number:
                        s.number -= 1
                self.updated_at = datetime.now().isoformat()
                self._log(f"Usunięto krok {step_number}")
                return True
        return False

    def clear(self):
        """Czyści cały plan."""
        self.steps = []
        self.goal = None
        self.created_at = None
        self.updated_at = None
        self._log("Plan wyczyszczony")

    def _log(self, message: str, level: str = "info"):
        """Wewnętrzne logowanie."""
        if self.terminal and hasattr(self.terminal, 'logger'):
            logger = getattr(self.terminal, 'logger')
            if hasattr(logger, level):
                getattr(logger, level)(f"[ActionPlanManager] {message}")


# Funkcje pomocnicze dla szybkiego tworzenia planu

def create_simple_plan(goal: str, steps_descriptions: List[str]) -> List[Dict[str, Any]]:
    """
    Tworzy prostą listę kroków z opisów.
    
    Args:
        goal: Cel planu
        steps_descriptions: Lista opisów kroków
        
    Returns:
        Lista słowników gotowa do użycia w create_plan
    """
    return [{"description": desc} for desc in steps_descriptions]


# Przykład użycia
if __name__ == "__main__":
    # Przykładowe użycie
    manager = ActionPlanManager()
    
    # Tworzenie planu
    steps = [
        {"description": "Zaktualizować listę pakietów", "command": "apt update"},
        {"description": "Zainstalować Nginx", "command": "apt install nginx -y"},
        {"description": "Uruchomić usługę Nginx", "command": "systemctl start nginx"},
        {"description": "Włączyć autostart", "command": "systemctl enable nginx"},
        {"description": "Sprawdzić status", "command": "systemctl status nginx"},
    ]
    
    manager.create_plan("Instalacja serwera Nginx", steps)
    
    # Wyświetlenie początkowe
    manager.display_plan()
    
    # Symulacja wykonywania
    import time
    for step in manager.steps[:3]:
        manager.mark_step_in_progress(step.number)
        manager.display_compact()
        time.sleep(0.5)
        manager.mark_step_done(step.number, f"Wykonano pomyślnie")
        time.sleep(0.3)
    
    # Wyświetlenie końcowe
    manager.display_plan(show_details=True)
    
    # Zapis do pliku
    manager.save_to_file("/tmp/test_plan.json")
    print("\nKontekst dla AI:")
    print(manager.get_context_for_ai())
