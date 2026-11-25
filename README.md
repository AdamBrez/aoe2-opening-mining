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

```sh
.venv/bin/python extract_openings.py                                    # 10-match sample
.venv/bin/python extract_openings.py --db data/age_of_empires_ocel2.sqlite  # all 1,000 matches
```

Output goes to `output/<database name>/`:

- `opening_events.csv`: event log of every player's opening (one case = one
  player in one match), up to the start of Feudal Age research
- `sessions.csv`: one row per player per match with opening KPIs (Feudal
  timing, villagers, town-center idle time, Feudal queue wait, first buildings)
