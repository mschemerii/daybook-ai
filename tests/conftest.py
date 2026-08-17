import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from src.repositories.database import Database
from src.repositories.dependency_repository import DependencyRepository
from src.repositories.task_repository import TaskRepository
from src.repositories.time_entry_repository import TimeEntryRepository
from src.repositories.journal_repository import JournalRepository
from src.repositories.governance_repository import GovernanceRepository
from src.services.task_service import TaskService
from src.services.time_entry_service import TimeEntryService

@pytest.fixture
def db(tmp_path): return Database(tmp_path / "test.db")
@pytest.fixture
def task_repo(db): return TaskRepository(db)
@pytest.fixture
def dependency_repo(db): return DependencyRepository(db)
@pytest.fixture
def journal_repo(db): return JournalRepository(db)
@pytest.fixture
def governance(db): return GovernanceRepository(db)
@pytest.fixture
def task_service(task_repo, dependency_repo):
    return TaskService(task_repo, dependency_repo)
@pytest.fixture
def time_entry_repo(db): return TimeEntryRepository(db)
@pytest.fixture
def time_entry_service(time_entry_repo, task_repo):
    return TimeEntryService(time_entry_repo, task_repo)
