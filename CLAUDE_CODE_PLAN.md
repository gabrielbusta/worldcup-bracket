# World Cup 2026 Bracket Optimizer — Build Plan

A Pyomo-based optimizer that produces the **expected-points-maximizing** entry for the
official **FIFA World Cup 2026 Bracket Challenge** (play.fifa.com), using live win
probabilities from **Polymarket**.

This file is the single source of truth for continuing the build in Claude Code.

---

## 1. The contest we're optimizing (OFFICIAL rules, verified from the FIFA app)

The FIFA Bracket Challenge "Full Tournament Bracket" has two prediction stages and a
**survival/advancement** scoring model (NOT per-match-winner).

### Stage A — Group stage
For each of the 12 groups (A–L), rank all four teams 1st→4th. Top 2 auto-advance; you
also separately pick the **8 best third-placed teams** to fill the 32-team knockout.

Scoring:
- **50 pts** per team placed in its exact finishing position
- **30 pts** bonus per group if all four positions are exactly correct

### Stage B — Knockout (advancement scoring)
You don't get points for "beating team X." You get points for **how far each picked
team actually advances**, banked cumulatively:

| Reaching round      | Points |
|---------------------|--------|
| Round of 16         | 20     |
| Quarterfinals       | 30     |
| Semifinals          | 40     |
| Final               | 75     |
| Champion (wins it)  | 100    |

Notes:
- **No points for reaching the Round of 32** — it's the entry round.
- A team that reaches the SF banks 20+30+40 = 90, regardless of who it beat.
- The 3rd-place playoff awards **no points** — ignore it in the objective.

### Key dates / constraints
- **Lockout: Thursday 11 June 2026** (first match). Pull odds before this; they're most
  accurate near the deadline.
- A separate **Second Chance Bracket** opens 27 June (knockout-only, R32 onward,
  pre-populated with real qualified teams). That's a cleaner phase-2 problem — pure
  advancement, no group coupling. Out of scope for v1.

---

## 2. Bracket topology — SOLVED, shipped as data

48 teams, 12 groups of 4 (A–L). Top 2 + 8 best thirds → 32-team knockout. Two
half-brackets feed the Final, plus a (point-less) 3rd-place playoff.

The full bracket structure has been extracted and validated from the **official FIFA
World Cup 26 Competition Regulations (Articles 12.6–12.11 + Annexe C)** and ships as two
JSON files. Load and use them directly; they are the authoritative source for bracket structure.

### `knockout_templates.json`
- `R32`: all 16 matches M73–M88 with their two feeders. Eight matches take a fixed
  group winner/runner-up pairing; eight take `["1X", "3rd:POOL"]` where POOL is the set
  of groups eligible to supply that slot's third-placed team.
