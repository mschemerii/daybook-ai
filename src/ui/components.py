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


def task_card(task, reason: str | None = None, on_open: Callable[[int], None] | None = None, key_prefix: str = "task") -> None:
    """Render an accessible task card with an explicit task-opening control."""
    priority_icon, priority_class = PRIORITY_META.get(task.priority, ("•", "priority-low"))
    status_icon, status_class = STATUS_META.get(task.status, ("•", "status-open"))
    due = task.due_date.isoformat() if task.due_date else "No due date"

    with st.container(border=True):
        title_col, open_col = st.columns([5, 1.25], vertical_alignment="center")
        title_col.markdown(f"### {escape(task.title)}")
        if on_open and task.id is not None:
            open_col.button(
                "Open task",
                key=f"{key_prefix}_open_{task.id}",
                use_container_width=True,
                on_click=on_open,
                args=(task.id,),
                help=f"Open and edit {task.title}",
            )

        st.markdown(
            f'<div class="task-meta">'
            f'<span class="task-badge {priority_class}">{priority_icon} Priority: {escape(task.priority)}</span>'
            f'<span class="task-badge {status_class}">{status_icon} Status: {escape(task.status)}</span>'
            f'<span class="task-badge due-badge">◷ Due: {escape(due)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if task.description:
            st.write(task.description)
        if reason:
            st.markdown(
                f'<div class="rule-explanation"><strong>Selected by application rules:</strong> {escape(reason)}</div>',
                unsafe_allow_html=True,
            )
