import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from pytrends.request import TrendReq

parser = argparse.ArgumentParser()
parser.add_argument("--all", action="store_true")
args = parser.parse_args()

root = Path(__file__).resolve().parent
raw = root / "data" / "raw" / "google_trends"
docs = root / "docs"
raw.mkdir(parents=True, exist_ok=True)
docs.mkdir(parents=True, exist_ok=True)

topics_file = docs / "trends_topics.json"

cities = {
    "Lexington": "Lexington Kentucky",
    "Louisville": "Louisville Kentucky",
    "Cincinnati": "Cincinnati Ohio",
    "Nashville": "Nashville Tennessee",
    "Knoxville": "Knoxville Tennessee",
}

events = [
    ("horse_kicks", "2022-10-18", "2022-04-18", "2023-04-18"),
    ("harmon_room", "2021-01-04", "2020-07-04", "2021-07-04"),
    ("plant_hotel", "2022-03-30", "2021-09-30", "2022-09-30"),
    ("hey_aliens", "2024-01-08", "2023-07-08", "2024-07-08"),
    ("neigh_i", "2025-09-17", "2025-03-17", "2026-03-17"),
    ("bluegrass_bathing", "2026-08-07", "2026-02-07", "2026-11-14"),
]

client = TrendReq(hl="en-US", tz=360, timeout=(10, 30))

def save_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

if topics_file.exists():
    topics = json.loads(topics_file.read_text(encoding="utf-8"))
else:
    topics = {}

for city, query in cities.items():
    if city in topics:
        continue

    print(f"\nLooking up {query}...")
    suggestions = client.suggestions(keyword=query)
    save_json(docs / f"topic_suggestions_{city.lower()}.json", suggestions)

    if not suggestions:
        raise SystemExit(
            f"No suggestions for {query}. Stop and check the browser manually."
        )

    for number, item in enumerate(suggestions, start=1):
        print(
            f"{number}: {item.get('title')} | "
            f"{item.get('type')} | {item.get('mid')}"
        )

    choice = input(
        f"Choose the number for the correct CITY topic for {query}, "
        "or q to stop: "
    ).strip()

    if choice.lower() == "q":
        raise SystemExit("Stopped. Completed topic choices were saved.")

    try:
        index = int(choice) - 1
        if not 0 <= index < len(suggestions):
            raise ValueError
        selected = suggestions[index]
        if not selected.get("mid"):
            raise ValueError
    except (ValueError, KeyError):
        raise SystemExit("Invalid selection. Rerun to continue.")

    topics[city] = selected
    save_json(topics_file, topics)
    time.sleep(20)

if len({topics[city]["mid"] for city in cities}) != len(cities):
    raise SystemExit("Duplicate topic IDs detected. Check docs/trends_topics.json.")

selected_events = events if args.all else events[:1]
topic_ids = [topics[city]["mid"] for city in cities]
rename_map = {topics[city]["mid"]: city for city in cities}

for position, (event, press_date, start, end) in enumerate(selected_events):
    existing = list(raw.glob(f"{event}_US_*_raw.csv"))
    if existing:
        print(f"Skipping {event}: an existing raw CSV is present.")
        continue

    if position:
        time.sleep(60)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = raw / f"{event}_US_{stamp}"

    print(f"\nRequesting {event}: {start} through {end}")

    try:
        client.build_payload(
            kw_list=topic_ids,
            cat=0,
            timeframe=f"{start} {end}",
            geo="US",
            gprop="",
        )
        frame = client.interest_over_time()

        if frame.empty:
            raise RuntimeError("Google returned no observations.")

        missing = set(topic_ids) - set(frame.columns)
        if missing:
            raise RuntimeError(f"Missing topic columns: {missing}")

        frame.to_csv(f"{prefix}_raw.csv", index_label="date")
        frame.rename(columns=rename_map).to_csv(
            f"{prefix}_named.csv", index_label="date"
        )

        metadata = {
            "event_id": event,
            "working_first_press_date": press_date,
            "start": start,
            "end": end,
            "geo": "US",
            "category": 0,
            "search_type": "web",
            "timezone_offset_minutes": 360,
            "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
            "method": "pytrends 4.9.2 interest_over_time",
            "topics": topics,
            "rows": len(frame),
            "columns": list(frame.columns),
        }
        save_json(Path(f"{prefix}_metadata.json"), metadata)

        print(f"Saved {event}: {len(frame)} observations.")
        print(frame.rename(columns=rename_map).head().to_string())

    except Exception as error:
        save_json(
            docs / f"trends_error_{event}_{stamp}.json",
            {
                "event_id": event,
                "error_type": type(error).__name__,
                "error": str(error),
                "time_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        raise SystemExit(
            f"Stopped on {event}: {type(error).__name__}: {error}\n"
            "Do not repeatedly retry if Google reports 429 or blocks access."
        )

print("\nCollection finished. Keep raw files unchanged.")