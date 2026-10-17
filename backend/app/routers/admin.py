"""Admin-only bug backlog — see Presenters/BugBacklog.js and
app/services/feedback.py.

    GET   /admin/bug-reports            -> list[BugReport], newest first
    PATCH /admin/bug-reports/{id}       {status?, owner?} -> BugReport

Admins only: every route here requires a signed-in user whose Google email
is in ADMIN_EMAILS (401 signed out, 403 otherwise) — see
app/routers/deps.py#require_admin and docs/features/user-profiles.md#auth.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.models.report import BugReport, BugReportUpdate
from app.routers.deps import require_admin
from app.services import feedback as feedback_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/bug-reports", response_model=list[BugReport])
async def list_bug_reports() -> list[BugReport]:
    return await feedback_service.list_reports()


@router.patch("/bug-reports/{report_id}", response_model=BugReport)
async def update_bug_report(report_id: str, payload: BugReportUpdate) -> BugReport:
    updated = await feedback_service.update_report(report_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Bug report not found")
    return updated
