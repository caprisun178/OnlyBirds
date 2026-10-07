-- 0008_bug_reports_owner_and_investigating.sql
-- Extends 0007_bug_reports.sql: an "investigating" status between
-- not_started and the two terminal states, and an owner column so an admin
-- can claim a report. See Presenters/BugBacklog.js.

alter table bug_reports drop constraint if exists bug_reports_status_check;
alter table bug_reports add constraint bug_reports_status_check
    check (status in ('not_started', 'investigating', 'not_fixed', 'fixed'));

-- Plain text, same reasoning as user_id on this table (0007's own comment):
-- no auth/roles exist yet (user-profiles.md is still "Planned"), so there's
-- no real admin identity to reference — whoever takes ownership just types
-- a name here. Revisit once real accounts exist.
alter table bug_reports add column if not exists owner text;
