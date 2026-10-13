-- 0009_observation_import_batch.sql
-- Bulk photo import (docs/features/bulk-import.md §3): every observation
-- logged by one import shares an import_batch_id, so "Undo this import"
-- can delete exactly that set. Null for wizard-logged observations.
-- Apply with backend/scripts/migrate.sh.

alter table observations add column if not exists import_batch_id text;

create index if not exists observations_import_batch_idx
    on observations (user_id, import_batch_id)
    where import_batch_id is not null;
