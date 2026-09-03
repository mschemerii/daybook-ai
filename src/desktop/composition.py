from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.agent.local_llm import LocalModelClient
from src.repositories.database import Database
from src.repositories.dependency_repository import DependencyRepository
from src.repositories.governance_repository import GovernanceRepository
from src.repositories.journal_repository import JournalRepository
from src.repositories.planning_repository import PlanningRepository
from src.repositories.reporting_repository import ReportingRepository
from src.repositories.reporting_settings_repository import ReportingSettingsRepository
from src.repositories.task_repository import TaskRepository
from src.repositories.time_entry_repository import TimeEntryRepository
from src.services.context_service import ContextService
from src.services.planning_service import PlanningService
from src.services.reporting_service import ReportingService
from src.services.report_export_service import ReportExportService
from src.services.task_service import TaskService
from src.services.time_entry_service import TimeEntryService


@dataclass(frozen=True, slots=True)
class DesktopCompositionConfig:
    """Environment-resolved inputs for one desktop application composition."""

    project_root: Path
    database_path: Path
    preferences_path: Path
    seed_demo: bool
    model_base_url: str
    model_name: str
    model_api_key: str

    @classmethod
    def from_environment(cls, project_root: Path) -> "DesktopCompositionConfig":
        project_root = project_root.resolve()
        load_dotenv(project_root / ".env")

        database_path = _resolve_local_path(
            project_root,
            os.getenv("DAYBOOK_DB_PATH", "data/daybook.db"),
        )
        preferences_path = _resolve_local_path(
            project_root,
            os.getenv("DAYBOOK_PREFERENCES_PATH", ".daybook-preferences.json"),
        )
        seed_demo = os.getenv("DAYBOOK_SEED_DEMO", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        return cls(
            project_root=project_root,
            database_path=database_path,
            preferences_path=preferences_path,
            seed_demo=seed_demo,
            model_base_url=os.getenv(
                "DAYBOOK_MODEL_BASE_URL",
                "http://127.0.0.1:8080/v1",
            ),
            model_name=os.getenv("DAYBOOK_MODEL_NAME", "auto"),
            model_api_key=os.getenv("DAYBOOK_MODEL_API_KEY", ""),
        )


def _resolve_local_path(project_root: Path, configured: str) -> Path:
    path = Path(configured).expanduser()
    if path.is_absolute():
        return path
    return (project_root / path).resolve()


@dataclass(frozen=True, slots=True)
class ShellSnapshot:
    open_tasks: int
    due_today: int
    completed_tasks: int
    journal_today: bool
    ai_status: str
    database_name: str


@dataclass(slots=True)
class DesktopServices:
    """Single composition root shared by all native desktop views."""

    database: Database
    tasks: TaskRepository
    dependencies: DependencyRepository
    time_entries: TimeEntryRepository
    journals: JournalRepository
    governance: GovernanceRepository
    planning: PlanningRepository
    reporting: ReportingRepository
    reporting_settings: ReportingSettingsRepository
    task_service: TaskService
    time_entry_service: TimeEntryService
    context_service: ContextService
    planning_service: PlanningService
    reporting_service: ReportingService
    report_export_service: ReportExportService
    model: LocalModelClient

    def shell_snapshot(self, *, today: date | None = None) -> ShellSnapshot:
        """Read a small deterministic shell summary without invoking the model."""
        selected_date = today or date.today()
        open_tasks = self.tasks.list_all(include_completed=False)
        due_today = self.task_service.due_today(selected_date)
        completed_tasks = self.task_service.completed()
        verified = os.getenv("DAYBOOK_LLM_VERIFIED", "").strip().lower()
        if verified == "true":
            ai_status = "Ready"
        elif verified == "false":
            ai_status = "Unavailable"
        else:
            ai_status = "Not checked"
        return ShellSnapshot(
            open_tasks=len(open_tasks),
            due_today=len(due_today),
            completed_tasks=len(completed_tasks),
            journal_today=self.journals.get(selected_date) is not None,
            ai_status=ai_status,
            database_name=self.database.path.name,
        )


def build_desktop_services(config: DesktopCompositionConfig) -> DesktopServices:
    """Build repositories and services once for the native desktop process."""
    database = Database(config.database_path, seed_demo=config.seed_demo)
    tasks = TaskRepository(database)
    dependencies = DependencyRepository(database)
    time_entries = TimeEntryRepository(database)
    journals = JournalRepository(database)
    governance = GovernanceRepository(database)
    planning = PlanningRepository(database)
    reporting = ReportingRepository(database)
    reporting_settings = ReportingSettingsRepository(database)
    model = LocalModelClient(
        config.model_base_url,
        config.model_name,
        api_key=config.model_api_key,
    )
    task_service = TaskService(tasks, dependencies)

    return DesktopServices(
        database=database,
        tasks=tasks,
        dependencies=dependencies,
        time_entries=time_entries,
        journals=journals,
        governance=governance,
        planning=planning,
        reporting=reporting,
        reporting_settings=reporting_settings,
        task_service=task_service,
        time_entry_service=TimeEntryService(time_entries, tasks),
        context_service=ContextService(tasks, journals),
        planning_service=PlanningService(task_service, planning, model),
        reporting_service=ReportingService(reporting),
        report_export_service=ReportExportService(),
        model=model,
    )
