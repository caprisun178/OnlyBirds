"""Turns a beta report into a `bug_reports` row instead of an email — see
app/dao/bug_report_repo.py and migrations/0007_bug_reports.sql. Used to be
one email per report (app/dao/email.py); that only ever reached one inbox
and nothing tracked whether a reported problem actually got fixed. This
persists every report so the admin bug-backlog screen
(Presenters/BugBacklog.js) can triage them instead.
"""

from app.dao.bug_report_repo import bug_report_repo
from app.models.report import BugReport, BugReportUpdate, ReportCreate


async def create_report(report: ReportCreate) -> BugReport:
    return await bug_report_repo.create(report)


async def list_reports() -> list[BugReport]:
    return await bug_report_repo.list_all()


async def update_report(report_id: str, payload: BugReportUpdate) -> BugReport | None:
    return await bug_report_repo.update(report_id, payload)
