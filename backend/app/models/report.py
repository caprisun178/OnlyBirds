"""Pydantic models for the beta "Report a problem" button and its admin
backlog screen. Persisted in `bug_reports`
(migrations/0007_bug_reports.sql, 0008_bug_reports_owner_and_investigating.sql)
— replaced the old one-email-per-report behavior (see
app/services/feedback.py) with a triageable backlog instead.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

BugReportStatus = Literal["not_started", "investigating", "not_fixed", "fixed"]


class ReportCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    screen: str | None = None
    url: str | None = None
    user_id: str | None = None
    user_agent: str | None = None


class BugReport(BaseModel):
    id: str
    message: str
    screen: str | None = None
    url: str | None = None
    user_id: str | None = None
    user_agent: str | None = None
    status: BugReportStatus = "not_started"
    # Plain text, not a real user reference — see 0008's own comment: no
    # auth/roles exist yet, so "taking ownership" just means typing a name.
    owner: str | None = None
    created_at: datetime
    updated_at: datetime


class BugReportUpdate(BaseModel):
    """Partial update for the admin backlog screen — status and/or owner,
    only whichever was actually sent (`exclude_unset`, same pattern as
    `ObservationUpdate`) gets touched."""

    status: BugReportStatus | None = None
    owner: str | None = None
