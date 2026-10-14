"""Test Your Skill. See docs/features/test-your-skill.md.

    GET /quiz/question?mode=photo|audio&region_code=world&family=
    GET /quiz/filters?region_code=world
"""

from fastapi import APIRouter, HTTPException, Query

from app.dao.ebird import EBirdConfigError
from app.services import quiz as quiz_service
from app.services.quiz import DEFAULT_REGION, QuizMode

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.get("/question")
async def get_question(
    mode: QuizMode = Query(),
    region_code: str = Query(default=DEFAULT_REGION),
    family: str | None = Query(default=None),
):
    try:
        return await quiz_service.get_question(mode, region_code=region_code, family=family)
    except quiz_service.NoQuestionAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EBirdConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/filters")
async def get_filters(region_code: str = Query(default=DEFAULT_REGION)):
    try:
        return await quiz_service.get_filter_options(region_code)
    except EBirdConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
