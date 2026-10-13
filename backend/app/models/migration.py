"""Migration calendar response models — docs/features/migration-calendar.md §4."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Pattern = Literal["resident", "summer", "winter", "passage", "irregular"]
DataQuality = Literal["good", "limited", "insufficient"]


class CalendarSpecies(BaseModel):
    scientific_name: str
    common_name: str | None = None
    pattern: Pattern
    # 52 values, each week's effort-normalized share relative to this
    # species' own peak week (0–1) — a bar-chart row.
    weekly: list[float]


class CalendarResponse(BaseModel):
    cell_id: str
    status: Literal["ready"] = "ready"
    built_at: datetime
    refreshing: bool = False  # older than 90 days; a rebuild is running in the background
    data_quality: DataQuality
    total_obs: int
    species: list[CalendarSpecies]


class BuildingResponse(BaseModel):
    """Returned with 202 while a cell's first build runs — poll again."""

    cell_id: str
    status: Literal["building"] = "building"


class NowSpecies(BaseModel):
    scientific_name: str
    common_name: str | None = None
    pattern: Pattern
    weekly: list[float]
    photo_url: str | None = None
    photo_attribution: str | None = None
    on_life_list: bool | None = None  # only when the request had a user_id


class NowResponse(BaseModel):
    cell_id: str
    week: int
    built_at: datetime
    refreshing: bool = False
    data_quality: DataQuality
    arriving: list[NowSpecies]
    peak: list[NowSpecies]
    leaving: list[NowSpecies]
