#!/usr/bin/env python3
"""
Export the milestone log of the analysis population as one CSV for SAP
Signavio Process Intelligence.

One row per event: case id, activity, timestamp, plus case attributes
(opening type, Feudal click, villagers, map) and the event's delay against
the build order. Events in the same second get millisecond offsets so that
Signavio keeps the logged order (e.g. House 1 before House 2).

Input:  output/<database name>/milestone_events.csv, sessions.csv,
        milestone_delays.csv (run extract_openings.py and compare_to_guides.py)
Output: output/<database name>/signavio_milestones.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from extract_openings import DEFAULT_DB, DEFAULT_OUT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="OCEL 2.0 SQLite file")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args()

    data_dir = args.out / args.db.stem
    sessions = pd.read_csv(data_dir / "sessions.csv")
    sessions = sessions[sessions["in_analysis"]]
    milestones = pd.read_csv(data_dir / "milestone_events.csv")
    milestones = milestones[milestones["session_id"].isin(sessions["session_id"])].copy()
    delays = pd.read_csv(data_dir / "milestone_delays.csv")[["session_id", "milestone", "guide_s", "delay_s"]]

    order_in_second = milestones.groupby(["session_id", "time"]).cumcount()
    milestones["timestamp"] = (pd.to_datetime(milestones["time"])
                               + pd.to_timedelta(order_in_second, unit="ms"))

    case_attributes = sessions[["session_id", "opening_type", "feudal_click_s",
                                "villagers_at_click_max", "initial_walls"]]
    export = (
        milestones.merge(case_attributes, on="session_id")
        .merge(delays, on=["session_id", "milestone"], how="left")
        .rename(columns={"session_id": "case_id", "milestone": "activity",
                         "villagers": "villagers_max", "initial_walls": "arena_map"})
    )
    export["timestamp"] = export["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    columns = ["case_id", "activity", "timestamp", "game_s", "villagers_max", "guide_s", "delay_s",
               "opening_type", "feudal_click_s", "villagers_at_click_max", "arena_map", "player_id"]
    path = data_dir / "signavio_milestones.csv"
    export[columns].to_csv(path, index=False)
    print(f"{export['case_id'].nunique()} cases, {len(export)} events written to {path}")


if __name__ == "__main__":
    main()
