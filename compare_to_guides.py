#!/usr/bin/env python3
"""
Compare each player's opening milestones with the build order of their
opening type (first look at RQ2/RQ3).

For every guide step: delay = actual time - guide time. "Time lost in step" is
how much the delay grew since the previous guide step, which shows where in
the opening players fall behind. Guide steps a player never did are reported
as skipped.

Input:  output/<database name>/milestone_events.csv and sessions.csv
        (run extract_openings.py first)
Output: output/<database name>/milestone_delays.csv and delay_by_step.png

Run with:
  .venv/bin/python compare_to_guides.py                      # 10-match sample
  .venv/bin/python compare_to_guides.py --db data/age_of_empires_ocel2.sqlite
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from build_orders import BUILD_ORDERS, build_orders_frame  # noqa: E402
from extract_openings import DEFAULT_DB, DEFAULT_OUT  # noqa: E402


def milestone_delays(milestones: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    guides = build_orders_frame()
    comparable = sessions["in_analysis"] & sessions["opening_type"].isin(guides["opening_type"])
    players = sessions.loc[comparable, ["session_id", "opening_type"]]
    expected = players.merge(guides, on="opening_type")
    delays = expected.merge(
        milestones[["session_id", "milestone", "game_s"]],
        on=["session_id", "milestone"], how="left",
    ).rename(columns={"game_s": "actual_s"})
    delays["skipped"] = delays["actual_s"].isna()
    delays["delay_s"] = delays["actual_s"] - delays["guide_s"]

    in_dark_age = ~delays["during_feudal_research"] & ~delays["skipped"]
    ordered = delays[in_dark_age].sort_values(["session_id", "step"])
    previous = ordered.groupby("session_id")["delay_s"].shift(fill_value=0)
    delays.loc[ordered.index, "time_lost_in_step_s"] = ordered["delay_s"] - previous
    return delays.sort_values(["session_id", "step"])


def plot_delays(delays: pd.DataFrame, path: Path) -> None:
    """Median delay at each Dark Age guide step, one panel per opening type."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharey=True)
    for ax, build_order in zip(axes.flat, BUILD_ORDERS):
        rows = delays[delays["opening_type"].eq(build_order.opening_type)
                      & ~delays["during_feudal_research"]]
        if rows.empty:
            ax.set_visible(False)
            continue
        steps = rows.groupby("step").agg(milestone=("milestone", "first"),
                                         median=("delay_s", "median"),
                                         q25=("delay_s", lambda d: d.quantile(0.25)),
                                         q75=("delay_s", lambda d: d.quantile(0.75)))
        x = range(len(steps))
        ax.fill_between(x, steps["q25"], steps["q75"], color="#4c72b0", alpha=0.2,
                        label="middle 50% of players")
        ax.plot(x, steps["median"], marker="o", color="#4c72b0", label="median")
        ax.axhline(0, color="#c44e52", linestyle="--", linewidth=1, label="on build-order time")
        ax.set_xticks(list(x), steps["milestone"].str.replace("Build ", "").str.replace("Research ", ""),
                      rotation=40, ha="right")
        players = rows["session_id"].nunique()
        ax.set_title(f"{build_order.opening_type} ({players} players) vs. {build_order.name}", fontsize=10)
        ax.set_ylabel("delay vs. build order (s)")
    axes.flat[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Where players fall behind the build order (Dark Age steps)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="OCEL 2.0 SQLite file")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args()

    out_dir = args.out / args.db.stem
    milestones = pd.read_csv(out_dir / "milestone_events.csv")
    sessions = pd.read_csv(out_dir / "sessions.csv")
    delays = milestone_delays(milestones, sessions)
    delays.to_csv(out_dir / "milestone_delays.csv", index=False)
    plot_delays(delays, out_dir / "delay_by_step.png")

    summary = (
        delays.groupby(["opening_type", "step", "milestone"])
        .agg(players=("session_id", "nunique"),
             skipped=("skipped", "sum"),
             guide_s=("guide_s", "first"),
             median_actual_s=("actual_s", "median"),
             median_delay_s=("delay_s", "median"),
             median_time_lost_s=("time_lost_in_step_s", "median"))
        .reset_index(level="step", drop=True)
    )
    with pd.option_context("display.width", 200, "display.max_rows", 100, "display.max_columns", 20):
        print(summary.round(0))
    print(f"\nwritten: {out_dir / 'milestone_delays.csv'}")


if __name__ == "__main__":
    main()
