# Test your skill

> **Status:** Built, on `working/sparisi/Feature-test-your-skill` (cut from
> the same point as `dev/current` — it does **not** have Pinned Birds, Plan
> a Trip, or Explore Map's selected-pin highlighting, all of which live on
> the separate `working/sparisi/Feature-plan-a-trip` branch. Nothing in
> this feature depends on any of that, by design — see
> [§2](#2-where-the-data-comes-from-and-where-it-goes)). Backend and
> frontend both verified live, including every filter combination described
> below.

## 1. What you're building

A quick multiple-choice quiz: a real bird photo or a real call/song
recording, four common-name choices, pick one, see immediately whether you
were right. A running score for the session ("3/5 correct"). **Nothing is
recorded** — no database row, no history, no login requirement; refresh the
page and the score is gone. That's intentional, not a cut corner: this is a
"test yourself for fun" feature, not a tracked leaderboard, and that's what
makes it so cheap to build (see §3 — there's no database change at all).

Two modes, user-switchable: **By Sight** (photo) and **By Ear** (audio).
Optional filters, combinable: **type** (a real taxonomic family — "New
World Warblers," "Crows, Jays, and Magpies," "Owls," ...) and **region**
(any eBird region — country, state/province, or county). Both default to
unfiltered ("Any type," "Anywhere") — the original "stay random, any and
all birds" request this feature started from.

Reached from a new **Test Your Skill** button on `Home.js`'s header nav,
alongside Life List / Add Observation / Plan a Trip.

### Where the questions come from

The first version of this page pulled from `app/data/birds.py`'s 72-species
curated set (built for Add Observation's describe-and-guess flow). That
set is color/shape-grouped ("looks blue," "looks like a hawk"), not
taxonomic — it has no clean idea of "warblers" or "corvids" at all, and
color groups only had 3-6 species each, too thin for a real filter. Once
filtering was requested, the quiz was repointed at
**`app/dao/region_repo.py#get_checklist(region_code)`** instead — already
built and cached for Life List's region completion view, so this isn't new
infrastructure, just a new caller of it:

- `region_code="world"` is eBird's own broadest region and genuinely means
  "everything" — confirmed live: ~10,800 species, every real family
  ("New World Warblers": 115 species, "Crows, Jays, and Magpies": 136,
  "Owls": 222, 249 distinct families total). That's the unfiltered default.
- Any narrower `region_code` (a country, state/province, or county — same
  codes Life List's region picker already produces) narrows the pool to
  species actually on that region's real checklist.
- Each checklist row already carries `family_common_name` (eBird's own
  taxonomy) — that's both the **type** filter's values and the basis for
  picking sensible distractors (see below), no new "what's confusable with
  this" logic needed, it's the same field Life List's own "bird type"
  filter already uses.

A question: pick one random species from the filtered checklist, pull a
**real** photo or recording for it, pick up to 3 others from its own
`family_common_name` within that same (possibly filtered) checklist as the
wrong answers, shuffle all 4, done.

!!! note "Commons coverage is much spottier across the full taxonomy than the curated 72"
    Confirmed live: a random sample of 30 species from the unfiltered
    *world* pool (deliberately including very obscure, non-North-American
    birds) had a real Commons photo 21/30 of the time (~70%) — well below
    the curated set's near-100% coverage of common backyard species.
    `_MAX_ATTEMPTS = 12` in `app/services/quiz.py` is calibrated against
    that number: at a 70% per-try success rate, 12 tries fails to find
    *any* usable species with probability ~0.3¹² — negligible for a broad
    pool. A narrow filter (a thin family, or a small region, or both at
    once) can still legitimately exhaust its own pool before finding one
    with real media — that's a real "try a wider filter" outcome
    (`NoQuestionAvailable`, surfaced as a 503 with a clear message), not a
    bug to silently retry forever.

!!! note "A question must use a *real* photo/recording, never the placeholder"
    `bird_photos.py#get_stock_photo()` always returns *something* — a real
    Wikimedia Commons photo, or (if Commons has nothing) a generated
    placeholder image with the species' own common name printed on it as
    text. That's a fine fallback everywhere else it's used (a seen species
    without the user's own photo still needs *some* image), but it would be
    a literal, visible answer key here. The quiz must check
    `attribution is None` (the placeholder's tell — see that function's own
    docstring) and skip to a different random species if so.
    `bird_audio.py#get_audio()` is simpler: it has no placeholder at all —
    returns `None` outright when Commons has nothing — so the same
    "try a different species" loop applies, just without needing to check
    an attribution field.

    Both lookups are already cached (`bird_photos.py`'s disk cache,
    `bird_audio.py`'s in-memory one), so after the first few questions of a
    session, "does this species have real media" is a cache hit, not a live
    Commons call — the retry loop stays cheap in practice even though
    Commons coverage isn't 100% of the 72-species set.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| The species pool, filtered by region/family | eBird taxonomy + region checklists, via the existing `app/dao/region_repo.py#get_checklist()` | its own existing process-lifetime cache (30-day staleness, same as Life List already relies on) — not duplicated here |
| Region-picker options (country/state/county) | eBird, via the existing `GET /regions` endpoint (`app/routers/life_list.py`) | reused directly from the frontend — no new backend endpoint for this part |
| Photo | Wikimedia Commons, via the existing `app/dao/bird_photos.py` | its own existing cache — not duplicated here |
| Audio | Wikimedia Commons, via the existing `app/dao/bird_audio.py` | its own existing cache — not duplicated here |
| The question (which bird, which 4 choices) | generated fresh, server-side, per request | **nowhere — not persisted at all** |
| The user's answer / score | client-side only | **nowhere — not sent to the backend at all.** The question response already includes the correct answer (see §4's example); since nothing is scored or recorded server-side, there's no integrity reason to hide it behind a separate "submit answer" round trip — grading happens entirely in the browser |

**No external API beyond what's already integrated** (eBird, Wikimedia
Commons — both via code that already existed before this feature). **No
database change** — this is the one feature in this repo with an empty §3.

## 3. Database changes (SQL)

None. No new table, no migration file. If a later version wants a
leaderboard or a "my quiz history," that's a deliberate, separate decision
(and a real scope change — it would mean actually handling user identity
and persistence here, which this version explicitly avoids) — don't add
persistence to this feature quietly as a "small addition" without recognizing
that's what it is.

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/quiz/question?mode=photo\|audio&region_code=&family=` | one fresh question, graded answer included. `region_code` defaults to `"world"`; `family` is optional (omit for "Any type") |
| `GET` | `/quiz/filters?region_code=` | every taxonomic family actually present in that region's checklist, each with a species count — feeds the "type" dropdown so it never offers a filter with nothing behind it |
| `GET` | `/regions?parent=&type=` | **not new** — Life List's existing region-picker endpoint, reused as-is for the "region" filter's country/state/county cascade |

Both quiz endpoints 503 (not 500) on a missing `EBIRD_API_KEY` or an
unsatisfiable filter combination (`NoQuestionAvailable`) — both are
expected, recoverable states, not server errors.

### Example — `GET /quiz/question?mode=photo&family=New%20World%20Warblers`

```json
{
  "mode": "photo",
  "photo_url": "https://upload.wikimedia.org/...",
  "audio_url": null,
  "attribution": "John Smith / Wikimedia Commons, CC BY-SA 4.0",
  "choices": [
    {"common_name": "Tennessee Warbler", "scientific_name": "Leiothlypis peregrina"},
    {"common_name": "Worm-eating Warbler", "scientific_name": "Helmitheros vermivorum"},
    {"common_name": "Fan-tailed Warbler", "scientific_name": "Euthlypis lachrymosa"},
    {"common_name": "Rufous-capped Warbler", "scientific_name": "Basileuterus rufifrons"}
  ],
  "correct_scientific_name": "Euthlypis lachrymosa"
}
```

(A real response, confirmed live — only warblers in it, as expected with
that `family` filter.) `mode=audio` swaps `photo_url`/`audio_url`'s
null-ness. `choices` is always exactly 4, pre-shuffled server-side (the
correct answer isn't always in the same position) with `scientific_name` as
each choice's stable identity (two species can share a common-name-ish look
but never a scientific name).

### Example — `GET /quiz/filters?region_code=world` (truncated)

```json
[
  {"name": "Barn-Owls", "count": 19},
  {"name": "Crows, Jays, and Magpies", "count": 136},
  {"name": "New World Warblers", "count": 115},
  {"name": "Owls", "count": 222}
]
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | none new | reuses `app/dao/bird_photos.py`, `app/dao/bird_audio.py`, `app/dao/region_repo.py` exactly as they are |
| `services/` | `app/services/quiz.py` (**new**) | `get_question(mode, region_code, family)`: fetch + filter the checklist, require real media (retry on a placeholder/missing recording), build 4 shuffled choices from the correct species' own family within the filtered pool; `get_filter_options(region_code)`: distinct families + counts for the "type" dropdown |
| `routers/` | `app/routers/quiz.py` (**new**) | `GET /quiz/question`, `GET /quiz/filters` |
| `Dao/` | `frontend/src/Dao/quiz.js` (**new**) | raw calls to both quiz endpoints |
| `Services/` | `frontend/src/Services/quiz.js` (**new**) | thin passthrough for the quiz calls; also re-exports `Dao/regions.js`'s existing `regionsDAO.getChildren()` for the region picker, so the Presenter only ever imports one Service |
| `Presenters/` | `Presenters/TestYourSkill.js` (**new**) | owns the session (mode, filters, current question, picked answer, revealed state, running score) and a region picker mirroring `LifeList.js`'s own cascading country/state/county UI |
| `Components/` | none new — the question card and the region picker are both simple enough to stay inline in the Presenter, same as `PlanATrip.js`'s likely-species cards | |

### Color convention for right/wrong

Reuse this app's existing success/danger tokens — don't invent new colors:
`var(--ob-color-success-text)`/`--ob-color-success-bg` (the same green
already used for "Seen" tags and the map's own-sighting pins) for the
correct choice once revealed, `var(--ob-color-danger-text)`/`--ob-color-danger-bg`
(same red as error alerts and the map's selected-pin marker) for a wrong
pick. The other two, un-picked choices stay neutral.

## 6. Build order

All ✅ — built and verified live, in this order:

1. ✅ `app/services/quiz.py#get_question()` — originally pure logic over
   `app/data/birds.py`'s curated 72, **repointed** to
   `region_repo.get_checklist()` once filtering was requested; no new
   persistence either way.
2. ✅ `app/routers/quiz.py` — `GET /quiz/question`; registered in `app/main.py`.
3. ✅ Tests (15, `tests/test_quiz.py`): canned checklist fixture (no live
   eBird calls); a placeholder (`attribution: None`) photo is rejected and
   retried; a `None` audio result is rejected and retried; distractors
   prefer the correct species' own family and fall back to the wider pool
   only when that family is too thin; a `family` filter actually narrows
   the pool; `NoQuestionAvailable` on an impossible filter combination or
   on exhausted retries; router-level 422/503s.
4. ✅ `app/services/quiz.py#get_filter_options()` + `GET /quiz/filters` —
   added alongside the `region_repo` repoint, same commit.
5. ✅ Frontend: `Dao/quiz.js` → `Services/quiz.js` → `Presenters/TestYourSkill.js`,
   including the type dropdown and the region picker (reusing
   `Dao/regions.js`'s `regionsDAO` directly for the country/state/county
   cascade — no duplicate region-picker code).
6. ✅ Add the **Test Your Skill** button to `Home.js`'s nav; register the
   `test-your-skill` route in `preview.js`'s `SCREENS`.
7. ✅ Live verification: cold `/quiz/filters` ~4.7s (full world taxonomy,
   first load), cached ~0.3s; a `family=New World Warblers` question came
   back with only warblers in it; a `region_code=US` question came back
   scoped to that region; `object-fit: contain` (not `cover`) on the photo
   after a real "tall bird photo got cropped to just legs, head cut off"
   report — showing the whole bird matters more than filling the frame for
   an ID quiz.

## Related pages

- [Life List page](life-list.md) — owns `region_repo.get_checklist()`, the
  `/regions` endpoint, and the cascading region-picker pattern this reuses
  directly rather than reimplementing
- [Add Observation](add-observation.md) — owns the Commons-backed
  photo/audio pattern this reuses wholesale (`app/data/birds.py`'s curated
  set was this feature's original species source, before the repoint to
  the full taxonomy in §1)
- [Bird information page](bird-info.md) — a different, persistent reuse of
  the same Commons pattern; not a dependency of this feature or vice versa
