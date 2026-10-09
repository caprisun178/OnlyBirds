# External services & API risk

> **Status:** Assessment, October 2026. Every outside service OnlyBirds
> depends on, what its terms allow, how likely it is that we could be
> asked to stop (or simply be cut off), and what we'd do then. This applies
> whichever hosting option is chosen
> ([self-hosted](production-environment.md) or
> [cloud](production-environment-cloud.md)). Terms change, so **re-read each
> provider's terms before public launch** and whenever the app's purpose
> changes (especially if it ever makes money).

## 1. The headline risks

1. **Our two core data sources are licensed for non-commercial use only.**
    - **eBird:** the API license is non-commercial; commercial use requires a written
      agreement with Cornell.
    - **iNaturalist:** its Terms of Use forbid using its content for a commercial purpose.

    As long as OnlyBirds is a free, non-commercial hobby/education
    project, this is fine. **Ads, subscriptions, paid features, or running
    it as a business would break both** unless we get agreements first.
    Many iNaturalist and Wikimedia *photos* are also licensed
    non-commercial (CC BY-NC) on top of that.
2. **eBird can revoke our access at any time, with or without notice.**
   eBird is the backbone of Life List, Explore Map, Plan a Trip, Test Your
   Skill and region detection, so losing it would break most of the app.
3. **We're already out of line with two providers' rules:**
    - The public Nominatim geocoder's policy forbids autocomplete, which our
      place search does.
    - Esri expects an ArcGIS account and API key for production use of its
      basemap tiles, and we use the tiles anonymously.

    Both are easy to fix (§3).
4. **Attribution is required almost everywhere** (eBird, iNaturalist
   photos, Wikimedia Commons, Wikipedia, Esri/OSM), and the app doesn't yet
   show it consistently.

## 2. Inventory and risk ratings

**Likelihood** = chance we're asked to stop, blocked, or the service goes
away within a year at our current use. **Impact** = how much of the app
breaks if it does.

