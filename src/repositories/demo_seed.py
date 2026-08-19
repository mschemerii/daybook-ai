from __future__ import annotations

import sqlite3
from datetime import date, timedelta


DEMO_TASKS = (
    {
        "title": "Prepare deployment package",
        "description": (
            "Package the application, confirm configuration, and prepare the "
            "deployment checklist for the demonstration environment."
        ),
        "priority": "High",
        "due_offset_days": 0,
        "estimated_hours": 4.0,
        "completion_criterion": (
            "The deployment package and checklist are ready for validation."
        ),
    },
    {
        "title": "Validate deployment package",
        "description": (
            "Run functional checks against the prepared deployment package and "
            "record any issues that must be resolved before presentation."
        ),
        "priority": "Medium",
        "due_offset_days": 1,
        "estimated_hours": 3.0,
        "completion_criterion": (
            "Validation checks are complete and blocking issues are documented."
        ),
    },
    {
        "title": "Present deployment results",
        "description": (
            "Summarize the validated deployment and present the result to "
            "stakeholders."
        ),
        "priority": "Medium",
        "due_offset_days": 2,
        "estimated_hours": 1.5,
        "completion_criterion": (
            "Stakeholders receive the deployment summary and outcome."
        ),
    },
)


def seed_demo_data(conn: sqlite3.Connection) -> None:
    """Insert the small first-launch demonstration dataset."""
    today = date.today()
    rows = [
        (
            task["title"],
            task["description"],
            task["priority"],
            (today + timedelta(days=task["due_offset_days"])).isoformat(),
            "Open",
            "Included sample data",
            "First-launch demonstration task.",
            task["estimated_hours"],
            "standard",
            "user_created",
            task["completion_criterion"],
        )
        for task in DEMO_TASKS
    ]

    conn.executemany(
        """
        INSERT INTO tasks(
            title,
            description,
            priority,
            due_date,
            status,
            source,
            notes,
            estimated_hours,
            task_type,
            provenance,
            completion_criterion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