- `R16`, `QF`, `SF`, `FINAL`: the fixed winner-of-match wiring (e.g. M89 = W74 v W77).
- `third_place_pools`: the 8 winner-slots → eligible-group sets (verified to exactly
  equal Annexe C's actual usage across all 495 rows).
- `winner_group`: winner-slot → its own group letter (for the no-rematch rule).

### `annex_c.json` — the 495-combination third-place assignment table
Keyed by the **sorted 8-letter combination** of which groups produced qualifying thirds
(e.g. `"ABCDEFGH"`), value is `{winner_slot: third_slot}`, e.g.
`{"1A":"3H","1B":"3G","1D":"3B","1E":"3C","1G":"3A","1I":"3F","1K":"3D","1L":"3E"}`.
This is THE lookup that resolves which third-placed team fills each R32 third-slot once
you know which 8 thirds advanced. There are exactly C(12,8)=495 entries.

**Integrity:** `annex_c.json` is transcribed verbatim from the official Annexe C and
verified cell-by-cell — all 495 rows, 495 distinct combos = C(12,8), consistent with the
Article 12.6 pools. Treat it as authoritative; load and use it as-is, do not regenerate or
"repair" entries (the structural rules can validate a row but cannot reconstruct one).

### How the model uses these
A team's knockout PATH is determined by (i) its group placement (1st/2nd/3rd) and (ii)
for thirds, which 8 advance. Given the optimizer's choice of the 8 advancing thirds, look
up `annex_c.json[combo]` to place them, fill the R32 from `knockout_templates.json`, then
walk the fixed R16→Final wiring. This is what makes "P(team reaches round r)" computable.

---

## 3. Data source — Polymarket (grounded in official docs)

Base URLs (no auth for read access):
- **Gamma API** `https://gamma-api.polymarket.com` — market discovery/metadata
- **CLOB API** `https://clob.polymarket.com` — live prices/midpoints

### Endpoints we use
- Fetch an event by slug:
  `GET https://gamma-api.polymarket.com/events?slug=<slug>`
  or `GET /events/slug/<slug>`
- Discover all WC markets by tag:
  `GET /events?tag_id=<id>&active=true&closed=false&limit=100` (paginate with `offset`)
  Discover the tag id via `GET /sports` or `GET /tags`.
- Each event has a `markets[]` array. Each market has:
  - `outcomes` — stringified JSON list, e.g. `"[\"Yes\", \"No\"]"`
  - `outcomePrices` — stringified JSON list, e.g. `"[\"0.17\", \"0.83\"]"` (price == implied prob)
  - `clobTokenIds` — stringified JSON list of token ids (parse with `json.loads`)
- For a single live probability per token (alternative to outcomePrices):
  `GET https://clob.polymarket.com/midpoint?token_id=<id>` → `{"mid_price": "0.45"}`
  (midpoint = avg of best bid/ask). Batch via the CLOB `/midpoints` endpoint.

### Gotchas (from docs + sandbox testing)
- `outcomes`, `outcomePrices`, `clobTokenIds` come back as **stringified JSON** —
  must `json.loads` each.
- Always pass `active=true&closed=false` for live markets.
- Rate limits are generous (general ~4000/10s; `/events` ~500/10s). Cache anyway.
- Markets we need:
  - **"World Cup Winner"** (50+ team outcomes) → champion probabilities `P(win)`.
  - **Per-group winner / advancement markets** (e.g. "World Cup Group D Winner") →
    group-stage placement + qualification probabilities.
- Team name normalization: Polymarket uses full names ("France"); the bracket data uses
  group-position codes. Build a `team_codes.py` mapping (team name <-> code <-> group)
  used everywhere, seeded from the current draw.

### Probability modeling (the one genuinely hard part)
The FIFA model scores **reaching** each round. We need, per team `t` and round `r`, the
REAL-WORLD probability `P_real(t reaches r)`. These are pure DATA — properties of the
world, not of our bracket — so each `(t, r)` becomes a fixed coefficient in the objective
(see Section 4 for why this matters). Approaches for v1:

1. **Champion-anchored (recommended):** take `P(champion)` per team from the winner
   market, derive a Bradley–Terry / Elo-like strength rating consistent with those odds,
   then **Monte-Carlo simulate** the tournament to estimate `P_real(reach r)` for every
   team and round. These are the objective coefficients.
2. **Market-direct (if available):** if Polymarket exposes "reach SF"/"reach final" per
   team, read them directly and skip simulation.

Keep this in `probabilities.py` behind a clean function returning a table:
`reach_probs(seeding) -> {team: {"R16":p,"QF":p,"SF":p,"F":p,"CHAMP":p}}`.

**Important dependency:** `P_real(reach r)` depends on a team's PATH, which depends on the
group SEEDING (1st/2nd/3rd) and which 8 thirds advanced. So reach-probs are computed
*given a seeding*. The decomposed solve order (Section 4) resolves this cleanly: fix the
group seeding first, then simulate, then optimize the knockout selection.

---

## 4. The optimization model (Pyomo) — DECOMPOSED, EV-maximizing

### The key structural insight
FIFA scores you for *how far a team you advanced actually goes* — NOT for correctly
naming the opponent it beat. So the expected points from advancing team `t` to round `r`
is a **fixed coefficient** `ADV_PTS[r] * P_real(t reaches r)`. The `P_real` values are
data (Section 3). The optimizer's job is to **select a self-consistent bracket** that
lights up the highest-value `(team, round)` cells, subject to bracket feasibility (only
one team advances out of each match). Opponent picks are scoring-irrelevant; they matter
only as slot occupancy that blocks other teams' deep runs.

The genuine coupling that justifies a global optimizer (vs. naive per-group greedy) is
that a team's group RANK changes BOTH its group-stage points AND its knockout path (hence
its `P_real`), and the choice of 8 advancing thirds reshapes R32 pairings via Annexe C.

