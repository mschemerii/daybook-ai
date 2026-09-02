from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path

from reportlab import __file__ as reportlab_init
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.models.entities import Task, TimeEntry
from src.models.reporting import ReportResult, ReportTaskNode


TASK_COLUMNS = (
    "id",
    "title",
    "description",
    "priority",
    "due_date",
    "status",
    "source",
    "notes",
    "estimated_hours",
    "task_type",
    "parent_task_id",
    "subtask_order",
    "provenance",
    "completion_criterion",
    "created_at",
    "updated_at",
)
TIME_ENTRY_COLUMNS = (
    "id",
    "task_id",
    "work_date",
    "minutes",
    "note",
    "created_at",
    "updated_at",
)


class ReportExportService:
    def __init__(self) -> None:
        self._ensure_fonts()

    @staticmethod
    def _ensure_fonts() -> None:
        fonts_dir = Path(reportlab_init).resolve().parent / "fonts"
        regular = fonts_dir / "Vera.ttf"
        bold = fonts_dir / "VeraBd.ttf"
        if not regular.exists() or not bold.exists():
            raise RuntimeError("ReportLab bundled Vera fonts are unavailable.")
        registered = set(pdfmetrics.getRegisteredFontNames())
        if "DaybookVera" not in registered:
            pdfmetrics.registerFont(TTFont("DaybookVera", str(regular)))
        if "DaybookVeraBold" not in registered:
            pdfmetrics.registerFont(TTFont("DaybookVeraBold", str(bold)))

    @staticmethod
    def _format_minutes(minutes: int) -> str:
        hours, remainder = divmod(minutes, 60)
        if hours and remainder:
            return f"{hours}h {remainder}m"
        if hours:
            return f"{hours}h"
        return f"{remainder}m"

    @staticmethod
    def _format_timestamp(value: datetime | None) -> str:
        if value is None:
            return ""
        return value.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _task_row(task: Task) -> dict[str, object]:
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "due_date": task.due_date.isoformat() if task.due_date else "",
            "status": task.status,
            "source": task.source,
            "notes": task.notes,
            "estimated_hours": "" if task.estimated_hours is None else task.estimated_hours,
            "task_type": task.task_type,
            "parent_task_id": "" if task.parent_task_id is None else task.parent_task_id,
            "subtask_order": "" if task.subtask_order is None else task.subtask_order,
            "provenance": task.provenance,
            "completion_criterion": task.completion_criterion,
            "created_at": ReportExportService._format_timestamp(task.created_at),
            "updated_at": ReportExportService._format_timestamp(task.updated_at),
        }

    @staticmethod
    def _entry_row(entry: TimeEntry) -> dict[str, object]:
        return {
            "id": entry.id,
            "task_id": entry.task_id,
            "work_date": entry.work_date.isoformat(),
            "minutes": entry.minutes,
            "note": entry.note,
            "created_at": ReportExportService._format_timestamp(entry.created_at),
            "updated_at": ReportExportService._format_timestamp(entry.updated_at),
        }

    @staticmethod
    def _csv_bytes(columns: tuple[str, ...], rows: list[dict[str, object]]) -> bytes:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return stream.getvalue().encode("utf-8")

    @staticmethod
    def _validated_tasks(report: ReportResult) -> list[Task]:
        tasks = [node.task for node in report.iter_nodes()]
        task_ids = [int(task.id) for task in tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Report hierarchy contains duplicate task IDs.")
        exported_ids = set(task_ids)
        for task in tasks:
            if task.parent_task_id is not None and task.parent_task_id not in exported_ids:
                raise ValueError(
                    f"Task {task.id} references parent {task.parent_task_id} outside the report."
                )
        for entry in report.detailed_entries:
            if entry.task_id not in exported_ids:
                raise ValueError(
                    f"Time entry {entry.id} references task {entry.task_id} outside the report."
                )
        actual_total = sum(entry.minutes for entry in report.detailed_entries)
        if actual_total != report.grand_total_minutes:
            raise ValueError(
                "Report total does not reconcile with its detailed time entries."
            )
        return sorted(tasks, key=lambda task: int(task.id))

    def export_csv_zip(self, report: ReportResult) -> bytes:
        tasks = self._validated_tasks(report)
        task_rows = [self._task_row(task) for task in tasks]
        entry_rows = [self._entry_row(entry) for entry in report.detailed_entries]
        task_csv = self._csv_bytes(TASK_COLUMNS, task_rows)
        entry_csv = self._csv_bytes(TIME_ENTRY_COLUMNS, entry_rows)

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, payload in (
                ("tasks.csv", task_csv),
                ("time_entries.csv", entry_csv),
            ):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o600 << 16
                archive.writestr(info, payload)
        return output.getvalue()

    @staticmethod
    def _styles():
        base = getSampleStyleSheet()
        title = ParagraphStyle(
            "DaybookTitle",
            parent=base["Title"],
            fontName="DaybookVeraBold",
            fontSize=16,
            leading=20,
            alignment=TA_LEFT,
            spaceAfter=8,
        )
        heading = ParagraphStyle(
            "DaybookHeading",
            parent=base["Heading2"],
            fontName="DaybookVeraBold",
            fontSize=11,
            leading=14,
            spaceBefore=8,
            spaceAfter=5,
        )
        normal = ParagraphStyle(
            "DaybookNormal",
            parent=base["BodyText"],
            fontName="DaybookVera",
            fontSize=8.5,
            leading=11,
        )
        small = ParagraphStyle(
            "DaybookSmall",
            parent=normal,
            fontSize=7.5,
            leading=9.5,
        )
        return title, heading, normal, small

    @staticmethod
    def _flatten_nodes(report: ReportResult) -> list[tuple[int, ReportTaskNode]]:
        rows: list[tuple[int, ReportTaskNode]] = []

        def visit(node: ReportTaskNode, depth: int) -> None:
            rows.append((depth, node))
            for child in node.children:
                visit(child, depth + 1)

        for root in report.roots:
            visit(root, 0)
        return rows

    def _build_summary_story(self, report: ReportResult):
        title_style, heading_style, normal_style, small_style = self._styles()
        story = [
            Paragraph("Daybook AI - Summary Report", title_style),
            Paragraph(escape(report.report_range.label), normal_style),
            Paragraph(
                f"Recorded total: {self._format_minutes(report.grand_total_minutes)}",
                normal_style,
            ),
            Spacer(1, 0.12 * inch),
            Paragraph("Task summary", heading_style),
        ]
        if not report.roots:
            story.append(Paragraph("No recorded time in this period.", normal_style))
        else:
            data = [
                [
                    Paragraph("Task", small_style),
                    Paragraph("Estimate", small_style),
                    Paragraph("Subtask est.", small_style),
                    Paragraph("Recorded", small_style),
                ]
            ]
            for depth, node in self._flatten_nodes(report):
                indent = "&nbsp;" * (depth * 4)
                task_text = f"{indent}{escape(node.task.title)}"
                if node.task.task_type == "epic":
                    task_text += " <b>(Epic)</b>"
                estimate = (
                    "-"
                    if node.task.estimated_hours is None
                    else f"{node.task.estimated_hours:g}h"
                )
                subtask_estimate = (
                    f"{node.subtask_estimated_hours:g}h"
                    if node.task.task_type == "epic"
                    else "-"
                )
                data.append(
                    [
                        Paragraph(task_text, small_style),
                        Paragraph(estimate, small_style),
                        Paragraph(subtask_estimate, small_style),
                        Paragraph(self._format_minutes(node.display_minutes), small_style),
                    ]
                )
            table = LongTable(
                data,
                repeatRows=1,
                colWidths=[3.6 * inch, 0.8 * inch, 0.9 * inch, 0.9 * inch],
                hAlign="LEFT",
            )
            table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, 0), "DaybookVeraBold"),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(table)

        if report.current_tasks_in_progress:
            story.extend(
                [
                    Spacer(1, 0.12 * inch),
                    Paragraph("Current Tasks in Progress", heading_style),
                ]
            )
            for task in report.current_tasks_in_progress:
                due = task.due_date.isoformat() if task.due_date else "No due date"
                story.append(
                    Paragraph(f"• {escape(task.title)} - due {due}", normal_style)
                )
        return story

    def export_summary_pdf(self, report: ReportResult) -> bytes:
        self._validated_tasks(report)
        output = io.BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=LETTER,
            leftMargin=0.55 * inch,
            rightMargin=0.55 * inch,
            topMargin=0.55 * inch,
            bottomMargin=0.55 * inch,
            title="Daybook AI Summary Report",
        )
        document.build(self._build_summary_story(report))
        return output.getvalue()

    def export_detailed_pdf(self, report: ReportResult) -> bytes:
        self._validated_tasks(report)
        title_style, heading_style, normal_style, small_style = self._styles()
        output = io.BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=LETTER,
            leftMargin=0.55 * inch,
            rightMargin=0.55 * inch,
            topMargin=0.55 * inch,
            bottomMargin=0.55 * inch,
            title="Daybook AI Detailed Report",
        )
        task_names = {int(node.task.id): node.task.title for node in report.iter_nodes()}
        story = [
            Paragraph("Daybook AI - Detailed Report", title_style),
            Paragraph(escape(report.report_range.label), normal_style),
            Paragraph(
                f"Recorded total: {self._format_minutes(report.grand_total_minutes)}",
                normal_style,
            ),
            Spacer(1, 0.12 * inch),
            Paragraph("Task hierarchy", heading_style),
        ]
        if not report.roots:
            story.append(Paragraph("No recorded time in this period.", normal_style))
        else:
            for depth, node in self._flatten_nodes(report):
                prefix = "&#160;" * (depth * 4)
                kind = " (Epic)" if node.task.task_type == "epic" else ""
                story.append(
                    Paragraph(
                        f"{prefix}{escape(node.task.title)}{kind} - "
                        f"{self._format_minutes(node.display_minutes)}",
                        normal_style,
                    )
                )
        story.extend(
            [
                Spacer(1, 0.12 * inch),
                Paragraph("Actual time entries", heading_style),
            ]
        )
        if not report.detailed_entries:
            story.append(Paragraph("No actual time entries in this period.", normal_style))
        else:
            for entry in report.detailed_entries:
                task_name = task_names.get(entry.task_id)
                if task_name is None:
                    raise ValueError(
                        f"Detailed entry {entry.id} references task outside report hierarchy."
                    )
                metadata = Table(
                    [
                        [
                            Paragraph(entry.work_date.isoformat(), small_style),
                            Paragraph(escape(task_name), small_style),
                            Paragraph(self._format_minutes(entry.minutes), small_style),
                        ]
                    ],
                    colWidths=[1.0 * inch, 4.5 * inch, 0.8 * inch],
                    hAlign="LEFT",
                )
                metadata.setStyle(
                    TableStyle(
                        [
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                            ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ]
                    )
                )
                story.append(metadata)
                if entry.note:
                    story.append(Paragraph(escape(entry.note), normal_style))
                story.append(Spacer(1, 0.08 * inch))
        if report.current_tasks_in_progress:
            story.extend(
                [
                    Spacer(1, 0.12 * inch),
                    Paragraph("Current Tasks in Progress", heading_style),
                ]
            )
            for task in report.current_tasks_in_progress:
                due = task.due_date.isoformat() if task.due_date else "No due date"
                story.append(Paragraph(f"• {escape(task.title)} - due {due}", normal_style))
        document.build(story)
        return output.getvalue()
