"""Admin-only bug backlog — see Presenters/BugBacklog.js and
app/services/feedback.py.

    GET   /admin/bug-reports            -> list[BugReport], newest first
    PATCH /admin/bug-reports/{id}       {status?, owner?} -> BugReport

**No real access control yet.** There's no auth/roles in this app at all
(see docs/features/user-profiles.md — still "Planned"), so these routes are
reachable by anyone who knows the URL, same as every other endpoint today.
"Admin-only" currently just means it's linked from Home's nav as a distinct,
clearly-labeled screen, not hidden behind any real permission check — gate
this for real (a role check) once real auth lands.
"""

from fastapi import APIRouter, HTTPException

from app.models.report import BugReport, BugReportUpdate
from app.services import feedback as feedback_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/bug-reports", response_model=list[BugReport])
async def list_bug_reports() -> list[BugReport]:
    return await feedback_service.list_reports()


@router.patch("/bug-reports/{report_id}", response_model=BugReport)
async def update_bug_report(report_id: str, payload: BugReportUpdate) -> BugReport:
    updated = await feedback_service.update_report(report_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Bug report not found")
    return updated
