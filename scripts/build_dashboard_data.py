from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"

weekly = pd.read_csv(CLEAN / "weekly_excess.csv")
results = pd.read_csv(CLEAN / "event_results.csv")

keys = ["event_id", "series"]

assert not weekly.duplicated(keys + ["event_week"]).any(), (
    "Duplicate campaign/source/week rows found."
)
assert not results.duplicated(keys).any(), (
    "Duplicate campaign/source results found."
)

summary_columns = keys + [
    "name",
    "first_press_date",
    "peak_week",
    "peak_week_start",
    "peak_excess",
    "half_life_weeks",
    "half_life_status",
]

dashboard = weekly.merge(
    results[summary_columns],
    on=keys,
    how="left",
    validate="many_to_one",
    indicator=True,
)

assert dashboard["_merge"].eq("both").all(), (
    "Some weekly rows have no matching event result."
)
dashboard = dashboard.drop(columns="_merge")

source_labels = {
    "google_trends_city_topic": "Google Trends",
    "wikipedia_article_pageviews": "Wikipedia",
}

dashboard["source_label"] = dashboard["series"].map(source_labels)
assert dashboard["source_label"].notna().all(), "Unknown source found."

dashboard["event_marker"] = (
    dashboard["event_week"].eq(0).astype(int)
)

dashboard["event_week_start"] = (
    pd.to_datetime(dashboard["week_start"])
    - pd.to_timedelta(dashboard["event_week"] * 7, unit="D")
).dt.strftime("%Y-%m-%d")

dashboard["half_life_display"] = dashboard.apply(
    lambda row: (
        "Not estimable"
        if pd.isna(row["half_life_weeks"])
        else f'{row["half_life_weeks"]:g} weeks'
    ),
    axis=1,
)

dashboard = dashboard.sort_values(
    ["event_id", "series", "event_week"]
)

output = CLEAN / "dashboard_weekly.csv"
dashboard.to_csv(output, index=False)

print(f"Saved {len(dashboard):,} rows to {output.relative_to(ROOT)}")
print(
    dashboard[
        ["name", "source_label", "peak_excess",
         "peak_week", "half_life_display"]
    ]
    .drop_duplicates()
    .to_string(index=False)
)