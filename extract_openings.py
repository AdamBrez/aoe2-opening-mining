#!/usr/bin/env python3
"""
Extract each player's opening from the Age of Empires II OCEL 2.0 SQLite log.

One case = one player in one match (the `Session` object). Every event in the
log is linked to exactly one session. The opening is every event of a session
up to and including "Start Research Feudal Age", i.e. the moment the town
center actually begins the research. This can be minutes after the player's
click when villagers are still queued ahead of it.
Timestamps are game time: villagers take exactly 25 s and Feudal Age research
exactly 130 s in the log. Map setup events (pre-built walls and gates) are
left out of the opening log.

Output (in output/<database name>/):
  opening_events.csv  flat event log of the openings, ready for pm4py
  sessions.csv        one row per session with opening KPIs

Run with:
  .venv/bin/python extract_openings.py                      # 10-match sample
  .venv/bin/python extract_openings.py --db data/age_of_empires_ocel2.sqlite
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "data" / "age_of_empires_ocel2_10_match_filter.sqlite"
DEFAULT_OUT = BASE_DIR / "output"

FEUDAL_CLICK = "Command Research Feudal Age"
FEUDAL_START = "Start Research Feudal Age"
MAP_SETUP_PREFIXES = ("Create Initial Stone Wall", "Create Initial Gate")

# First "Start Build <X>" time per building is reported in sessions.csv.
TRACKED_BUILDINGS = [
    "House", "Lumber Camp", "Mill", "Mining Camp", "Farm", "Dock",
    "Barracks", "Archery Range", "Stable",
]
NON_MILITARY_UNITS = {"Villager", "Fishing Ship", "Trade Cart"}


def load_events(con: sqlite3.Connection) -> pd.DataFrame:
    """One row per event with its session, match, time and a few object links."""
    type_tables = pd.read_sql("SELECT ocel_type_map FROM event_map_type", con)
    times = pd.concat(
        [pd.read_sql(f'SELECT ocel_id, ocel_time FROM "event_{t}"', con)
         for t in type_tables["ocel_type_map"]],
        ignore_index=True,
    )
    links = pd.read_sql(
        """
        SELECT eo.ocel_event_id AS ocel_id,
               MAX(CASE WHEN o.ocel_type = 'Session' THEN o.ocel_id END) AS session_id,
               MAX(CASE WHEN o.ocel_type = 'Match' THEN o.ocel_id END) AS match_id,
               MAX(o.ocel_type = 'Player') AS by_player,
               MAX(o.ocel_type = 'Town Center') AS at_town_center,
               SUM(o.ocel_type = 'Villager') AS n_villagers,
               MAX(CASE WHEN o.ocel_type = 'Villager' THEN o.ocel_id END) AS villager_id
        FROM event_object eo
        JOIN object o ON o.ocel_id = eo.ocel_object_id
        GROUP BY eo.ocel_event_id
        """,
        con,
    )
    events = (
        pd.read_sql("SELECT ocel_id, ocel_type AS activity FROM event", con)
        .merge(times, on="ocel_id")
        .merge(links, on="ocel_id")
    )
    events["time"] = pd.to_datetime(events["ocel_time"])
    # Event ids look like e_M271214755_42; the number keeps same-second events in log order.
    events["seq"] = events["ocel_id"].str.rsplit("_", n=1).str[-1].astype(int)

    match_start = events.groupby("match_id")["time"].transform("min")
    events["game_s"] = (events["time"] - match_start).dt.total_seconds()
    events["source"] = events["by_player"].map({1: "player", 0: "game"})

    players = pd.read_sql(
        """
        SELECT oo.ocel_source_id AS player_id, oo.ocel_target_id AS session_id
        FROM object_object oo
        JOIN object p ON p.ocel_id = oo.ocel_source_id AND p.ocel_type = 'Player'
        JOIN object s ON s.ocel_id = oo.ocel_target_id AND s.ocel_type = 'Session'
        """,
        con,
    ).drop_duplicates("session_id")
    events = events.merge(players, on="session_id", how="left")

    events = events.sort_values(["session_id", "game_s", "seq"]).reset_index(drop=True)
    starting = events["activity"].eq("Create Initial Villager")
    produced = events["activity"].eq("Complete Queue Villager")
    events["villagers"] = (starting | produced).astype(int).groupby(events["session_id"]).cumsum()
    return events.drop(columns=["ocel_time", "by_player"])


def cut_openings(events: pd.DataFrame) -> pd.DataFrame:
    """Keep each session's events up to and including the start of Feudal Age research."""
    position = events.groupby("session_id").cumcount()
    start_position = (
        position[events["activity"].eq(FEUDAL_START)]
        .groupby(events["session_id"]).min()
    )
    limit = events["session_id"].map(start_position)
    map_setup = events["activity"].str.startswith(MAP_SETUP_PREFIXES)
    return events[(position <= limit) & ~map_setup].copy()