### Decomposed solve (chosen approach — mirrors the FIFA app's own 3-step flow)
Solve in stages, fixing each before the next. Faster, far easier to validate; not
guaranteed jointly optimal (acceptable for v1; note the tradeoff below).

**Step 1 — Group placement (per-group, near-trivial).** For each of the 12 groups,
choose the 1/2/3/4 ordering maximizing group-stage EV:
`50 * sum_pos P(team finishes pos) + 30 * P(all four exactly correct)`.
This is independent across groups for the SCORING part, so enumerate all 24 permutations
per group and take the best — OR express as a tiny assignment MILP. Output: the seeding
(who is 1A, 2A, 3A, … 1L, 2L, 3L) and the 12 third-placed teams.

**Step 2 — Which 8 thirds advance + bracket selection (the MILP).** Given Step 1's
seeding, run `probabilities.py` to get `P_real(t reaches r)` for every team/round. Then
solve ONE MILP that simultaneously (a) picks which 8 of 12 thirds advance and (b) selects
the bracket, maximizing summed advancement EV.

### Step-2 decision variables (binary)
- `adv3[g]` — group `g`'s third-placed team is among the 8 that advance. `sum = 8`.
- `reach[t, r]` for r in {R16, QF, SF, F, CHAMP} — team `t` is advanced to round `r`.

### Step-2 constraints
- `sum_g adv3[g] == 8`. A team's `reach[*]` can be 1 only if it qualified (auto for
  1st/2nd; for a third, gated on its `adv3`).
- **Bracket descent / one-per-slot.** Exactly one team advances out of each match, and a
  team can reach round `r` only if it also reaches `r-1`:
  `reach[t,'QF'] <= reach[t,'R16']`, … , `reach[t,'CHAMP'] <= reach[t,'F']`.
- **Per-round counts:** `sum_t reach[t,'R16']==16`, QF==8, SF==4, F==2, CHAMP==1.
- **Path feasibility** comes from the resolved bracket: once Step-1 seeding + the chosen
  `adv3` fix the R32 pairings (via `knockout_templates.json` + `annex_c.json`), each
  match's two feeder slots are known, so `reach` flows along the real tree. Two teams in
  the same match: at most one gets `reach` at the next level.

### Step-2 objective (pure expected points, LINEAR)
```
maximize  sum over teams t, rounds r:  ADV_PTS[r] * P_real(t reaches r) * reach[t, r]
```
All coefficients are constants → linear MILP. Step-1 group EV is already banked.

### Tradeoff noted (for later)
Decomposing means Step 1 ignores how a chosen group rank might set up a better knockout
path. A **joint MILP** (Section: stretch) would trade group points against path quality
in one solve, but it's heavier to formulate and harder to validate. Ship decomposed v1,
revisit if the gap matters.

### Solver
- **HiGHS** — the current Pyomo-recommended open-source solver. Install `pip install
  highspy`; use `SOLVER = pyo.SolverFactory("appsi_highs")` (APPSI persistent interface)
  or `"highs"`. Handles LP / **MIP** / **QP** (the QP support means the phase-2 risk dial
  needs NO solver swap).
- Guardrails: `assert SOLVER.available()` before solving; pass `tee=True` to see logs.
  HiGHS has had reports of *silent failure on very large/complex MILPs* in some Pyomo
  versions — our model is small (~190 group binaries in Step 1 if done as MILP; ~160
  `reach` binaries + 12 `adv3` in Step 2), so we stay well inside the safe zone. Check
  `results.solver.termination_condition == 'optimal'`.
- Phase 2 (later): **risk dial** for pool play — swap the linear EV objective for an
  EV-minus-variance form (contrarian vs favorites-heavy). HiGHS QP covers it.

