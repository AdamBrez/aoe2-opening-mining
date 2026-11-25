#!/usr/bin/env python3
"""
Process discovery and variant analysis of the openings (RQ1), per opening type.

Uses the milestone log of the players in the analysis population
(sessions.csv `in_analysis`). For every opening type it writes:
  dfg_frequency.png    directly-follows graph, arc = number of players
  dfg_performance.png  directly-follows graph, arc = median time in between
  bpmn_split_miner.png Split Miner model
  variants.csv         most common milestone sequences
Plus overview charts and discovery_summary.csv for all types.

Input:  output/<database name>/milestone_events.csv and sessions.csv
        (run extract_openings.py first)
Output: output/<database name>/discovery/

Run with:
  .venv/bin/python discover.py                      # 10-match sample
  .venv/bin/python discover.py --db data/age_of_empires_ocel2.sqlite
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from build_orders import build_orders_frame  # noqa: E402
from extract_openings import DEFAULT_DB, DEFAULT_OUT  # noqa: E402

logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")
sys._pm4py_welcome_shown = True  # suppresses the banner PM4Py prints on import

import pm4py  # noqa: E402
from pm4py.algo.discovery.split_miner import algorithm as split_miner  # noqa: E402
from pm4py.vis import _setup_parameters  # noqa: E402
from pm4py.visualization.dfg import visualizer as dfg_visualizer  # noqa: E402

pm4py.util.constants.SHOW_PROGRESS_BAR = False

OPENING_TYPES = ["Scouts", "Archers", "Fast Castle", "Drush", "Men-at-Arms"]
# Arcs (and start/end activities) followed by fewer players than this share are
# left out of the DFG pictures to keep them readable.
MIN_ARC_SHARE = 0.05
SPLIT_MINER_PARAMETERS = {"epsilon": 0.1, "eta": 0.4}
TOP_VARIANTS = 10
VARIANT_COVERAGE = 0.8


def to_event_log(milestones: pd.DataFrame) -> pd.DataFrame:
    log = milestones.copy()
    log["time"] = pd.to_datetime(log["time"])
    return pm4py.format_dataframe(log, case_id="session_id", activity_key="milestone",
                                  timestamp_key="time")


def filtered_dfg(log: pd.DataFrame, min_count: int):
    dfg, start, end = pm4py.discover_dfg(log)
    dfg = {arc: count for arc, count in dfg.items() if count >= min_count}
    shown = {activity for arc in dfg for activity in arc}
    keep = lambda counts: {a: c for a, c in counts.items() if c >= min_count and a in shown}  # noqa: E731
    return dfg, keep(start), keep(end)


def save_frequency_dfg(dfg: dict, start: dict, end: dict, activity_counts: dict,
                       path: Path, title: str) -> None:
    """Like pm4py.save_vis_dfg, but nodes show the real number of players, not
    an estimate from the (filtered) arcs."""
    names = dfg_visualizer.Variants.FREQUENCY.value.Parameters
    parameters = _setup_parameters("png", graph_title=title)
    parameters[names.START_ACTIVITIES] = start
    parameters[names.END_ACTIVITIES] = end
    shown = {activity for arc in dfg for activity in arc}
    counts = {a: c for a, c in activity_counts.items() if a in shown}
    gviz = dfg_visualizer.apply(dfg, activities_count=counts,
                                variant=dfg_visualizer.Variants.FREQUENCY, parameters=parameters)
    dfg_visualizer.save(gviz, str(path))


def variant_table(log: pd.DataFrame) -> pd.DataFrame:
    traces = log.groupby("case:concept:name")["concept:name"].apply(" > ".join)
    counts = traces.value_counts()
    table = pd.DataFrame({"variant": counts.index, "players": counts.values})
    table["share"] = table["players"] / table["players"].sum()
    table["cumulative_share"] = table["share"].cumsum()
    return table


def discover_type(name: str, log: pd.DataFrame, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    players = log["case:concept:name"].nunique()
    min_count = max(1, round(MIN_ARC_SHARE * players))

    dfg, start, end = filtered_dfg(log, min_count)
    save_frequency_dfg(dfg, start, end, log["concept:name"].value_counts().to_dict(),
                       out_dir / "dfg_frequency.png",
                       f"{name} - directly-follows graph (players, arcs with at least {min_count})")

    performance, _, _ = pm4py.discover_performance_dfg(log)
    performance = {arc: stats for arc, stats in performance.items() if arc in dfg}
    pm4py.save_vis_performance_dfg(performance, start, end, str(out_dir / "dfg_performance.png"),
                                   aggregation_measure="median",
                                   graph_title=f"{name} - median time between milestones")

    bpmn = split_miner.apply(log, parameters=SPLIT_MINER_PARAMETERS,
                             variant=split_miner.Variants.CLASSIC)
    pm4py.save_vis_bpmn(bpmn, str(out_dir / "bpmn_split_miner.png"),
                        graph_title=f"{name} - Split Miner")
    net, im, fm = pm4py.convert_to_petri_net(bpmn)
    fitness = pm4py.fitness_token_based_replay(log, net, im, fm)["log_fitness"]
    precision = pm4py.precision_token_based_replay(log, net, im, fm)

    variants = variant_table(log)
    variants.head(TOP_VARIANTS).round(3).to_csv(out_dir / "variants.csv", index=False)
    return {
        "opening_type": name,
        "players": players,
        "variants": len(variants),
        "top_variant_share": variants["share"].iloc[0],
        f"variants_for_{int(VARIANT_COVERAGE * 100)}pct": int((variants["cumulative_share"] < VARIANT_COVERAGE).sum()) + 1,
        "split_miner_fitness": fitness,
        "split_miner_precision": precision,
        "bpmn_nodes": len(bpmn.get_nodes()),
    }


def plot_overview(sessions: pd.DataFrame, out_dir: Path) -> None:
    counts = sessions["opening_type"].value_counts()
    fig, ax = plt.subplots(figsize=(7, 3.5))
    counts.sort_values().plot.barh(ax=ax, color="#4c72b0")
    ax.set_xlabel("players")
    ax.set_ylabel("")
    ax.set_title(f"Opening types ({len(sessions)} players)")
    for i, value in enumerate(counts.sort_values()):
        ax.text(value, i, f" {value}", va="center")
    fig.tight_layout()
    fig.savefig(out_dir / "opening_types.png", dpi=150)
    plt.close(fig)

    guide_click = (
        build_orders_frame().query("milestone == 'Click Feudal Age'")
        .set_index("opening_type")["guide_s"]
    )
    types = [t for t in OPENING_TYPES if t in set(sessions["opening_type"])]
    data = [sessions.loc[sessions["opening_type"].eq(t), "feudal_click_s"] / 60 for t in types]
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.boxplot(data, tick_labels=types, showfliers=False)
    for i, opening in enumerate(types, start=1):
        if opening in guide_click:
            ax.plot(i, guide_click[opening] / 60, marker="*", color="#c44e52", markersize=12,
                    label="build order" if i == 1 else None)
    ax.set_ylabel("Feudal click (game minutes)")
    ax.set_title("When players click Feudal Age, by opening type")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(out_dir / "feudal_click_by_type.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="OCEL 2.0 SQLite file")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args()

    data_dir = args.out / args.db.stem
    out_dir = data_dir / "discovery"
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = pd.read_csv(data_dir / "sessions.csv")
    sessions = sessions[sessions["in_analysis"]]
    milestones = pd.read_csv(data_dir / "milestone_events.csv")
    milestones = milestones[milestones["session_id"].isin(sessions["session_id"])]

    plot_overview(sessions, out_dir)
    rows = []
    for opening in OPENING_TYPES:
        ids = sessions.loc[sessions["opening_type"].eq(opening), "session_id"]
        if ids.empty:
            continue
        log = to_event_log(milestones[milestones["session_id"].isin(ids)])
        folder = out_dir / opening.lower().replace(" ", "_").replace("-", "_")
        rows.append(discover_type(opening, log, folder))

    summary = pd.DataFrame(rows).round(3)
    summary.to_csv(out_dir / "discovery_summary.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(summary.to_string(index=False))
    print(f"\nwritten: {out_dir}")


if __name__ == "__main__":
    main()
