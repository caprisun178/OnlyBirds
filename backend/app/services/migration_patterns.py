"""Pure classification rules for the migration calendar — no I/O, so they're
unit-testable with plain lists and tunable without touching the database.
See docs/features/migration-calendar.md §1 ("Classifying a species").

Inputs are a species' weekly observation counts and the location's weekly
*total* bird observations (the effort denominator), both keyed by
iNaturalist's week of year (1–53). Week 53 only exists in some years and is
folded into week 52 everywhere here, so every output is exactly 52 weeks.
"""

from __future__ import annotations

from typing import Literal

Pattern = Literal["resident", "summer", "winter", "passage", "irregular"]
Movement = Literal["arriving", "peak", "leaving"]

WEEKS = 52
MIN_TOTAL_OBS = 20  # fewer observations than this all year: too little data to call...
MIN_OBS_SHARE = 0.0002  # ...or than 0.02% of the area's observations, in data-rich areas
MIN_WEEKS_SEEN = 3  # seen in fewer distinct weeks than this: a one-off, not a pattern
MAX_ONE_WEEK_SHARE = 0.6  # more than this share of all its sightings in one week: one rarity everyone photographed
PRESENT_FRACTION = 0.15  # a week counts as "present" at >= 15% of the species' own peak
RESIDENT_MIN_WEEKS = 44
MOSTLY_PRESENT = 0.5  # share of a season's weeks that must be "present"
MOSTLY_ABSENT = 0.25  # ...or at most this share, to count as absent that season
PEAK_FRACTION = 0.7

# 0-based week indexes (week 1 = index 0), northern hemisphere.
_JAN_FEB = range(0, 8)  # weeks 1–8
_JUN_JUL = range(21, 30)  # weeks 22–30
_SPRING = range(9, 23)  # weeks 10–23
_FALL = range(31, 48)  # weeks 32–48


def fold_weeks(by_week: dict[int, int]) -> list[int]:
    """`{week: count}` (1–53) -> 52 counts, week 53 added into week 52."""
    out = [0] * WEEKS
    for week, count in by_week.items():
        index = min(max(int(week), 1), WEEKS) - 1
        out[index] += count
    return out


def relative_weekly(counts: list[int], totals: list[int]) -> list[float]:
    """Effort-normalized, smoothed, then scaled so the species' own peak
    week is 1.0 — what a bar-chart row needs. All zeros if never seen."""
    shares = [c / t if t else 0.0 for c, t in zip(counts, totals)]
    # Circular 3-week mean: week 52 neighbours week 1 (winter wraps).
    smooth = [(shares[i - 1] + shares[i] + shares[(i + 1) % WEEKS]) / 3 for i in range(WEEKS)]
    peak = max(smooth)
    return [round(s / peak, 4) if peak else 0.0 for s in smooth]


def min_obs_for(area_total_obs: int) -> int:
    """The minimum yearly observations to classify a species at all, scaled
    to the area: 20 in Raleigh (~100k observations/year), 43 in Seattle
    (~214k), never below 20. Without the scaling, escaped peafowl and a
    handful of Ross's Goose records came out as "seasonal visitors" in
    data-rich cells; with a floor of 10, year-round feeder birds that are
    mostly photographed in winter (Tufted Titmouse, Song Sparrow) came out
    as "winter visitors" in a data-poor rural cell."""
    return max(MIN_TOTAL_OBS, round(area_total_obs * MIN_OBS_SHARE))


def classify(
    counts: list[int], relative: list[float], southern: bool = False, min_obs: int = MIN_TOTAL_OBS
) -> Pattern:
    """One species' seasonal pattern from its 52 folded weekly counts and
    its `relative_weekly()` curve. Southern-hemisphere locations swap the
    summer and winter blocks. `min_obs`: see `min_obs_for()`."""
    total = sum(counts)
    if total < min_obs or not any(relative):
        return "irregular"
    # A single rare bird that many people photographed (Kirtland's Warbler
    # near Raleigh: 17 records, 76% of them in one week) isn't a migration.
    if sum(1 for c in counts if c) < MIN_WEEKS_SEEN or max(counts) / total > MAX_ONE_WEEK_SHARE:
        return "irregular"

    present = [r >= PRESENT_FRACTION for r in relative]
    if sum(present) >= RESIDENT_MIN_WEEKS:
        return "resident"

    def fraction(block: range) -> float:
        return sum(present[i] for i in block) / len(block)

    winter_block, summer_block = (_JUN_JUL, _JAN_FEB) if southern else (_JAN_FEB, _JUN_JUL)
    winter, summer = fraction(winter_block), fraction(summer_block)

    if winter >= MOSTLY_PRESENT and summer >= MOSTLY_PRESENT:
        return "resident"  # partial migrants: thinner some weeks, but here year-round
    if summer >= MOSTLY_PRESENT and winter <= MOSTLY_ABSENT:
        return "summer"
    if winter >= MOSTLY_PRESENT and summer <= MOSTLY_ABSENT:
        return "winter"
    if winter <= MOSTLY_ABSENT and summer <= MOSTLY_ABSENT and (fraction(_SPRING) > 0 or fraction(_FALL) > 0):
        return "passage"
    return "irregular"


SEASON_EDGE_WEEKS = 4  # how close to a seasonal visitor's arrival/departure counts as "arriving"/"leaving"


def movement(relative: list[float], week: int, pattern: Pattern = "passage") -> Movement | None:
    """Where a migrant is in its cycle in `week` (1–53), or `None` if it's
    not around — or, for a summer/winter visitor, settled in for the season.

    Passage migrants go by the curve's slope: at/near peak, rising, falling.
    Summer/winter visitors can't: their numbers in photos drift for reasons
    that aren't migration (a summer breeder is photographed less once the
    spring singing stops), and slope-based rules called nesting Purple
    Martins and Wood Thrushes "leaving" in early May near Raleigh. So for
    them it's about the edges of their stay: absent within the last few
    weeks = arriving, usually gone within the next few = leaving.
    """
    i = min(max(week, 1), WEEKS) - 1
    now = relative[i]
    if now < PRESENT_FRACTION:
        return None

    if pattern in ("summer", "winter"):
        absent = lambda j: relative[j % WEEKS] < PRESENT_FRACTION  # noqa: E731
        recently_absent = any(absent(i - k) for k in range(1, SEASON_EDGE_WEEKS + 1))
        soon_absent = any(absent(i + k) for k in range(1, SEASON_EDGE_WEEKS + 1))
        if recently_absent and not soon_absent:
            return "arriving"
        if soon_absent and not recently_absent:
            return "leaving"
        if not (recently_absent or soon_absent):
            return None  # here for the season, not moving
        # A stay this short behaves like a passage migrant: fall through.

    if now >= PEAK_FRACTION:
        return "peak"
    return "arriving" if now > relative[i - 2] else "leaving"
