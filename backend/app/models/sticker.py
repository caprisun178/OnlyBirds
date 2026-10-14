from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RuleType = Literal[
    "first_ever",
    "first_in_group",
    "group_complete",
    "count_milestone",
    "region_complete",
    "first_in_region",
]
Rarity = Literal["common", "uncommon", "rare"]


class Sticker(BaseModel):
    code: str
    name: str
    description: str | None = None
    image_url: str | None = None
    rule_type: RuleType
    criteria: dict = Field(default_factory=dict)
    rarity: Rarity = "common"
    sort_order: int = 0


class Group(BaseModel):
    code: str
    kind: Literal["rank", "set"]
    rank_query: str | None = None
    species_codes: list[str] = Field(default_factory=list)
    taxon_groups: list[str] = Field(default_factory=list)


class UserSticker(BaseModel):
    user_id: str
    sticker_code: str
    awarded_at: datetime
    observation_id: str | None = None


class StickerShelfItem(Sticker):
    earned: bool = False
    awarded_at: datetime | None = None
    progress: int | None = None
    target: int | None = None


class StickerShelf(BaseModel):
    earned: list[StickerShelfItem]
    locked: list[StickerShelfItem]