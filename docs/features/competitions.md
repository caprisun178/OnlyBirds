# Competitions

> **Status:** Scoping — nothing built. Scope covers how a competition is
> defined, how it's scored, how it resists cheating, and the data model.
> Product decisions made 2026-10-09 are recorded in [§8](#8-decisions);
> photo verification is laid out as options in
> [Photo verification](#photo-verification) for a final call. **Shares Community's
> blocker:** real sign-in has to exist first (see
> [Community → Prerequisites](community.md#prerequisites)), since a public
> leaderboard of user IDs anyone can impersonate isn't a competition.

## 1. What you're building

Time-boxed contests with a **leaderboard**, scored from the observations
people already log through [Add Observation](add-observation.md). For example:

- **Most observations this week**
- **Most owl photos this month**
- **Most species in Washington this weekend** (a "Big Weekend")
- **Most birds identified by ear this week** (`detection_type = 'sound'`)

No new logging flow. You compete by birding normally, and the leaderboard
counts the observations that qualify.

### A competition is one metric + filters + a time window

Every competition, official or user-made, is the same five things. That
means "most owl photos" is a row of data, not new code:

| Part | Options | Example: "Most owl photos this month" |
|---|---|---|
| **Metric** (what's counted) | `observations` · `species` (distinct) · `photos` · `sounds` | `photos` |
| **Taxon filter** (optional) | a list of eBird families (from the taxonomy Test Your Skill already uses), or a list of species | families `Owls`, `Barn Owls` |
| **Region** (optional) | any eBird region code; `world` = anywhere | `world` |
| **Window** | `starts_at` → `ends_at` | Oct 1 → Nov 1 |
| **Recurrence** | `none` (one-off) or `weekly` / `monthly` (a new instance starts automatically) | `monthly` |

### Two kinds

1. **Official competitions.** A small rotating set we define, seeded from a
   repo fixture the same way the Stickers catalog is planned to be. To start:
   *Weekly Observations*, *Weekly Species*, *Monthly Owl Photos*, *Monthly
   Ear Birder*. Everyone who has opted in to competitions is entered
   automatically. There are two flavours (both decided):
    - **Global** (`region_code = 'world'`): one board, with a **region
      filter on the leaderboard view** ("show me Washington"). The filter
      only re-ranks the same competition's entrants; it isn't a separate
      prize.
    - **Regional**: a competition whose own `region_code` is set
      (e.g. *Washington Weekly Species*). Only observations in that region
      count, and it has its own podium and stickers. Start with a handful
      of regional series where there are actually users, rather than one
      per state up front.
2. **Challenges** (phase 3). A user creates a one-off competition with the
   same five parts and invites people, or posts it to their region's
   [Community](community.md) board. Only people who join are ranked.

### Screens

| Screen | What's on it |
|---|---|
| **Competitions** (list) | Active competitions with time remaining and *your* current rank/score in each; recently finished ones with winners. Reached from a Home button, or as a third tab in Community. |
| **Competition detail** | Rules in plain words ("Photos of any owl, logged Oct 1–31, anywhere"), the leaderboard (top 25 + your own row pinned), and for photo competitions a gallery of the top entries' qualifying photos. |
| **Profile** | A "Competitions" opt-in toggle; past placements; winner stickers on the sticker shelf. |

### Prizes

Placements award **stickers**: a podium sticker per finished competition
(1st/2nd/3rd) plus a "Took part" sticker. That plugs into the
[Stickers](stickers.md) engine as a new `competition_place` rule type, so
competitions don't need their own trophy system. Finishing also sends a
`competition_result` notification through the existing bell.

## Fair play

Raw "most observations" is trivially gameable: log the same robin 500
times, re-upload one photo, or backdate a year of sightings. Since the
leaderboard *is* the feature, these rules are part of v1, not polish:

| Rule | Why |
|---|---|
| **Only `source = 'manual'` and `status = 'logged'` observations count, with no exceptions** (decided: no per-challenge "imports allowed" option either). | Competitions are about birding *in OnlyBirds*. Imported eBird/iNaturalist records aren't the user's activity in this app, and could be bulk-imported. Drafts don't count. |
| **`observed_at` must be inside the window, and the observation must be *created* before `ends_at` + 48h.** | Blocks backdating a pile of old sightings into this week, while still allowing a grace period to log Sunday's walk on Monday. |
| **`observations` metric counts at most one per species per day per user.** | It's checklist-style, so the score reflects birding, not data entry. 40 robins at the feeder is one robin-day. *Most species* is already immune. |
| **Photo checks** (see [Photo verification](#photo-verification) below). | Duplicates, wrong birds, old photos, and photos lifted from the web each need a different check. |
| **Reports + admin exclusions.** Any entrant can report a qualifying observation (reusing Community's `content_reports` pattern); an admin can exclude it from that competition. | Covers whatever the automated checks miss. |
| **Standings are snapshotted when a competition ends.** | Editing or deleting an observation afterwards can't change who won. |

## Photo verification

"Is this the user's own photo, taken during the competition, of the right
bird?" can't be *proven* from an uploaded file. Proving it would take
in-app camera capture, which [PWA](pwa.md) deliberately ruled out
(upload-only). What we *can* do is stack cheap checks that each catch one
kind of cheating, and spend money only where it matters: on photos about to
win something.

### What each check catches

| # | Check | Catches | Misses | Cost | Runs on |
|---|---|---|---|---|---|
| 1 | **Exact duplicate** (SHA-256 of the file) | the same file uploaded twice, by anyone | any re-save, crop or resize | free | every upload |
| 2 | **Near-duplicate** (perceptual hash via the `imagehash` library, on top of Pillow, which is already a dependency) | the same photo cropped, resized, re-compressed or screenshotted; two users entering the same photo | different photos of the same scene | free | every upload, compared against all stored hashes |
| 3 | **EXIF date and GPS.** Uploads currently store the original file, so EXIF survives to the server. Read *date taken* and *GPS* with Pillow | photos taken before the window opened; photos taken outside the competition's region | photos with EXIF stripped (screenshots, social media downloads, some phone share flows); deliberately edited EXIF | free | every upload |
| 4 | **Right bird** (BioCLIP, already built, see [Photo-based bird ID](bird-id.md)) | a non-owl in an owl competition | a different owl species, which still counts | free (CPU on our server) | qualifying photos |
| 5 | **Reverse image search** (Google Cloud Vision *Web Detection*: [first 1,000/month free, then $3.50 per 1,000](https://cloud.google.com/vision/pricing)) | photos copied from the web: Wikipedia, Flickr, eBird/Macaulay, other people's Instagram | photos that aren't online anywhere (e.g. borrowed from a friend) | free at our scale *if* limited to podium contenders | the **top 10 entries' photos at close** only |
| 6 | **Reports + admin review** | anything else | — | admin time | on demand |

[TinEye's API](https://blog.tineye.com/new-image-search-pricing/) is the
alternative for #5 (100 free searches, then bundles from $200 per 5,000),
but Cloud Vision's monthly free tier fits "check the podium only" better.
Either way it's a new external integration (an API key in Render, a DAO
file), and it sends contenders' photos to a third party, which the
opt-in screen should say.

### How the results are used (recommended)

Each qualifying photo gets a status: **verified**, **unverified** or
**flagged**.

- **Flagged** = it failed #1 or #2 (duplicate), #4 (wrong bird), or #3
  (EXIF date before the window / GPS outside the region), or #5 found it
  online. It **doesn't count** until an admin clears it.
- **Verified** = EXIF date (and GPS, for regional competitions) present and
  consistent, and no flags. It counts.
- **Unverified** = no EXIF, no flags. It **counts on the leaderboard**, so
  people with EXIF-stripping phones aren't locked out. To **place on the
  podium**, it must also pass #5 at close. Shown with a small "unverified"
  marker on the leaderboard's photo gallery.

This puts the friction only where the prize is. The checks are free
(#1–#4) for everyone, and the single paid check (#5) runs on roughly 30
photos per competition per period, which stays within Cloud Vision's free
tier for a long time.

!!! warning "Existing privacy leak, fix regardless of competitions"
    `services/uploads.py` stores the **original file** in a **public**
    Supabase bucket (`dao/storage.py` returns a public URL). Any phone photo
    with GPS EXIF therefore publishes the photographer's exact location,
    downloadable by anyone with the photo's URL. That contradicts the
    region-only display decided below and Community's sensitive-species
    stance. The fix also serves check #3: at upload, **read** EXIF date + GPS
    into database columns, then **strip** EXIF from the stored copy with
    Pillow. Worth doing as its own small PR before any competition work.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| Competition definitions (official) | a fixture file in the repo, seeded like the Stickers catalog | `competitions` |
| Competition definitions (challenges) | the user | `competitions` (`created_by` set) |
| Who's competing | profile opt-in toggle (official); join button (challenges) | `users.competitions_opt_in`; `competition_entries` |
| Live scores / leaderboard | **computed** from `observations` at read time. Nothing stored, the same as profile totals | not stored |
| Taxon filter → which species count | the cached eBird world taxonomy (`region_repo.get_checklist("world")`, already used by Test Your Skill), resolved from family names to scientific names | not stored; the cache already exists |
| Photo hashes (exact + perceptual) | computed in `services/uploads.py` at upload | `observations.photo_sha256`, `photo_phash` |
| EXIF date taken + GPS | read with Pillow at upload, then **stripped** from the stored file | `observations.photo_taken_at`, `photo_lat`, `photo_lng`. **Server-only**, never returned by any endpoint |
| Classifier check on photos | BioCLIP (`dao/bioclip_classifier.py`, already built) | `competition_flags` |
| Reverse image search | Google Cloud Vision Web Detection, podium contenders only, at close | `observations.photo_web_checked_at` + a `competition_flags` row if matches were found |
| Final standings | snapshot at close | `competition_results` |
| Exclusions | admin | `competition_exclusions` |

!!! note "Live scores are computed, not stored"
    A leaderboard is one `group by user_id` query over `observations`,
    filtered by window, region, source and species set. That's cheap at
    hobby scale with the indexes below, and there's no stored score to drift
    out of sync when someone edits an observation. If it ever gets slow,
    a short cache (like `nominatim.py`'s 60-second search cache) goes in
    front of it; there's no need for a scores table.

!!! note "No cron needed: competitions close lazily"
    Render's free tier has no scheduler. Any read of a competition whose
    `ends_at` has passed and that has no `finalized_at` finalizes it first:
    it snapshots results, awards stickers, sends notifications, and creates
    the next instance if it's recurring. This runs in one transaction,
    guarded by `finalized_at`, so it happens exactly once.

## 3. Database changes (SQL)

One migration. See [Database & migrations](database.md#how-to-apply-a-migration).
`0007` is taken by [Community](community.md#3-database-changes-sql) if that
lands first; use the next free number.

```sql
-- 0008_competitions.sql

create table competitions (
    id              uuid primary key default gen_random_uuid(),
    series_key      text,                       -- e.g. 'weekly-observations'; groups recurring instances
    title           text not null,
    description     text not null default '',
    metric          text not null check (metric in ('observations', 'species', 'photos', 'sounds')),
    taxon_families  text[],                     -- eBird familyComName values, e.g. {'Owls','Barn Owls'}; null = any bird
    taxon_species   text[],                     -- explicit scientific names (alternative to families); null = not used
    region_code     text not null default 'world',
    starts_at       timestamptz not null,
    ends_at         timestamptz not null check (ends_at > starts_at),
    recurrence      text not null default 'none' check (recurrence in ('none', 'weekly', 'monthly')),
    created_by      uuid references users(id) on delete cascade,   -- null = official
    finalized_at    timestamptz,
    created_at      timestamptz not null default now(),
    unique (series_key, starts_at)              -- one instance per period per series
);
create index competitions_active_idx on competitions (ends_at) where finalized_at is null;

-- explicit membership, for user-created challenges
create table competition_entries (
    competition_id  uuid not null references competitions(id) on delete cascade,
    user_id         uuid not null references users(id) on delete cascade,
    joined_at       timestamptz not null default now(),
    primary key (competition_id, user_id)
);

-- frozen standings at close
create table competition_results (
    competition_id  uuid not null references competitions(id) on delete cascade,
    user_id         uuid not null references users(id) on delete cascade,
    rank            integer not null,
    score           integer not null,
    primary key (competition_id, user_id)
);

-- observations an admin removed from one competition
create table competition_exclusions (
    competition_id  uuid not null references competitions(id) on delete cascade,
    observation_id  uuid not null references observations(id) on delete cascade,
    reason          text,
    created_at      timestamptz not null default now(),
    primary key (competition_id, observation_id)
);

-- automated checks that failed, awaiting an admin (see "Photo verification")
create table competition_flags (
    competition_id  uuid not null references competitions(id) on delete cascade,
    observation_id  uuid not null references observations(id) on delete cascade,
    check_kind      text not null check (check_kind in
                      ('duplicate', 'near_duplicate', 'exif_date', 'exif_location', 'classifier', 'web_match')),
    detail          jsonb not null default '{}',  -- e.g. {"matches": ["https://flickr.com/..."]} or {"top5": [...]}
    resolved_at     timestamptz,                  -- admin decided ...
    upheld          boolean,                      -- ... true = stays out, false = cleared, counts again
    created_at      timestamptz not null default now(),
    primary key (competition_id, observation_id, check_kind)
);

alter table users add column competitions_opt_in boolean not null default false;

-- photo facts captured at upload (EXIF is then stripped from the stored file)
alter table observations add column photo_sha256         text;
alter table observations add column photo_phash          text;              -- 64-bit perceptual hash, hex
alter table observations add column photo_taken_at       timestamptz;       -- EXIF DateTimeOriginal, if present
alter table observations add column photo_lat            double precision;  -- EXIF GPS, if present; server-only
alter table observations add column photo_lng            double precision;
alter table observations add column photo_web_checked_at timestamptz;       -- reverse image search done

create index observations_competition_idx on observations (observed_at, user_id)
    where source = 'manual' and status = 'logged';
create index observations_photo_sha_idx on observations (photo_sha256) where photo_sha256 is not null;
```

| Table / column | Why it exists |
|---|---|
| `competitions` | Each row is one instance with a concrete window; recurring ones share a `series_key`. The filters are columns, not code, so a new kind of competition is an insert. |
| `competition_entries` | Membership for challenges only. Official competitions use the profile opt-in instead of per-competition joins. |
| `competition_results` | The snapshot that makes past winners permanent. |
| `competition_exclusions` / `competition_flags` | Moderation: the admin's direct removals, and failed automated checks awaiting a decision. An unresolved or upheld flag keeps the photo out of the count. |
| `users.competitions_opt_in` | Leaderboards show usernames publicly, so being ranked is opt-in. Defaults to off. |
| `observations.photo_*` | What the verification checks need, captured once at upload. Null for photos uploaded before this migration, which therefore count as *unverified*. `photo_lat`/`photo_lng` exist only for the regional-competition GPS check and must never be returned by the API. |

Also extend the `notifications` kind check with `competition_result`, and
add `competition_place` to the Stickers rule types.

### The leaderboard query (sketch)

```sql
-- $1 starts_at, $2 ends_at, $3 region prefix ('' for world), $4 species set (null = any)
select o.user_id,
       count(distinct (s.scientific_name, (o.observed_at at time zone 'UTC')::date)) as score   -- metric = observations
from observations o
join species s on s.id = o.species_id
join users u   on u.id = o.user_id and u.competitions_opt_in
where o.source = 'manual' and o.status = 'logged'
  and o.observed_at >= $1 and o.observed_at < $2
  and o.created_at  <  $2 + interval '48 hours'
  and ($3 = '' or o.region like $3 || '%')
  and ($4::text[] is null or s.scientific_name = any($4))
  and not exists (select 1 from competition_exclusions e
                  where e.competition_id = $5 and e.observation_id = o.id)
group by o.user_id
order by score desc
limit 25;
```

`species` → `count(distinct s.scientific_name)`; `photos` →
`count(distinct o.photo_sha256)` with `photo_sha256 is not null` and no
unresolved or upheld `competition_flags` row for that observation;
`sounds` → `observations` scoring plus `detection_type = 'sound'`.
Ties share a rank, and the tiebreak is who reached the score first.

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/competitions?status=active\|finished&region=` | list, each with time left and the caller's own rank/score; lazily finalizes anything past `ends_at` |
| `GET` | `/competitions/{id}` | rules + leaderboard (top 25 + caller's row) + for photo metrics the top entries' photos |
| `GET` | `/competitions/{id}/entries/{username}` | the observations that counted for one person, with their verification status: transparency, and the basis for reports. **Region and date only, never exact location** (decided) |
| `PATCH` | `/users/me` | `{competitions_opt_in}` (extends the existing profile `PATCH`) |
| `POST` | `/competitions` | *phase 3*: create a challenge; server validates window ≤ 31 days and families exist in the taxonomy |
| `POST` / `DELETE` | `/competitions/{id}/join` | *phase 3*: challenges only |
| `POST` | `/competitions/{id}/exclusions` | admin: `{observation_id, reason}` |
| `GET` | `/competitions/flags` | admin: unresolved flags, with each check's `detail` |
| `POST` | `/competitions/flags/{competition_id}/{observation_id}/{check_kind}` | admin: `{upheld: true\|false}` |

### Example — `GET /competitions/{id}`

```json
{
  "id": "b7e2…",
  "title": "Monthly Owl Photos",
  "rules": "Photos of any owl, logged October 1–31, anywhere.",
  "metric": "photos",
  "taxon_families": ["Owls", "Barn Owls"],
  "region_code": "world",
  "starts_at": "2026-10-01T00:00:00Z",
  "ends_at": "2026-11-01T00:00:00Z",
  "finalized": false,
  "leaderboard": [
    { "rank": 1, "username": "hawkeye", "score": 9 },
    { "rank": 2, "username": "owlbert", "score": 7 }
  ],
  "me": { "rank": 14, "score": 2 }
}
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/competition_repo.py` (**new**) | competitions CRUD, the leaderboard query, results snapshot, exclusions/flags. Same in-memory + Postgres pattern as `notification_repo.py` |
| `dao/` | `app/dao/region_repo.py` (reuse) | world taxonomy for family → species resolution |
| `dao/` | `app/dao/bioclip_classifier.py` (reuse) | check #4, right bird |
| `dao/` | `app/dao/vision_web.py` (**new**) | check #5, Cloud Vision Web Detection; needs a `GOOGLE_VISION_API_KEY` in Render |
| `services/` | `app/services/competitions.py` (**new**) | resolve filters, rank + tiebreak, lazy finalize + next-instance creation, sticker/notification fan-out, plain-words rules text |
| `services/` | `app/services/uploads.py` (extend) | hashes + EXIF read, then strip EXIF before storing |
| `services/` | `app/services/photo_checks.py` (**new**) | checks #1–#5 → flags; verified/unverified/flagged status |
| `routers/` | `app/routers/competitions.py` (**new**) | endpoints above |
| `data/` | `app/data/competitions.py` (**new**) | official series fixture |
| `Presenters/` | `Competitions.js`, `CompetitionDetail.js` (**new**) | list + detail/leaderboard |
| `Components/` | `Leaderboard.js` (**new**); reuse `SightingDetail.js` for entry photos | presentational |

## 6. Build order

**Phase 0: prerequisites.** Real sign-in and usernames (shared with
[Community](community.md#prerequisites)). Separately and sooner: the
EXIF-stripping privacy fix (see the warning in
[Photo verification](#photo-verification)); it's a small PR that's
worth shipping on its own.

**Phase 1: official, non-photo competitions**

1. Migration; `competition_repo.py`; seed the *Weekly Observations* and
   *Weekly Species* series.
2. `competitions.py` service: leaderboard query, fair-play filters, lazy
   finalize, next-instance creation.
   Tests: backdated observation excluded, 48h grace honored, robin-day
   dedupe, opt-out users hidden, finalize runs exactly once, ties.
3. Router + profile opt-in toggle.
4. Frontend: list + detail + `Leaderboard`. Home button.

**Phase 2: taxon + photo competitions**

5. Photo facts at upload (hashes, EXIF read + strip); family → species
   resolution; first regional series.
6. *Monthly Owl Photos* and *Monthly Ear Birder* series.
7. Checks #1–#4 → flags, admin flags/exclusions endpoints, "unverified"
   marker in the gallery.
8. Check #5 at close for podium contenders (needs the Cloud Vision key).
9. Stickers `competition_place` rule + `competition_result` notification
   (needs Stickers built, or ship results-only first).

**Phase 3: user challenges**

10. Create/join endpoints and the compose form; post-to-Community link.

## 7. Related pages

- [Community](community.md): shared auth blocker; challenges can be posted there; `content_reports` pattern
- [Add Observation](add-observation.md): the observations being scored
- [Stickers](stickers.md): prizes
- [Photo-based bird ID](bird-id.md): the classifier check
- [Test your skill](test-your-skill.md): the family-level taxonomy filter reused here
- [User profiles](user-profiles.md): opt-in toggle, past placements
- [Database & migrations](database.md)

## 8. Decisions

Decided 2026-10-09:

| # | Question | Decision |
|---|---|---|
| 1 | Is being ranked opt-in? | **Yes, opt-in.** `users.competitions_opt_in` defaults to off. |
| 2 | Global or regional competitions? | **Both.** Global competitions have a region filter on the leaderboard view, *and* there are separate regional competitions with their own podiums (see [Two kinds](#two-kinds)). |
| 3 | Which week? | **Monday 00:00 UTC → Monday 00:00 UTC.** |
| 4 | How strict on photo authenticity? | **Depends on what's verifiable.** The options and a recommended tiered approach are in [Photo verification](#photo-verification). Still needs a final call, mainly whether to add the paid reverse-image-search integration (check #5). |
| 5 | Do eBird/iNaturalist imports ever count? | **No.** Only observations logged in OnlyBirds, with no per-challenge exception. |
| 6 | How much of leaders' observations is public? | **Region and date only**, never exact pins. |
