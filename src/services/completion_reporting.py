"""Completion snapshots and observed blocker durations, independent of time-entry dates."""
from datetime import datetime


def completion_rows(snapshot, report_range):
    tasks = {t.id: t for t in snapshot.tasks}
    rows = []
    for event in snapshot.lifecycle:
        if event['task_id'] not in tasks:
            continue
        task = tasks[event['task_id']]
        legacy = event['event'] == 'legacy_completed'
        if legacy:
            if task.status != 'Completed' or any(
                e['task_id'] == task.id and e['event'] == 'completed'
                for e in snapshot.lifecycle
            ):
                continue
        elif event['event'] != 'completed':
            continue
        when = datetime.fromisoformat(event['occurred_at']) if event['occurred_at'] else None
        if when and not report_range.start_date <= when.date() <= report_range.end_date:
            continue
        intervals = []
        reasons = set()
        partial = legacy or any(e['task_id'] == task.id and e['event'] == 'history_started'
                                for e in snapshot.lifecycle)
        for block in snapshot.blocks:
            if block['task_id'] != task.id or when is None:
                continue
            start = datetime.fromisoformat(block['started_at'])
            end = min(datetime.fromisoformat(block['ended_at']), when) if block['ended_at'] else when
            if start <= end:
                intervals.append((start, end))
                reasons.add(block['reason'])
                partial = partial or bool(block['start_unknown'])
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        blocked = sum((end-start).total_seconds() for start, end in merged) / 60
        estimate = event['estimate_hours']
        actual = event['actual_minutes']
        rows.append(dict(task_id=task.id, title=event['title'],
            completed_at=event['occurred_at'] or 'Unknown (legacy)',
            estimate_hours=estimate, actual_minutes=actual,
            variance_minutes=(actual - estimate*60) if actual is not None and estimate is not None else None,
            blocked_minutes=None if legacy else round(blocked, 2),
            history_quality='Partial / unknown before migration' if partial else 'Observed since creation',
            blocker_reasons='; '.join(sorted(reasons)),
            elapsed_hours=round((when-task.created_at).total_seconds()/3600, 2) if when else None,
        ))
    return tuple(rows)
