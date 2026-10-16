"""Turns a beta report into one email to the maintainer — see
app/dao/email.py and docs/features/report-a-problem.md. No database table:
a report that's read a day late is still useful once it's landed in an
inbox, and this whole feature is meant to come back out after the beta.
"""

from app.dao import email as email_dao
from app.models.report import ReportCreate


async def send_report(report: ReportCreate) -> None:
    lines = [report.message.strip(), ""]
    if report.screen:
        lines.append(f"Screen: {report.screen}")
    if report.url:
        lines.append(f"URL: {report.url}")
    if report.user_id:
        lines.append(f"User: {report.user_id}")
    if report.user_agent:
        lines.append(f"Browser: {report.user_agent}")

    subject = f"[Only Birds beta] {report.screen or 'Report'}"
    await email_dao.send_email(subject, "\n".join(lines))