---

## 5. File layout

```
wc2026_optimizer/
  CLAUDE_CODE_PLAN.md        <- this file
  scoring.py                 <- OFFICIAL FIFA point values (done; see below)
  team_codes.py              <- name<->code mapping, group assignments    [DONE]
  knockout_templates.json    <- R32/R16/QF/SF/Final wiring + 3rd pools  [DONE, shipped]
  annex_c.json               <- 495-combo 3rd-place assignment table     [DONE, shipped]
  bracket_structure.py       <- thin loader/helpers over the two JSONs   [DONE]
  odds.py                    <- Polymarket Gamma/CLOB client + mock mode [DONE]
  probabilities.py           <- winner-odds -> reach_probs via simulation [DONE]
  model.py                   <- Pyomo variables/constraints/objective    [DONE]
  solve.py                   <- runs it, prints the optimal bracket       [DONE]
  SOURCES.md                 <- every URL real data was pulled from       [DONE]
  tests/                     <- pytest: 48 tests, mock end-to-end         [DONE]
```

**v1 STATUS: complete.** `python solve.py --mock` (offline) or `python solve.py` (live
Polymarket) produces the full bracket + EV breakdown. 48 tests pass. Built/run in the
`worldcup-bracket` conda env (pyomo + highspy + numpy + requests).

`scoring.py` is already written with the REAL values:
```python
GROUP_CORRECT_POSITION_POINTS = 50
GROUP_PERFECT_BONUS           = 30
ADVANCEMENT_POINTS = {"R16": 20, "QF": 30, "SF": 40, "F": 75, "CHAMP": 100}
ADVANCEMENT_ROUNDS = ["R16", "QF", "SF", "F", "CHAMP"]
GROUP_SCORING_POSITIONS = [1, 2, 3, 4]
THIRD_PLACE_PLAYOFF_POINTS = 0   # FIFA awards none
```

---

## 6. Build order for Claude Code

1. `team_codes.py` + `bracket_structure.py` — encode the 12 groups (current draw). The
   bracket structure is ALREADY DONE: load `knockout_templates.json` and `annex_c.json`
   (shipped, validated). `bracket_structure.py` is just a thin loader + path-walk helper
   (given the 8 advancing thirds -> resolve every R32 slot -> walk to Final).
2. `odds.py` — Gamma client with: (a) live mode hitting the real API, (b) `--mock` mode
   with realistic hardcoded JSON so the pipeline runs offline. Parse the stringified
   `outcomes`/`outcomePrices`/`clobTokenIds`.
3. `probabilities.py` — convert winner-market odds → pairwise strengths → Monte-Carlo
   `reach_probs(seeding)`. Unit-test that per-round counts (16/8/4/2/1) and chaining hold.
4. `model.py` — **Step 1 first:** per-group placement EV (enumerate 24 perms/group, or a
   tiny assignment MILP); output the seeding + 12 thirds. Verify against hand-computed EV
   on mock data. **Then Step 2:** the advancement-selection MILP (`adv3` + `reach`), using
   reach-probs computed from Step 1's fixed seeding.
5. `solve.py` — run Step 1 → simulate → Step 2; pretty-print the full bracket, total
   expected points, and a per-stage breakdown (group EV vs advancement EV).
6. `tests/` — per-group permutation feasibility; "exactly 8 thirds"; per-round counts and
   monotone `reach` chaining; a full mock-data end-to-end asserting a known optimum.

## 7. Open questions to confirm in-app (don't block v1; parameterize)
- Does "reach R16" require winning the R32 match? (Assume yes.)
- Are all four group positions scored at 50, or only 1/2/3? (Assume all four.)
- Is the 30-pt perfect-group bonus on top of the 4×50, or instead of? (Assume on top.)

## 8. Pyomo conventions + MILP linearizations (grounded in Pyomo 6.10 docs)

Use current idiomatic Pyomo (verified against pyomo.readthedocs.io/en/latest):

