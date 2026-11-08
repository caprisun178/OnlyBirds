"""Sticker rules and the user's collectible shelf."""

from __future__ import annotations

import re

from app.dao.notification_repo import notification_repo
from app.dao.sticker_repo import sticker_repo
from app.data.birds import all_birds
from app.models.life_list import LifeListEntry
from app.models.sticker import (
    Group,
    GroupMember,
    Sticker,
    StickerShelf,
    StickerShelfItem,
    UserSticker,
)
from app.services.life_list import get_life_list


_BIRD_GROUP_BY_SCIENTIFIC_NAME = {
    bird["scientific_name"].casefold(): bird["group"] for bird in all_birds()
}


def _matches_group_member(entry: LifeListEntry, member: GroupMember) -> bool:
    return (
        entry.species.source_ids.get("ebird") == member.ebird_code
        or (entry.species.scientific_name or "").casefold() == member.scientific_name.casefold()
    )


def _matches_taxon_group(entry: LifeListEntry, group: Group) -> bool:
    inferred_group = _BIRD_GROUP_BY_SCIENTIFIC_NAME.get(
        (entry.species.scientific_name or "").casefold()
    )
    if {entry.species.taxon_group, inferred_group} & set(group.taxon_groups):
        return True

    common_name_words = set(re.findall(r"[a-z]+", (entry.species.common_name or "").casefold()))
    return bool(common_name_words & set(group.common_name_terms))


def _matches_group(entry: LifeListEntry, group: Group) -> bool:
    return (
        any(_matches_group_member(entry, member) for member in group.members)
        or _matches_taxon_group(entry, group)
    )


def _group_progress(group_code: str, entries: list[LifeListEntry]) -> tuple[int, int | None, bool]:
    """Calculate matched species, target size, and completion for a group."""
    group = sticker_repo.get_group(group_code)
    if group is None:
        return 0, None, False
    if group.members:
        matched = sum(
            any(_matches_group_member(entry, member) for entry in entries)
            for member in group.members
        )
        return matched, len(group.members), matched == len(group.members)
    matched = sum(_matches_taxon_group(entry, group) for entry in entries)
    return matched, None, matched > 0


def _is_earned(sticker: Sticker, entries: list[LifeListEntry]) -> bool:
    """Determine whether the current life list satisfies a sticker rule."""
    if sticker.rule_type == "first_ever":
        return bool(entries)
    if sticker.rule_type == "count_milestone":
        return len(entries) >= int(sticker.criteria["threshold"])
    if sticker.rule_type == "first_in_group":
        group = sticker_repo.get_group(sticker.criteria["group"])
        return group is not None and any(_matches_group(entry, group) for entry in entries)
    if sticker.rule_type == "group_complete":
        progress, target, complete = _group_progress(sticker.criteria["group"], entries)
        return target is not None and progress == target and complete
    return False


async def evaluate_stickers(
    user_id: str,
    observation_id: str | None = None,
    entries: list[LifeListEntry] | None = None,
) -> list[UserSticker]:
    """Award every newly satisfied sticker rule for a user, and add a
    `sticker_awarded` notification for each one (the bell and feed)."""
    entries = entries if entries is not None else await get_life_list(user_id)
    existing = {award.sticker_code for award in await sticker_repo.list_awards(user_id)}
    awarded: list[UserSticker] = []
    for sticker in sticker_repo.list_stickers():
        if sticker.code not in existing and _is_earned(sticker, entries):
            awarded.append(await sticker_repo.award(user_id, sticker.code, observation_id))
            await notification_repo.insert(
                user_id,
                "sticker_awarded",
                {"sticker_code": sticker.code, "name": sticker.name, "image_url": sticker.image_url},
                # A sticker is earned once, so one notification per user and sticker.
                f"sticker_awarded:{user_id}:{sticker.code}",
            )
    return awarded


def stickers_for(awards: list[UserSticker]) -> list[Sticker]:
    """The catalog entries (name, art, rarity...) for a list of awards."""
    return [s for s in (sticker_repo.get_sticker(a.sticker_code) for a in awards) if s is not None]


def _shelf_item(sticker: Sticker, award: UserSticker | None, entries: list[LifeListEntry]) -> StickerShelfItem:
    """Combine catalog data, award state, and current progress for the UI."""
    progress = target = None
    if sticker.rule_type == "first_in_group":
        group = sticker_repo.get_group(sticker.criteria["group"])
        if group is not None:
            progress = int(any(_matches_group(entry, group) for entry in entries))
            target = 1
    elif sticker.rule_type == "group_complete":
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
    awards = {award.sticker_code: award for award in await sticker_repo.list_awards(user_id)}
    items = [_shelf_item(sticker, awards.get(sticker.code), entries) for sticker in sticker_repo.list_stickers()]
    return StickerShelf(
        earned=[item for item in items if item.earned],
        locked=[item for item in items if not item.earned],
    )


async def list_stickers() -> list[Sticker]:
    """Return the complete sticker catalog for the API."""
    return sticker_repo.list_stickers()