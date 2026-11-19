from pathlib import Path

import pandas as pd

root = Path(__file__).resolve().parents[1]
clean = root / "data" / "clean"

weekly = pd.read_csv(clean / "weekly_indexed.csv", parse_dates=["week_start"])
events = pd.read_csv(clean / "events.csv")
controls = ["Louisville", "Cincinnati", "Nashville", "Knoxville"]
cities = ["Lexington", *controls]
keys = ["event_id", "series", "event_week", "week_start"]

wide = weekly.pivot(index=keys, columns="geography", values="indexed_value")
if set(wide.columns) != set(cities):
    raise SystemExit(f"Unexpected city columns: {wide.columns.tolist()}")
if wide[cities].isna().any().any():
    raise SystemExit("At least one week is missing a city; do not average fewer controls.")

gaps = wide.reset_index()
gaps.columns.name = None
gaps["comparison_mean"] = gaps[controls].mean(axis=1)
gaps["excess"] = gaps["Lexington"] - gaps["comparison_mean"]

results = []
for (event_id, source), g in gaps.groupby(["event_id", "series"]):
    g = g.sort_values("event_week").set_index("event_week")
    baseline = g.loc[-9:-2, "excess"]
    launch = g.loc[0:4]

    if baseline.index.tolist() != list(range(-9, -1)):
        raise SystemExit(f"Incomplete baseline: {event_id} / {source}")
    if launch.index.tolist() != list(range(5)):
        raise SystemExit(f"Incomplete launch window: {event_id} / {source}")

    peak_week = int(launch["excess"].idxmax())
    peak = launch.loc[peak_week]
    peak_excess = float(peak["excess"])
    noise_sd = float(baseline.std(ddof=1))
    clears_screen = noise_sd > 0 and peak_excess > 2 * noise_sd

    half_life = None
    if noise_sd == 0:
        status = "not estimated: zero measured baseline variation"
    elif not clears_screen:
        status = "not estimated: peak did not clear noise screen"
    elif peak["Lexington"] <= 100:
        status = "not estimated: Lexington not above baseline at peak"
    else:
        after_peak = launch.loc[launch.index > peak_week, "excess"]
        crossings = after_peak[after_peak <= peak_excess / 2]
        if len(crossings):
            half_life = int(crossings.index[0]) - peak_week
            status = "observed: first weekly crossing"
        elif after_peak.empty:
            status = "not observed: peak at end of window"
        else:
            status = "not observed by week +4"

    results.append({
        "event_id": event_id,
        "series": source,
        "peak_week": peak_week,
        "peak_week_start": peak["week_start"],
        "lexington_at_peak": peak["Lexington"],
        "comparison_at_peak": peak["comparison_mean"],
        "peak_excess": peak_excess,
        "baseline_excess_sd": noise_sd,
        "peak_in_baseline_sd": peak_excess / noise_sd if noise_sd > 0 else None,
        "clears_noise_screen": clears_screen,
        "half_life_weeks": half_life,
        "half_life_status": status,
    })

results = pd.DataFrame(results).merge(
    events[["event_id", "name", "first_press_date"]],
    on="event_id",
    how="left",
    validate="many_to_one",
)
if len(results) != 12 or results["first_press_date"].isna().any():
    raise SystemExit("Expected 12 results: six campaigns by two sources.")

results["half_life_weeks"] = results["half_life_weeks"].astype("Int64")
results = results.sort_values(["first_press_date", "series"])
gaps.to_csv(clean / "weekly_excess.csv", index=False)
results.to_csv(clean / "event_results.csv", index=False)

show = [
    "name", "series", "peak_week", "lexington_at_peak",
    "peak_excess", "baseline_excess_sd",
    "half_life_weeks", "half_life_status",
]
print(results[show].round(2).to_string(index=False, na_rep="-"))
print("\nSaved weekly_excess.csv and event_results.csv in data/clean.")
