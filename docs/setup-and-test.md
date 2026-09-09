# Set up & test your changes

The short path from a fresh clone to an open pull request. Each step links to a
deeper page if you need it.

## 1. Get the code

```bash
git clone <your-fork-or-origin-url> OnlyBirds
cd OnlyBirds
```

## 2. Start the backend

```bash
cd backend
python -m venv .venv
# Windows:       .venv\Scripts\Activate.ps1
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # then open .env and set EBIRD_API_KEY
python -m uvicorn main:app --reload
```

Open <http://localhost:8000/docs>. If the API page loads, you're set. No eBird
key yet? The server still starts; eBird calls just come back empty.

*Details, versions, troubleshooting →* [Environment Setup](index.md)

## 3. Make your change on a branch

Never work directly on `main` or `dev/current`.

```bash
git checkout dev/current && git pull
git checkout -b working/<you>/<feature>       # e.g. working/sam/pinned-birds
```

Building a whole feature? Start from its page and claim it in the table first.

*The full workflow (releases, protection rules) →*
[Contributing → Branch & PR workflow](contributing.md#branch--pr-workflow) ·
*feature specs →* [Features](features/overview.md)

## 4. Run the tests

Backend tests run **offline** — no database, no API key, no network.

```bash
cd backend
python -m pytest                       # everything
python -m pytest tests/test_health.py  # one file
python -m pytest -k life_list          # tests whose name matches
```

Add a test for anything you changed. Copy the shape of an existing
`backend/tests/test_*.py` — they use canned payloads, never live calls.

Changed the database schema? Add a `backend/migrations/NNNN_name.sql` file and
run it against **your own** database — never the shared one.

*Migration how-to and SQL conventions →*
[Database & migrations](features/database.md)

## 5. Check it by hand

Run the server (step 2) and click through `/docs`, or use `curl`.

*Endpoint list and example calls →* [Backend API](backend.md)

## 6. Open a pull request

```bash
git push -u origin working/<you>/<feature>
```

Open the PR **into `dev/current`**. The checklist fills in automatically. CI runs
the tests and a docs build on every push — get it green before asking for
review.

## Common snags

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | run commands from inside `backend/` |
| eBird calls return 403 / empty | `EBIRD_API_KEY` missing in `backend/.env`; restart the server |
| `uvicorn` / `pytest` "not found" | use `python -m uvicorn …` / `python -m pytest` |
| port 8000 in use | `python -m uvicorn main:app --reload --port 8001` |

*More →* [Environment Setup → Troubleshooting](index.md#troubleshooting)
