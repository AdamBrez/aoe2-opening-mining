#!/usr/bin/env python3
"""
Extract each player's opening from the Age of Empires II OCEL 2.0 SQLite log.

One case = one player in one match (the `Session` object); every event in the
log is linked to exactly one session. Timestamps are game time.

Reliability of the log (checked on the 10-match sample):
  * Player commands (building starts, research and unit orders, gather orders)
    are recorded from the game files and are reliable.
  * Game events (villager spawned, research started/finished) are reconstructed
    by the dataset authors and are not: Feudal-only buildings often appear
    before the reconstructed Feudal arrival, and villager ids are shared
    between the two players of a match.
  Therefore the opening ends at the estimated Feudal arrival
  (Feudal click + 130 s research time), which includes what the player does
  while the research runs, and opening milestones use player commands only.

Output (in output/<database name>/):
  opening_events.csv    all events of the openings, with `source` player/game
  milestone_events.csv  abstracted log: first time each milestone happens
                        (player commands only), ready for discovery and
                        conformance checking
  sessions.csv          one row per session: KPIs, opening type, data flags

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
FEUDAL_RESEARCH_S = 130.0
MAP_SETUP_PREFIXES = ("Create Initial Stone Wall", "Create Initial Gate")

# Milestone name -> player command it is derived from (first occurrence).
MILESTONES = {
    "Build Lumber Camp": "Start Build Lumber Camp",
    "Build Mill": "Start Build Mill",
    "Build Mining Camp": "Start Build Mining Camp",
    "Build Farm": "Start Build Farm",
    "Build Barracks": "Start Build Barracks",
    "Build Dock": "Start Build Dock",
    "Research Loom": "Command Research Loom",
    "Train Militia": "Command Queue Militia",
    "Click Feudal Age": FEUDAL_CLICK,
}
NUMBERED_HOUSES = 4  # "Build House 1" ... "Build House 4"

# Actions that are only possible once Feudal Age is reached.
FEUDAL_ONLY = [
    "Start Build Stable", "Start Build Archery Range", "Start Build Blacksmith",
    "Start Build Market", "Start Build Watch Tower",
    "Command Research DoubleBit Axe", "Command Research Horse Collar",
    "Command Research Gold Mining", "Command Research Wheelbarrow",
    "Command Research Fletching", "Command Research ManatArms",
    "Command Queue Scout Cavalry", "Command Queue Archer", "Command Queue Skirmisher",
    "Command Queue Spearman", "Command Queue Camel Scout", "Command Queue Steppe Lancer",
]

TRACKED_BUILDINGS = [
    "House", "Lumber Camp", "Mill", "Mining Camp", "Farm", "Dock",
    "Barracks", "Archery Range", "Stable",
]
NON_MILITARY_UNITS = {"Villager", "Fishing Ship", "Trade Cart"}

# Opening classification windows, in seconds after the estimated Feudal arrival.
FAST_CASTLE_WINDOW_S = 180
MAN_AT_ARMS_WINDOW_S = 60
FIRST_BUILDING_WINDOW_S = 300


def load_events(con: sqlite3.Connection) -> pd.DataFrame:
    """One row per event with its session, match, game time and source."""
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
               MAX(o.ocel_type = 'Player') AS by_player
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
    return events.drop(columns=["ocel_time", "by_player", "seq"])


def feudal_arrival(events: pd.DataFrame) -> pd.Series:
    """Estimated Feudal arrival per session: first Feudal click + research time."""
    clicks = events.loc[events["activity"].eq(FEUDAL_CLICK)].groupby("session_id")["game_s"].min()
    return clicks + FEUDAL_RESEARCH_S


def cut_openings(events: pd.DataFrame, arrival: pd.Series) -> pd.DataFrame:
    """Each session's events up to its estimated Feudal arrival, without map setup."""
    limit = events["session_id"].map(arrival)
    map_setup = events["activity"].str.startswith(MAP_SETUP_PREFIXES)
    return events[(events["game_s"] <= limit) & ~map_setup].copy()


def milestone_log(openings: pd.DataFrame) -> pd.DataFrame:
    """First occurrence of each milestone per session, from player commands only."""
    player = openings[openings["source"].eq("player")]
    to_milestone = {command: name for name, command in MILESTONES.items()}
    firsts = player[player["activity"].isin(to_milestone)].copy()
    firsts["milestone"] = firsts["activity"].map(to_milestone)
    firsts = firsts.drop_duplicates(["session_id", "milestone"])

    houses = player[player["activity"].eq("Start Build House")].copy()
    houses["number"] = houses.groupby("session_id").cumcount() + 1
    houses = houses[houses["number"] <= NUMBERED_HOUSES]
    houses["milestone"] = "Build House " + houses["number"].astype(str)

    log = pd.concat([firsts, houses.drop(columns="number")], ignore_index=True)
    columns = ["session_id", "match_id", "player_id", "milestone", "time", "game_s", "villagers"]
    return log.sort_values(["session_id", "game_s"])[columns]


def town_center_idle(session: pd.DataFrame, until_s: float) -> float:
    """Seconds before `until_s` in which the town center trained nothing.

    Based on the reconstructed villager production, which ignores being housed
    or short of resources, so this is a lower bound of the real idle time.
    """
    starts = session.loc[session["activity"].eq("Start Queue Villager"), "game_s"].sort_values()
    ends = session.loc[session["activity"].eq("Complete Queue Villager"), "game_s"].sort_values()
    intervals = list(zip(starts, ends))
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


