#!/usr/bin/env bash
#
# Apply every backend/migrations/*.sql file, in filename order, against the
# database in $DATABASE_URL. Safe to re-run: a file that has already been
# applied is skipped (tracked in the schema_migrations table).
#
# Usage:
#   export DATABASE_URL="postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres"
#   ./backend/scripts/migrate.sh
#
# Requires the psql client:  https://www.postgresql.org/download/
#
set -euo pipefail

cd "$(dirname "$0")/.."   # -> backend/

# Load backend/.env if present, so you don't have to export DATABASE_URL by hand.
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

: "${DATABASE_URL:?set DATABASE_URL in backend/.env (copy from .env.example)}"

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -c "
  create table if not exists schema_migrations (
    filename   text primary key,
    applied_at timestamptz not null default now()
  );"

shopt -s nullglob
for f in migrations/*.sql; do
  name=$(basename "$f")
  applied=$(psql "$DATABASE_URL" -tAc \
    "select 1 from schema_migrations where filename = '$name'")
  if [ "$applied" = "1" ]; then
    echo "skip    $name  (already applied)"
    continue
  fi
  echo "apply   $name"
  # the migration and its bookkeeping row commit together, or not at all
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction \
    -f "$f" \
    -c "insert into schema_migrations (filename) values ('$name');"
done

echo "migrations up to date."
