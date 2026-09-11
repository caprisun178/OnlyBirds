# Verify your setup

Run these checks after [Set up & test your changes](setup-and-test.md). Each one
is a command and what you should see. If a check fails, the fix is linked.

Tick as you go:

- [ ] Python is 3.13+
- [ ] Dependencies are installed in the venv
- [ ] The backend starts
- [ ] `/health` responds
- [ ] `/docs` loads in a browser
- [ ] iNaturalist call works (no key needed)
- [ ] eBird call works (needs the key) — or you know it's running key-less
- [ ] Tests pass
- [ ] *(optional)* Docs site builds
- [ ] *(optional)* Database reachable + migrations applied

## 1. Python version

```bash
python --version
```

Expect `Python 3.13.x`. Older → install 3.13 (see
[Environment Setup](index.md#prerequisites)).

## 2. Virtual env + dependencies

With the venv active:

```bash
pip show fastapi
```

Expect a version line. `WARNING: Package(s) not found` → you're not in the venv,
or `pip install -r requirements.txt` hasn't run. See
[Environment Setup → Back-end setup](index.md#3-back-end-setup).

## 3. The backend starts

From `backend/`:

```bash
python -m uvicorn main:app --reload
```

Expect it to end with `Application startup complete.` Leave it running and open a
**second terminal** for the next checks. `ModuleNotFoundError: No module named
'app'` → run from inside `backend/`.

## 4. `/health` responds

```bash
curl http://localhost:8000/health
```

Expect:

```json
{"status":"ok","version":"...","ebird_key_configured":true}
```

`"ebird_key_configured":false` is fine — it just means you haven't added a key
yet (checks 6 and 8 still work).

## 5. `/docs` loads

Open <http://localhost:8000/docs>. Expect the interactive API page listing
`/health`, `/species/search`, `/sightings/nearby`, `/observations`, and
`/users/{user_id}/life-list`.

## 6. iNaturalist call (no key needed)

```bash
curl "http://localhost:8000/species/search?q=raven"
```

Expect a JSON array with entries like
`{"scientific_name":"Corvus corax","common_name":"Common Raven",...}`. An error
or empty array here means the server can't reach `api.inaturalist.org` — check
your network.

## 7. eBird call (needs the key)

```bash
curl "http://localhost:8000/sightings/nearby?lat=47.66&lng=-122.31&source=ebird"
```

- **Key set** → a JSON array of recent sightings. Empty can just mean nothing was
  reported near those coordinates lately — try `source=all`.
- **No key** → expected to be empty; iNaturalist (check 6) still works. Get a
  free key: <https://ebird.org/api/keygen>.
- **Anything else** (a `502`, etc.) → see
  [eBird API → Error & failure behavior](ebird-api.md#error-failure-behavior).

## 8. Tests pass

```bash
cd backend
python -m pytest
```

Expect all green. The suite is offline — no database, no key, no network. If it
fails on a fresh clone, something is wrong with the install, not your change.

## 9. *(optional)* Docs site builds

```bash
pip install -r docs/requirements.txt
mkdocs build --strict
```

Expect `Documentation built in … seconds`. `--strict` fails on a broken internal
link.

## 10. *(optional)* Database

Only if you're doing database work.

```bash
psql "$DATABASE_URL" -c "select 1;"                 # -> one row, value 1
./backend/scripts/migrate.sh                        # -> "migrations up to date."
psql "$DATABASE_URL" -c "select filename from schema_migrations order by filename;"
```

The last command should list `0001_baseline.sql` (plus any feature migrations
you've run). Can't connect / no `psql` → [Deployment](deployment.md#1-database-supabase).

## All green?

Your environment is good. Pick up a [feature](features/overview.md), or see the
[branch & PR workflow](contributing.md#branch-pr-workflow).