def classify_opening(row: dict) -> str:
    """Rule-based opening type from the timing of key commands around Feudal Age."""
    arrival = row["feudal_arrival_est_s"]
    if arrival is None:
        return "No Feudal click"

    def within(time: float | None, start: float, end: float) -> bool:
        return time is not None and start <= time <= end

    drush = within(row["first_militia_s"], 0, arrival)
    if within(row["castle_click_s"], 0, arrival + FAST_CASTLE_WINDOW_S):
        return "Drush-FC" if drush else "Fast Castle"
    if within(row["man_at_arms_s"], 0, arrival + MAN_AT_ARMS_WINDOW_S):
        return "Men-at-Arms"
    if drush:
        return "Drush"
    window_end = arrival + FIRST_BUILDING_WINDOW_S
    stable = row["first_stable_s"] if within(row["first_stable_s"], 0, window_end) else None
    archery = row["first_archery_range_s"] if within(row["first_archery_range_s"], 0, window_end) else None
    if stable is not None or archery is not None:
        return "Scouts" if archery is None or (stable is not None and stable < archery) else "Archers"
    return "Other"


def summarize_sessions(events: pd.DataFrame, arrival: pd.Series) -> pd.DataFrame:
    rows = []
    for session_id, s in events.groupby("session_id", sort=False):
        click = first_time(s, FEUDAL_CLICK)
        arrival_est = arrival.get(session_id)
        arrival_est = None if pd.isna(arrival_est) else arrival_est
        queued_units = s[s["activity"].str.startswith("Command Queue ")].copy()
        queued_units["unit"] = queued_units["activity"].str.removeprefix("Command Queue ")
        military = queued_units[~queued_units["unit"].isin(NON_MILITARY_UNITS)]
        initial_scout = s.loc[
            s["activity"].isin(["Create Initial Scout Cavalry", "Create Initial Eagle Scout",
                                "Create Initial Camel Scout"]),
            "activity",
        ]
        feudal_only = s.loc[s["activity"].isin(FEUDAL_ONLY), "game_s"]
        first_feudal_action = feudal_only.min() if len(feudal_only) else None

        row = {
            "session_id": session_id,
            "match_id": s["match_id"].iloc[0],
            "player_id": s["player_id"].iloc[0],
            "starting_villagers": int(s["activity"].eq("Create Initial Villager").sum()),
            "initial_scout": initial_scout.iloc[0].removeprefix("Create Initial ") if len(initial_scout) else None,
            "initial_walls": bool(s["activity"].eq("Create Initial Stone Wall").any()),
            "feudal_click_s": click,
            "feudal_arrival_est_s": arrival_est,
            "first_feudal_action_s": first_feudal_action,
            "castle_click_s": first_time(s, "Command Research Castle Age"),
            "villagers_at_click_max": int(s.loc[s["game_s"] <= click, "villagers"].max()) if click is not None else None,
            "tc_idle_before_click_min_s": town_center_idle(s, click) if click is not None else None,
            "loom_s": first_time(s, "Command Research Loom"),
            "first_militia_s": first_time(s, "Command Queue Militia"),
            "man_at_arms_s": first_time(s, "Command Research ManatArms"),
            "first_military_unit": military["unit"].iloc[0] if len(military) else None,
            "first_military_unit_s": military["game_s"].iloc[0] if len(military) else None,
        }
        for building in TRACKED_BUILDINGS:
            key = "first_" + building.lower().replace(" ", "_") + "_s"
            row[key] = first_time(s, f"Start Build {building}")

        row["opening_type"] = classify_opening(row)
        row["water_map"] = row["first_dock_s"] is not None and (click is None or row["first_dock_s"] < click)
        row["flag_missing_feudal_click"] = click is None and first_feudal_action is not None
        row["flag_feudal_action_too_early"] = (
            click is not None and first_feudal_action is not None and first_feudal_action < click
        )
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
    arrival = feudal_arrival(events)
    openings = cut_openings(events, arrival)
    milestones = milestone_log(openings)
    sessions = summarize_sessions(events, arrival)

    event_columns = ["session_id", "match_id", "player_id", "ocel_id", "activity", "time",
                     "game_s", "source", "villagers"]
    openings[event_columns].to_csv(out_dir / "opening_events.csv", index=False)
    milestones.to_csv(out_dir / "milestone_events.csv", index=False)
    sessions.round(1).to_csv(out_dir / "sessions.csv", index=False)

    print(f"{args.db.name}: {events['match_id'].nunique()} matches, {len(sessions)} sessions, "
          f"{len(events)} events")
    print(f"  sessions with a Feudal click: {sessions['feudal_click_s'].notna().sum()}; "
          f"opening events: {len(openings)}; milestone events: {len(milestones)}")
    print("  opening types: " + ", ".join(f"{k} {v}" for k, v in sessions["opening_type"].value_counts().items()))
    flagged = sessions["flag_missing_feudal_click"] | sessions["flag_feudal_action_too_early"]
    print(f"  sessions with data flags: {flagged.sum()}")
    print(f"  output: {out_dir}")


if __name__ == "__main__":
    main()
