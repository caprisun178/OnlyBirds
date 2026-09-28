# Features overview

MVP feature breakdown. **Each feature has its own page** — if you are building a
feature, that page is the only one you need: it has the screens, the data
sources, the API, the SQL, and the code layout.

| Feature | Status | Start it… |
|---|---|---|
| [Life List page](life-list.md) | Partial — API returns entries; region filter + checklist view planned | after baseline |
| [Add Observation](add-observation.md) | Partial — `POST /observations` exists; identification flow planned | after baseline |
| [User profiles](user-profiles.md) | Planned | after baseline |
| [Stickers](stickers.md) | Planned | after Add Observation |
| [Pinned birds](pinned-birds.md) | Planned | after Add Observation + profiles |
| [Bird information page](bird-info.md) | Planned | any time (independent) |
| [Explore map](explore-map.md) | Planned | after Add Observation (needs `observations.geom`) |

Nothing here is fully built yet. *Partial* means some API already exists.

## Who's working on what

**Claiming a feature:** put your name in the Owner column, add your branch
(`working/<you>/<feature>`, cut from `dev/current`), set the status, and open a
quick PR into `dev/current` so everyone can see it's taken.
One owner per feature at a time — if a row already has a name, ping that person
before starting.

| Feature | Owner | Branch | Status | Notes |
|---|---|---|---|---|
| [Life List page](life-list.md) | _unassigned_ | | not started | |
| [Add Observation](add-observation.md) | Sarah Parisi | | in progress | |
| [User profiles](user-profiles.md) | _unassigned_ | | not started | |
| [Stickers](stickers.md) | _unassigned_ | | not started | |
| [Pinned birds](pinned-birds.md) | _unassigned_ | | not started | |
| [Bird information page](bird-info.md) | _unassigned_ | | not started | |
| [Explore map](explore-map.md) | _unassigned_ | | not started | |

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
| `species_content` | [Bird information page](bird-info.md) | **new** (cache) — description, migration, media for a species |
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
