# Community

> **Status:** Scoping — nothing built. This page is a first-pass scope:
> the shape of the feature, the data model, and the decisions still open
> (listed in [§8](#8-open-questions)). **Blocked on real sign-in**: see
> [Prerequisites](#prerequisites) before writing any code.

## 1. What you're building

A **Community** screen (a Home button, next to Plan a Trip) where birders
can do two things:

1. **Talk bird** — a discussion board. Anyone signed in can start a thread
   ("Anyone seen the Snowy Owl at Discovery Park this week?", "ID help:
   sparrow at my feeder"), and others reply. A thread can optionally be
   tagged with a **species** and can optionally attach one of the author's
   own **observations**. That makes "help me ID this" and "look what I
   saw" posts first-class, not just text.
2. **Make outing plans** — an outing is a thread with an event attached:
   *where* (a public eBird hotspot), *when* (date + start time), an
   optional cap on attendees, and an RSVP button (going / maybe). People
   ask questions about the outing in that thread's replies, using the same
   reply system as discussions.

Both are **scoped to a region** by default. The board opens on the user's
`default_region` (see [User profiles](user-profiles.md#default-region)),
so someone in Washington sees Washington threads and outings, not a global
firehose. A region picker (the same `RegionPicker` the Life List uses)
switches region, and `world` shows everything.

### Screens

| Screen | What's on it |
|---|---|
| **Community** (list) | Two tabs: *Discussions* (newest-activity first) and *Outings* (upcoming first, past outings hidden by default). Region picker. "New thread" / "Plan an outing" buttons. |
| **Thread** | The original post (with species tag / attached observation card if present), then replies oldest-first, then a reply box. For an outing: an event header above the post (hotspot, date/time, mini map, attendee count, RSVP button, attendee list). |
| **New thread / New outing** | A form. Outings reuse Plan a Trip's place search, but pick from **eBird hotspots** near the search result, not a free address (see [Safety](#safety-and-moderation)). |

### Deliberately *not* in v1

| Not building | Why |
|---|---|
| **Live chat / direct messages** | Real-time chat needs websockets or a push service, which is a poor fit for Render's free tier (the service sleeps after 15 min idle). DMs are also the single biggest moderation and harassment surface. A threaded board plus the existing notification bell covers "talk bird" without either. Revisit after v1 has real users. |
| **Followers / friends graph** | [User profiles](user-profiles.md) already decided "no follower graph in MVP"; region scoping does the job of "show me people near me." |
| **Likes / upvotes, rich text, image uploads in posts** | Nice-to-haves. Photos already come in through an attached observation, which reuses Add Observation's existing upload path. |
| **Recurring outings** | Every outing is one event. A weekly walk is posted weekly. |

### Entry points from existing screens

These are cheap cross-links that make the feature feel woven in rather
than bolted on. They are phase 3 in the [build order](#6-build-order):

- **Plan a Trip → hotspot drill-down**: "Plan an outing here" button,
  prefilled with that hotspot and the trip's start date.
- **Bird info page**: "Discussions about this bird" (threads tagged with
  that species).
- **Add Observation (after saving)**: "Share to Community" starts a thread
  with that observation attached.
- **Notification bell**: replies, RSVPs, and outing changes arrive through
  the existing feed (new `kind`s, see [§3](#3-database-changes-sql)).

## Prerequisites

!!! warning "Real sign-in is a hard blocker"
    Today every screen defaults to `userId = 'u1'` (`Home.js`,
    `ReportButton.js`, ...), and the backend trusts whatever user ID the
    request carries. [User profiles](user-profiles.md#auth) lists token
    verification as a follow-up. That has been harmless so far because
    everything a user creates is only visible to that user. Community is the
    first feature where one user's content is shown to **other** users, so
    without verified identity anyone can post, edit or delete as anyone
    else. Before phase 1:

    1. **Sign-in on the frontend.** Supabase Auth is the natural fit, since
       Supabase Storage is already in use for photos (`SUPABASE_URL` is
       already configured).
    2. **Token verification on the backend.** A FastAPI dependency that
       verifies the Supabase JWT and resolves it to a `users` row. Every
       community write endpoint takes the user from the token, **never**
       from the request body or query string.
    3. **Usernames.** Posts display an author name. `users.username` exists
       (migration 0003), but the profile *frontend* isn't built yet. At
       minimum, a "pick a username" step on first sign-in is needed.

    This is worth scoping as its own feature page (`auth.md`), because every
    existing screen benefits from it, not just Community.

## Safety and moderation

Outings put strangers from the internet in the same physical place, so the
defaults lean cautious:

- **Outings meet at public eBird hotspots only.** The location is picked
  from `GET /ref/hotspot/geo` results (already wrapped for Plan a Trip),
  never typed as a free address. That way nobody posts their home as a
  meeting point, and every outing location is an established public
  birding site.
- **Report a post or reply.** Each post and reply gets a small "Report"
  action that writes a `content_reports` row and emails the team (reusing
  `app/dao/email.py` from the beta Report-a-problem button). Content with
  **3+ distinct reports is auto-hidden** pending review.
- **Authors can edit and delete their own content.** Deletes are soft
  (`deleted_at`), so a reply chain doesn't collapse and reports keep their
  target.
- **Rate limits.** For example, at most 10 threads/outings and 60 replies
  per user per day, enforced in the service layer. That's enough for any real
  use and blunts spam.
- **Admin removal.** A minimal `users.is_admin` flag, plus `DELETE`
  endpoints that bypass the author check. There's no admin UI in v1;
  removals are done by API call.
- **Sensitive species.** eBird hides exact locations for some species
  (nesting owls, poaching targets). Tagging a thread with one of those is
  fine, but the attached-observation map for that thread should show the
  region only, not the pin. See [open question 5](#8-open-questions).

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| Threads (discussions + outings) | the user | `threads` |
| Outing details (hotspot, time, cap) | the user picks a hotspot from eBird `GET /ref/hotspot/geo` (already used by Plan a Trip) | `outings`. Hotspot name/lat/lng are **copied in** at creation, so an outing still renders if eBird is down or renames the hotspot |
| Replies | the user | `thread_replies` |
| RSVPs | the user | `outing_rsvps` |
| Species tag | the existing species search (Add Observation's identification flow) | `threads.scientific_name` + `common_name`, keyed on scientific name for the same reason `pinned_birds` is (see `0005_pinned_birds_and_notifications.sql`) |
| Attached observation | the author's own `observations` row | `threads.observation_id` (FK). The card is rendered live from the observation |
| Author name / avatar | `users.username`, `users.avatar_url` | not copied, joined at read time |
| Reports | the user | `content_reports`, plus an email to the team |
| Reply / RSVP / outing-changed alerts | our own writes | `notifications` (existing table, new `kind`s) |
| Region | the thread's author picks it (defaults to their `default_region`); for an outing it's derived from the hotspot's own `subnational1Code` | `threads.region_code` |

No new external API. Everything is our own data, plus one eBird call that
Plan a Trip already makes.

## 3. Database changes (SQL)

One migration. See [Database & migrations](database.md#how-to-apply-a-migration).
The next free number is `0007`.

```sql
-- 0007_community.sql

-- one row per discussion thread OR outing (an outing is a thread + an outings row)
create table threads (
    id               uuid primary key default gen_random_uuid(),
    user_id          uuid not null references users(id) on delete cascade,
    kind             text not null check (kind in ('discussion', 'outing')),
    region_code      text not null,                -- eBird region code, e.g. 'US-WA'; 'world' allowed
    title            text not null check (char_length(title) between 1 and 140),
    body             text not null default '' check (char_length(body) <= 5000),
    scientific_name  text,                         -- optional species tag
    common_name      text,                         -- denormalized for display
    observation_id   uuid references observations(id) on delete set null,
    reply_count      integer not null default 0,   -- maintained by the service, for list sorting/display
    last_activity_at timestamptz not null default now(),
    hidden_at        timestamptz,                  -- set by auto-hide (3+ reports) or an admin
    deleted_at       timestamptz,                  -- soft delete by author
    edited_at        timestamptz,
    created_at       timestamptz not null default now()
);
create index threads_region_activity_idx on threads (region_code, kind, last_activity_at desc)
    where deleted_at is null and hidden_at is null;
create index threads_species_idx on threads (scientific_name) where scientific_name is not null;

-- the event half of an outing thread (1:1 with threads where kind = 'outing')
create table outings (
    thread_id      uuid primary key references threads(id) on delete cascade,
    ebird_loc_id   text not null,                  -- eBird hotspot id, e.g. 'L123456'
    location_name  text not null,                  -- copied from eBird at creation
    lat            double precision not null,
    lng            double precision not null,
    starts_at      timestamptz not null,
    ends_at        timestamptz,
    max_attendees  integer check (max_attendees is null or max_attendees > 0),
    cancelled_at   timestamptz
);
create index outings_starts_idx on outings (starts_at) where cancelled_at is null;

create table thread_replies (
    id          uuid primary key default gen_random_uuid(),
    thread_id   uuid not null references threads(id) on delete cascade,
    user_id     uuid not null references users(id) on delete cascade,
    body        text not null check (char_length(body) between 1 and 5000),
    hidden_at   timestamptz,
    deleted_at  timestamptz,
    edited_at   timestamptz,
    created_at  timestamptz not null default now()
);
create index thread_replies_thread_idx on thread_replies (thread_id, created_at);

create table outing_rsvps (
    thread_id   uuid not null references outings(thread_id) on delete cascade,
    user_id     uuid not null references users(id) on delete cascade,
    status      text not null check (status in ('going', 'maybe')),
    created_at  timestamptz not null default now(),
    primary key (thread_id, user_id)
);

create table content_reports (
    id           uuid primary key default gen_random_uuid(),
    reporter_id  uuid not null references users(id) on delete cascade,
    target_type  text not null check (target_type in ('thread', 'reply')),
    target_id    uuid not null,
    reason       text,
    created_at   timestamptz not null default now(),
    unique (reporter_id, target_type, target_id)   -- one report per person per item
);

alter table users add column is_admin boolean not null default false;

-- new notification kinds
alter table notifications drop constraint notifications_kind_check;
alter table notifications add constraint notifications_kind_check
    check (kind in ('pin_hit', 'sticker_awarded',
                    'thread_reply', 'outing_rsvp', 'outing_changed', 'outing_cancelled'));
```

| Table | Why it exists |
|---|---|
| `threads` | One table for both discussions and outings, so the list, reply, report and hide logic is written once. `kind` says which. |
| `outings` | The event fields only an outing has. Kept out of `threads` so discussions don't carry eight always-null columns. |
| `thread_replies` | Flat replies (no nesting). A flat list is easier to read on a phone and easier to build. |
| `outing_rsvps` | Who's coming. The primary key means one RSVP per person; changing going → maybe is an upsert, and un-RSVPing is a delete. |
| `content_reports` | The moderation queue, and the count that drives auto-hide. |

!!! note "Check the constraint name before running"
    `notifications_kind_check` is Postgres's auto-generated name for the
    inline check in 0005. Confirm it with `\d notifications` before applying.
    Also extend `NotificationKind` in `app/models/notification.py` to match.

## 4. API endpoints

All writes take the user from the verified token (see
[Prerequisites](#prerequisites)), never from the body.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/community/threads?region=&kind=&species=&cursor=` | list, newest activity first; `kind=outing` sorts by `starts_at` and hides past outings unless `include_past=true` |
| `POST` | `/community/threads` | `{kind:'discussion', region_code, title, body, scientific_name?, observation_id?}` |
| `GET` | `/community/threads/{id}` | thread + replies (+ outing + RSVP summary if an outing) |
| `PATCH` | `/community/threads/{id}` | author only: title / body / species |
| `DELETE` | `/community/threads/{id}` | author or admin; soft delete |
| `POST` | `/community/outings` | `{title, body, ebird_loc_id, starts_at, ends_at?, max_attendees?}`. The server looks up the hotspot to fill name/lat/lng/region rather than trusting client-sent coordinates |
| `PATCH` | `/community/outings/{id}` | author only. Changing time or place notifies everyone who RSVP'd (`outing_changed`) |
| `POST` | `/community/outings/{id}/cancel` | author only; notifies RSVPs (`outing_cancelled`) |
| `PUT` | `/community/outings/{id}/rsvp` | `{status:'going'|'maybe'}`. Returns 409 if `going` would exceed `max_attendees` |
| `DELETE` | `/community/outings/{id}/rsvp` | un-RSVP |
| `POST` | `/community/threads/{id}/replies` | `{body}`. Notifies the thread author (`thread_reply`) |
| `PATCH` / `DELETE` | `/community/replies/{id}` | author only (delete: author or admin) |
| `POST` | `/community/reports` | `{target_type, target_id, reason?}`. The third distinct report sets `hidden_at` |

### Example — `GET /community/threads/{id}` for an outing

```json
{
  "id": "6f1c…",
  "kind": "outing",
  "title": "Saturday morning warbler walk",
  "body": "Meeting at the south parking lot. Beginners welcome!",
  "author": { "username": "hawkeye", "avatar_url": null },
  "region_code": "US-WA",
  "scientific_name": null,
  "outing": {
    "location_name": "Discovery Park",
    "ebird_loc_id": "L162763",
    "lat": 47.6618, "lng": -122.4219,
    "starts_at": "2026-10-17T08:00:00-07:00",
    "max_attendees": 12,
    "going_count": 5, "maybe_count": 2,
    "my_rsvp": "going",
    "cancelled": false
  },
  "replies": [
    { "id": "…", "author": { "username": "owlbert" }, "body": "Is there parking?", "created_at": "…" }
  ]
}
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/community_repo.py` (**new**) | SQL for threads, outings, replies, RSVPs, reports. Same in-memory + Postgres dual pattern as `notification_repo.py` |
| `dao/` | `app/dao/ebird.py` (reuse) | hotspot lookup by `locId` when creating an outing |
| `services/` | `app/services/community.py` (**new**) | author/admin checks, rate limits, reply-count + `last_activity_at` upkeep, auto-hide at 3 reports, capacity check on RSVP, firing notifications |
| `services/` | `app/services/notifications.py` (extend) | the four new `kind`s |
| `routers/` | `app/routers/community.py` (**new**) | the endpoints above; register in `app/main.py` |
| `models/` | `app/models/community.py` (**new**) | Pydantic request/response models |
| `Dao/` | `frontend/src/Dao/community.js` (**new**) | raw calls |
| `Services/` | `frontend/src/Services/community.js` (**new**) | UI-shaped models (relative times, "3 spots left") |
| `Presenters/` | `Presenters/Community.js` (**new**) | list screen with the two tabs + region picker |
| `Presenters/` | `Presenters/CommunityThread.js` (**new**) | thread / outing detail, replies, RSVP |
| `Presenters/` | `Presenters/CommunityCompose.js` (**new**) | new thread / new outing form |
| `Components/` | `ThreadCard.js`, `OutingHeader.js` (**new**); reuse `SightingsMap.js` (outing mini map), `SightingDetail.js` (attached observation card) | presentational |

Like Plan a Trip, the reply box needs the targeted-update treatment (don't
full-`render()` while someone is typing) when a background refresh lands.

**Freshness without websockets:** the thread screen re-fetches when the
tab regains focus and after the user's own post. The notification bell
already polls for unread counts, and that's enough to surface "someone
replied" in v1.

## 6. Build order

**Phase 0: prerequisites** (separate feature, see [above](#prerequisites))

1. Supabase Auth sign-in on the frontend; replace the `'u1'` defaults.
2. Backend JWT-verification dependency; resolve token → `users` row.
3. First-sign-in username picker.

**Phase 1: discussions**

4. Write and run `backend/migrations/0007_community.sql`.
5. `community_repo.py` → `community.py` service → `community.py` router.
   Tests: create/list/reply, author-only edit, soft delete hides from
   lists, rate limit, region filter.
6. Frontend: `Community.js` (discussions tab only) → `CommunityThread.js`
   → `CommunityCompose.js`. Add the Home button.
7. Report action + auto-hide + email. Ship phase 1 here.

**Phase 2: outings**

8. Outing create (with hotspot lookup), RSVP, capacity, cancel.
   Tests: capacity 409, RSVP upsert, cancelled outings sort out of "upcoming."
9. Frontend: Outings tab, `OutingHeader` with mini map + RSVP, outing
   compose form with the hotspot picker.
10. Notifications: `thread_reply`, `outing_rsvp`, `outing_changed`,
    `outing_cancelled` in the feed + bell.

**Phase 3: cross-links**

11. Plan a Trip "Plan an outing here", Bird info "Discussions about this
    bird", Add Observation "Share to Community".
12. Optional: an outing-reminder notification the day before (needs a
    scheduled job, since Render free tier has no cron; could be a GitHub
    Actions schedule hitting an endpoint).

## 7. Related pages

- [User profiles](user-profiles.md): usernames, avatars, `default_region`, and the auth follow-up this depends on
- [Plan a trip](plan-a-trip.md): the hotspot lookup and place search outings reuse
- [Pinned birds](pinned-birds.md): the `notifications` table and bell this extends
- [Add Observation](add-observation.md): the observation a thread can attach
- [Bird information page](bird-info.md): a "discussions about this bird" entry point
- [Database & migrations](database.md)

## 8. Open questions

Decisions to make before or during phase 1. Each has a recommended default,
so work can start without blocking on them.

1. **Region-scoped or one global board?** *Recommended: region-scoped,
   defaulting to `default_region`, with `world` as an option.* Outings are
   inherently local, and a small user base can widen to country level or
   `world` with the picker.
2. **Who can create outings?** *Recommended: any signed-in user in v1*,
   gated only by the rate limit. Alternative: require an account older
   than N days or a minimum number of logged observations, as a light
   anti-spam/anti-creep filter.
3. **Should RSVP lists be public?** *Recommended: show usernames of
   "going" attendees to other signed-in users only*, so people know who
   they're meeting. Hide them from signed-out visitors.
4. **Can signed-out visitors read the board?** *Recommended: yes, read
   only*, since it's good for discovery. Posting, replying and RSVPing need
   sign-in.
5. **Sensitive species handling.** Does eBird's sensitive-species list
   need to be pulled in (for hiding attached-observation pins), or is
   region-only display for *every* attached observation simpler and good
   enough? *Leaning toward the latter for v1.*
6. **Age and safety policy for in-person meetups.** Does the app need a
   minimum age or a meetup-safety notice on outing pages? This is a
   product/policy call, not an engineering one.
