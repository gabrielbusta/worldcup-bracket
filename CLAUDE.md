# World Cup 2026 Bracket Optimizer

Pyomo/Monte-Carlo optimizer that produces the **expected-points-maximizing** entry for the
official **FIFA World Cup 2026 Bracket Challenge** (play.fifa.com), using live win
probabilities from **Polymarket**. Full design rationale is in `CLAUDE_CODE_PLAN.md`.

## ⏰ Lockout-day quickstart (run this on 11 June 2026, before the first match)

```bash
conda activate worldcup-bracket
cd ~/worldcup-bracket
python solve.py --sims 60000          # LIVE: pulls current Polymarket odds, prints bracket
```

Then copy the picks from the printed bracket into the FIFA app. To also save a dated,
fill-in-ready file:

```bash
python solve.py --sims 60000 > "submission_$(date +%Y%m%d).txt"
```

That's it. Everything below is reference.

## Environment

Conda env **`worldcup-bracket`** (Python 3.11). Deps: `pyomo`, `highspy` (HiGHS solver),
`numpy`, `requests`, `pytest`. If recreating:

```bash
conda create -n worldcup-bracket python=3.11 numpy requests -y
conda run -n worldcup-bracket pip install pyomo highspy pytest
```

Always run things **inside the env** (`conda activate worldcup-bracket` or `conda run -n
worldcup-bracket …`). The base env does NOT have the solver.

## How to run

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
check `odds.py` constants and `SOURCES.md` for the current slugs.

## Pipeline (data flow)

```
odds.py            Polymarket group-winner + champion markets  (live or --mock snapshot)
  ↓
probabilities.py   odds → calibrated team strengths → full-tournament Monte-Carlo →
                   group-placement probs + marginal reach probs (R16/QF/SF/F/CHAMP)
  ↓
model.py           Step 1: per-group best 1-4 ordering (24 perms, EV = 50·placement + 30·perfect)
                   Step 2: enumerate 495 third-advancer combos × tree-DP / HiGHS MILP → best bracket
  ↓
solve.py           pretty-print groups + full R32→Final bracket + expected-points breakdown
```

Static bracket topology lives in `knockout_templates.json` (R32→Final wiring, third-place
pools) and `annex_c.json` (the 495-row third-place assignment table). `bracket_structure.py`
is a thin resolver over them. `team_codes.py` is the 48-team draw + name normalization.
`scoring.py` holds the official FIFA point values. **Do not regenerate the two JSONs** —
they're transcribed/validated from the official regulations.

## Key facts to remember (non-obvious)

- **Reach probs are MARGINAL and path-independent.** FIFA banks a round's points if your
  picked team *actually* reaches it "regardless of who it beat", so we use the real-world
  marginal P(team reaches round r) from whole-tournament simulation — NOT a seeding-
  conditioned knockout-only sim. This is an intentional improvement over the plan's wording.
- **The "8 best thirds" pick is EV-neutral.** All 8 R32 third-slots face a group winner, so
  the optimal bracket never advances a third → which 8 you pick doesn't change the score.
  Pick the realistic ones for the form if you like.
- **Calibration matches BOTH markets.** Strengths are fit so simulated P(win group) matches
  the group market AND champion mass matches the champion market. If you change the match
  model (`GROUP_GOAL_C`, `KO_SCALE` in `probabilities.py`), re-check it still converges
  (`test_calibration_tracks_both_markets`).
- **DP == MILP.** The fast tree-DP and the Pyomo/HiGHS MILP give identical brackets
  (`test_dp_matches_milp`); the MILP is the one that extends to the phase-2 variance/QP risk dial.
- **Champion is close at the top.** France/Spain are near-tied (~0.16); the champion pick can
  flip between runs/odds updates. That's expected, not a bug.

## Data provenance

Every URL real data was pulled from is in `SOURCES.md` (group + champion market endpoints,
timestamped price snapshots). Cross-check the draw against fifa.com before lockout if unsure.

## Stretch / not yet built (v1 is complete)

- Phase-2 **risk dial**: swap linear EV for EV−λ·variance (QP) for contrarian pool play —
  HiGHS handles QP, no solver swap (see `CLAUDE_CODE_PLAN.md` §4).
- **Joint MILP** trading group rank against knockout path (v1 decomposes the two steps).
- **Second Chance Bracket** (opens 27 June, knockout-only) — cleaner pure-advancement problem.
