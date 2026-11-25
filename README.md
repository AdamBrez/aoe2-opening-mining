# Where Do Players Lose Time in the Age of Empires II Opening?

PA231 Process Mining project. See [VISION.md](VISION.md) for the goal and
research questions.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Download the dataset ([Zenodo](https://zenodo.org/records/13365584), CC BY 4.0)
into `data/` (not tracked by git):

```sh
mkdir -p data && cd data
curl -L -o sample.zip "https://zenodo.org/records/13365584/files/age_of_empires_ocel2_10_match_filter.zip?download=1"
unzip -j sample.zip "*.sqlite" && rm sample.zip
curl -L -o age_of_empires_ocel2.sqlite "https://zenodo.org/records/13365584/files/age_of_empires_ocel2.sqlite?download=1"
```

The full SQLite file is 850 MB; the 10-match sample is enough for development.

## Usage

Add `--db data/age_of_empires_ocel2.sqlite` to the first and last command to
use all 1,000 matches instead of the 10-match sample.

```sh
.venv/bin/python extract_openings.py   # openings, milestones, opening types
.venv/bin/python build_orders.py       # reference build orders
.venv/bin/python compare_to_guides.py  # milestone delays against the guides
```

Output goes to `output/<database name>/` (`build_orders.csv` to `output/`):

- `opening_events.csv`: all events of every player's opening (one case = one
  player in one match), up to the estimated Feudal arrival
- `milestone_events.csv`: abstracted opening trace per player (first time of
  each milestone, player commands only)
- `sessions.csv`: one row per player per match with KPIs, opening type and
  data-quality flags
- `milestone_delays.csv`: each milestone's delay against the build order of
  the player's opening type
- `build_orders.csv`: the 4 reference build orders as milestones

## Data reliability

Only player commands are recorded in the game files; events triggered by the
game are reconstructed by the dataset authors and are unreliable (see the
limitations in [VISION.md](VISION.md)). The analysis therefore uses player
commands, and the Feudal arrival is estimated as click + 130 s.
