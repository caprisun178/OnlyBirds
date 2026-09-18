"""Sticker rules and the user's collectible shelf."""

from __future__ import annotations

from app.dao.sticker_repo import sticker_repo
from app.models.life_list import LifeListEntry
from app.models.sticker import Sticker, StickerShelf, StickerShelfItem, UserSticker
from app.services.life_list import get_life_list


def _species_codes(entries: list[LifeListEntry]) -> set[str]:
    """Collect eBird species codes represented in the user's life list."""
    return {
        entry.species.source_ids["ebird"]
        for entry in entries
        if "ebird" in entry.species.source_ids
    }


def _taxon_groups(entries: list[LifeListEntry]) -> set[str]:
    """Collect taxonomic group labels represented in the user's life list."""
    return {
        entry.species.taxon_group
        for entry in entries
        if entry.species.taxon_group
    }


def _group_progress(group_code: str, entries: list[LifeListEntry]) -> tuple[int, int | None, bool]:
    """Calculate matched species, target size, and completion for a group."""
    group = sticker_repo.get_group(group_code)
    if group is None:
        return 0, None, False
    seen_codes = _species_codes(entries)
    if group.species_codes:
        matched = len(seen_codes.intersection(group.species_codes))
        return matched, len(group.species_codes), matched == len(group.species_codes)
    matched = len(_taxon_groups(entries).intersection(group.taxon_groups))
    return matched, None, matched > 0


def _is_earned(sticker: Sticker, entries: list[LifeListEntry]) -> bool:
    """Determine whether the current life list satisfies a sticker rule."""
    if sticker.rule_type == "first_ever":
        return bool(entries)
    if sticker.rule_type == "count_milestone":
        return len(entries) >= int(sticker.criteria["threshold"])
    if sticker.rule_type == "first_in_group":
        return _group_progress(sticker.criteria["group"], entries)[0] > 0
    if sticker.rule_type == "group_complete":
        progress, target, complete = _group_progress(sticker.criteria["group"], entries)
        return target is not None and progress == target and complete
    return False


async def evaluate_stickers(
    user_id: str,
    observation_id: str | None = None,
    entries: list[LifeListEntry] | None = None,
) -> list[UserSticker]:
    """Award every newly satisfied sticker rule for a user."""
    entries = entries if entries is not None else await get_life_list(user_id)
    existing = {award.sticker_code for award in sticker_repo.list_awards(user_id)}
    awarded: list[UserSticker] = []
    for sticker in sticker_repo.list_stickers():
        if sticker.code not in existing and _is_earned(sticker, entries):
            awarded.append(sticker_repo.award(user_id, sticker.code, observation_id))
    return awarded


def _shelf_item(sticker: Sticker, award: UserSticker | None, entries: list[LifeListEntry]) -> StickerShelfItem:
    """Combine catalog data, award state, and current progress for the UI."""
    progress = target = None
    if sticker.rule_type in {"first_in_group", "group_complete"}:
        progress, target, _ = _group_progress(sticker.criteria["group"], entries)
    elif sticker.rule_type == "count_milestone":
        progress = len(entries)
        target = int(sticker.criteria["threshold"])
    return StickerShelfItem(
        **sticker.model_dump(),
        earned=award is not None,
        awarded_at=award.awarded_at if award else None,
        progress=progress,
        target=target,
    )


async def get_sticker_shelf(user_id: str) -> StickerShelf:
    """Build the user's earned and locked sticker collection."""
    entries = await get_life_list(user_id)
    awards = {award.sticker_code: award for award in sticker_repo.list_awards(user_id)}
    items = [_shelf_item(sticker, awards.get(sticker.code), entries) for sticker in sticker_repo.list_stickers()]
    return StickerShelf(
        earned=[item for item in items if item.earned],
        locked=[item for item in items if not item.earned],
    )


async def list_stickers() -> list[Sticker]:
    """Return the complete sticker catalog for the API."""
    return sticker_repo.list_stickers()