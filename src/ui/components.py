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
    priority_icon, priority_class = PRIORITY_META.get(
        task.priority,
        ("•", "priority-medium"),
    )
    status_icon, status_class = STATUS_META.get(
        task.status,
        ("•", "status-open"),
    )

    due_text = format_date(task.due_date)

    with st.container(
        border=True,
        key=f"task_card_{key_prefix}_{task.id}",
    ):
        st.markdown(
            f'<h4 class="task-card-title">{escape(str(task.title))}</h4>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="task-meta">
                <span class="task-badge {priority_class}">
                    {priority_icon} Priority: {escape(str(task.priority))}
                </span>
                <span class="task-badge {status_class}">
                    {status_icon} Status: {escape(str(task.status))}
                </span>
                <span class="task-badge due-badge">
                    Due: {escape(due_text)}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if task.description:
            st.markdown(
                f'<p class="task-card-description">'
                f'{escape(str(task.description))}</p>',
                unsafe_allow_html=True,
            )

        if task.source:
            st.markdown(
                f'<p class="task-card-source">'
                f'Source: {escape(str(task.source))}</p>',
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
                    on_reopen(task.id)
                    st.success("Task reopened.")
                    st.rerun()
