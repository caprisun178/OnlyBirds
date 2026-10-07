"""Persistence for the bug-report backlog — see
migrations/0007_bug_reports.sql / 0008_bug_reports_owner_and_investigating.sql
and app/services/feedback.py. Same dual-backend pattern as
app/dao/observation_repo.py / pin_repo.py: `InMemoryBugReportRepo` (default,
and what every test runs against) or `PostgresBugReportRepo` (real
persistence, once `DATABASE_URL` is set).

Unlike pinned_birds/observations, `user_id`/`owner` here are plain text, not
FKs into `users` (see the migrations' own comments) — so, unlike
pin_repo.py, there's no auth_provider_id -> users.id lookup dance needed
anywhere below.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from psycopg.rows import dict_row

from app.config import get_settings
from app.dao.db import get_pool
from app.models.report import BugReport, BugReportUpdate, ReportCreate


class BugReportRepo(Protocol):
    async def create(self, report: ReportCreate) -> BugReport: ...
    async def list_all(self) -> list[BugReport]: ...
    async def update(self, report_id: str, payload: BugReportUpdate) -> BugReport | None: ...


class InMemoryBugReportRepo:
    def __init__(self) -> None:
        self._by_id: dict[str, BugReport] = {}

    async def create(self, report: ReportCreate) -> BugReport:
        now = datetime.now(timezone.utc)
        row = BugReport(
            id=uuid.uuid4().hex,
            message=report.message,
            screen=report.screen,
            url=report.url,
            user_id=report.user_id,
            user_agent=report.user_agent,
            status="not_started",
            created_at=now,
            updated_at=now,
        )
        self._by_id[row.id] = row
        return row

    async def list_all(self) -> list[BugReport]:
        return sorted(self._by_id.values(), key=lambda r: r.created_at, reverse=True)

    async def update(self, report_id: str, payload: BugReportUpdate) -> BugReport | None:
        existing = self._by_id.get(report_id)
        if existing is None:
            return None
        fields = payload.model_dump(exclude_unset=True)
        fields["updated_at"] = datetime.now(timezone.utc)
        updated = existing.model_copy(update=fields)
        self._by_id[report_id] = updated
        return updated


class PostgresBugReportRepo:
    """Real persistence against Postgres (Neon). See module docstring."""

    async def create(self, report: ReportCreate) -> BugReport:
        return await asyncio.to_thread(self._create_sync, report)

    async def list_all(self) -> list[BugReport]:
        return await asyncio.to_thread(self._list_all_sync)

    async def update(self, report_id: str, payload: BugReportUpdate) -> BugReport | None:
        return await asyncio.to_thread(self._update_sync, report_id, payload)

    # ---- sync internals, each run off the event loop via to_thread above --

    def _create_sync(self, report: ReportCreate) -> BugReport:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into bug_reports (message, screen, url, user_id, user_agent)
                    values (%s, %s, %s, %s, %s)
                    returning *
                    """,
                    (report.message, report.screen, report.url, report.user_id, report.user_agent),
                )
                row = cur.fetchone()
        return self._row_to_report(row)

    def _list_all_sync(self) -> list[BugReport]:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select * from bug_reports order by created_at desc")
                rows = cur.fetchall()
        return [self._row_to_report(r) for r in rows]

    def _update_sync(self, report_id: str, payload: BugReportUpdate) -> BugReport | None:
        try:
            report_uuid = uuid.UUID(report_id)
        except ValueError:
            return None  # not a real id at all — same "clean 404, not a DB error" reasoning as observation_repo.py

        # Only the fields actually sent get touched — `exclude_unset` so an
        # omitted field isn't overwritten with a stray `null` (e.g. updating
        # just `status` must never blank out an existing `owner`).
        fields = payload.model_dump(exclude_unset=True)
        if not fields:
            return self._get_sync(report_uuid)

        set_clause = ", ".join(f"{column} = %s" for column in fields)
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"update bug_reports set {set_clause}, updated_at = now() where id = %s returning *",
                    (*fields.values(), report_uuid),
                )
                row = cur.fetchone()
        return self._row_to_report(row) if row else None

    def _get_sync(self, report_uuid: uuid.UUID) -> BugReport | None:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select * from bug_reports where id = %s", (report_uuid,))
                row = cur.fetchone()
        return self._row_to_report(row) if row else None

    @staticmethod
    def _row_to_report(row: dict[str, Any]) -> BugReport:
        return BugReport(
            id=str(row["id"]),
            message=row["message"],
            screen=row["screen"],
            url=row["url"],
            user_id=row["user_id"],
            user_agent=row["user_agent"],
            status=row["status"],
            owner=row["owner"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _build_default_repo() -> BugReportRepo:
    if get_settings().database_url:
        return PostgresBugReportRepo()
    return InMemoryBugReportRepo()


bug_report_repo: BugReportRepo = _build_default_repo()
