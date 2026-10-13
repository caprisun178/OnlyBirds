"""Migration calendar endpoints — docs/features/migration-calendar.md §4.

    GET /migration/calendar?lat=&lng=                 full-year bar chart data
    GET /migration/now?lat=&lng=&week=&user_id=       arriving / peak / leaving

Both return 202 `{status: "building", cell_id}` while a location's grid cell
is being built for the first time (about 2 minutes); the frontend polls.
"""

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import JSONResponse

from app.models.migration import BuildingResponse, CalendarResponse, NowResponse
from app.services import life_list as life_list_service
from app.services import migration as migration_service

router = APIRouter(prefix="/migration", tags=["migration"])


def _building(cell_id: str) -> JSONResponse:
    return JSONResponse(status_code=202, content=BuildingResponse(cell_id=cell_id).model_dump())


@router.get(
    "/calendar",
    response_model=CalendarResponse,
    responses={202: {"model": BuildingResponse}},
)
async def get_calendar(
    background_tasks: BackgroundTasks,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
):
    cell_id, calendar, build_args = await migration_service.ensure_cell(lat, lng)
    if build_args:
        background_tasks.add_task(migration_service.build_cell, *build_args)
    if calendar is None:
        return _building(cell_id)
    return await migration_service.calendar(cell_id, calendar, lat)


@router.get(
    "/now",
    response_model=NowResponse,
    responses={202: {"model": BuildingResponse}},
)
async def get_now(
    background_tasks: BackgroundTasks,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    week: int | None = Query(None, ge=1, le=53),
    user_id: str | None = None,
):
    cell_id, calendar, build_args = await migration_service.ensure_cell(lat, lng)
    if build_args:
        background_tasks.add_task(migration_service.build_cell, *build_args)
    if calendar is None:
        return _building(cell_id)
    seen = None
    if user_id:
        entries = await life_list_service.get_life_list(user_id)
        seen = {e.species.scientific_name.lower() for e in entries if e.species.scientific_name}
    return await migration_service.now(
        cell_id, calendar, lat, min(week or migration_service.current_week(), 52), seen
    )
