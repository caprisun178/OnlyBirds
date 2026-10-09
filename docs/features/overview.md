# Features overview

MVP feature breakdown. **Each feature has its own page** — if you are building a
feature, that page is the only one you need: it has the screens, the data
sources, the API, the SQL, and the code layout.

| Feature | Status | Start it… |
|---|---|---|
| [Life List page](life-list.md) | Partial — region completion view works end to end (picker, checklist, seen/unseen, progress, sort, filters, pagination); Postgres persistence for the checklist cache, the "world" life list, and deep-linking a missing card into Add Observation still planned | after baseline |
| [Add Observation](add-observation.md) | Partial — `POST /observations`, the describe & guess identification flow, and field-notes photo upload all work end to end; see the page for what's still missing | after baseline |
| [User profiles](user-profiles.md) | Partial — backend done (`POST /users`, `GET /users/{username}`, `PATCH /users/{id}`); frontend screens planned | after baseline |
| [Stickers](stickers.md) | Planned | after Add Observation |
| [Pinned birds](pinned-birds.md) | **Completed** — region tagging, pin + notification API, match/dedupe engine, migrations applied to the live database; frontend `PinButton` on Life List cards, `NotificationBell` with an unread preview dropdown, full `NotificationsFeed` screen, click-through to the exact sighting on the map (highlighted, not just centered) — all built and verified live end to end | after Add Observation + profiles |
| [Bird information page](bird-info.md) | Planned, but fully scoped — every data source confirmed buildable (Wikipedia for About text plus sex-differences/migration/habitat prose, reuses the existing Commons-backed photo/audio caches, no Cornell licensing needed); see the page for the exact entry-point-by-entry-point click wiring | any time (independent) |
| [Photo-based bird ID](bird-id.md) | **Completed** — slots into the existing describe & guess flow as a third `method` with no new database table. Model swapped from a fixed 525-label classifier to BioCLIP (zero-shot, no fixed species list) after the old ceiling caused a confirmed real-world miss (§9); candidate pool is the classifier's default set plus, when the user gives a location/date, that region's real eBird checklist added on top (never replacing it — an earlier version that replaced it caused a live regression, documented in §9). Describe-flow's generic path separately reorders toward regional plausibility (§8). Render free tier memory still unconfirmed for the new dependency weight (`torch` + `open_clip_torch`) | after Add Observation |
| [Explore map](explore-map.md) | Partial — MVP live and well beyond bare point+radius now (place search with live suggestions, species-photo filter, trip-planning box with top spots, a mi/km toggle); full spec (viewport-driven bbox fetch, clustering, `observations.geom`) still not started | after baseline for the MVP; after Add Observation for the rest |
| [Plan a trip](plan-a-trip.md) | **Completed** — destination + date-range input, eBird hotspot suggestions with a per-hotspot last-year sightings map (eBird + iNaturalist merged, cached, degrades gracefully), iNaturalist-based "likely species," life-list gap — built and verified live end to end | after baseline |
| [Test your skill](test-your-skill.md) | **Completed** — a no-persistence photo/sound quiz over the full eBird taxonomy, filterable by taxonomic type (warblers, corvids, owls, ...) and by region, reusing Life List's checklist/region-picker infrastructure and Add Observation's Commons-backed media lookups. No database change at all; see the page for why | after Add Observation + Life List |
| [Community](community.md) | Scoping — discussion board + outing plans (RSVP at public eBird hotspots), region-scoped; first-pass data model and API on the page, open questions listed. **Blocked on real sign-in** (today every screen is `u1`) | after auth + profiles |
| [Competitions](competitions.md) | Scoping — time-boxed leaderboards (most observations this week, most owl photos this month, …) computed live from logged observations, with fair-play rules (no imports/backdating, robin-day dedupe, photo hashing, classifier flagging) and sticker prizes. **Blocked on real sign-in**, same as Community | after auth + profiles; prizes after Stickers |
| [Progressive Web App](pwa.md) | Planned, scoped — manifest + service worker to make the site installable on a phone; no native wrapper, no in-app camera (upload-only, decided); needs real icon art before it can start | any time (independent) |

*Partial* means some API already exists but the feature isn't done end to end. **Completed** means the backend and frontend are both built and verified live — see that page's own Status line for specifics.

## Who's working on what

**Claiming a feature:** put your name in the Owner column, add your branch
(`working/<you>/<feature>`, cut from `dev/current`), set the status, and open a
quick PR into `dev/current` so everyone can see it's taken.
One owner per feature at a time — if a row already has a name, ping that person
before starting.

