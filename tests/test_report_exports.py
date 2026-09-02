import csv
from dataclasses import replace
from datetime import date, datetime
from io import BytesIO, StringIO
import zipfile

from pypdf import PdfReader

from src.repositories.reporting_repository import ReportingRepository
from src.services.report_export_service import (
    ReportExportService,
    TASK_COLUMNS,
    TIME_ENTRY_COLUMNS,
)
from src.services.reporting_service import ReportingService
from src.utils.report_ranges import custom_range, monthly_range
from tests.helpers import insert_entry, insert_task


def build_report(db, start=date(2026, 9, 1), end=date(2026, 9, 30)):
    return ReportingService(ReportingRepository(db)).build_report(
        custom_range(start, end), today=date(2026, 9, 15)
    )


def read_csv_from_zip(payload, member):
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        text = archive.read(member).decode('utf-8')
    return list(csv.DictReader(StringIO(text)))


def pdf_text(payload):
    reader = PdfReader(BytesIO(payload))
    return '\n'.join(page.extract_text() or '' for page in reader.pages), len(reader.pages)


def test_zip_has_exact_members_frozen_schema_and_reconciled_minutes(db):
    epic = insert_task(db, 'Export epic', task_type='epic', estimated_hours=10)
    child = insert_task(db, 'Export child', parent_task_id=epic, subtask_order=0)
    unrelated = insert_task(db, 'Unrelated')
    insert_entry(db, child, date(2026, 9, 1), 61, 'Café résumé / 作業')
    report = build_report(db)
    payload = ReportExportService().export_csv_zip(report)

    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert archive.namelist() == ['tasks.csv', 'time_entries.csv']
        task_text = archive.read('tasks.csv').decode('utf-8')
        entry_text = archive.read('time_entries.csv').decode('utf-8')
        assert 'Café résumé / 作業' in entry_text
        assert task_text.splitlines()[0].split(',') == list(TASK_COLUMNS)
        assert entry_text.splitlines()[0].split(',') == list(TIME_ENTRY_COLUMNS)

    tasks = read_csv_from_zip(payload, 'tasks.csv')
    entries = read_csv_from_zip(payload, 'time_entries.csv')
    assert [int(row['id']) for row in tasks] == [epic, child]
    assert unrelated not in [int(row['id']) for row in tasks]
    child_row = next(row for row in tasks if int(row['id']) == child)
    assert int(child_row['parent_task_id']) == epic
    assert sum(int(row['minutes']) for row in entries) == report.grand_total_minutes == 61
    assert entries[0]['work_date'] == '2026-09-01'
    assert entries[0]['minutes'] == '61'


def test_zip_output_is_byte_for_byte_deterministic(db):
    task = insert_task(db, 'Stable')
    insert_entry(db, task, date(2026, 9, 1), 30, 'same')
    report = build_report(db)
    exporter = ReportExportService()
    assert exporter.export_csv_zip(report) == exporter.export_csv_zip(report)


def test_summary_pdf_contains_hierarchy_totals_and_utf8_latin_text(db):
    epic = insert_task(db, 'Résumé epic', task_type='epic', estimated_hours=12)
    child = insert_task(db, 'Café task', parent_task_id=epic, subtask_order=0, estimated_hours=3)
    insert_entry(db, child, date(2026, 9, 1), 90, 'José – analysis')
    report = build_report(db)
    payload = ReportExportService().export_summary_pdf(report)
    text, pages = pdf_text(payload)
    assert pages >= 1
    assert 'Daybook AI' in text
    assert 'Résumé epic' in text
    assert 'Café task' in text
    assert '1h 30m' in text


def test_detailed_pdf_contains_oldest_to_newest_entries_and_long_content_survives(db):
    task = insert_task(db, 'Long report task')
    first = 'FIRST ENTRY ' + ('alpha beta gamma ' * 220)
    last = 'LAST ENTRY survives pagination'
    insert_entry(db, task, date(2026, 9, 1), 30, first)
    for day in range(2, 21):
        insert_entry(db, task, date(2026, 9, day), 15, f'entry {day} ' + ('content ' * 40))
    insert_entry(db, task, date(2026, 9, 21), 45, last)
    report = build_report(db)
    text, pages = pdf_text(ReportExportService().export_detailed_pdf(report))
    assert pages > 1
    assert 'FIRST ENTRY' in text
    assert 'LAST ENTRY survives pagination' in text
    assert text.index('FIRST ENTRY') < text.index('LAST ENTRY survives pagination')


def test_empty_pdf_exports_are_readable(db):
    report = build_report(db)
    exporter = ReportExportService()
    summary_text, _ = pdf_text(exporter.export_summary_pdf(report))
    detailed_text, _ = pdf_text(exporter.export_detailed_pdf(report))
    assert 'No recorded time in this period.' in summary_text
    assert 'No actual time entries in this period.' in detailed_text


def test_summary_pdf_includes_current_tasks_in_progress_for_current_month(db):
    insert_task(db, 'Follow up task', due_date=date(2026, 9, 22))
    report = ReportingService(ReportingRepository(db)).build_report(
        monthly_range(date(2026, 9, 1)), today=date(2026, 9, 15)
    )
    text, _ = pdf_text(ReportExportService().export_summary_pdf(report))
    assert 'Current Tasks in Progress' in text
    assert 'Follow up task' in text


def test_exports_fail_loudly_when_report_total_does_not_reconcile(db):
    task = insert_task(db, 'Mismatch')
    insert_entry(db, task, date(2026, 9, 1), 30)
    report = build_report(db)
    inconsistent = replace(report, grand_total_minutes=31)
    exporter = ReportExportService()
    for action in (
        exporter.export_csv_zip,
        exporter.export_summary_pdf,
        exporter.export_detailed_pdf,
    ):
        try:
            action(inconsistent)
        except ValueError as exc:
            assert 'does not reconcile' in str(exc)
        else:
            raise AssertionError('Inconsistent report export did not fail loudly')


def test_csv_includes_all_recursive_ancestors_and_preserves_parent_chain(db):
    root = insert_task(db, 'Top epic', task_type='epic')
    middle = insert_task(
        db,
        'Nested epic',
        task_type='epic',
        parent_task_id=root,
        subtask_order=0,
    )
    leaf = insert_task(
        db,
        'Leaf task',
        parent_task_id=middle,
        subtask_order=0,
    )
    insert_entry(db, leaf, date(2026, 9, 2), 45, 'leaf work')

    tasks = read_csv_from_zip(
        ReportExportService().export_csv_zip(build_report(db)),
        'tasks.csv',
    )
    rows = {int(row['id']): row for row in tasks}
    assert set(rows) == {root, middle, leaf}
    assert rows[root]['parent_task_id'] == ''
    assert int(rows[middle]['parent_task_id']) == root
    assert int(rows[leaf]['parent_task_id']) == middle


def test_csv_timestamps_follow_sqlite_storage_convention(db):
    task = insert_task(db, 'Timestamp task')
    insert_entry(db, task, date(2026, 9, 3), 20, 'timestamp check')
    payload = ReportExportService().export_csv_zip(build_report(db))

    task_row = read_csv_from_zip(payload, 'tasks.csv')[0]
    entry_row = read_csv_from_zip(payload, 'time_entries.csv')[0]
    for row in (task_row, entry_row):
        datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S')
        datetime.strptime(row['updated_at'], '%Y-%m-%d %H:%M:%S')
