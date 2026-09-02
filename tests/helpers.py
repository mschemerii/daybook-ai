from datetime import date


def insert_task(
    db,
    title,
    *,
    due_date=None,
    status='Open',
    estimated_hours=None,
    task_type='standard',
    parent_task_id=None,
    subtask_order=None,
    description='',
    notes='',
):
    with db.connect() as conn:
        cur = conn.execute(
            '''INSERT INTO tasks(
                title, description, priority, due_date, status, source, notes,
                estimated_hours, task_type, parent_task_id, subtask_order,
                provenance, completion_criterion
            ) VALUES (?, ?, 'Medium', ?, ?, 'User', ?, ?, ?, ?, ?, 'user_created', '')''',
            (
                title,
                description,
                due_date.isoformat() if isinstance(due_date, date) else due_date,
                status,
                notes,
                estimated_hours,
                task_type,
                parent_task_id,
                subtask_order,
            ),
        )
        return int(cur.lastrowid)


def insert_entry(db, task_id, work_date, minutes, note=''):
    with db.connect() as conn:
        cur = conn.execute(
            'INSERT INTO time_entries(task_id, work_date, minutes, note) VALUES (?, ?, ?, ?)',
            (task_id, work_date.isoformat(), minutes, note),
        )
        return int(cur.lastrowid)