| Feature | Owner | Branch | Status | Notes |
|---|---|---|---|---|
| [Life List page](life-list.md) | Sarah Parisi | | in progress (region completion view done, Postgres persistence + world list not started) | |
| [Add Observation](add-observation.md) | Sarah Parisi | | in progress | |
| [User profiles](user-profiles.md) | Yasmin Castro | | in progress (backend done, frontend not started) | |
| [Stickers](stickers.md) | _unassigned_ | | not started | |
| [Pinned birds](pinned-birds.md) | Sarah Parisi | `working/sparisi/Feature-plan-a-trip` | done | |
| [Bird information page](bird-info.md) | _unassigned_ | | not started | |
| [Photo-based bird ID](bird-id.md) | Sarah Parisi | | done (coverage-widening follow-on not started) | |
| [Explore map](explore-map.md) | Sarah Parisi | | in progress (MVP done, full spec not started) | |
| [Plan a trip](plan-a-trip.md) | Sarah Parisi | `working/sparisi/Feature-plan-a-trip` | done | |
| [Test your skill](test-your-skill.md) | Sarah Parisi | `working/sparisi/Feature-test-your-skill` | done | |
| [Community](community.md) | _unassigned_ | | not started | blocked on auth, see page |
| [Competitions](competitions.md) | _unassigned_ | | not started | blocked on auth, see page |
| [Progressive Web App](pwa.md) | _unassigned_ | | not started | blocked on icon art, see page |

*Status* is one of: `not started` · `in progress` · `in review` · `done`.

## How to use a feature page

Every feature page has the same seven sections:

1. **What you're building** — the screens and behaviour, in plain terms.
2. **Where the data comes from and where it goes** — a table mapping every
   piece of data to its source (our database, a cache table, or an external
   API) and where it is stored. **Read this before writing any code.**
3. **Database changes (SQL)** — copy-paste SQL, every column explained. See
   [Database & migrations](database.md) for how to run it.
4. **API endpoints** — the routes the frontend calls, with request/response
   shapes.
5. **How the code is layered** — which file in `dao/` / `services/` /
   `presenters/` / `components/` does what, and which files to create.
6. **Build order** — a numbered checklist from migration to UI.
7. **Related pages**.

## The layering (same on backend and frontend)

The FastAPI backend and the frontend use the same layers. A feature touches
all of them, top to bottom. The frontend is plain JS — no framework, no build
step; see [Building a screen](../frontend-screens.md).

| Layer | Backend | Frontend | Does |
|---|---|---|---|
| HTTP surface | `app/routers/` | — | defines endpoints, validates input, sets status codes |
| Data access | `app/dao/` | `src/Dao/` | the **only** place that talks to a database or an external API |
| Business logic | `app/services/` | `src/Services/` | turns raw data into the shape the UI needs |
| Screens | — | `src/Presenters/` | own state and event handlers, render markup into a container element |
| Presentational | — | `src/Components/` | pure, reusable, no data fetching |

**The one rule that matters:** only `dao/` calls eBird, iNaturalist, or Postgres.
If you are writing an `httpx` call or SQL anywhere else, move it down a layer.
See [Contributing](../contributing.md) and [Architecture](../architecture.md).

## Data model additions (summary)

Full SQL is on each feature page; this is the map.

| Table | Feature | Change |
|---|---|---|
| `users` | [User profiles](user-profiles.md) | + `username`, `avatar_url`, `default_region` |
| `observations` | [Add Observation](add-observation.md) | + `region`, `geom`, `status` |
| `identifications` | [Add Observation](add-observation.md) | **new** — how a species was chosen, and whether the guess was right |
| `region_checklists` | [Life List page](life-list.md) | **new** (cache) — species list for an eBird region |
| `stickers`, `user_stickers`, `groups` | [Stickers](stickers.md) | **new** — catalog, award ledger, group definitions |
| `pinned_birds`, `notifications` | [Pinned birds](pinned-birds.md) | **new** — want-to-see list + the notification feed |
| `species_content` | [Bird information page](bird-info.md) | **new** (cache) — About text plus sex-differences/migration/habitat prose (photos/audio reuse `bird_photos.py`/`bird_audio.py`'s own existing caches; no migration *map* in v1 — see that page) |
| `threads`, `outings`, `thread_replies`, `outing_rsvps`, `content_reports` | [Community](community.md) | **new** — discussion threads, outing events + RSVPs, moderation reports; `users` + `is_admin`; `notifications` gains four `kind`s |
| `competitions`, `competition_entries`, `competition_results`, `competition_exclusions`, `competition_flags` | [Competitions](competitions.md) | **new** — competition definitions, challenge membership, frozen standings, moderation; `users` + `competitions_opt_in`; `observations` + `photo_sha256` |
| `sighting_cache` | [Explore map](explore-map.md) | **new** (cache) — eBird / iNat sightings for a map tile |

## End-to-end flow

How the features connect when a user logs a bird:

```text
Add Observation → /identify/describe → user confirms species
      → POST /observations   (source = manual, region + geom derived)
      → Services: first time this user has seen this species?
            yes → insert life_list_entries row
                → evaluate_stickers(user_id)
                      → insert user_stickers rows + push sticker_awarded notifications
                → profile life-list total / sticker count recompute  (they are COUNT queries)
      → evaluate_pins(observation)
            → other users who pinned this species, whose pin region contains the
              observation's region → insert pin_hit notifications
      → Life List page now shows that species' card filled in (was a MissingBird)
      → Explore map shows the new sighting
```
