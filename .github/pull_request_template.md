<!-- Base branch: dev/current. Keep dev/current green — a PR merges only when
     every box below is ticked. See docs/contributing.md#branch--pr-workflow. -->

## What this changes


## Feature page
<!-- link the docs/features/*.md page this implements, or "n/a" -->


## How I tested it
<!-- describe the manual run: what you clicked / curled, and what you saw -->


## Checklist
- [ ] Branched off `dev/current` and this PR targets `dev/current`
- [ ] `cd backend && python -m pytest` passes locally
- [ ] New / changed endpoints have an offline test (canned payloads, no network)
- [ ] If the schema changed: a `backend/migrations/NNNN_*.sql` file is included
      and I ran `scripts/migrate.sh` against my own dev database
- [ ] I pulled the latest `dev/current` into this branch and there are no
      migration number clashes
- [ ] Docs updated (feature page / `backend.md` / env vars in `.env.example`)
- [ ] Manually exercised the feature end to end (notes above)