| Service | What we use it for | Code | Terms in brief | Likelihood | Impact |
|---|---|---|---|---|---|
| **eBird API 2.0** (Cornell Lab) | taxonomy, regions + checklists, recent/notable sightings, hotspots, historic checklists, point → region | `dao/ebird.py`, `dao/region_repo.py` | API key; **non-commercial** license; **revocable any time**, with or without notice; attribution to eBird.org with a link; abuse → suspension ([terms](https://www.birds.cornell.edu/home/ebird-api-terms-of-use/)) | Low if non-commercial and polite; **High if commercial** | **Critical** |
| **iNaturalist API v1** | sightings near a point, "likely species" counts, hotspot drill-down sightings + photos | `dao/inaturalist.py` | No key for reads; ~**60 req/min** recommended (100 max), under **10,000 req/day**; heavy use → **blocked without notification**; Terms forbid **commercial** use of content; each photo has its own license ([terms](https://www.inaturalist.org/pages/terms)) | Low–Medium (daily cap reachable as users grow) | High |
| **Nominatim** (OpenStreetMap, public server) | place search + reverse geocoding | `dao/nominatim.py` | ~1 req/s total; **autocomplete forbidden**; heavy users must self-host or use a commercial provider ([policy](https://operations.osmfoundation.org/policies/nominatim/)) | **High** (we already break the autocomplete rule) | Medium |
| **Wikimedia Commons** | species photos + bird-call audio, with attribution metadata | `dao/commons.py`, `dao/bird_photos.py`, `dao/bird_audio.py` | Free API; must send a descriptive User-Agent with contact info; **thumbnails at non-standard widths are strictly rate-limited since 2026**; every file has its own license (CC BY / BY-SA / some NC) | Low | Medium |
| **Wikipedia** (REST + Action APIs) | Bird Info "About" text and sections | `dao/wikipedia.py` | Free; User-Agent policy; text is **CC BY-SA 4.0**: attribute + link, and adapted text must stay CC BY-SA | Very low | Low |
| **Esri basemap tiles** (`server.arcgisonline.com`) | the map background on every map | `frontend/src/Components/leaflet.js` | Esri's current developer model expects an **ArcGIS Location Platform account + API key** for production apps; attribution ("Esri, HERE, Garmin, © OpenStreetMap contributors") required ([Esri Leaflet FAQ](https://developers.arcgis.com/esri-leaflet/faq)) | Medium | High (maps go blank) |
| **Hugging Face** (BioCLIP model download) | photo identification model, fetched as `hf-hub:imageomics/bioclip` | `dao/bioclip_classifier.py` | Model is **MIT-licensed**, commercial use OK. Risk is *availability*: downloaded at startup, so an outage, rate limit or removal blocks photo ID on a fresh server | Low | Medium |
| **unpkg CDN** (Leaflet JS/CSS) | the map library itself | `Components/leaflet.js` | Free CDN, no SLA; a CDN outage or compromised package breaks maps | Low | High |
| **placehold.co** | placeholder image when Commons has no photo | `dao/bird_photos.py` | Free service, no SLA | Low | Very low |
| **Render, Neon, Supabase, GitHub Pages** | today's hosting | — | Covered by the production proposals; replaced in production | — | — |

**Planned, not yet used.** Check the terms before building:

| Service | Planned for | What to know |
|---|---|---|
| **Macaulay Library** (Cornell) | species photos/audio (`dao/macaulay.py` stub) | Media is copyrighted by the contributors; reuse generally needs Cornell's permission/agreement. Its public search is behind bot protection. Treat as "needs a formal agreement." |
| **eBird Status & Trends** | migration/abundance (`dao/status_trends.py` stub) | Data products have their own [terms of use](https://ebird.org/about/products-access-terms-of-use); access is by request and non-commercial. |
| **Xeno-canto** | bird-call recordings | Per-recording Creative Commons licenses, many non-commercial; its current API needs a key. |
| **IUCN Red List API** | conservation status / habitat | Token by application, non-commercial terms, attribution. |
| **Google Cloud Vision** | reverse image search ([Competitions](features/competitions.md#photo-verification)) | Paid commercial API, no use restriction beyond billing; sends user photos to Google (disclose in privacy policy). |

## 3. What to do about each

### eBird: protect the backbone

- **Talk to Cornell before public launch.** Email the eBird API team
  describing OnlyBirds: what we fetch, how much, that it's non-commercial,
  and how we attribute. A known, well-behaved project is far less likely to
  be cut off without warning, and it's the only way to learn their view on
  anything unclear (e.g. how long we may cache data).
- **Register the key to a project account**, not one person's eBird
  account, so access survives people leaving.
- **Attribution:** show "Data from [eBird.org](https://ebird.org)" (linked)
  wherever eBird data appears: Life List checklists, Explore Map, Plan a
  Trip hotspots, Test Your Skill.
- **Keep our own copy, via the official bulk channels.** The eBird Basic
  Dataset and iNaturalist's GBIF export, never by paging through the
  APIs. Scoped in [Seeded sighting data](features/data-seeding.md).
- **Reduce how much we depend on live calls:**
    - The **eBird/Clements taxonomy is published as a yearly download**.
      Import it into our own table, which removes taxonomy calls entirely.
    - Persist region checklists in the planned `region_checklists` cache
      table instead of process memory.
    - Respect sensible request rates; never bulk-download.
- **If eBird access ended:**
    - **Sightings:** fall back to iNaturalist (already merged in Explore Map
      and Plan a Trip).
    - **Taxonomy:** use our own imported copy.
    - **Hotspots and checklists have no equal substitute.** Plan a Trip's
      hotspot suggestions and Life List's region checklists would degrade
      the most.

### iNaturalist: stay under the limits, honor photo licenses

- **Rate limit ourselves** in `dao/inaturalist.py`: a shared limiter at
  ≤ 60 req/min, plus caching of identical requests. Daily usage is the
  number to watch as users grow (10,000/day across *all* users).
- **Photo licenses:** only display iNaturalist photos that carry an open
  license, always with the photographer's name and license, and **skip
  "all rights reserved" photos**. Check what `SightingDetail.js` shows today.
- **Fallback: [GBIF](https://www.gbif.org)**. iNaturalist's research-grade
  observations are published to GBIF, which has a free, open API built for
  reuse (with its own data-user agreement and per-record licenses). It's a
  good secondary source for "sightings near here" if iNaturalist ever
  blocked us.

### Nominatim: replace for production (already planned)

Swap to a geocoding provider that allows autocomplete (see the production
proposals). Dev can keep public Nominatim at low volume, with the existing
cache and a proper User-Agent with contact details.

### Wikimedia Commons and Wikipedia: small fixes

- **User-Agent:** `dao/commons.py` sends
  `OnlyBirds/0.1 (+https://github.com/)`, which has no real contact. Use the
  same descriptive form `dao/wikipedia.py` already uses (repo URL +
  contact). The User-Agent policy is now actively enforced, and requests
  without contact info get throttled.
- **Thumbnail width:** we request `iiurlwidth=320`; Wikimedia serves the
  nearest standard step (330 px). Request a standard step directly
  (e.g. 330 or 500) to stay clear of the strict limits on non-standard
  sizes.
- **Attribution:** we already store each file's attribution; make sure
  it's visible next to every photo and recording, linking to the file page.
  Show "From Wikipedia, CC BY-SA 4.0" with a link on Bird Info text.
- **Licenses:** Commons files include some non-commercial ones. That's fine
  today, but it would need filtering if the app ever became commercial.

### Esri basemap: get a key, or switch tiles

Either:

- **Register an ArcGIS Location Platform account** (free tier) and use an
  API key with Esri's supported Leaflet integration. Keep the attribution.
- **Or switch to OpenStreetMap-based tiles:** a tile provider with a free
  tier (MapTiler, Stadia Maps), or **self-host vector tiles** with
  Protomaps (a single PMTiles file served by Caddy), which fits the
  [self-hosted plan](production-environment.md) well. Don't point the app
  at `tile.openstreetmap.org` directly; OSM's own tile policy discourages
  app-scale use.

### Hugging Face, unpkg, placehold.co: remove runtime dependencies

- **BioCLIP:** bake the model weights into the server/container image (or
  our own storage) and **pin the model revision**, so starting a server
  never depends on Hugging Face being up.
- **Leaflet:** vendor the files into `frontend/` (or at least add
  Subresource Integrity hashes) instead of loading from unpkg at runtime.
- **Placeholder image:** ship a local SVG instead of calling placehold.co.

## 4. Cross-cutting practices

| Practice | Why |
|---|---|
| **Decide the commercial question now.** Write down "OnlyBirds is non-commercial" (or not) in the README. | It determines whether the two core data sources are even usable, and which photo licenses we can show. |
| **All API keys and accounts belong to the project**, recorded in a shared password manager. | Access shouldn't depend on one person. |
| **Every external call stays in `dao/`** (already the rule) **with a timeout, a cache, and graceful degradation** | One provider failing should hide a section, not break a screen. Explore Map and Plan a Trip already degrade this way. |
| **A "Data sources & credits" page** in the app, linked from the footer | One place listing eBird, iNaturalist, Wikimedia, Wikipedia, OpenStreetMap/Esri with links and licenses, on top of per-item credits. |
| **Monitor provider errors.** Count 4xx/5xx per provider in logs/error tracking and alert on spikes. | A 403 or 429 from eBird/iNaturalist is the early warning that we're being throttled or blocked. |
| **Contact providers before launch** (Cornell/eBird, iNaturalist) | Cheapest insurance against revocation; goodwill matters with nonprofit data providers. |
| **Re-review terms yearly** and before any change in business model | Terms change (Wikimedia, Esri and AWS all changed policies in 2025–2026). |

## 5. Action checklist

Before public launch:

- [ ] Decide and document commercial vs non-commercial.
- [ ] Email eBird API team and iNaturalist describing the app.
- [ ] Move the eBird key to a project account.
- [ ] Attribution for eBird, iNaturalist photos, Commons media, Wikipedia
      text, and map tiles; add a credits page.
- [ ] Replace Nominatim for autocomplete in production.
- [ ] Esri API key, or switch tile source.
- [ ] Rate limiter for iNaturalist.
- [ ] Fix the Commons User-Agent and request a standard thumbnail width.
- [ ] Skip iNaturalist photos without an open license.
- [ ] Bundle BioCLIP weights and Leaflet; drop placehold.co.

Soon after:

- [ ] Import the eBird taxonomy download; persist checklist caches.
- [ ] Evaluate GBIF as a secondary sightings source.
- [ ] Provider error-rate alerts.

## Related pages

- [Production environment (self-hosted)](production-environment.md)
- [Production on AWS or another cloud](production-environment-cloud.md)
- [eBird API](ebird-api.md): how we call it
- [Bird information page](features/bird-info.md): Wikipedia/Commons usage and the planned Cornell sources
