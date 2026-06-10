# World Cup 2026 Bracket Optimizer

A Pyomo / Monte-Carlo optimizer that produces the **expected-points-maximizing** entry for
the official [**FIFA World Cup 2026 Bracket Challenge**](https://play.fifa.com), using live
win probabilities from [**Polymarket**](https://polymarket.com).

It pulls current market odds, calibrates per-team strengths, simulates the whole tournament,
and solves for the bracket with the highest expected FIFA score under the official scoring
rules. The full design rationale lives in [`CLAUDE_CODE_PLAN.md`](CLAUDE_CODE_PLAN.md).

## Quickstart

```bash
conda create -n worldcup-bracket python=3.11 numpy requests -y
conda run -n worldcup-bracket pip install pyomo highspy pytest
conda activate worldcup-bracket

python solve.py --sims 60000          # LIVE: pulls current Polymarket odds, prints bracket
```

Then copy the printed picks into the FIFA app. To save a dated, fill-in-ready file:

```bash
python solve.py --sims 60000 > "submission_$(date +%Y%m%d).txt"
```

A worked, human-readable submission produced this way is checked in as
[`SUBMISSION.md`](SUBMISSION.md).

## Commands

| Command | What it does |
|---------|--------------|
| `python solve.py` | LIVE odds → full bracket + EV breakdown (the real submission) |
| `python solve.py --mock` | Offline, uses the embedded 2026-06-09 odds snapshot |
| `python solve.py --sims 60000` | More Monte-Carlo precision (default ~40k) |
| `python odds.py` / `--mock` | Inspect the raw Polymarket odds being used |
| `python probabilities.py --mock` | Inspect simulated reach probabilities |
| `python model.py --mock` | Run the optimizer, terse output |
| `pytest tests/ -q` | Full test suite (48 tests, ~15s) |

Live mode hits `gamma-api.polymarket.com` (no auth). If a market slug 404s near lockout,
check the constants in `odds.py` and the current slugs in [`SOURCES.md`](SOURCES.md).

## Pipeline

```
odds.py            Polymarket group-winner + champion markets  (live or --mock snapshot)
  ↓
probabilities.py   odds → calibrated team strengths → full-tournament Monte-Carlo →
                   group-placement probs + marginal reach probs (R16/QF/SF/F/CHAMP)
  ↓
model.py           Step 1: per-group best 1–4 ordering (24 perms, EV = 50·placement + 30·perfect)
                   Step 2: enumerate 495 third-advancer combos × tree-DP / HiGHS MILP → best bracket
  ↓
solve.py           pretty-print groups + full R32→Final bracket + expected-points breakdown
```

Static bracket topology lives in `knockout_templates.json` (R32→Final wiring, third-place
pools) and `annex_c.json` (the 495-row third-place assignment table); `bracket_structure.py`
is a thin resolver over them. `team_codes.py` is the 48-team draw + name normalization.
`scoring.py` holds the official FIFA point values.

## How it works (non-obvious bits)

- **Reach probabilities are marginal and path-independent.** FIFA banks a round's points if
  your picked team *actually* reaches it regardless of who it beat, so we use the real-world
  marginal `P(team reaches round r)` from a whole-tournament simulation — not a
  seeding-conditioned knockout-only sim.
- **Calibration matches both markets.** Strengths are fit so simulated `P(win group)` matches
  the group market *and* champion mass matches the champion market.
- **DP == MILP.** The fast tree-DP and the Pyomo/HiGHS MILP give identical brackets; the MILP
  is the one that extends to the phase-2 variance / QP risk dial.
- **The "8 best thirds" pick is EV-neutral.** All 8 R32 third-slots face a group winner, so
  the optimal bracket never advances a third — which 8 you pick doesn't change the score.

## Data provenance

Every URL real data was pulled from is in [`SOURCES.md`](SOURCES.md) (group + champion market
endpoints, timestamped price snapshots).

## Stretch (not yet built)

- **Risk dial:** swap linear EV for EV − λ·variance (QP) for contrarian pool play.
- **Joint MILP** trading group rank against knockout path (v1 decomposes the two steps).
- **Second Chance Bracket** (opens 27 June, knockout-only).
