"""Pydantic models for the beta "Report a problem" button.

Not persisted anywhere — a report is just an email (see
app/services/feedback.py). No table, no migration.
"""

from pydantic import BaseModel, Field


class ReportCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    screen: str | None = None
    url: str | None = None
    user_id: str | None = None
    user_agent: str | None = None