- **Indexed constraints/objectives via `rule=`**, not inline `expr=`:
  ```python
  def group_perm_rule(m, g, pos):
      return sum(m.x[t, pos, g] for t in teams_in[g]) == 1
  m.group_perm = pyo.Constraint(groups, positions, rule=group_perm_rule)
  ```
- **String index sets are first-class** — index variables by team codes / group
  letters directly: `m.x = pyo.Var(teams, positions, groups, domain=pyo.Binary)`.
- **Linear objective** can use `pyo.summation(coef, var)` or an explicit `sum(...)`
  generator with `sense=pyo.maximize`.
- **Solver**: `pyo.SolverFactory("appsi_highs")` (HiGHS via `pip install highspy`).
  `assert SOLVER.available()`; `results = SOLVER.solve(m, tee=True)`; check
  `results.solver.termination_condition == 'optimal'`.

### Linearization 1 — perfect-group bonus (AND of binaries)
The 30-pt bonus fires only if all four positions in a group are predicted correctly.
That's a product of binaries → linearize. Let `correct[t,pos,g]` be 1 iff the *actual*
result matches the pick (this is a probability coefficient in EV mode, but if you ever
go to a realized/what-if mode it's binary). For the EV objective you DON'T need an AND —
you just multiply the per-position probabilities to get `P(perfect group g)` as a
**constant coefficient** and apply it to a single `perfect[g]` binary that is forced to
equal the group's joint pick. Standard AND linearization for `y = AND(z1..z4)`:
```
y <= z_i           for each i        # y can't be 1 unless every z_i is 1
y >= sum(z_i) - 3                     # y must be 1 when all four are 1
y in {0,1}
```
In pure-EV mode the simpler route is: the objective coefficient on `perfect[g]` is
`GROUP_PERFECT_BONUS * P(all four correct | the chosen ordering)`, and `perfect[g]`
is tied to the four placement vars with the AND constraints above.

### Linearization 2 — knockout path coupling (advancement)
A team can only "reach round r" if (a) it qualified from its group in a slot that feeds
the relevant bracket path, and (b) it survived the prior round. Encode survival as
monotone binaries and gate them on qualification:
```
reach[t,'R16'] <= qualified[t]                 # must qualify first
reach[t,'QF']  <= reach[t,'R16']               # advancement chaining (reach r requires reach r-1)
reach[t,'SF']  <= reach[t,'QF']
reach[t,'F']   <= reach[t,'SF']
reach[t,'CHAMP'] <= reach[t,'F']
```
Structural counts per round (one champion, two finalists, etc.):
```
sum_t reach[t,'CHAMP'] == 1
sum_t reach[t,'F']     == 2
sum_t reach[t,'SF']    == 4
sum_t reach[t,'QF']    == 8
sum_t reach[t,'R16']   == 16
```
Half-bracket constraints: each of the two halves contributes exactly one finalist; the
R32 slot a team occupies (determined by group position + which thirds advanced) decides
which half it's in. Enforce with slot→half incidence built in `bracket_structure.py`.

### EV coefficients (the key point)
In pure-EV mode the objective is **linear** because every `P(...)` is a precomputed
constant from `probabilities.py`:
```
maximize
  sum_{t,pos,g} 50 * P(t finishes pos in g) * x[t,pos,g]
+ sum_{g}       30 * P(perfect g | ordering) * perfect[g]
+ sum_{t,r}     ADV_PTS[r] * P(t reaches r) * reach[t,r]
```
HiGHS solves this MILP directly. The phase-2 variance penalty (risk dial) is a QP, which
the SAME HiGHS solver handles — no solver swap needed.

### Suggested tests (pytest)
- group permutation feasibility (rows & cols each sum to 1)
- `sum(reach[:,'CHAMP']) == 1`, per-round counts (16/8/4/2/1), reach-chaining holds
- exactly 8 thirds advance
- mock end-to-end returns `optimal` and a known champion under rigged probabilities

## 9. Sandbox note
Anthropic's sandbox egress is allowlisted (PyPI/GitHub/etc.) and does NOT include
`gamma-api.polymarket.com`, so live pulls fail *here*. On your machine there's no such
limit — `odds.py` live mode will work. That's why `odds.py` ships with a mock mode.
