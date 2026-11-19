import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

parser = argparse.ArgumentParser()
parser.add_argument("--all", action="store_true", help="Collect all six events")
args = parser.parse_args()

root = Path(__file__).resolve().parent
trends = root / "data" / "raw" / "google_trends"
raw = root / "data" / "raw" / "wikipedia"
clean = root / "data" / "clean"
raw.mkdir(parents=True, exist_ok=True)
clean.mkdir(parents=True, exist_ok=True)

cities = {
    "Lexington": "Lexington, Kentucky",
    "Louisville": "Louisville, Kentucky",
    "Cincinnati": "Cincinnati",
    "Nashville": "Nashville, Tennessee",
    "Knoxville": "Knoxville, Tennessee",
}

events = {}
for path in sorted(trends.glob("*_metadata.json")):
    metadata = json.loads(path.read_text(encoding="utf-8"))
    events[metadata["event_id"]] = metadata

if not events:
    raise SystemExit(f"No Google Trends metadata files found in {trends}")

if args.all:
    selected = sorted(events.values(), key=lambda m: m["working_first_press_date"])
else:
    if "horse_kicks" not in events:
        raise SystemExit("Horse Kicks metadata was not found.")
    selected = [events["horse_kicks"]]

contact = os.environ.get("WIKI_CONTACT", "").strip()
if not contact:
    raise SystemExit("Set $env:WIKI_CONTACT in this PowerShell window first.")

base = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
session = requests.Session()
session.headers.update({
    "User-Agent": f"HalfLifeOfAStunt/1.0 ({contact})",
    "Accept": "application/json",
})

frames = []
for event in selected:
    event_id = event["event_id"]
    start, end = event["start"], event["end"]
    expected = pd.date_range(start, end, freq="D")

    for city, title in cities.items():
        article = quote(title.replace(" ", "_"), safe="")
        url = (
            f"{base}/en.wikipedia.org/all-access/user/{article}/daily/"
            f"{start.replace('-', '')}/{end.replace('-', '')}"
        )
        stem = f"{event_id}_{city.lower()}_{start}_{end}"
        path = raw / f"{stem}.json"
        receipt = raw / f"{stem}.receipt.json"

        if path.exists() and receipt.exists():
            print(f"Cached: {event_id} / {city}")
        else:
            print(f"Fetching: {event_id} / {city}")
            try:
                response = session.get(url, timeout=30)
                response.raise_for_status()
                payload = response.json()
                if not payload.get("items"):
                    raise ValueError("No daily observations returned.")
            except (requests.RequestException, ValueError) as exc:
                raise SystemExit(f"Stopped on {event_id} / {city}: {exc}")
            path.write_bytes(response.content)
            receipt.write_text(
                json.dumps({
                    "source_url": url,
                    "pulled_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                }, indent=2),
                encoding="utf-8",
            )
            time.sleep(1)

        info = json.loads(receipt.read_text(encoding="utf-8"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        data = pd.DataFrame(payload["items"])
        dates = pd.to_datetime(
            data["timestamp"].astype(str).str[:8], format="%Y%m%d"
        )
        if dates.duplicated().any():
            raise SystemExit(f"Duplicate daily dates in {path.name}")

        missing = expected.difference(dates)
        extra = pd.DatetimeIndex(dates).difference(expected)
        if len(missing) or len(extra):
            print(f"  QA: {len(missing)} missing, {len(extra)} out-of-window days.")

        frames.append(pd.DataFrame({
            "event_id": event_id,
            "date": dates.dt.strftime("%Y-%m-%d"),
            "series": "wikipedia_article_pageviews",
            "geography": city,
            "article": title,
            "value": data["views"],
            "source": "Wikimedia Analytics API",
            "source_url": info["source_url"],
            "pull_date": info["pulled_at_utc"][:10],
        }))

result = pd.concat(frames, ignore_index=True)
output = clean / (
    "wikipedia_daily_all_events.csv" if args.all else "wikipedia_daily_test.csv"
)
result.sort_values(["event_id", "geography", "date"]).to_csv(output, index=False)
print(f"\nSaved {len(result):,} daily rows to {output}")
print(result.groupby("event_id").size().to_string())