-- 0007_bug_reports.sql
-- See app/services/feedback.py and the admin bug-backlog screen
-- (Presenters/BugBacklog.js). Replaces the beta "Report a problem" button's
-- old behavior (one email per report, see git history for
-- app/dao/email.py) with a persisted, triageable backlog instead.

create table if not exists bug_reports (
    id          uuid primary key default gen_random_uuid(),
    message     text not null,
    screen      text,                 -- which route the reporter was on, e.g. "life-list"
    url         text,                 -- full page URL, for the exact state/query params
    -- Plain text, not a FK to users(id): a report is useful even from a
    -- user row that doesn't exist yet (no real auth/profiles — see
    -- user-profiles.md), and nothing here needs referential integrity with
    -- the user table the way observations/pinned_birds do.
    user_id     text,
    user_agent  text,
    status      text not null default 'not_started'
                    check (status in ('not_started', 'not_fixed', 'fixed')),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create index if not exists bug_reports_status_idx on bug_reports (status, created_at desc);
