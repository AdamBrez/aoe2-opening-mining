# Project Vision: Where Do Players Lose Time in the Age of Empires II Opening?

PA231 Process Mining, autumn 2026

## In one sentence

We treat the first minutes of an Age of Empires II game as a business process:
we find which openings players actually use, compare them with the published
build orders, and show where players lose time on the way to the second age
(Feudal Age), so players know which steps they must follow and which they can
safely skip.

## Who is it for

**Intermediate players who learn openings from build-order guides and want to
improve.**

> *Tomáš, 23, Brno. Plays ranked 1v1. Learned the "Scouts" opening from a
> YouTube guide, but reaches Feudal Age 1–2 minutes later than the guide says
> and doesn't know why.*
> **Goal:** know which mistakes in his opening cost the most time, and which
> steps of the guide he doesn't need to worry about.

Secondary audience: authors of build-order guides ("Which step of my guide do
people skip, and does it matter?").

## Background

- **Opening:** the first ~10 minutes of a game, where each player builds an
  economy (villagers, houses, resource camps) before advancing to Feudal Age.
- **Build order:** a step-by-step opening script published by experienced
  players, like a chess opening. It acts as our *reference process model*.
  Source: [RTS Builds](https://github.com/CraftySalamander/rtsbuilds)
  (machine-readable build orders, each with author and source video).
- **Dataset:** object-centric event log of 1,000 matches
  ([Zenodo](https://zenodo.org/records/13365584)). The dataset authors name
  build-order conformance checking as open future work (Liss et al., ICPM 2024
  Workshops).

## Main goal and research questions

**Main goal (A): Where do players lose time in the opening?**
**Supporting goal (B): Which openings do players use, and how closely do they
follow the build orders?**

| # | Question | Course topic | Technique |
|---|----------|--------------|-----------|
| RQ1 (B) | Which openings do players actually play? | Discovery, variant analysis | DFG and Split/Heuristic Miner on the opening log; group players into opening types (Scouts, Archers, Drush, Fast Castle) by clustering their action sequences |
| RQ2 (B) | How closely do players follow the build order of their opening? | Conformance checking, declarative PM | Build orders modelled as Petri nets; alignment fitness per player; Declare rules for the flexible parts (e.g. *mill before Feudal*, *Loom before Feudal*) |
| RQ3 (A) | Where is time lost? | Performance mining | Time from match start to the start of Feudal research; town-center idle time between villagers; Feudal queue wait (the research waits behind villagers still queued at the click); timing of key buildings against the build order; bottleneck analysis |
| RQ4 (A+B) | Which deviations and time losses matter most? | Process mining + data mining | Relate deviations and idle times to Feudal timing (regression / decision tree), within each opening type |

## Expected outcome

For each common opening, a short list of:

- **Must-follow steps:** deviations that clearly delay Feudal Age
  (e.g. "a late mill costs ~X seconds").
- **Flexible steps:** deviations that cost little or nothing.
- **Biggest time sinks:** e.g. "town-center idle time before minute 5 costs
  more than any single ordering mistake".

## Approach

1. **Data preparation:** one case = one player in one match (the `Session`
   object). Keep events up to the moment Feudal Age research starts. Remove
   noise (e.g. `Set Gather Point None`, pre-built map walls), filter out
   unusual game modes.
2. **Reference models:** translate 3–4 build orders into the dataset's
   activity names (`Start Build Mill`, `Command Research Feudal Age`, …).
3. **Analysis:** RQ1 → RQ4 as in the table above, using pm4py.

## Limitations

- No player rank, winner, civilization or map in the data. We measure opening
  **efficiency** (time to Feudal, villagers at Feudal), not winning.
- Some build-order steps are not visible (sheep, boar and berries all appear as
  `Gather Food`), so models cover buildings, research, villager count and the
  resource split only.
- Different openings aim for different Feudal times, so all comparisons are
  made within the same opening type.
- Events triggered by the game (villager spawned, building finished) are
  reconstructed by the dataset authors from player commands, not recorded.
  Villager idle time is therefore not measurable (every new villager gets a
  task at the moment it spawns), and being blocked by missing houses or
  resources is probably not modelled.
