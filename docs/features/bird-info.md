# Bird information page

> **Status:** Planned. Independent of the other features — can be built any time
> after the baseline schema.

## 1. What you're building

A reference page for a single species — the app's field guide. Reached by
**searching** ("herons", "Buteo", "Great Blue") or by tapping any species
anywhere in the app (`SpeciesCard`, `MissingBird`, a `CandidateList` result, a
sticker, a `pin_hit` notification). Read-only; the only user data on it is a
"you have seen this" badge and the [pin](pinned-birds.md) toggle.

### What it shows

| Block | Content | Source |
|---|---|---|
| Header | common + scientific name, taxonomy (order / family), size | eBird taxonomy |
| Images | representative photos, swipeable | Macaulay Library |
| Sounds | call + song audio with an inline player | Macaulay Library |
| Migration | text summary + weekly relative-abundance / range map | eBird Status & Trends |
| About | ID, habitat, behavior, diet — a few short paragraphs | Cornell (All About Birds / Birds of the World) |
| Your status | "Seen — first on 3 May 2024" or "Not seen yet", plus a pin toggle | our `life_list_entries` / `pinned_birds` |

### Search

- The query matches common name, scientific name, and family against the eBird
  taxonomy, which we already load into the `species` table for the
  [Life List](life-list.md).
- The **same search** backs manual species selection in
  [Add Observation](add-observation.md) — one search service, two entry points.
- Results: common name, thumbnail, family; tap → species page.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| Taxonomy: names, family, codes | eBird `GET /ref/taxonomy/ebird` | `species` table (already populated by the Life List) |
| Search matches | our `species` table | queried live with a trigram index (below) |
| Photos + call/song audio | Macaulay Library asset API, keyed by species code | asset refs cached in `species_content.media` (jsonb); the media files are hot-linked, not downloaded |
| Migration / abundance summary + map | eBird Status & Trends | `species_content.migration` |
| About paragraphs | All About Birds (free) or Birds of the World (licensed) | `species_content.about` |
| Attribution string | required by Cornell / Macaulay | `species_content.attribution`, shown in `AttributionFooter` |
| "Seen / not seen" + pin state | our own data | `life_list_entries`, `pinned_birds` |

!!! note "Content beyond taxonomy is not one clean API"
    eBird's public API gives **taxonomy and observation data only** — not
    life-history text. Media, migration, and description each come from a
    different Cornell property. Fetch each one in its own `dao/` function, cache
    the result in `species_content`, and if a licensed text source is not
    available yet, let the About block fall back to taxonomy + an outbound link.

## 3. Database changes (SQL)

One cache table, plus a search index on the existing `species` table. See
[Database & migrations](database.md#how-to-apply-a-migration).

```sql
-- 0007_species_content.sql

create extension if not exists pg_trgm;   -- fuzzy text search for the species search box

-- fast "search as you type" over species names
create index species_common_name_trgm on species using gin (common_name gin_trgm_ops);
create index species_sci_name_trgm    on species using gin (scientific_name gin_trgm_ops);

-- cached field-guide content, one row per species
create table species_content (
    species_code text primary key,           -- eBird speciesCode
    about        text,                        -- description paragraphs (may be null → fall back to taxonomy)
    migration    text,                        -- migration / abundance summary
    media        jsonb not null default '[]', -- [{type:'photo'|'audio', macaulay_id, thumb_url, credit}]
    attribution  text,                        -- e.g. 'Macaulay Library / Cornell Lab of Ornithology'
    fetched_at   timestamptz not null default now()
);
```

| Column | Meaning |
|---|---|
| `species_code` | eBird code; primary key, so one row per species. |
| `about` / `migration` | Plain text blocks the page renders. Null `about` is fine — the UI shows taxonomy and a link out instead. |
| `media` | A JSON list of photo/audio references. Each entry has the Macaulay asset id (to build the URL), a thumbnail, and the required credit line. |
| `attribution` | The credit text to display under the content. Cornell requires it. |
| `fetched_at` | Refresh the row when this is older than ~30 days. |
| `species_*_trgm` indexes | Make `where common_name ilike '%heron%'` fast enough to run on every keystroke. |

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/species?q={query}` | search → `[{code, common_name, sci_name, family, thumb_url}]` |
| `GET` | `/species/{code}` | full profile: names, taxonomy, `about`, `migration`, media refs, `attribution` |
| `GET` | `/species/{code}/media?type=photo\|audio` | Macaulay asset list for the carousel / player |

`GET /species/search?q=` already exists (iNaturalist autocomplete); this feature
switches search to our own `species` table and adds the profile + media routes.

### Example — `GET /species/bkcchi`

```json
{
  "code": "bkcchi",
  "common_name": "Black-capped Chickadee",
  "sci_name": "Poecile atricapillus",
  "family": "Paridae (Tits, Chickadees, and Titmice)",
  "about": "A bird almost universally considered 'cute' ...",
  "migration": "Largely resident; northern birds may move south in irruption years ...",
  "media": [
    { "type": "photo", "macaulay_id": "302271551", "thumb_url": "https://...", "credit": "R. Smith / Macaulay Library" },
    { "type": "audio", "macaulay_id": "155258",    "thumb_url": null,          "credit": "W. Hershberger / Macaulay Library" }
  ],
  "attribution": "Content from the Cornell Lab of Ornithology; media from the Macaulay Library."
}
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/species_repo.py` (**new**) | search `species`; read + upsert `species_content` |
| `dao/` | `app/dao/macaulay.py` (**new**) | fetch photo / audio asset lists |
| `dao/` | `app/dao/status_trends.py` (**new**) | fetch migration / abundance summary |
| `services/` | `app/services/species.py` (extend) | merge taxonomy + `species_content` + media into one profile model; attach the user's seen / pinned status |
| `routers/` | `app/routers/species.py` (extend) | `GET /species`, `GET /species/{code}`, `GET /species/{code}/media` |
| `Dao/` | `frontend/src/Dao/species.js` (extend) | search + profile calls |
| `Services/` | `frontend/src/Services/species.js` (**new**) | UI-shaped profile |
| `Presenters/` | `Presenters/SpeciesSearch.jsx`, `Presenters/SpeciesPage.jsx` (**new**) | search box + results; the profile page and its media / pin interactions |
| `Components/` | `SearchBar`, `SpeciesHeader`, `MediaCarousel`, `AudioPlayer`, `RangeMap`, `AttributionFooter` | presentational |

## 6. Build order

1. Write and run `backend/migrations/0007_species_content.sql`.
2. Point `GET /species` at our `species` table with the trigram index (drop the
   iNat autocomplete dependency for search).
3. Add `app/dao/species_repo.py` with a `get_content(code)` that returns the
   cached row or fetches + upserts it.
4. Add `app/dao/macaulay.py` and `app/dao/status_trends.py` — return stub data
   first so the page renders end to end.
5. Extend `app/services/species.py` to assemble the profile.
6. Add the profile + media routes.
7. Tests: canned taxonomy + Macaulay payloads; assert the merged profile shape.
8. Frontend: `SpeciesSearch.jsx` → `SpeciesPage.jsx` → media components +
   `AttributionFooter`.

## Related pages

- [Life List page](life-list.md) — populates `species`, links to this page
- [Add Observation](add-observation.md) — shares the species search
- [Pinned birds](pinned-birds.md) — the pin toggle on this page
- [Explore map](explore-map.md) — sighting popups link here
- [Database & migrations](database.md)
