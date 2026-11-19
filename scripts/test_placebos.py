from pathlib import Path

import pandas as pd

clean = Path(__file__).resolve().parents[1] / "data" / "clean"
weekly = pd.read_csv(clean / "weekly_indexed.csv", parse_dates=["week_start"])
real = pd.read_csv(clean / "event_results.csv")
events = pd.read_csv(clean / "events.csv", parse_dates=["first_press_date"])

keys = ["event_id", "series"]
cities = ["Lexington", "Louisville", "Cincinnati", "Nashville", "Knoxville"]
week = pd.Timedelta(weeks=1)
launches = events["first_press_date"].dt.to_period("W-SAT").dt.start_time
blocked = [(start, start + 4 * week) for start in launches]

if real.duplicated(keys).any() or len(real) != 12:
    raise SystemExit("Expected 12 unique campaign-source rows in event_results.csv.")

def score(wide, anchor):
    dates = [anchor + k * week for k in range(-9, 5)]
    block = wide.reindex(dates)
    if block.isna().any().any():
        return None

    baseline = block.iloc[:8].mean()
    if not baseline.gt(0).all():
        return None

    indexed = 100 * block / baseline
    gap = indexed["Lexington"] - indexed[cities[1:]].mean(axis=1)
    post = gap.iloc[9:]
    peak_date = post.idxmax()
    peak = float(post.loc[peak_date])
    sd = float(gap.iloc[:8].std(ddof=1))
    lex = float(indexed.loc[peak_date, "Lexington"])

    return {
        "peak_excess": peak,
        "peak_week": int((peak_date - anchor) // week),
        "lexington_at_peak": lex,
        "baseline_excess_sd": sd,
        "passes_both_screens": sd > 0 and peak > 2 * sd and lex > 100,
    }

detail = []
summary = []
for (event_id, source), g in weekly.groupby(keys):
    wide = (
        g.pivot(index="week_start", columns="geography", values="weekly_value")
        .reindex(columns=cities)
        .sort_index()
    )
    observed = real.loc[real["event_id"].eq(event_id) & real["series"].eq(source)]
    if len(observed) != 1:
        raise SystemExit(f"Missing or duplicate real result: {event_id} / {source}")
    observed = observed.iloc[0]
    anchor = pd.Timestamp(observed["first_press_date"]).to_period("W-SAT").start_time

    actual = score(wide, anchor)
    if (
        actual is None
        or abs(actual["peak_excess"] - observed["peak_excess"]) > 1e-8
        or actual["peak_week"] != observed["peak_week"]
    ):
        raise SystemExit(f"Real-event replication failed: {event_id} / {source}")

    candidates = []
    last_end = None
    for fake in wide.index:
        start, end = fake - 9 * week, fake + 4 * week
        if any(start <= b_end and end >= b_start for b_start, b_end in blocked):
            continue
        result = score(wide, fake)
        if result is None:
            continue

        # Date-only selection: earliest eligible block, then next disjoint block.
        disjoint = last_end is None or start > last_end
        if disjoint:
            last_end = end
        candidates.append({
            "event_id": event_id,
            "series": source,
            "placebo_week_start": fake,
            "window_start": start,
            "window_end_week_start": end,
            **result,
            "at_least_real_peak": result["peak_excess"] >= actual["peak_excess"] - 1e-8,
            "in_nonoverlapping_subset": disjoint,
        })

    detail.extend(candidates)
    subset = [row for row in candidates if row["in_nonoverlapping_subset"]]
    hits = sum(row["at_least_real_peak"] for row in candidates)
    subset_hits = sum(row["at_least_real_peak"] for row in subset)
    summary.append({
        "name": observed["name"],
        "event_id": event_id,
        "series": source,
        "real_peak_excess": actual["peak_excess"],
        "n_eligible": len(candidates),
        "n_at_least_real_peak": hits,
        "share_at_least_real_peak": hits / len(candidates) if candidates else None,
        "n_nonoverlapping": len(subset),
        "n_nonoverlapping_at_least_real_peak": subset_hits,
    })

summary = pd.DataFrame(summary)
if len(summary) != 12:
    raise SystemExit("Expected 12 placebo summaries.")
pd.DataFrame(detail).to_csv(clean / "placebo_windows.csv", index=False)
summary.to_csv(clean / "placebo_summary.csv", index=False)
print(summary.drop(columns="event_id").round(3).to_string(index=False, na_rep="-"))
print("\nSaved placebo_windows.csv and placebo_summary.csv in data/clean.")
