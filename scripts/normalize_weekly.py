from pathlib import Path

import pandas as pd

root = Path(__file__).resolve().parents[1]
clean = root / "data" / "clean"

series = pd.read_csv(clean / "series.csv", parse_dates=["date"])
events = pd.read_csv(clean / "events.csv", parse_dates=["first_press_date"])

group = ["event_id", "series", "geography"]
weekly_key = group + ["week_start"]

if series.duplicated(group + ["date"]).any():
    raise SystemExit("Duplicate input dates within a campaign, source, and city.")
if series["value"].isna().any():
    raise SystemExit("Missing input values. Review series.csv before continuing.")

def sunday(dates):
    return dates.dt.to_period("W-SAT").dt.start_time

def is_true(column):
    return column.astype("string").str.lower().eq("true").fillna(False)

# Trends is already weekly.
trends = series.loc[series["series"].eq("google_trends_city_topic")].copy()
keep = is_true(trends["week_fully_covered"]) & ~is_true(trends["source_partial"])
trends_weekly = (
    trends.loc[keep, group + ["date", "value"]]
    .rename(columns={"date": "week_start", "value": "weekly_value"})
)

# Wikipedia: only sum weeks with all seven distinct dates.
wiki = series.loc[series["series"].eq("wikipedia_article_pageviews")].copy()
wiki["week_start"] = sunday(wiki["date"])
wiki_weeks = wiki.groupby(weekly_key, as_index=False).agg(
    days=("date", "nunique"),
    weekly_value=("value", "sum"),
)
wiki_weekly = wiki_weeks.loc[
    wiki_weeks["days"].eq(7), weekly_key + ["weekly_value"]
]

weekly = pd.concat([trends_weekly, wiki_weekly], ignore_index=True)
weekly = weekly.merge(
    events[["event_id", "first_press_date"]],
    on="event_id",
    how="left",
    validate="many_to_one",
)
if weekly["first_press_date"].isna().any():
    raise SystemExit("At least one campaign is missing its press date.")

weekly["event_week_start"] = sunday(weekly["first_press_date"])
weekly["event_week"] = (
    (weekly["week_start"] - weekly["event_week_start"]).dt.days // 7
)
if weekly.duplicated(weekly_key).any():
    raise SystemExit("Duplicate weekly observation key.")

baseline = (
    weekly.loc[weekly["event_week"].between(-9, -2)]
    .groupby(group, as_index=False)
    .agg(
        baseline_mean=("weekly_value", "mean"),
        baseline_weeks=("event_week", "nunique"),
    )
)
weekly = weekly.merge(baseline, on=group, how="left", validate="many_to_one")
bad = ~weekly["baseline_weeks"].eq(8) | ~weekly["baseline_mean"].gt(0)
if bad.any():
    print(weekly.loc[bad, group + ["baseline_weeks", "baseline_mean"]]
          .drop_duplicates().to_string(index=False))
    raise SystemExit("Every baseline must have eight complete weeks and a positive mean.")

weekly["indexed_value"] = 100 * weekly["weekly_value"] / weekly["baseline_mean"]
check = (
    weekly.loc[weekly["event_week"].between(-9, -2)]
    .groupby(group)["indexed_value"].mean()
)
if not check.sub(100).abs().lt(1e-9).all():
    raise SystemExit("Baseline QA failed: at least one group does not average 100.")

output = clean / "weekly_indexed.csv"
weekly.sort_values(group + ["event_week"]).to_csv(output, index=False)

print(f"Saved {len(weekly):,} rows to {output}")
print(f"Checked {len(check)} baseline groups; all average 100.")
print(f"Excluded {int((~keep).sum())} Trends rows.")
print(f"Excluded {int(wiki_weeks['days'].ne(7).sum())} incomplete Wikipedia city-weeks.")
print(weekly.loc[
    weekly["event_id"].eq("horse_kicks")
    & weekly["series"].eq("google_trends_city_topic")
    & weekly["geography"].eq("Lexington")
    & weekly["event_week"].eq(0),
    ["week_start", "weekly_value", "baseline_mean", "indexed_value"],
].to_string(index=False))