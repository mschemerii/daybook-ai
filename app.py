from __future__ import annotations

import os
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlencode

import streamlit as st
from dotenv import load_dotenv

from src.agent.local_llm import LocalModelClient, LocalModelError
from src.models.entities import JournalEntry
from src.repositories.database import Database
from src.repositories.dependency_repository import DependencyRepository
from src.repositories.governance_repository import GovernanceRepository
from src.repositories.journal_repository import JournalRepository
from src.repositories.task_repository import TaskRepository
from src.repositories.time_entry_repository import TimeEntryRepository
from src.services.context_service import ContextService
from src.services.task_service import (
    DESCRIPTION_MAX_LENGTH,
    EPIC_ESTIMATE_MAX_HOURS,
    STANDARD_ESTIMATE_MAX_HOURS,
    TITLE_MAX_LENGTH,
    DependencyOffer,
    ReopenConfirmationRequired,
    TaskService,
    TaskValidationError,
)
from src.services.time_entry_service import (
    MAX_ENTRY_MINUTES,
    TIME_ENTRY_NOTE_MAX_LENGTH,
    TimeEntryService,
    TimeEntryValidationError,
)
from src.ui.components import format_estimated_hours, page_header, task_card
from src.utils.dates import format_date, format_datetime

load_dotenv()
st.set_page_config(page_title="Daybook AI", page_icon="📘", layout="wide", initial_sidebar_state="collapsed")

DB_PATH = Path(os.getenv("DAYBOOK_DB_PATH", "data/daybook.db"))
MODEL_BASE_URL = os.getenv("DAYBOOK_MODEL_BASE_URL", "http://127.0.0.1:8080/v1")
MODEL_NAME = os.getenv("DAYBOOK_MODEL_NAME", "auto")
MODEL_API_KEY = os.getenv("DAYBOOK_MODEL_API_KEY", "")
CONTROLLER_URL = os.getenv("DAYBOOK_CONTROLLER_URL", "http://127.0.0.1:8500")
CONTROLLER_TOKEN = os.getenv("DAYBOOK_CONTROLLER_TOKEN", "")
PAGES = ["Today", "Tasks", "Daily Journal", "Assistant", "About", "Ethical AI"]

@st.cache_resource
def services():
    db = Database(DB_PATH)
    tasks = TaskRepository(db)
    dependencies = DependencyRepository(db)
    time_entries = TimeEntryRepository(db)
    journals = JournalRepository(db)
    governance = GovernanceRepository(db)
    return (
        tasks,
        dependencies,
        journals,
        governance,
        TaskService(tasks, dependencies),
        TimeEntryService(time_entries, tasks),
        ContextService(tasks, journals),
        LocalModelClient(MODEL_BASE_URL, MODEL_NAME, api_key=MODEL_API_KEY),
    )


(
    tasks,
    dependencies,
    journals,
    governance,
    task_service,
    time_entry_service,
    context_service,
    llm,
) = services()

if "page" not in st.session_state:
    st.session_state.page = "Today"

if "selected_task_id" not in st.session_state:
    st.session_state.selected_task_id = None

if "pending_page" not in st.session_state:
    st.session_state.pending_page = None

if "pending_reopen_task_id" not in st.session_state:
    st.session_state.pending_reopen_task_id = None

if "pending_dependency_offer" not in st.session_state:
    st.session_state.pending_dependency_offer = None

if "pending_delete_task_id" not in st.session_state:
    st.session_state.pending_delete_task_id = None

pending_page = st.session_state.pending_page

if pending_page is not None:
    st.session_state.page = pending_page
    st.session_state.navigation_radio = pending_page
    st.session_state.pending_page = None
elif "navigation_radio" not in st.session_state:
    st.session_state.navigation_radio = st.session_state.page


def open_task(task_id: int) -> None:
    """Queue navigation to the selected task on the next rerun."""
    st.session_state.selected_task_id = task_id
    st.session_state.pending_page = "Tasks"


def close_task() -> None:
    st.session_state.selected_task_id = None


def reopen_task(task_id: int) -> bool:
    """Reopen immediately or queue a named dependency confirmation."""
    try:
        task_service.reopen_task(task_id)
        return True
    except ReopenConfirmationRequired:
        st.session_state.pending_reopen_task_id = task_id
        return False


def task_identity(task) -> str:
    """Identify duplicate titles unambiguously without widening the layout."""
    if task.parent_task_id is not None:
        try:
            parent = tasks.get(task.parent_task_id)
            return f"{task.title} — under {parent.title} (task {task.id})"
        except KeyError:
            pass
    return f"{task.title} (task {task.id})"


