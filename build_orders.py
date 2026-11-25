#!/usr/bin/env python3
"""
Reference build orders, translated into the milestone names of
extract_openings.py.

Source: RTS Builds (https://github.com/CraftySalamander/rtsbuilds), generic
(not civilization-specific) build orders. Each step has the guide's game time
and villager count. Steps the guide places "before Feudal" (during the Feudal
research) carry the guide's Feudal arrival time as a deadline.

Steps the dataset cannot show are left out: hunting, boar luring, deer pushing
and food sources (all food is one generic "Gather Food").

Run to write output/build_orders.csv.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Step:
    milestone: str
    guide_s: int
    villagers: int
    during_feudal_research: bool = False


@dataclass(frozen=True)
class BuildOrder:
    opening_type: str
    name: str
    author: str
    source: str
    steps: tuple[Step, ...]


BUILD_ORDERS = (
    BuildOrder(
        opening_type="Scouts",
        name="Scouts rush - 18 pop",
        author="Morley Games",
        source="https://youtu.be/PcKxbQKlZH8",
        steps=(
            Step("Build House 1", 0, 3),
            Step("Build House 2", 0, 3),
            Step("Build Lumber Camp", 150, 9),
            Step("Build House 3", 225, 12),
            Step("Build Mill", 250, 13),
            Step("Research Loom", 375, 17),
            Step("Click Feudal Age", 375, 17),
            Step("Build Barracks", 505, 17, during_feudal_research=True),
            Step("Build House 4", 505, 17, during_feudal_research=True),
        ),
    ),
    BuildOrder(
        opening_type="Archers",
        name="Archers 19 pop",
        author="Morley Games",
        source="https://youtu.be/p4U2Eznqn7A",
        steps=(
            Step("Build House 1", 0, 3),
            Step("Build House 2", 0, 3),
            Step("Build Lumber Camp", 175, 10),
            Step("Build House 3", 200, 11),
            Step("Build Mill", 275, 14),
            Step("Research Loom", 400, 18),
            Step("Click Feudal Age", 400, 18),
            Step("Build House 4", 530, 18, during_feudal_research=True),
            Step("Build Barracks", 530, 18, during_feudal_research=True),
            Step("Build Mining Camp", 530, 18, during_feudal_research=True),
        ),
    ),
    BuildOrder(
        opening_type="Drush",
        name="19 Pop Feudal Drush",
        author="Hera",
        source="https://youtu.be/R9IFzyYMAjA",
        steps=(
            Step("Build House 1", 0, 3),
            Step("Build House 2", 0, 3),
            Step("Build Lumber Camp", 150, 9),
            Step("Build House 3", 200, 11),
            Step("Build Barracks", 350, 17),
            Step("Build House 4", 350, 17),
            Step("Research Loom", 400, 18),
            Step("Click Feudal Age", 400, 18),
            Step("Train Militia", 530, 18, during_feudal_research=True),
            Step("Build Mill", 530, 18, during_feudal_research=True),
        ),
    ),
    BuildOrder(
        opening_type="Fast Castle",
        name="Arena Fast Castle Boom",
        author="Hera",
        source="https://youtu.be/JsTNM7j6fs4",
        steps=(
            Step("Build House 1", 0, 3),
            Step("Build House 2", 0, 3),
            Step("Build Lumber Camp", 150, 9),
            Step("Build House 3", 200, 11),
            Step("Build Mill", 200, 11),
            Step("Build Farm", 350, 17),
            Step("Build House 4", 450, 21),
            Step("Build Mining Camp", 500, 23),
            Step("Click Feudal Age", 500, 23),
        ),
    ),
)


def build_orders_frame() -> pd.DataFrame:
    rows = [
        {
            "opening_type": bo.opening_type,
            "build_order": bo.name,
            "author": bo.author,
            "source": bo.source,
            "step": number,
            "milestone": step.milestone,
            "guide_s": step.guide_s,
            "guide_villagers": step.villagers,
            "during_feudal_research": step.during_feudal_research,
        }
        for bo in BUILD_ORDERS
        for number, step in enumerate(bo.steps, start=1)
    ]
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = BASE_DIR / "output" / "build_orders.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    build_orders_frame().to_csv(out, index=False)
    print(f"{len(BUILD_ORDERS)} build orders written to {out}")
