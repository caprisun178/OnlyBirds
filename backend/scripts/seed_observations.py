"""Seed sample observations for a user, via the running API.

Posts realistic-looking `Observation` rows to a running backend
(`POST /observations`) so you have data to look at without clicking through
the Add Observation wizard by hand - species come from the same canned
reference set the describe & guess flow uses (`app/data/birds.py`, 72
species across owls, raptors, waterfowl, songbirds, etc.), so names are
real and varied.

Usage (from backend/, with the API running - `uvicorn app.main:app --reload`):

    python scripts/seed_observations.py --user-id u1
    python scripts/seed_observations.py --user-id u1 --count 30 --seed 42
    python scripts/seed_observations.py --user-id u1 --base-url http://localhost:8000

Data lives in the in-memory store (see `app/dao/observation_repo.py`), so it
disappears on the next backend restart, and re-running this script just adds
more observations - there's no delete endpoint to clear existing ones.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # -> backend/, so `app` imports regardless of cwd

import httpx

from app.data.birds import all_birds

SAMPLE_LOCATIONS = [
    ("Discovery Park, Seattle, WA", 47.6618, -122.4219),
    ("Central Park, New York, NY", 40.7829, -73.9654),
    ("Golden Gate Park, San Francisco, CA", 37.7694, -122.4862),
    ("Everglades National Park, FL", 25.2866, -80.8987),
    ("Rocky Mountain National Park, CO", 40.3428, -105.6836),
    ("Cape May Point, NJ", 38.9351, -74.9613),
    ("Chicago Botanic Garden, IL", 42.1483, -87.7878),
    ("Mount Rainier National Park, WA", 46.8523, -121.7603),
]

NOTE_TEMPLATES = [
    "Perched quietly for a few minutes before flying off.",
    "Foraging on the ground near the trail.",
    "Heard calling before it came into view.",
    "Seen briefly at the feeder.",
    "Flew low overhead, easy to identify.",
    "",  # plenty of real observations have no notes
    "",
]

SEX_CHOICES = [None, "male", "female", "unknown"]
LIFE_STAGE_CHOICES = [None, "adult", "juvenile", "fledgling", "unknown"]


def build_payload(user_id: str, days_back: int) -> dict:
    bird = random.choice(all_birds())
    location_name, lat, lng = random.choice(SAMPLE_LOCATIONS)
    observed_at = datetime.now(timezone.utc) - timedelta(
        days=random.uniform(0, days_back), hours=random.uniform(0, 23)
    )
    return {
        "user_id": user_id,
        "species": {
            "common_name": bird["common_name"],
            "scientific_name": bird["scientific_name"],
        },
        "observed_at": observed_at.isoformat(),
        "location_name": location_name,
        "lat": lat,
        "lng": lng,
        "sex": random.choice(SEX_CHOICES),
        "life_stage": random.choice(LIFE_STAGE_CHOICES),
        "notes": random.choice(NOTE_TEMPLATES) or None,
        "source": "manual",
        "status": "logged",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user-id", required=True, help="user_id to attach the seeded observations to")
    parser.add_argument("--count", type=int, default=15, help="how many observations to create (default: 15)")
    parser.add_argument("--days-back", type=int, default=120, help="spread observed_at over this many past days (default: 120)")
    parser.add_argument("--base-url", default="http://localhost:8000", help="running backend's base URL (default: %(default)s)")
    parser.add_argument("--seed", type=int, default=None, help="random seed, for reproducible output")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    payloads = [build_payload(args.user_id, args.days_back) for _ in range(args.count)]

    try:
        client = httpx.Client(base_url=args.base_url, timeout=10.0)
    except httpx.InvalidURL as exc:
        print(f"Invalid --base-url: {exc}", file=sys.stderr)
        return 1

    created = 0
    with client:
        for payload in payloads:
            try:
                resp = client.post("/observations", json=payload)
            except httpx.ConnectError:
                print(
                    f"Could not reach {args.base_url} - is the backend running?\n"
                    f"  cd backend && uvicorn app.main:app --reload",
                    file=sys.stderr,
                )
                return 1

            if resp.status_code == 201:
                created += 1
                print(f"  + {payload['species']['common_name']:28s} {payload['observed_at'][:10]}  {payload['location_name']}")
            else:
                print(f"  ! {payload['species']['common_name']:28s} failed ({resp.status_code}): {resp.text}", file=sys.stderr)

        try:
            life_list = client.get(f"/users/{args.user_id}/life-list").json()
        except httpx.ConnectError:
            life_list = []

    print(f"\nSeeded {created}/{len(payloads)} observations for user '{args.user_id}'.")
    print(f"Life list now has {len(life_list)} species.")
    return 0 if created == len(payloads) else 1


if __name__ == "__main__":
    raise SystemExit(main())
