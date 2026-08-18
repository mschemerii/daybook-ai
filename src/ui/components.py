from __future__ import annotations

from html import escape

import streamlit as st

from src.utils.dates import format_date


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

PROVENANCE_LABELS = {
    "ai_generated": "Created from an AI proposal approved by you",
    "ai_generated_user_edited": "Created from an AI proposal you edited and approved",
    "user_added_during_review": "Added by you during AI proposal review",
}


def format_estimated_hours(value: float | None) -> str:
    if value is None:
        return "Not estimated"
    return f"{value:g} hours"


def meaningful_task_origin(task) -> str | None:
    """Describe only origins that add useful context for the user."""
    if task.source == "Sample data":
        return "Included sample data"
    return PROVENANCE_LABELS.get(task.provenance)


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
    blocking_prerequisites=None,
) -> None:
    """Render an accessible task card with optional task actions.

    ``on_open`` receives the task ID when the Open task button is selected.
    ``on_reopen`` receives the task ID when the Reopen button is selected.
    ``blocking_prerequisites`` names dependency-derived blockers.
    """
    priority_icon, priority_class = PRIORITY_META.get(
        task.priority,
        ("•", "priority-medium"),
    )
    status_icon, status_class = STATUS_META.get(
        task.status,
        ("•", "status-open"),
    )

    due_text = format_date(task.due_date)
    task_type = "Epic" if task.task_type == "epic" else "Task"
    badges = [
        f'<span class="task-badge {priority_class}">'
        f'{priority_icon} Priority: {escape(str(task.priority))}</span>',
        f'<span class="task-badge {status_class}">'
        f'{status_icon} Status: {escape(str(task.status))}</span>',
        f'<span class="task-badge due-badge">Due: {escape(due_text)}</span>',
        f'<span class="task-badge due-badge">Type: {escape(task_type)}</span>',
    ]
    if task.parent_task_id is not None and task.subtask_order is not None:
        badges.append(
            '<span class="task-badge due-badge">'
            f'Epic position: {task.subtask_order + 1}</span>'
        )
    badges.append(
        '<span class="task-badge due-badge">'
        f'Estimate: {escape(format_estimated_hours(task.estimated_hours))}</span>'
    )

    with st.container(
        border=True,
        key=f"task_card_{key_prefix}_{task.id}",
    ):
        st.markdown(
            f'<h4 class="task-card-title">{escape(str(task.title))}</h4>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div class="task-meta">{"".join(badges)}</div>',
            unsafe_allow_html=True,
        )

        if task.description:
            st.markdown(
                f'<p class="task-card-description">'
                f'{escape(str(task.description))}</p>',
                unsafe_allow_html=True,
            )

        task_origin = meaningful_task_origin(task)
        if task_origin:
            st.markdown(
                f'<p class="task-card-source">'
                f'Origin: {escape(task_origin)}</p>',
                unsafe_allow_html=True,
            )

        if rule_explanation:
            st.markdown(
                f"""
                <div class="rule-explanation">
                    <strong>Selected by application rules:</strong>
                    {escape(str(rule_explanation))}
                </div>
                """,
                unsafe_allow_html=True,
            )

        if blocking_prerequisites:
            blocker_names = ", ".join(
                f"{prerequisite.title} (task {prerequisite.id})"
                for prerequisite in blocking_prerequisites
            )
            st.warning(f"Blocked by incomplete prerequisites: {blocker_names}")

        actions = []

        if on_open is not None:
            actions.append("open")

        if on_reopen is not None and task.status == "Completed":
            actions.append("reopen")

        if actions:
            columns = st.columns(len(actions), gap="small")

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
                    reopened = on_reopen(task.id)
                    if reopened is not False:
                        st.success("Task reopened.")
                    st.rerun()