def format_minutes(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h {remainder}m"
    if hours:
        return f"{hours}h"
    return f"{remainder}m"


def navigate_to(page_name: str) -> None:
    """Queue navigation until the next Streamlit rerun."""
    st.session_state.pending_page = page_name

    if page_name != "Tasks":
        st.session_state.selected_task_id = None


def render_task_hierarchy(task, *, depth: int = 0) -> None:
    if depth:
        st.caption(f"{'↳ ' * depth}Subtask of the item above")
    task_card(
        task,
        on_open=open_task,
        key_prefix=f"all_level_{depth}",
        blocking_prerequisites=task_service.blocking_prerequisites(task.id),
    )
    for child in tasks.list_subtasks(task.id):
        render_task_hierarchy(child, depth=depth + 1)


st.markdown(
    """
<style>
.block-container {padding-top: 2.6rem; padding-bottom: 2rem; max-width: 1120px;}
[data-testid="stSidebar"], [data-testid="collapsedControl"] {display: none;}
.st-key-top_navigation {
    position: sticky;
    top: 2.25rem;
    z-index: 999;
    background: var(--background-color);
    padding: .8rem 0 .7rem 0;
    border-bottom: 1px solid color-mix(in srgb, var(--text-color) 18%, transparent);
}
.st-key-top_navigation [role="radiogroup"] {gap: .25rem; flex-wrap: wrap;}
.st-key-top_navigation label {
    border: 1px solid color-mix(in srgb, var(--text-color) 22%, transparent);
    border-radius: .55rem;
    padding: .25rem .6rem;
    background: var(--secondary-background-color);
}
.st-key-top_navigation label:has(input:checked) {
    border-width: 2px;
    border-color: #0072B2;
}
.shutdown-link-wrap {
    display:flex;
    justify-content:flex-end;
    align-items:center;
    padding-top:.2rem;
}
.shutdown-link {
    display:inline-flex;
    width:100%;
    min-height:2.45rem;
    align-items:center;
    justify-content:center;
    border-radius:.55rem;
    border:1px solid color-mix(in srgb, #D55E00 70%, var(--text-color));
    color:var(--text-color) !important;
    background:color-mix(in srgb, #D55E00 12%, var(--background-color));
    font-weight:650;
    text-decoration:none !important;
    padding:.45rem .75rem;
}
.shutdown-link:hover {
    border-color:#D55E00;
    background:color-mix(in srgb, #D55E00 20%, var(--background-color));
}
.task-card-title {
    margin:0 0 .35rem 0;
    font-size:1.18rem;
    line-height:1.35;
}
.task-card-description {
    margin:0 0 .45rem 0;
    line-height:1.55;
}
.task-card-source {
    margin:0 0 .65rem 0;
    color:var(--text-color);
    font-size:.85rem;
    opacity:.82;
}
.task-meta {
    display:flex;
    gap:.45rem;
    row-gap:.4rem;
    flex-wrap:wrap;
    margin:.1rem 0 .7rem 0;
}
.task-badge {
    display:inline-flex;
    align-items:center;
    gap:.25rem;
    border:1px solid currentColor;
    border-radius:999px;
    padding:.18rem .55rem;
    font-size:.82rem;
    font-weight:650;
    line-height:1.35;
    white-space:nowrap;
}
.priority-high {--badge-accent:#D55E00;}
.priority-medium {--badge-accent:#0072B2;}
.priority-low {--badge-accent:#009E73;}
.status-open {--badge-accent:#0072B2;}
.status-progress {--badge-accent:#CC79A7;}
.status-blocked {--badge-accent:#D55E00;}
.status-completed {--badge-accent:#009E73;}
.priority-high,
.priority-medium,
.priority-low,
.status-open,
.status-progress,
.status-blocked,
.status-completed {
    color:color-mix(
        in srgb,
        var(--badge-accent) 60%,
        var(--text-color)
    );
    background:color-mix(
        in srgb,
        var(--badge-accent) 12%,
        var(--background-color)
    );
}
.due-badge {color:var(--text-color); background:var(--secondary-background-color);}
[class*="st-key-task_card_"] {
    margin-bottom:.7rem;
}
[class*="st-key-task_card_"] [data-testid="stHorizontalBlock"] {
    gap:.55rem;
    flex-wrap:wrap;
}
[class*="st-key-task_card_"] [data-testid="stColumn"] {
    min-width:8.5rem;
    flex:1 1 8.5rem;
}
@media (max-width: 640px) {
    .task-card-title {font-size:1.08rem;}
    [class*="st-key-task_card_"] [data-testid="stColumn"] {
        min-width:100%;
        flex-basis:100%;
    }
}
.rule-explanation {
    margin-top:.45rem;
    padding:.55rem .7rem;
    border-left:4px solid #F0E442;
    background:color-mix(in srgb, #F0E442 14%, var(--background-color));
    color:var(--text-color);
    border-radius:.2rem;
}
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] {color:var(--text-color);}
.small-note {font-size:.85rem; color:var(--text-color); opacity:.86;}
</style>
""",
    unsafe_allow_html=True,
)

with st.container(key="top_navigation"):
    detected_gpu = os.getenv(
        "DAYBOOK_DETECTED_GPU",
        "Not checked—start with python run.py",
    )
    detected_backend = os.getenv(
        "DAYBOOK_DETECTED_BACKEND",
        "Unknown",
    )

    title_column, shutdown_column = st.columns(
        [9, 2],
        vertical_alignment="center",
    )

    with title_column:
        st.markdown("### Daybook AI")
        st.caption(
            "Local-first prototype · No telemetry · "
            f"Runtime: {detected_gpu} · Backend: {detected_backend}"
        )

    with shutdown_column:
        shutdown_query = urlencode({"token": CONTROLLER_TOKEN})
        shutdown_url = escape(
            f"{CONTROLLER_URL.rstrip('/')}/shutdown?{shutdown_query}",
            quote=True,
        )

        st.markdown(
            f"""
            <div class="shutdown-link-wrap">
                <a
                    class="shutdown-link"
                    href="{shutdown_url}"
                    target="_top"
                    aria-label="Shut down Daybook AI"
                    title="Close Daybook AI and stop locally started services"
                >
                    ⏻ Shut down
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )

    page = st.radio(
        "Primary navigation",
        PAGES,
        horizontal=True,
        label_visibility="collapsed",
        key="navigation_radio",
    )

    if page != st.session_state.page:
        st.session_state.page = page
        if page != "Tasks":
            st.session_state.selected_task_id = None
        st.rerun()


page = st.session_state.page

pending_reopen_id = st.session_state.pending_reopen_task_id
if pending_reopen_id is not None:
    try:
        reopening_task = tasks.get(pending_reopen_id)
        affected_tasks = task_service.reopen_affected_tasks(pending_reopen_id)
    except KeyError:
        st.session_state.pending_reopen_task_id = None
        st.warning("That task no longer exists.")
        st.rerun()

    affected_names = ", ".join(task_identity(task) for task in affected_tasks)
    st.warning(
        f"Reopening {task_identity(reopening_task)} will also reopen completed "
        "dependent tasks and block open dependents while prerequisites remain "
        f"incomplete. Affected: {affected_names}"
    )
    confirm_reopen, cancel_reopen = st.columns(2)
    if confirm_reopen.button(
        "Confirm reopening cascade",
        key="confirm_dependency_reopen",
        use_container_width=True,
    ):
        task_service.reopen_task(
            pending_reopen_id,
            confirm_dependency_cascade=True,
        )
        st.session_state.pending_reopen_task_id = None
        st.success("Task and affected dependents reopened.")
        st.rerun()
    if cancel_reopen.button(
        "Cancel",
        key="cancel_dependency_reopen",
        use_container_width=True,
    ):
        st.session_state.pending_reopen_task_id = None
        st.info("No task records were changed.")
        st.rerun()

if page == "Today":
    page_header("Today", "A compact, actionable view before focused work begins.")
    open_tasks = tasks.list_all(False)
    blocked = task_service.blocked()
    due = task_service.due_today()
    completed = task_service.completed()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open tasks", len(open_tasks))
    c2.metric("Due today", len(due))
    c3.metric("Blockers", len(blocked))
    c4.metric("Completed", len(completed))

    st.subheader("Recommended focus")
    st.caption("Selected by application rules. The local AI may explain the result, but it does not set the order.")
    focus = task_service.focus_items()
    if not focus:
        st.info("No open, unblocked tasks are available.")
    for task in focus:
        task_card(task, task_service.explain_rule_selection(task), open_task, "focus")

    st.subheader("Due today")
    if due:
        for task in due:
            task_card(task, on_open=open_task, key_prefix="due")
    else:
        st.info("No tasks are due today.")

    st.subheader("Current blockers")
    if blocked:
        for task in blocked:
            task_card(
                task,
                on_open=open_task,
                key_prefix="blocked",
                blocking_prerequisites=task_service.blocking_prerequisites(
                    task.id
                ),
            )
    else:
        st.info("No blocked tasks.")

    st.subheader("Completed tasks")
    st.caption("Recently completed work remains visible here. Reopen a task to return it to Open status.")
    if completed:
        for task in completed[:10]:
            task_card(
                task,
                on_open=open_task,
                on_reopen=reopen_task,
                key_prefix="completed",
            )
        if len(completed) > 10:
            st.caption(f"Showing 10 of {len(completed)} completed tasks. Open the Tasks page and enable Show completed to view all.")
    else:
        st.info("No completed tasks yet.")

elif page == "Tasks":
    selected_id = st.session_state.selected_task_id
    try:
        selected_task = tasks.get(selected_id) if selected_id is not None else None
    except KeyError:
        st.warning("That task no longer exists.")
        close_task()
        st.rerun()

    if selected_task:
        page_header("Task details", "Review or update the selected task.")
        if st.button("← Back to all tasks"):
            close_task()
            st.rerun()
        dependency_blockers = task_service.blocking_prerequisites(
            selected_task.id
        )
        task_card(
            selected_task,
            key_prefix="detail",
            blocking_prerequisites=dependency_blockers,
        )
        if selected_task.status == "Completed" and st.button(
            "Reopen task",
            key=f"detail_reopen_{selected_task.id}",
        ):
            if reopen_task(selected_task.id):
                st.success("Task reopened.")
            st.rerun()

        children = tasks.list_subtasks(selected_task.id)
        if selected_task.task_type == "epic":
            completed_children = sum(
                child.status == "Completed" for child in children
            )
            original_estimate, child_estimate, completion = st.columns(3)
            original_estimate.metric(
                "Original epic estimate",
                format_estimated_hours(selected_task.estimated_hours),
            )
            child_estimate.metric(
                "Current subtask estimate",
                format_estimated_hours(
                    tasks.subtask_estimated_hours(selected_task.id)
                ),
            )
            completion.metric(
                "Completed subtasks",
                f"{completed_children} of {len(children)}",
            )

        own_recorded_minutes = time_entry_service.recorded_minutes(
            selected_task.id
        )
        total_recorded_minutes = time_entry_service.recorded_minutes(
            selected_task.id,
            include_descendants=selected_task.task_type == "epic",
        )
        if selected_task.task_type == "epic":
            own_time, hierarchy_time = st.columns(2)
            own_time.metric("Recorded on epic", format_minutes(own_recorded_minutes))
            hierarchy_time.metric(
                "Recorded across epic",
                format_minutes(total_recorded_minutes),
            )
        else:
            st.metric("Recorded time", format_minutes(own_recorded_minutes))

        status_options = (
            ["Completed"]
            if selected_task.status == "Completed"
            else ["Open", "In Progress", "Blocked"]
        )
        epic_has_incomplete_children = (
            selected_task.task_type == "epic"
            and any(child.status != "Completed" for child in children)
        )
        estimate_limit = float(
            EPIC_ESTIMATE_MAX_HOURS
            if selected_task.task_type == "epic"
            else STANDARD_ESTIMATE_MAX_HOURS
        )
        with st.form(f"edit_{selected_task.id}"):
            title = st.text_input(
                "Title",
                selected_task.title,
                max_chars=TITLE_MAX_LENGTH,
            )
            description = st.text_area(
                "Description",
                selected_task.description,
                max_chars=DESCRIPTION_MAX_LENGTH,
            )
            priority_values = ["High", "Medium", "Low"]
            priority = st.selectbox(
                "Priority",
                priority_values,
                index=priority_values.index(selected_task.priority),
            )
            use_due = st.checkbox(
                "Set due date",
                value=selected_task.due_date is not None,
            )
            due_date = st.date_input(
                "Due date",
                value=selected_task.due_date or date.today(),
                format="MM-DD-YYYY",
                disabled=not use_due,
            )
            use_estimate = st.checkbox(
                "Set estimated duration",
                value=selected_task.estimated_hours is not None,
            )
            estimated_hours = st.number_input(
                "Estimated hours",
                min_value=0.25,
                max_value=estimate_limit,
                value=float(selected_task.estimated_hours or 0.25),
                step=0.25,
                disabled=not use_estimate,
            )
            status = st.selectbox(
                "Status",
                status_options,
                index=status_options.index(selected_task.status),
                disabled=selected_task.status == "Completed",
            )
            source = st.text_input("Source or provenance", selected_task.source)
            notes = st.text_area("Notes", selected_task.notes)
            completion_criterion = st.text_area(
                "Definition of done",
                selected_task.completion_criterion,
                max_chars=DESCRIPTION_MAX_LENGTH,
            )
            save, complete, delete = st.columns(3)
            if save.form_submit_button("Save changes", use_container_width=True):
                try:
                    task_service.update_task(selected_task.id, {
                        "title": title.strip(), "description": description, "priority": priority,
                        "due_date": due_date if use_due else None, "status": status,
                        "source": source or "User", "notes": notes,
                        "estimated_hours": estimated_hours if use_estimate else None,
                        "completion_criterion": completion_criterion,
                    })
                    st.success("Task updated.")
                    st.rerun()
                except (TaskValidationError, ValueError) as exc:
                    st.error(str(exc))
            if complete.form_submit_button(
                "Mark complete",
                use_container_width=True,
                disabled=(
                    selected_task.status == "Completed"
                    or epic_has_incomplete_children
                    or bool(dependency_blockers)
                ),
                help=(
                    "Complete every subtask before closing the epic."
                    if epic_has_incomplete_children
                    else (
                        "Incomplete prerequisites: "
                        + ", ".join(
                            task_identity(task)
                            for task in dependency_blockers
                        )
                        if dependency_blockers
                        else None
                    )
                ),
            ):
                try:
                    task_service.complete_task(selected_task.id)
                    st.success("Task completed.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if delete.form_submit_button(
                "Review deletion",
                use_container_width=True,
            ):
                st.session_state.pending_delete_task_id = selected_task.id
                st.rerun()

        if st.session_state.pending_delete_task_id == selected_task.id:
            deletion = task_service.deletion_preview(selected_task.id)
            st.warning(
                f"Delete {task_identity(selected_task)}? This cannot be undone."
            )
            if deletion.deletes_recorded_time:
                st.error(
                    "This task has recorded time. Deleting it also deletes those "
                    "time entries."
                )
            if deletion.preserved_tasks:
                preserved_names = ", ".join(
                    task_identity(task) for task in deletion.preserved_tasks
                )
                st.info(
                    "These subtasks have recorded time and will be preserved as "
                    f"standalone tasks: {preserved_names}"
                )
            if deletion.deleted_tasks:
                deleted_names = ", ".join(
                    task_identity(task) for task in deletion.deleted_tasks
                )
                st.warning(
                    "These subtasks have no recorded time and will be deleted: "
                    f"{deleted_names}"
                )
            confirm_delete, cancel_delete = st.columns(2)
            if confirm_delete.button(
                "Confirm deletion",
                key=f"confirm_delete_{selected_task.id}",
                use_container_width=True,
            ):
                task_service.delete_task(selected_task.id, confirmed=True)
                st.session_state.pending_delete_task_id = None
                close_task()
                st.rerun()
            if cancel_delete.button(
                "Cancel",
                key=f"cancel_delete_{selected_task.id}",
                use_container_width=True,
            ):
                st.session_state.pending_delete_task_id = None
                st.rerun()

        st.subheader("Recorded time")
        st.caption(
            "Recorded time is separate from the estimate. Each entry is limited "
            "to 12 hours, and all entries for one day cannot exceed 24 hours."
        )
        with st.form(f"add_time_entry_{selected_task.id}"):
            entry_date = st.date_input(
                "Work date",
                value=date.today(),
                format="MM-DD-YYYY",
                key=f"time_date_{selected_task.id}",
            )
            entry_minutes = st.number_input(
                "Duration in minutes",
                min_value=1,
                max_value=MAX_ENTRY_MINUTES,
                value=30,
                step=1,
                key=f"time_minutes_{selected_task.id}",
            )
            entry_note = st.text_area(
                "Time-entry note",
                max_chars=TIME_ENTRY_NOTE_MAX_LENGTH,
                key=f"time_note_{selected_task.id}",
            )
            if st.form_submit_button("Add time entry"):
                try:
                    time_entry_service.create(
                        selected_task.id,
                        work_date=entry_date,
                        minutes=int(entry_minutes),
                        note=entry_note,
                    )
                    st.success("Time entry added.")
                    st.rerun()
                except TimeEntryValidationError as exc:
                    st.error(str(exc))

        task_time_entries = time_entry_service.list_for_task(selected_task.id)
        if task_time_entries:
            for entry in task_time_entries:
                with st.expander(
                    f"{format_date(entry.work_date)} · {format_minutes(entry.minutes)}"
                ):
                    with st.form(f"edit_time_entry_{entry.id}"):
                        edited_date = st.date_input(
                            "Work date",
                            value=entry.work_date,
                            format="MM-DD-YYYY",
                        )
                        edited_minutes = st.number_input(
                            "Duration in minutes",
                            min_value=1,
                            max_value=MAX_ENTRY_MINUTES,
                            value=entry.minutes,
                            step=1,
                        )
                        edited_note = st.text_area(
                            "Time-entry note",
                            value=entry.note,
                            max_chars=TIME_ENTRY_NOTE_MAX_LENGTH,
                        )
                        update_entry, delete_entry = st.columns(2)
                        if update_entry.form_submit_button(
                            "Update entry", use_container_width=True
                        ):
                            try:
                                time_entry_service.update(
                                    entry.id,
                                    work_date=edited_date,
                                    minutes=int(edited_minutes),
                                    note=edited_note,
                                )
                                st.success("Time entry updated.")
                                st.rerun()
                            except TimeEntryValidationError as exc:
                                st.error(str(exc))
                        if delete_entry.form_submit_button(
                            "Delete entry", use_container_width=True
                        ):
                            time_entry_service.delete(entry.id)
                            st.rerun()
        else:
            st.caption("No recorded time for this task.")

        st.subheader("Hierarchy")
        descendants = tasks.descendant_ids(selected_task.id)
        parent_candidates = [
            task
            for task in tasks.list_all(include_completed=True)
            if task.id != selected_task.id and task.id not in descendants
        ]
        parent_labels = {None: "No parent (standard task)"}
        parent_labels.update(
            {task.id: f"{task.title} (task {task.id})" for task in parent_candidates}
        )
        parent_options = list(parent_labels)
        current_parent = selected_task.parent_task_id
        parent_index = (
            parent_options.index(current_parent)
            if current_parent in parent_options
            else 0
        )
        with st.form(f"parent_{selected_task.id}"):
            chosen_parent = st.selectbox(
                "Parent task",
                parent_options,
                index=parent_index,
                format_func=parent_labels.get,
            )
            if st.form_submit_button("Update parent"):
                try:
                    if chosen_parent is None and current_parent is not None:
                        task_service.remove_subtask(selected_task.id)
                    elif chosen_parent is not None and chosen_parent != current_parent:
                        task_service.reassign_subtask(
                            selected_task.id,
                            chosen_parent,
                        )
                    st.success("Task hierarchy updated.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

        st.subheader("Dependencies")
        st.caption(
            "Direction: this task requires its prerequisites. Blocking is "
            "calculated from incomplete prerequisites."
        )
        prerequisite_tasks = task_service.prerequisites(selected_task.id)
        dependent_tasks = task_service.dependents(selected_task.id)

        st.markdown("**Prerequisites this task requires**")
        if prerequisite_tasks:
            for prerequisite in prerequisite_tasks:
                prerequisite_label, remove_prerequisite = st.columns([4, 1])
                prerequisite_label.write(task_identity(prerequisite))
                if remove_prerequisite.button(
                    "Remove",
                    key=(
                        f"remove_dependency_{selected_task.id}_"
                        f"{prerequisite.id}"
                    ),
                    use_container_width=True,
                ):
                    task_service.remove_dependency(
                        selected_task.id,
                        prerequisite.id,
                    )
                    st.rerun()
        else:
            st.caption("No prerequisites.")

        st.markdown("**Tasks that depend on this task**")
        if dependent_tasks:
            for dependent in dependent_tasks:
                dependent_label, remove_dependent = st.columns([4, 1])
                dependent_label.write(task_identity(dependent))
                if remove_dependent.button(
                    "Remove",
                    key=f"remove_dependent_{dependent.id}_{selected_task.id}",
                    use_container_width=True,
                ):
                    task_service.remove_dependency(
                        dependent.id,
                        selected_task.id,
                    )
                    st.rerun()
        else:
            st.caption("No dependent tasks.")

        dependency_candidates = [
            task
            for task in tasks.list_all(include_completed=True)
            if task.id != selected_task.id
        ]
        if dependency_candidates:
            candidate_labels = {
                task.id: task_identity(task) for task in dependency_candidates
            }
            with st.form(f"add_dependency_{selected_task.id}"):
                prerequisite_id = st.selectbox(
                    "Add prerequisite",
                    list(candidate_labels),
                    format_func=candidate_labels.get,
                )
                if st.form_submit_button("Add dependency"):
                    try:
                        offer = task_service.add_dependency(
                            selected_task.id,
                            prerequisite_id,
                        )
                        if offer is not None:
                            st.session_state.pending_dependency_offer = offer
                        st.success("Dependency added.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
        else:
            st.caption("Create another task before adding a dependency.")

        pending_offer: DependencyOffer | None = (
            st.session_state.pending_dependency_offer
        )
        if (
            pending_offer is not None
            and pending_offer.dependent_task_id == selected_task.id
        ):
            if pending_offer.kind == "create_epic":
                st.info(
                    "These are standalone tasks. You may create an epic with "
                    "the prerequisite first and the dependent second. The "
                    "dependency will remain in place."
                )
                name_choice = st.radio(
                    "Epic name",
                    ["Use suggested name", "Enter another name"],
                    key=f"epic_name_choice_{selected_task.id}",
                    horizontal=True,
                )
                custom_name = st.text_input(
                    "New epic name",
                    max_chars=TITLE_MAX_LENGTH,
                    disabled=name_choice == "Use suggested name",
                    key=f"custom_epic_name_{selected_task.id}",
                )
                st.caption(
                    f"Suggested name: {pending_offer.suggested_epic_name}"
                )
                accept_offer, decline_offer = st.columns(2)
                if accept_offer.button(
                    "Create epic",
                    key=f"accept_epic_offer_{selected_task.id}",
                    use_container_width=True,
                ):
                    chosen_name = (
                        pending_offer.suggested_epic_name
                        if name_choice == "Use suggested name"
                        else custom_name
                    )
                    try:
                        epic = task_service.convert_dependency_pair_to_epic(
                            pending_offer.dependent_task_id,
                            pending_offer.prerequisite_task_id,
                            chosen_name or "",
                        )
                        st.session_state.pending_dependency_offer = None
                        open_task(epic.id)
                        st.rerun()
                    except (TaskValidationError, ValueError) as exc:
                        st.error(str(exc))
                if decline_offer.button(
                    "Keep dependency only",
                    key=f"decline_epic_offer_{selected_task.id}",
                    use_container_width=True,
                ):
                    st.session_state.pending_dependency_offer = None
                    st.rerun()
            elif pending_offer.kind == "append_to_epic":
                epic = tasks.get(pending_offer.prerequisite_task_id)
                st.info(
                    f"You may add this task as the final subtask of "
                    f"{task_identity(epic)}. Its direct dependency on the epic "
                    "will be removed to avoid a completion deadlock."
                )
                accept_append, decline_append = st.columns(2)
                if accept_append.button(
                    "Add as final subtask",
                    key=f"accept_append_offer_{selected_task.id}",
                    use_container_width=True,
                ):
                    task_service.append_dependent_to_epic(
                        pending_offer.dependent_task_id,
                        pending_offer.prerequisite_task_id,
                    )
                    st.session_state.pending_dependency_offer = None
                    st.rerun()
                if decline_append.button(
                    "Keep dependency only",
                    key=f"decline_append_offer_{selected_task.id}",
                    use_container_width=True,
                ):
                    st.session_state.pending_dependency_offer = None
                    st.rerun()

        with st.expander("Add subtask", expanded=False):
            with st.form(f"add_subtask_{selected_task.id}"):
                subtask_title = st.text_input(
                    "Subtask title",
                    max_chars=TITLE_MAX_LENGTH,
                )
                subtask_description = st.text_area(
                    "Subtask description",
                    max_chars=DESCRIPTION_MAX_LENGTH,
                )
                subtask_priority = st.selectbox(
                    "Subtask priority",
                    ["High", "Medium", "Low"],
                    index=["High", "Medium", "Low"].index(
                        selected_task.priority
                    ),
                )
                use_subtask_due = st.checkbox("Set subtask due date")
                subtask_due = st.date_input(
                    "Subtask due date",
                    value=selected_task.due_date or date.today(),
                    format="MM-DD-YYYY",
                    disabled=not use_subtask_due,
                )
                use_subtask_estimate = st.checkbox(
                    "Set subtask estimated duration"
                )
                subtask_estimate = st.number_input(
                    "Subtask estimated hours",
                    min_value=0.25,
                    max_value=float(STANDARD_ESTIMATE_MAX_HOURS),
                    value=0.25,
                    step=0.25,
                    disabled=not use_subtask_estimate,
                )
                subtask_done = st.text_area(
                    "Subtask definition of done",
                    max_chars=DESCRIPTION_MAX_LENGTH,
                )
                if st.form_submit_button("Add subtask"):
                    try:
                        task_service.add_subtask(
                            selected_task.id,
                            title=subtask_title.strip(),
                            description=subtask_description,
                            priority=subtask_priority,
                            due_date=subtask_due if use_subtask_due else None,
                            estimated_hours=(
                                subtask_estimate
                                if use_subtask_estimate
                                else None
                            ),
                            completion_criterion=subtask_done,
                        )
                        st.success("Subtask added.")
                        st.rerun()
                    except TaskValidationError as exc:
                        st.error(str(exc))

        if children:
            st.subheader("Subtasks")
            for index, child in enumerate(children):
                task_card(
                    child,
                    on_open=open_task,
                    key_prefix=f"subtask_{selected_task.id}",
                )
                move_up, move_down, remove = st.columns(3)
                if move_up.button(
                    "Move up",
                    key=f"move_up_{child.id}",
                    disabled=index == 0,
                    use_container_width=True,
                ):
                    task_service.move_subtask(child.id, -1)
                    st.rerun()
                if move_down.button(
                    "Move down",
                    key=f"move_down_{child.id}",
                    disabled=index == len(children) - 1,
                    use_container_width=True,
                ):
                    task_service.move_subtask(child.id, 1)
                    st.rerun()
                if remove.button(
                    "Remove from epic",
                    key=f"remove_subtask_{child.id}",
                    use_container_width=True,
                ):
                    task_service.remove_subtask(child.id)
                    st.rerun()
    else:
        page_header("Tasks", "Create and maintain locally stored work items.")
        with st.expander("Create task", expanded=False):
            with st.form("create_task"):
                title = st.text_input("Title", max_chars=TITLE_MAX_LENGTH)
                description = st.text_area(
                    "Description",
                    max_chars=DESCRIPTION_MAX_LENGTH,
                )
                priority = st.selectbox("Priority", ["High", "Medium", "Low"], index=1)
                use_due = st.checkbox("Set due date")
                due_date = st.date_input("Due date", value=date.today(), format="MM-DD-YYYY", disabled=not use_due)
                use_estimate = st.checkbox("Set estimated duration")
                estimated_hours = st.number_input(
                    "Estimated hours",
                    min_value=0.25,
                    max_value=float(STANDARD_ESTIMATE_MAX_HOURS),
                    value=0.25,
                    step=0.25,
                    disabled=not use_estimate,
                )
                status = st.selectbox("Status", ["Open", "In Progress", "Blocked", "Completed"])
                source = st.text_input("Source or provenance", value="User")
                notes = st.text_area("Notes")
                completion_criterion = st.text_area(
                    "Definition of done",
                    max_chars=DESCRIPTION_MAX_LENGTH,
                )
                if st.form_submit_button("Create task"):
                    try:
                        task_service.create_task(title=title.strip(), description=description, priority=priority,
                            due_date=due_date if use_due else None, status=status, source=source or "User", notes=notes,
                            estimated_hours=estimated_hours if use_estimate else None,
                            completion_criterion=completion_criterion)
                        st.success("Task created.")
                        st.rerun()
                    except TaskValidationError as exc:
                        st.error(str(exc))

        show_completed = st.checkbox("Show completed", value=False)
        current_tasks = tasks.list_roots(show_completed)
        if not current_tasks:
            st.info("No tasks to show.")
        for task in current_tasks:
            render_task_hierarchy(task)

elif page == "Daily Journal":
    page_header("Daily Journal", "Record progress, blockers, and reflection without scoring productivity.")
    selected = st.date_input("Entry date", value=date.today(), format="MM-DD-YYYY")
    entry = journals.get(selected) or JournalEntry(entry_date=selected)
    with st.form("journal"):
        completed = st.text_area("Completed today", entry.completed_today)
        progress = st.text_area("In progress", entry.in_progress)
        blocked_text = st.text_area("Blocked or waiting", entry.blocked_waiting)
        reflections = st.text_area("Notes and reflections", entry.reflections)
        tomorrow = st.text_area("Plan for tomorrow", entry.plan_tomorrow)
        if st.form_submit_button("Save entry"):
            journals.upsert(JournalEntry(selected, completed, progress, blocked_text, reflections, tomorrow))
            st.success("Journal entry saved locally.")
    st.subheader("Previous entries")
    for item in journals.list_recent(10):
        with st.expander(format_date(item.entry_date)):
            st.markdown(f"**Completed:** {item.completed_today or '—'}")
            st.markdown(f"**In progress:** {item.in_progress or '—'}")
            st.markdown(f"**Blocked/waiting:** {item.blocked_waiting or '—'}")
            st.markdown(f"**Reflections:** {item.reflections or '—'}")
            st.markdown(f"**Tomorrow:** {item.plan_tomorrow or '—'}")

elif page == "Assistant":
    page_header("Assistant", "Bounded local assistance with explicit data access.")
    ok, message = llm.healthcheck()
    (st.success if ok else st.warning)(message)
    include_tasks = st.checkbox("Allow access to selected task fields", value=False)
    include_journal = st.checkbox("Allow access to recent journal fields", value=False)
    retain_memory = st.checkbox("Save assistant memory", value=False, help="Disabled by default. Saved memory is user-controlled.")
    st.info("Only the minimum selected records are sent to the configured local model. No cloud service is used by Daybook AI.")
    request = st.text_area("Ask Daybook AI", placeholder="What should I focus on today?")
    if st.button("Send to local model", disabled=not request.strip()):
        records, provenance = context_service.build(include_tasks, include_journal)
        st.caption(f"Sending {len(records)} minimized local record(s) to {MODEL_BASE_URL}.")
        try:
            answer = llm.chat(request, records)
            st.markdown("**Local AI interpretation**")
            st.write(answer)
            st.markdown("**Records consulted**")
            st.json(provenance)
            governance.add_audit(request, provenance, answer)
            if retain_memory:
                governance.create_memory(f"Request: {request}\nResponse: {answer}")
        except LocalModelError as exc:
            st.error(str(exc))
            st.caption("Tasks and journals remain fully available in limited mode.")

    st.divider()
    st.subheader("User-controlled memory")
    for memory in governance.list_memories():
        with st.expander(f"Memory {memory['id']}"):
            edited = st.text_area("Content", memory["content"], key=f"m{memory['id']}")
            c1, c2 = st.columns(2)
            if c1.button("Update", key=f"mu{memory['id']}"):
                governance.update_memory(memory["id"], edited)
                st.rerun()
            if c2.button("Delete", key=f"md{memory['id']}"):
                governance.delete_memory(memory["id"])
                st.rerun()

    st.subheader("Audit history")
    if st.button("Delete all audit history"):
        governance.clear_audit()
        st.rerun()
    for audit in governance.list_audit():
        with st.expander(f"{format_datetime(audit['created_at'])} · {audit['user_request'][:60]}"):
            st.write(audit["recommendation"])
            st.json(audit["records_consulted"])
            if st.button("Delete record", key=f"a{audit['id']}"):
                governance.delete_audit(audit["id"])
                st.rerun()

elif page == "About":
    page_header("About Daybook AI")
    st.write("Daybook AI is a local-first personal task manager and daily journal for working professionals who want a clearer sense of organization before focused work begins.")
    st.write("It combines deterministic task rules with a bounded local language model for explanations, summaries, and task breakdowns. It does not monitor employees, score productivity, or act externally.")
    st.write("Designed and coded by **Michael Schemer**. This application is a prototype for an Ethical AI course project, not a completed commercial product.")
    st.button(
        "Open Ethical AI page",
        on_click=navigate_to,
        args=("Ethical AI",),
    )

elif page == "Ethical AI":
    page_header("Ethical AI", "Safeguards are implemented as product behavior, not only documentation.")
    principles = {
        "Human autonomy": "AI can recommend and propose, but cannot communicate externally or directly change commitments.",
        "Privacy": "SQLite and model context remain local; no telemetry is collected.",
        "Transparency": "Rule selections and AI interpretations are labeled separately, with consulted records shown.",
        "Accountability": "Assistant requests, provenance, responses, and approvals can be audited and deleted.",
        "Data minimization": "Only user-selected, limited fields are sent to the local model.",
        "Human oversight": "AI-originated writes require a visible proposal and explicit confirmation.",
        "User-controlled memory": "Persistent memory is off by default and can be inspected, edited, or deleted.",
        "No surveillance": "No productivity scoring, automatic time tracking, keystroke monitoring, or peer ranking exists. Recorded time is entered manually by the user.",
    }
    for title, text in principles.items():
        st.markdown(f"**{title}:** {text}")

    st.subheader("Interactive action policy")
    examples = {
        "Summarize selected local tasks": "Allowed",
        "Propose creating a task": "Requires confirmation",
        "Complete a task from an AI suggestion": "Requires confirmation",
        "Delete source information automatically": "Prohibited",
        "Send an email or message": "Prohibited",
        "Monitor keystrokes or application usage": "Prohibited",
    }
    choice = st.selectbox("Example action", list(examples))
    result = examples[choice]
    if result == "Allowed":
        st.success(result)
    elif result == "Requires confirmation":
        st.warning(result)
    else:
        st.error(result)
