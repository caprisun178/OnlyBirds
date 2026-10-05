"""Business logic for Plan a Trip — see docs/features/plan-a-trip.md.

Fans out to eBird (hotspots) and iNaturalist (last-year species counts)
concurrently, then cross-references the caller's life list if given.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx

from app.dao import ebird, inaturalist
from app.dao.ebird import EBirdConfigError
from app.models.observation import Observation
from app.models.trip import Hotspot, LikelySpecies, TripPlan
from app.services import adapters
from app.services.life_list import get_life_list

_SPECIES_PER_TRIP = 30
_HOTSPOT_SIGHTINGS_PER_PAGE = 50
_HOTSPOT_SIGHTINGS_RADIUS_KM = 2  # tight — a specific hotspot, not the whole trip search area
# Widens the last-year comparison window on each side — see
# _last_year_window()'s docstring for why a narrow (or single-day) trip
# needs this to find any meaningful amount of data. iNaturalist's cost is
# one API call regardless of window size, so this is "free" there.
_DATE_WINDOW_PAD_DAYS = 30
# eBird's historic endpoint, unlike iNaturalist, costs one real HTTP call
# *per day* in the window (see _ebird_historic_window()) — padding it by the
# same 30 days as iNaturalist meant ~61 calls per hotspot click, confirmed
# live at ~29 seconds end to end. A narrower, eBird-only pad cuts that to
# ~15 calls; iNaturalist still covers the full ±30-day window on its own
# (at no extra cost), so the "single-day trip returns nothing" case that
# motivated the padding in the first place is still handled by iNaturalist
# either way.
_EBIRD_DATE_WINDOW_PAD_DAYS = 7
# eBird's historic endpoint has no date-range param (one call per day — see
# _ebird_historic_window()), so even the narrower eBird-only window above is
# still dozens of real calls for one hotspot click. docs/ebird-api.md flags
# this app as having no caching or rate-limiting built yet, so this caps how
# many of those run at once rather than firing all of them simultaneously.
_EBIRD_HISTORIC_CONCURRENCY = 8


def _one_year_earlier(d: date) -> date:
    """Same month/day, one year back — guards the one real edge case (a
    Feb 29 trip date in a year that isn't itself a leap year) by nudging
    back a day rather than crashing.
    """
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def _last_year_window(start_date: date, end_date: date, pad_days: int = _DATE_WINDOW_PAD_DAYS) -> tuple[date, date]:
    """`start_date`..`end_date` shifted back one year, then padded `pad_days`
    on each side (default `_DATE_WINDOW_PAD_DAYS`, iNaturalist's window).
    A trip's exact dates shifted back exactly one year — especially a
    single-day trip, a 1-day window a year ago — is too thin a slice of
    real observation density to reliably return anything (a real "hotspot
    sightings map came back empty" case). The padding trades a bit of
    seasonal precision for a window wide enough to actually have data,
    while still centering on the right time of year rather than searching
    broadly across all seasons. `hotspot_sightings()` passes a smaller
    `pad_days` for its eBird half — see `_EBIRD_DATE_WINDOW_PAD_DAYS`'s
    comment for why.
    """
    pad = timedelta(days=pad_days)
    d1 = _one_year_earlier(start_date) - pad
    d2 = _one_year_earlier(end_date) + pad
    return d1, d2


async def plan_trip(
    lat: float,
    lng: float,
    start_date: date,
    end_date: date,
    radius_km: int = 25,
    user_id: str | None = None,
) -> TripPlan:
    """Suggested hotspots + likely species for a trip on `start_date`..
    `end_date` (this year or any year) — "likely" means "reported this often
    in roughly the same window last year" (see docs/features/plan-a-trip.md
    for why that's the honest scope, not a multi-year average). `user_id`
    is optional: given, each species' `new_for_you` is set from the caller's
    actual life list; omitted, it's left `None` rather than guessed.
    """
    d1, d2 = _last_year_window(start_date, end_date)

    hotspots_task = _safe_hotspots(lat, lng, radius_km)
    species_task = inaturalist.get_species_counts(
        lat, lng, radius_km, d1=d1.isoformat(), d2=d2.isoformat(), per_page=_SPECIES_PER_TRIP
    )
    life_list_task = get_life_list(user_id) if user_id else _noop()

    raw_hotspots, raw_species, life_list_entries = await asyncio.gather(
        hotspots_task, species_task, life_list_task
    )

    hotspots = [adapters.from_ebird_hotspot(h) for h in raw_hotspots]
    hotspots.sort(key=lambda h: h.species_all_time, reverse=True)

    likely_species = [adapters.from_inat_species_count(r) for r in raw_species]
    if user_id:
        seen = {
            e.species.scientific_name
            for e in life_list_entries
            if e.species.scientific_name
        }
        for sp in likely_species:
            sp.new_for_you = bool(sp.species.scientific_name) and sp.species.scientific_name not in seen

    return TripPlan(hotspots=hotspots, likely_species=likely_species)


# hotspot_sightings()'s result cache, keyed on every input that affects the
# result. No TTL/eviction — the data is a year-old (or older) window that
# genuinely barely changes within a process's lifetime, and this is a plain
# in-process dict (cleared on restart), not the shared `sighting_cache`
# table the full Explore Map spec still has planned. Only a result where the
# iNaturalist call actually succeeded gets cached (see the `inat_ok` check
# below) — a transient failure is never baked in as if it were a real,
# final answer; the next tap just tries again.
_hotspot_sightings_cache: dict[tuple, list[Observation]] = {}


async def hotspot_sightings(
    lat: float,
    lng: float,
    start_date: date,
    end_date: date,
    radius_km: int = _HOTSPOT_SIGHTINGS_RADIUS_KM,
    hotspot_loc_id: str | None = None,
) -> list[Observation]:
    """The actual sightings behind one hotspot's slice of the "likely
    species" window — same `_last_year_window()` date math `plan_trip()`
    uses, scoped tightly around a single hotspot's coordinates (not the
    whole trip search radius), so a user who taps a suggested hotspot can
    see exactly what was seen there, and roughly when, this time last year.

    `hotspot_loc_id`, if given, also merges in eBird checklist data for that
    exact hotspot across a narrower window (see `_ebird_historic_window()`
    and `_EBIRD_DATE_WINDOW_PAD_DAYS`). Omitted — or no `EBIRD_API_KEY`
    configured — results are iNaturalist-only, same as before this was added.

    The combined result is cached per (lat, lng, radius_km, dates, loc_id) —
    a repeat tap on the same hotspot is instant instead of re-paying
    eBird's per-day call cost; see `_hotspot_sightings_cache`.
    """
    cache_key = (lat, lng, radius_km, start_date, end_date, hotspot_loc_id)
    if cache_key in _hotspot_sightings_cache:
        return _hotspot_sightings_cache[cache_key]

    d1, d2 = _last_year_window(start_date, end_date)

    inat_task = _safe_inat_nearby(
        lat, lng, radius_km, per_page=_HOTSPOT_SIGHTINGS_PER_PAGE, d1=d1.isoformat(), d2=d2.isoformat()
    )
    if hotspot_loc_id:
        ebird_d1, ebird_d2 = _last_year_window(start_date, end_date, pad_days=_EBIRD_DATE_WINDOW_PAD_DAYS)
        ebird_task = _ebird_historic_window(hotspot_loc_id, ebird_d1, ebird_d2)
    else:
        ebird_task = _noop()

    (raw_inat, inat_ok), raw_ebird = await asyncio.gather(inat_task, ebird_task)

    sightings = [adapters.from_inaturalist(r) for r in raw_inat] + [adapters.from_ebird(r) for r in raw_ebird]
    sightings.sort(key=lambda o: o.observed_at, reverse=True)

    if inat_ok:
        _hotspot_sightings_cache[cache_key] = sightings
    return sightings


async def _safe_inat_nearby(
    lat: float, lng: float, radius_km: int, per_page: int, d1: str, d2: str
) -> tuple[list[dict], bool]:
    """A single iNaturalist call failing (a timeout, a flaky response — a
    real `httpx.RemoteProtocolError`, "Server disconnected without sending a
    response", happened live mid-session, alongside ~15-20 concurrent eBird
    calls) used to blank out the *whole* `hotspot_sightings()` response —
    including an otherwise-successful eBird half fetched concurrently.
    Same best-effort philosophy `_ebird_historic_window()`'s per-day calls
    already use: swallow it and return what we have (nothing, here), rather
    than letting one upstream hiccup 502 the entire request. The `bool`
    tells the caller whether to trust this enough to cache it.
    """
    try:
        raw = await inaturalist.get_nearby_observations(lat, lng, radius_km, per_page=per_page, d1=d1, d2=d2)
        return raw, True
    except httpx.HTTPError:
        return [], False


async def _ebird_historic_window(loc_id: str, d1: date, d2: date) -> list[dict]:
    """One eBird checklist-observation row per species, per day, for every
    day in `[d1, d2]` at this hotspot — `region_code` accepts a hotspot's
    own `locId` (confirmed live; see `dao/ebird.py#get_historic_checklist`'s
    docstring), so this needs no lat/lng→region-code lookup, just a call per
    day since the endpoint has no date-range param. `_EBIRD_HISTORIC_CONCURRENCY`
    caps how many of those run at once. `EBirdConfigError` (no key
    configured) or `httpx.HTTPError` (bad key, rate limit, eBird down) on
    any single day is swallowed rather than failing the whole request —
    iNaturalist's half of `hotspot_sightings()` is still useful on its own,
    unlike `_safe_hotspots()`'s single all-or-nothing call.
    """
    days = [d1 + timedelta(days=i) for i in range((d2 - d1).days + 1)]
    semaphore = asyncio.Semaphore(_EBIRD_HISTORIC_CONCURRENCY)

    async def fetch_one(d: date) -> list[dict]:
        async with semaphore:
            try:
                return await ebird.get_historic_checklist(loc_id, d)
            except (EBirdConfigError, httpx.HTTPError):
                return []

    results = await asyncio.gather(*(fetch_one(d) for d in days))
    return [row for day_rows in results for row in day_rows]


async def _safe_hotspots(lat: float, lng: float, radius_km: int) -> list[dict]:
    """No `EBIRD_API_KEY` configured shouldn't take down the whole trip
    plan — just means no hotspot suggestions, same graceful-degradation
    pattern `services/sightings.py#_safe_ebird` already uses.
    """
    try:
        return await ebird.get_hotspots_near(lat, lng, radius_km)
    except EBirdConfigError:
        return []


async def _noop() -> list:
    return []
