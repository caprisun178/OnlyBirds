"""Response/request shapes for Pinned Birds — see docs/features/pinned-birds.md.

Matched/keyed on `scientific_name`, not eBird's `speciesCode` (the feature
page's own draft) — see migrations/0005_pinned_birds_and_notifications.sql's
comment for why: `scientific_name` is the one species identity every source
(eBird, iNaturalist, and manually-logged sightings) reliably sets.
"""

from datetime import datetime

from pydantic import BaseModel


class PinnedBird(BaseModel):
    id: str | None = None
    user_id: str
    scientific_name: str
    common_name: str | None = None
    region: str
    created_at: datetime | None = None


class PinCreate(BaseModel):
    scientific_name: str
    common_name: str | None = None
    region: str | None = None  # omitted → the caller's own default_region


class PinRegionUpdate(BaseModel):
    region: str
