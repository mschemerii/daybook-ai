import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from src.repositories.database import Database
from src.repositories.task_repository import TaskRepository
from src.repositories.journal_repository import JournalRepository
from src.repositories.governance_repository import GovernanceRepository
from src.services.task_service import TaskService

@pytest.fixture
def db(tmp_path): return Database(tmp_path / "test.db")
@pytest.fixture
def task_repo(db): return TaskRepository(db)
@pytest.fixture
def journal_repo(db): return JournalRepository(db)
@pytest.fixture
def governance(db): return GovernanceRepository(db)
@pytest.fixture
def task_service(task_repo): return TaskService(task_repo)
