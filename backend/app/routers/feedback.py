"""Beta "Report a problem" endpoint.

    POST /feedback    {message, screen?, url?, user_id?, user_agent?} -> 202

Returns 503 while SMTP_HOST / SMTP_USER / SMTP_PASSWORD / REPORT_EMAIL_TO
aren't set, or 502 if they're set but the actual SMTP send fails (bad
credentials, wrong host/port, the provider rejecting the login, ...) — see
docs/features/report-a-problem.md.
"""

from fastapi import APIRouter, HTTPException, status

from app.dao.email import EmailNotConfigured, EmailSendFailed
from app.models.report import ReportCreate
from app.services import feedback as feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_report(report: ReportCreate) -> dict:
    try:
        await feedback_service.send_report(report)
    except EmailNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EmailSendFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "sent"}
