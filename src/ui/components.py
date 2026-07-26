from __future__ import annotations

from html import escape
from typing import Callable

import streamlit as st


PRIORITY_META = {
    "High": ("▲", "priority-high"),
    "Medium": ("◆", "priority-medium"),
    "Low": ("●", "priority-low"),
}

STATUS_META = {
    "Open": ("○", "status-open"),
    "In Progress": ("◐", "status-progress"),
    "Blocked": ("■", "status-blocked"),
    "Completed": ("✓", "status-completed"),
}


def page_header(title: str, subtitle: str = "") -> None:
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def task_card(
    task,
    rule_explanation: str | None = None,
    on_open=None,
    key_prefix: str = "task",
    on_reopen=None,
) -> None:
    """Render an accessible task card with optional task actions.

    ``on_open`` receives the task ID when the Open task button is selected.
    ``on_reopen`` receives the task ID when the Reopen button is selected.
    """
    priority_classes = {
        "High": ("▲", "priority-high"),
        "Medium": ("●", "priority-medium"),
        "Low": ("▼", "priority-low"),
    }
    status_classes = {
        "Open": ("○", "status-open"),
        "In Progress": ("◐", "status-progress"),
        "Blocked": ("■", "status-blocked"),
        "Completed": ("✓", "status-completed"),
    }

    priority_icon, priority_class = priority_classes.get(
        task.priority,
        ("•", "priority-medium"),
    )
    status_icon, status_class = status_classes.get(
        task.status,
        ("•", "status-open"),
    )

    due_text = (
        task.due_date.isoformat()
        if task.due_date is not None
        else "No due date"
    )

    with st.container(border=True):
        st.markdown(f"#### {task.title}")

        st.markdown(
            f"""
            <div class="task-meta">
                <span class="task-badge {priority_class}">
                    {priority_icon} Priority: {task.priority}
                </span>
                <span class="task-badge {status_class}">
                    {status_icon} Status: {task.status}
                </span>
                <span class="task-badge due-badge">
                    Due: {due_text}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if task.description:
            st.write(task.description)

        if task.source:
            st.caption(f"Source: {task.source}")

        if rule_explanation:
            st.markdown(
                f"""
                <div class="rule-explanation">
                    <strong>Selected by application rules:</strong>
                    {rule_explanation}
                </div>
                """,
                unsafe_allow_html=True,
            )

        actions = []

        if on_open is not None:
            actions.append("open")

        if on_reopen is not None and task.status == "Completed":
            actions.append("reopen")

        if actions:
            columns = st.columns(len(actions))

            column_index = 0

            if "open" in actions:
                if columns[column_index].button(
                    "Open task",
                    key=f"{key_prefix}_open_{task.id}",
                    use_container_width=True,
                ):
                    on_open(task.id)
                    st.rerun()

                column_index += 1

            if "reopen" in actions:
                if columns[column_index].button(
                    "Reopen",
                    key=f"{key_prefix}_reopen_{task.id}",
                    use_container_width=True,
                ):
                    on_reopen(task.id)
                    st.success("Task reopened.")
                    st.rerun()