def town_center_idle(session: pd.DataFrame, until_s: float) -> float:
    """Seconds before `until_s` in which the town center trained nothing.

    Busy = villager production (Start -> Complete Queue Villager, paired by
    villager) plus Loom research. Assumes one town center in the Dark Age.
    """
    starts = session[session["activity"].eq("Start Queue Villager")]
    ends = session[session["activity"].eq("Complete Queue Villager")]
    intervals = starts.merge(ends, on="villager_id", suffixes=("_s", "_e"))[["game_s_s", "game_s_e"]]
    intervals = list(intervals.itertuples(index=False, name=None))
    loom_start = session.loc[session["activity"].eq("Start Research Loom"), "game_s"]
    loom_end = session.loc[session["activity"].eq("Complete Research Loom"), "game_s"]
    if len(loom_start) and len(loom_end):
        intervals.append((loom_start.iloc[0], loom_end.iloc[0]))

    busy, covered_until = 0.0, 0.0
    for start, end in sorted(intervals):
        start, end = max(start, covered_until), min(end, until_s)
        if end > start:
            busy += end - start
            covered_until = end
    return until_s - busy


def first_time(session: pd.DataFrame, activity: str) -> float | None:
    times = session.loc[session["activity"].eq(activity), "game_s"]
    return times.iloc[0] if len(times) else None


def summarize_sessions(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for session_id, s in events.groupby("session_id", sort=False):
        click = first_time(s, FEUDAL_CLICK)
        start = first_time(s, FEUDAL_START)
        queued_units = s[s["activity"].str.startswith("Command Queue ")].copy()
        queued_units["unit"] = queued_units["activity"].str.removeprefix("Command Queue ")
        military = queued_units[~queued_units["unit"].isin(NON_MILITARY_UNITS)]
        initial_scout = s.loc[
            s["activity"].isin(["Create Initial Scout Cavalry", "Create Initial Eagle Scout",
                                "Create Initial Camel Scout"]),
            "activity",
        ]

        row = {
            "session_id": session_id,
            "match_id": s["match_id"].iloc[0],
            "player_id": s["player_id"].iloc[0],
            "starting_villagers": int(s["activity"].eq("Create Initial Villager").sum()),
            "initial_scout": initial_scout.iloc[0].removeprefix("Create Initial ") if len(initial_scout) else None,
            "initial_walls": bool(s["activity"].eq("Create Initial Stone Wall").any()),
            "feudal_click_s": click,
            "feudal_start_s": start,
            "feudal_queue_wait_s": start - click if start is not None and click is not None else None,
            "feudal_reached_s": first_time(s, "Complete Research Feudal Age"),
            "castle_click_s": first_time(s, "Command Research Castle Age"),
            "villagers_at_click": int(s.loc[s["game_s"] <= click, "villagers"].max()) if click is not None else None,
            "villagers_at_feudal_start": int(s.loc[s["game_s"] <= start, "villagers"].max()) if start is not None else None,
            "tc_idle_before_feudal_s": town_center_idle(s, start) if start is not None else None,
            "loom_s": first_time(s, "Command Research Loom"),
            "first_military_unit": military["unit"].iloc[0] if len(military) else None,
            "first_military_unit_s": military["game_s"].iloc[0] if len(military) else None,
        }
        for building in TRACKED_BUILDINGS:
            key = "first_" + building.lower().replace(" ", "_") + "_s"
            row[key] = first_time(s, f"Start Build {building}")
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="OCEL 2.0 SQLite file")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args()

    out_dir = args.out / args.db.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(args.db) as con:
        events = load_events(con)
    openings = cut_openings(events)
    sessions = summarize_sessions(events)

    event_columns = ["session_id", "match_id", "player_id", "ocel_id", "activity", "time",
                     "game_s", "source", "villagers", "at_town_center", "n_villagers"]
    openings[event_columns].to_csv(out_dir / "opening_events.csv", index=False)
    sessions.round(1).to_csv(out_dir / "sessions.csv", index=False)

    with_start = sessions["feudal_start_s"].notna()
    print(f"{args.db.name}: {events['match_id'].nunique()} matches, {len(sessions)} sessions, "
          f"{len(events)} events")
    print(f"  sessions that reach Feudal research: {with_start.sum()}; opening events: {len(openings)}")
    print(f"  output: {out_dir}")


if __name__ == "__main__":
    main()
