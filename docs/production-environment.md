# Production environment (proposal)

> **Status:** Proposal, for discussion. Nothing here is provisioned yet.
> Today there is only a **dev** environment, running on free managed tiers
> (Render, Neon, Supabase Storage, GitHub Pages). This page proposes a
> **self-hosted production environment**: servers we control, running our
> own database, backend and file storage, instead of renting each piece
> from a platform. It covers what that needs, why, what it costs, and what
> we become responsible for. Prices were checked October 2026; re-confirm
> before buying. How to stand up the *current* dev setup is in
> [Deployment](deployment.md).
>
> **See also:** [Production on AWS or another cloud](production-environment-cloud.md)
> (the alternative to self-hosting) and
> [External services & API risk](external-services.md) (the data APIs we
> depend on, whichever hosting we pick).

## 1. Summary

| | Today (dev, managed free tiers) | Proposed production (self-hosted) |
|---|---|---|
| **Server** | none of our own | **one VPS** with root access, e.g. Hetzner Cloud, 4 vCPU / 8 GB RAM / 80 GB disk, Ubuntu LTS |
| **Backend API** | Render Free (512 MB, sleeps after 15 min) | FastAPI in a Docker container on the VPS, always on |
| **Database** | Neon Free | **PostgreSQL + PostGIS** in a container on the VPS, never exposed to the internet |
| **File storage** | Supabase Storage, public bucket, original files with GPS EXIF | a disk volume on the VPS served by the web server, EXIF stripped at upload |
| **Auth** | none (every screen is user `u1`) | our own sign-in, implemented in the backend (see [§4.5](#45-authentication)) |
| **Web server / TLS** | provided by the hosts | **Caddy**: reverse proxy, automatic HTTPS, serves the static frontend and photos |
| **Frontend** | GitHub Pages from `dev/current` | served from the same VPS by Caddy at our own domain |
| **Backups** | whatever the free tiers do | nightly encrypted, **off-site** backups of the database + photos, with restore drills |
| **Monitoring** | Render logs | self-hosted error tracking + an *external* uptime check |
| **Not self-hosted (on purpose)** | — | outbound email relay and geocoding search, see [§5](#5-what-we-deliberately-dont-self-host) |
| **Estimated cost** | $0 | **≈ €15–30 / month**, plus roughly **2–4 hours/month** of upkeep |

## 2. Current state and gaps

What blocks running this as a production service today, roughly in order
of severity. Self-hosting doesn't remove any of these; it changes who fixes
some of them.

| # | Gap | Why it matters |
|---|---|---|
| G1 | **No authentication.** Every screen defaults to `userId = 'u1'`; the API trusts whatever user ID it's sent. | Anyone can read or change anyone's data. Blocks [Community](features/community.md) and [Competitions](features/competitions.md) outright. |
| G2 | **Photos are public originals with EXIF.** `dao/storage.py` uploads the original file to a public bucket. | Phone photos with GPS publish the user's exact location (often their home) to anyone with the link. |
| G3 | **The photo-ID model doesn't fit the current server.** BioCLIP's checkpoint alone is ~571 MB, plus `torch`; the free instance has 512 MB total ([Photo-based bird ID](features/bird-id.md)). | Photo identification can crash the service under load. |
| G4 | **The backend sleeps.** Free Render instances spin down after 15 min idle, and the next request takes ~30 s+. | The first user after a quiet period gets errors or "Search failed" (seen live). |
| G5 | **Only one environment.** One Render service (`onlybirds-dev`) serves the dev site *and* is what `main` deploys to. | Dev testing and real users would share a server and a database. |
| G6 | **The geocoding use breaks the provider's policy.** Place search sends live-as-you-type queries to the public Nominatim server, which [forbids autocomplete and allows ~1 req/s total](https://operations.osmfoundation.org/policies/nominatim/). | We can be blocked without notice. |
| G7 | **Silent in-memory fallback.** Repos fall back to in-memory storage when `DATABASE_URL` is unset (`dao/db.py`). | A misconfigured production deploy would look healthy while losing every write on restart. |
| G8 | **Caches live in process memory.** Nominatim results, region checklists, photo/audio lookups and BioCLIP text embeddings are per-process dicts. | Lost on every deploy/restart: slow, cold first requests. |
| G9 | **Storage is tied to Supabase's API.** `dao/storage.py` speaks Supabase Storage's HTTP API. | Self-hosting storage means changing this one DAO (small, but required). |
| G10 | **The app isn't containerized.** There's no `Dockerfile` or compose file; Render builds from `requirements.txt` directly. | Needed so production, a future staging server and laptops all run the same thing. |
| G11 | **No backups we control, no monitoring, no alerting.** | Data loss or an outage would be noticed by users first. |
| G12 | **Migrations are run by hand** from a laptop with `psql`. | Easy to forget, or to run against the wrong database. |
| G13 | **The docs disagree on the database.** [Deployment](deployment.md) says Supabase; the code, `render.yaml` and [Backend](backend.md) say Neon. | Confusing; fix when Deployment is rewritten for this setup. |

## 3. Requirements

**Must** = required before real users. **Should** = soon after launch.

### Availability and performance

| ID | Requirement | Level |
|---|---|---|
| R1 | The backend is always on; no idle sleep. | Must |
| R2 | Typical API reads answer in < 1 s at p95; photo identification in < 10 s. | Must |
| R3 | A deploy interrupts service for at most a few seconds (health-checked container restart). | Must |
| R4 | Target 99% monthly uptime (≈ 7 h downtime/month). That's honest for one self-managed server; raise it only by adding a second server. | Should |
| R5 | Enough memory that photo ID can't starve the database: ≥ 8 GB RAM total, with per-container memory limits. | Must |

### Data

| ID | Requirement | Level |
|---|---|---|
| R6 | PostgreSQL with PostGIS, bound to the private Docker network only (never a public port). | Must |
| R7 | Nightly encrypted backups of the database **and** the photo volume, copied **off the server** (a different provider/location), ≥ 14 days retained. | Must |
| R8 | Recovery targets: lose at most 24 h of data (RPO), back up within 4 h (RTO). **A restore is tested before launch and every quarter.** Tighten RPO to minutes later with continuous WAL archiving. | Must (24 h) / Should (WAL) |
| R9 | Production and dev have separate databases, files and API keys. | Must |
| R10 | The app refuses to start in production without `DATABASE_URL` (no in-memory fallback). | Must |
| R11 | Migrations run as a deploy step with a manual approval, never from a laptop. | Should |
| R12 | Slow-changing external data is cached in Postgres cache tables (the pattern [Database](features/database.md) already documents), not only in process memory. | Should |

### Security and privacy

| ID | Requirement | Level |
|---|---|---|
| R13 | Real sign-in; every endpoint that reads or writes user data takes the user from a verified token, never from the request. | Must |
| R14 | EXIF stripped from stored photos; capture date/GPS into server-only columns first if needed ([Competitions](features/competitions.md#photo-verification)). | Must |
| R15 | HTTPS only (HTTP redirects); CORS allows only our own origin(s). | Must |
| R16 | **Server hardening:** SSH by key only (passwords and root login disabled), firewall allowing only 22/80/443, automatic OS security updates, fail2ban (or equivalent) on SSH. | Must |
| R17 | Secrets in a root-only `.env` on the server and in GitHub Actions secrets; never in the repo. Production keys separate from dev. | Must |
| R18 | Rate limiting on sign-in, writes, uploads and the geocode proxy. | Must |
| R19 | Container images and OS packages updated at least monthly; Dependabot alerts enabled on the repo. | Must |
| R20 | Account deletion removes the user's rows **and** their photo files. | Must |

### Operations

| ID | Requirement | Level |
|---|---|---|
| R21 | Error tracking for backend and frontend, with alerts. | Must |
| R22 | An uptime check **from outside the server** (a server can't report that it's down), alerting by email/phone. | Must |
| R23 | Disk, memory and CPU alerts (a full disk is the most common way a single server dies). | Must |
| R24 | Logs retained ≥ 14 days. | Should |
| R25 | A runbook: deploy, roll back, restore from backup, rotate a secret, rebuild the server from scratch. | Must |
| R26 | The whole server is reproducible from the repo (compose file + setup script), so losing the VPS means hours to rebuild, not days. | Should |

### Third-party terms and legal

| ID | Requirement | Level |
|---|---|---|
| R27 | Geocoding through a service whose terms allow autocomplete at our volume ([§5](#5-what-we-deliberately-dont-self-host)). | Must |
| R28 | Re-check the terms of every external data source for a public app: **eBird API**, **iNaturalist**, **Wikimedia Commons** attribution, and the **Esri basemap tiles** used by `Components/leaflet.js`. | Must |
| R29 | Privacy policy and terms of use published before sign-up opens. As the operator we're directly responsible for the personal data we store. | Must |
| R30 | Decide a minimum age (in-person outings; COPPA if under-13s are possible). | Must before Community |

## 4. Proposed architecture

```text
                       users (browser / installed PWA)
                                    │ HTTPS 443
                                    ▼
┌──────────────────────── VPS (Ubuntu LTS, Docker Compose) ─────────────────────────┐
│  caddy        reverse proxy + automatic TLS                                       │
│    ├─ <domain>/          → static frontend (frontend/)                            │
│    ├─ <domain>/media/*   → photo volume (read-only, EXIF already stripped)        │
│    └─ api.<domain>/*     → api                                                    │
│  api          FastAPI + BioCLIP (memory-limited container)                        │
│  db           PostgreSQL 16 + PostGIS (private network only, data volume)         │
│  glitchtip    error tracking (Sentry-compatible), optional at launch              │
│  backup       nightly pg_dump + photo volume → restic → off-site                  │
└───────────────────────────────────────────────────────────────────────────────────┘
        │ outbound only                                │ encrypted backups
        ▼                                              ▼
  eBird · iNaturalist · Wikimedia ·             off-site storage (different provider)
  geocoding API · email relay
                                        external uptime monitor ──► alerts
```

### 4.1 The server

**Proposed:** one VPS from a provider where we get root access and full
control of the OS. For example:

| Option | Spec | ≈ price / month |
|---|---|---|
| **Hetzner Cloud CX33** (shared vCPU) | 4 vCPU, 8 GB RAM, 80 GB SSD | €6.49 + €0.50 IPv4 |
| Hetzner CCX13 (dedicated vCPU, steadier performance) | 2 vCPU, 8 GB RAM, 80 GB SSD | €15.99 |
| DigitalOcean Basic droplet | 4 vCPU, 8 GB RAM, 160 GB SSD | $48 |

**Recommendation: Hetzner, 8 GB RAM.** The memory budget is roughly
3 GB for the API with BioCLIP loaded, 2 GB for Postgres, ~1 GB for Caddy +
error tracking + OS, plus headroom. **Measure the API's peak memory during
a photo ID before committing**; if it's higher, resize the VPS (Hetzner
resizes in place). Pick a datacenter near users. Hetzner's US locations
(Ashburn, Hillsboro) don't offer every plan line, so check availability.
Hetzner raised prices twice in 2026, so confirm current numbers.

**Why a VPS, not hardware at home:** a home server is the most "owned"
option, but residential internet usually means a changing IP, blocked
ports, no SLA, and an outage whenever the power or router does. A VPS
keeps full control of the software and data, while the provider handles
power, network and failed disks. If a home server is still wanted, it
makes a good **staging** box or an **extra backup target**.

### 4.2 Containers (Docker Compose)

Everything runs as Docker containers defined in a `deploy/compose.yml`
in the repo (new), so production, a future staging server and laptops run
the same thing:

- **`caddy`**: TLS certificates from Let's Encrypt, renewed automatically.
  Serves `frontend/` and the photo volume directly, and proxies to `api`.
- **`api`**: built from a new `backend/Dockerfile`. Runs uvicorn with
  enough workers for the CPU, bearing in mind **each worker loads its own
  copy of BioCLIP**, so start with 1–2 workers and measure. Hard memory
  limit so a runaway request can't take the database down with it.
- **`db`**: the official `postgis/postgis` image. Data on a named volume;
  no published port, so only `api` and `backup` can reach it.
- **`backup`**: a small scheduled container (or a host cron job) running
  `pg_dump` and `restic` ([§4.6](#46-backups-and-recovery)).

### 4.3 Database

PostgreSQL 16 + PostGIS, self-managed. What we take on:

- **Tuning:** set `shared_buffers`, `work_mem` etc. for ~2 GB, not the
  defaults (e.g. with PGTune).
- **Connections:** `dao/db.py`'s pool (`max_size=5`, sized for Neon's free
  tier) can grow; Postgres on the same box allows ~100 by default.
- **Upgrades:** minor versions with image updates; **major versions**
  (16 → 17) need a planned `pg_dump`/restore or `pg_upgrade`, about once a
  year at most.
- **Migrating dev data** (optional): `pg_dump` from Neon, restore into the
  new database. Otherwise production starts empty and runs
  `backend/migrations/` from `0001`.

### 4.4 File storage

Photos and avatars go to a Docker volume on the VPS (e.g.
`/srv/onlybirds/media`), and Caddy serves them under `/media/`.

- `dao/storage.py` changes from "POST to Supabase" to "write a file". The
  DAO layer keeps this to one file (G9).
- **EXIF is stripped before the file is written** (R14), so serving files
  publicly no longer leaks locations.
- 80 GB of disk holds tens of thousands of phone photos. Add a Hetzner
  *Volume* (block storage, cheap per GB) when it fills, and alert at 80%
  disk (R23).
- **If we later want an S3-style API** (e.g. for direct browser uploads),
  a self-hosted S3-compatible store such as Garage or SeaweedFS can replace
  the plain folder. Not needed at launch.

### 4.5 Authentication

Supabase Auth was the plan, but it's a hosted service. The self-hosted
choices:

| Option | What it is | Trade-off |
|---|---|---|
| **A. Sign-in built into our backend** (recommended) | email + password accounts in our own Postgres: Argon2 password hashing (`argon2-cffi`), short-lived signed access tokens + revocable refresh tokens stored in the database, email verification and password reset via the email relay | Smallest footprint (no extra service or RAM). We own the security-sensitive code, so it must follow a checklist (hashing, rate limits, token expiry, constant-time compares, reset-token expiry) and get a careful review. |
| B. Self-hosted identity server | e.g. Authentik, Zitadel, Keycloak, Ory Kratos: full-featured (social login, MFA, admin UI) | Another service to run, patch and back up; 0.5–2 GB more RAM; more moving parts than this app needs today. |

Either way, every endpoint that reads or writes user data takes the user
from the verified token (R13), and the `'u1'` defaults are removed.
"Sign in with Google/Apple" can be added later with either option.

### 4.6 Backups and recovery

The part of self-hosting that matters most, because nobody else is doing it:

- **Nightly:** `pg_dump` (compressed) + the photo volume, uploaded with
  **restic** (encrypted, deduplicated, with its own retention policy) to
  storage at a **different provider or location** than the VPS, e.g. a
  Hetzner Storage Box in another region, or Backblaze B2. The data is
  encrypted before it leaves the server, so the backup host can't read it.
- **Retention:** 14 daily, 8 weekly, 6 monthly.
- **VPS snapshots** (Hetzner's backup option, +20% of server price) as a
  fast "roll the whole machine back" button. These are a convenience, *not*
  a substitute for off-site backups: they live with the same provider.
- **Restore drill** before launch and quarterly: restore last night's
  backup onto a fresh throwaway server and check the app works (R8).
- **Later:** continuous WAL archiving (pgBackRest or WAL-G) cuts possible
  data loss from 24 h to minutes.

### 4.7 Domain, DNS, TLS

Register a domain (≈ €10–20/year). Use `<domain>` for the app and
`api.<domain>` for the API (or `/api` on the same origin, which also
removes the need for CORS). Caddy obtains and renews certificates
automatically. `Dao/apiClient.js` gets the production hostname → API URL
mapping (its own comment anticipates this).

### 4.8 Monitoring and alerting

- **Errors:** **GlitchTip** (open source, Sentry-compatible, light enough
  for this box) self-hosted; the Sentry SDKs in FastAPI and the frontend
  report to it (R21). Sentry's own self-hosted edition is far heavier
  (needs 16 GB+), so not recommended.
- **Uptime:** must run **outside** the VPS (R22). Either Uptime Kuma on a
  second tiny server or a home machine (fully owned), or a free external
  pinger (UptimeRobot / Better Stack) as a pragmatic start.
- **Host metrics:** disk, memory, CPU alerts (R23), e.g. Netdata on the VPS
  or the provider's built-in graphs + alert rules.
- **Logs:** Docker's log driver with rotation; keep ≥ 14 days (R24).

### 4.9 Deploys and CI/CD

The existing flow stays: features → `dev/current` → release PR → `main`.
For production:

1. On push to `main`, GitHub Actions builds the API image and pushes it to
   GitHub Container Registry.
2. A **`production` GitHub environment** with required reviewers gates
   the deploy job.
3. The job SSHes to the VPS (a deploy-only user with a dedicated key),
   runs migrations (`backend/scripts/migrate.sh` inside the network), then
   `docker compose pull && docker compose up -d`. The API container's health
   check gates the switch (R3, R11).
4. **Rollback:** redeploy the previous image tag. Migrations stay additive
   (add, don't drop), so the previous image still runs.

### 4.10 Dev and staging

- **Dev** can stay on the current free managed tiers for now: it costs
  nothing and already works.
- Once the compose setup exists, a **small staging VPS** (≈ €4–7/month),
  deployed from `dev/current`, gives a production-identical place to test,
  and a place to run restore drills. Recommended before Community launches.

## 5. What we deliberately don't self-host

Self-hosting everything isn't always the more "owned" choice. These two
are much worse self-hosted at our scale:

| Service | Why not self-host | Proposed |
|---|---|---|
| **Outbound email** (verification, password reset, notifications) | Mail from a fresh VPS IP lands in spam or is rejected outright. Many providers (Hetzner included) block outbound port 25 on new accounts. Deliverability takes ongoing reputation work. | A transactional **SMTP relay** (e.g. Postmark, Amazon SES, Resend) sending as `no-reply@<domain>` with SPF/DKIM/DMARC set on *our* domain. The domain and DNS stay ours, and `dao/email.py` is already plain SMTP, so switching relays is configuration. |
| **Geocoding search** (place autocomplete) | The self-hostable autocomplete geocoder, [Photon](https://github.com/komoot/photon), recommends **64 GB RAM** and ~95 GB of disk for worldwide data, which is several times this whole server. | A geocoding API whose terms allow autocomplete (e.g. LocationIQ, Geoapify, MapTiler), behind our existing `/geocode/*` proxy. **Later option:** self-host Photon with only a regional (e.g. North America) data extract on a separate server, if users are concentrated there. |

eBird, iNaturalist and Wikimedia are data sources, not infrastructure, so
they stay external by nature.

## 6. What we become responsible for

Moving from managed platforms to our own server shifts these to us:

| Responsibility | Managed platform (before) | Self-hosted (now) | How we cover it |
|---|---|---|---|
| OS security patches | platform | **us** | `unattended-upgrades` for security updates; monthly reboot window |
| TLS certificates | platform | automatic | Caddy |
| Database backups + restores | platform | **us** | [§4.6](#46-backups-and-recovery), quarterly drill |
| Postgres upgrades | platform | **us** | yearly planned major upgrade |
| Uptime / incident response | platform (partly) | **us** | external monitor + alerts; best-effort response |
| Hardware failure | platform | provider (hardware), **us** (data) | off-site backups + reproducible setup (R26) |
| Capacity | platform scales on request | **us** | disk/memory alerts; resize VPS |
| Security hardening | platform | **us** | R16 checklist, Dependabot, monthly image updates |

**Expected effort:** ~2–4 hours a month (updates, checking backups and
alerts), plus initial setup of a few days. At least **two people** should
have server access and know the runbook.

## 7. Application changes production needs

| Change | Closes | Size |
|---|---|---|
| Sign-in (option A or B, [§4.5](#45-authentication)) + token verification on every user endpoint; remove the `'u1'` defaults | G1, R13 | large (own feature page) |
| Strip EXIF at upload (`services/uploads.py`) | G2, R14 | small |
| `backend/Dockerfile` + `deploy/compose.yml` + `deploy/Caddyfile` | G10, R26 | medium |
| `dao/storage.py` → local volume | G9 | small |
| `ENVIRONMENT=production` setting: refuse to start without `DATABASE_URL`, lock CORS, enable error reporting | G7, R10, R15, R21 | small |
| Rate limiting (e.g. `slowapi`) on sign-in, writes, uploads, `/geocode` | R18 | small |
| Geocoder swap in `dao/nominatim.py` | G6, R27 | small |
| Production hostname in `Dao/apiClient.js` | [§4.7](#47-domain-dns-tls) | tiny |
| Move process caches to Postgres cache tables | G8, R12 | medium |
| Account deletion incl. photo files | R20 | medium |
| Build + deploy + migrate GitHub Actions workflow | G12, R11 | medium |
| Rewrite [Deployment](deployment.md) for this setup | G13 | small |

## 8. Cost estimate

Monthly, at launch scale (hundreds of users):

| Item | ≈ / month |
|---|---|
| VPS: Hetzner CX33 (4 vCPU / 8 GB) + IPv4 | €7 |
| VPS snapshots (+20%) | €1.50 |
| Off-site backup storage (Storage Box / B2, ~100 GB) | €3–5 |
| Domain (≈ €15/year) | €1–2 |
| Email relay | free tier → a few € with volume |
| Geocoding API | free tier (watch volume) |
| Error tracking, uptime | €0 (self-hosted GlitchTip; free external pinger) |
| **Production total** | **≈ €15–20** |
| Optional: dedicated-vCPU server (CCX13) instead | +€9 |
| Optional: staging VPS | +€4–7 |

That's about a third of the managed equivalent (Render Standard +
Supabase Pro ≈ $50–70/month); the difference is paid in our time ([§6](#6-what-we-become-responsible-for)).

## 9. Rollout plan

1. **Decide** the open questions in [§10](#10-open-decisions); buy the domain.
2. **Containerize** (Dockerfile, compose, Caddyfile) and get the full stack
   running on a laptop with `docker compose up`.
3. **Ship the "Must" code changes** from [§7](#7-application-changes-production-needs)
   (sign-in, EXIF, storage DAO, production settings, rate limits, geocoder).
4. **Provision** the VPS: hardening checklist (R16), Docker, firewall,
   DNS records, secrets.
5. **Set up backups first**, then do a restore drill onto a throwaway
   server, *before* any real user data exists.
6. **Wire the deploy workflow**; deploy; run migrations.
7. **Load-check:** measure memory during photo ID with a few concurrent
   users; set container memory limits from what you see.
8. **Soft launch** to an invited group; watch errors, memory and disk for
   a couple of weeks.
9. Write the runbook (R25) and rewrite [Deployment](deployment.md).

## 10. Open decisions

1. **Provider and location:** Hetzner (recommended on price) vs another VPS
   host; which region, depending on where users are.
2. **Shared vs dedicated vCPU:** CX33 (cheapest) vs CCX13 (steadier
   photo-ID latency).
3. **Authentication:** built into the backend (option A, recommended) vs a
   self-hosted identity server (option B).
4. **Email relay and geocoding API** vendors, or self-host a regional
   geocoder later.
5. **Uptime monitoring:** fully owned (Uptime Kuma on a second machine) vs
   a free external pinger.
6. **Staging server** now or later.
7. **Who has server access** (at least two people) and who gets alerts.
8. **Domain name.**

## Related pages

- [Deployment](deployment.md): how the current (dev) setup is stood up
- [Production on AWS or another cloud](production-environment-cloud.md): the alternative
- [External services & API risk](external-services.md)
- [Architecture](architecture.md)
- [Photo-based bird ID](features/bird-id.md): BioCLIP's memory footprint
- [Community](features/community.md) / [Competitions](features/competitions.md): need sign-in and the EXIF fix
- [Database & migrations](features/database.md)
