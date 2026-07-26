from datetime import date, timedelta
from src.repositories.database import Database
from src.repositories.task_repository import TaskRepository
from src.repositories.journal_repository import JournalRepository
from src.models.entities import Task, JournalEntry

db = Database("data/daybook.db")
tasks = TaskRepository(db)
journals = JournalRepository(db)
if not tasks.list_all():
    tasks.create(Task(None, "Review deployment plan", "Check assumptions and unresolved risks.", "High", date.today(), "Open", "Sample data"))
    tasks.create(Task(None, "Prepare weekly update", "Summarize progress and blockers.", "Medium", date.today()+timedelta(days=1), "In Progress", "Sample data"))
    tasks.create(Task(None, "Confirm vendor response", "Waiting for clarification.", "High", None, "Blocked", "Sample data"))
if not journals.get(date.today()):
    journals.upsert(JournalEntry(date.today(), "Set up Daybook AI", "Reviewing course deliverables", "Waiting on local model selection", "Keep the prototype small and transparent", "Run tests and record demonstration"))
print("Sample local data initialized.")
