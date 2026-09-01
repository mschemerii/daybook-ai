from __future__ import annotations

from src.repositories.database import Database


class ReportingSettingsRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_fiscal_start_month(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT fiscal_start_month FROM reporting_settings WHERE id = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("Reporting settings row is missing.")
        month = row["fiscal_start_month"]
        if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise RuntimeError("Stored fiscal start month is invalid.")
        return month

    def set_fiscal_start_month(self, month: int) -> int:
        if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise ValueError("Fiscal start month must be an integer from 1 through 12.")
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE reporting_settings
                SET fiscal_start_month = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (month,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Reporting settings row is missing.")
        return self.get_fiscal_start_month()
