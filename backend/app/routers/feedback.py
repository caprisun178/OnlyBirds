"""Beta "Report a problem" endpoint.

    POST /feedback    {message, screen?, url?, user_id?, user_agent?} -> 201 BugReport

Persists to the `bug_reports` backlog (see app/services/feedback.py) instead
of emailing a maintainer — triage happens on the admin bug-backlog screen
(GET/PATCH under /admin/bug-reports, app/routers/admin.py), not an inbox.
"""

from fastapi import APIRouter, Depends, status

from app.models.report import BugReport, ReportCreate
from app.routers.deps import current_user_id
from app.services import feedback as feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=BugReport, status_code=status.HTTP_201_CREATED)
async def create_report(report: ReportCreate, current: str | None = Depends(current_user_id)) -> BugReport:
    # Signed-out users can still report problems; a signed-in one is
    # attributed from their session, not whatever user_id was sent.
    report = report.model_copy(update={"user_id": current})
    return await feedback_service.create_report(report)
