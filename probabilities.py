"""
probabilities.py — market odds -> team strengths -> Monte-Carlo tournament -> reach probs.

This is the "one genuinely hard part" (plan §3). It turns Polymarket odds into the two
probability tables the optimizer consumes:

  * group_placement_probs() -> {team: {1:p, 2:p, 3:p, 4:p}}      [Step-1 group-stage EV]
  * reach_probs()           -> {team: {R16,QF,SF,F,CHAMP: p}}    [Step-2 advancement EV]

MODELING DECISION (intentional divergence from the plan's wording).
The plan sketched `reach_probs(seeding)` by FIXING a group seeding and simulating only the
knockout. But FIFA's advancement scoring is PATH-INDEPENDENT — you bank a round's points if
your picked team *actually* reaches that round, "regardless of who it beat" (plan §1). So
the correct objective coefficient is the MARGINAL real-world P(team reaches round r). We
compute it by simulating the WHOLE tournament — group round-robins -> realized 8 best
thirds -> annex_c bracket resolution -> knockout — which integrates over BOTH things the
plan flagged (a team's group finish AND which thirds advance) instead of conditioning on a
guess. These marginals are properties of the world, independent of our bracket picks, so
each (team, round) is a fixed constant in the MILP objective (plan §4). The optimizer's
job is purely to select a feasible set of (team,round) cells to "light up".

STRENGTH MODEL (champion-anchored, two-level — plan §3 approach 1).
  * Within a group, relative strength comes from the sharp, local group-winner market:
    w_t ∝ P(win group)_t  (renormalized to mean 1 inside each group).
  * Cross-group scale comes from the champion market: a per-group log-offset o_g is
    calibrated by Monte-Carlo so each group's simulated champion mass matches the market's.
  * Final rating  R_t = o_g + log(w_t);  strength g_t = exp(R_t).

MATCH MODEL.
  * Group matches: Poisson goals with supremacy from the rating gap -> W/D/L + GD + GF,
    which is exactly what FIFA's third-place ranking (points, then GD, then GF) needs.
  * Knockout matches: Bradley-Terry, P(A beats B) = sigmoid(KO_SCALE * (R_A - R_B)).

Everything is vectorized over sims with numpy; the only per-sim Python step is the
annex_c third-slot lookup (a cheap dict access).
"""

from __future__ import annotations

import numpy as np

import bracket_structure as bs
import odds
import team_codes as tc
from scoring import ADVANCEMENT_ROUNDS

# --- Tunable model constants ------------------------------------------------------------
GROUP_GOAL_MU = 1.35     # baseline expected goals per team in an even group match
GROUP_GOAL_C = 0.45      # how strongly a rating gap turns into goal supremacy
KO_SCALE = 1.05          # knockout decisiveness: P(A) = sigmoid(KO_SCALE*(R_A - R_B))
WIN_GROUP_EXP = 1.0      # w_t ∝ P(win group)^WIN_GROUP_EXP (1.0 = proportional)

DEFAULT_SIMS = 40_000
CALIB_SIMS = 12_000
CALIB_ITERS = 40
CALIB_CLIP = 0.40        # max |per-iteration rating update| (stabilizes log-ratio steps)

# Stable team index space (0..47) over the canonical draw order.
TEAMS = tc.TEAMS
N_TEAMS = len(TEAMS)
TEAM_IDX = {t: i for i, t in enumerate(TEAMS)}
GROUP_OF = np.array([tc.GROUP_LETTERS.index(tc.group_of(t)) for t in TEAMS])
# group letter -> the 4 team indices in it (draw order)
GROUP_MEMBERS = {
    g: [TEAM_IDX[t] for t in tc.teams_in(g)] for g in tc.GROUP_LETTERS
}
# the 6 round-robin fixtures among a group's 4 slots (local indices 0..3)
GROUP_FIXTURES = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]


# --- Knockout wiring as flat index arrays (built once from the templates) ---------------
class KnockoutWiring:
    """Precomputed, combo-independent index structure for vectorized knockout sim.

    r32_slots: list of 32 specs (one per R32 feeder slot, in match order). Each is either
        ("fixed", group_idx, finish_pos) for a "1A"/"2A" slot, or
        ("third", winner_slot_str)      for a "3rd:POOL" slot resolved via annex_c.
    children[round]: list of (idx_a, idx_b) into the PREVIOUS round's winners array.
    """

    def __init__(self, templates):
        self.templates = templates
        r32_ids = list(templates["R32"].keys())
        self.r32_ids = r32_ids
        self.r32_slots = []
        for mid in r32_ids:
            for slot in templates["R32"][mid]:
                if slot.startswith("3rd:"):
                    winner_slot = next(
                        s for s in templates["R32"][mid] if s.startswith("1")
                    )
                    self.r32_slots.append(("third", winner_slot))
                else:
                    pos = int(slot[0])
                    g_idx = tc.GROUP_LETTERS.index(slot[1])
                    self.r32_slots.append(("fixed", g_idx, pos))

        # winner-of-match wiring for R16..FINAL, as indices into the prior round.
        self.round_order = ["R16", "QF", "SF", "FINAL"]
        ids_by_round = {"R32": r32_ids}
        for r in ("R16", "QF", "SF"):
            ids_by_round[r] = list(templates[r].keys())
        final_id = next(m for m in templates["FINAL"] if m.endswith("final"))
        ids_by_round["FINAL"] = [final_id]
        self.ids_by_round = ids_by_round

        prev_round = "R32"
        self.children = {}
        for r in self.round_order:
            prev_idx = {mid: i for i, mid in enumerate(ids_by_round[prev_round])}
            pairs = []
            match_ids = [final_id] if r == "FINAL" else list(templates[r].keys())
            for mid in match_ids:
                feeders = templates[r][mid] if r != "FINAL" else templates["FINAL"][final_id]
                a, b = feeders  # "W74", "W77"
                pairs.append((prev_idx["M" + a[1:]], prev_idx["M" + b[1:]]))
            self.children[r] = pairs
            prev_round = r


# --- Strength derivation ----------------------------------------------------------------
def within_group_strengths(group_winner_probs):
    """{team: w} with mean 1 inside each group, from the group-winner market."""
    w = {}
    for g in tc.GROUP_LETTERS:
        probs = group_winner_probs[g]
        raw = {t: max(probs[t], 1e-6) ** WIN_GROUP_EXP for t in probs}
        mean = sum(raw.values()) / len(raw)
        for t in raw:
            w[t] = raw[t] / mean
    return w


def base_ratings(group_winner_probs, group_offsets=None):
    """R_t = o_g + log(w_t) as a numpy array indexed by team (offsets default 0)."""
    w = within_group_strengths(group_winner_probs)
    offsets = group_offsets if group_offsets is not None else np.zeros(len(tc.GROUP_LETTERS))
    R = np.empty(N_TEAMS)
    for i, t in enumerate(TEAMS):
        R[i] = offsets[GROUP_OF[i]] + np.log(w[t])
    return R


# --- Simulation engine ------------------------------------------------------------------
def _simulate_groups(R, n_sims, rng):
    """Vectorized group stage. Returns:

    standings[g]: int array (n_sims, 4) of team indices ordered 1st..4th for group g.
    third_stats: for the 12 group-thirds, a ranking key (n_sims, 12) and the team idx.
    placement_counts: (48, 4) counts of finishes in pos 1..4 (for group_placement_probs).
    """
    placement_counts = np.zeros((N_TEAMS, 4))
    standings = {}
    thirds_idx = np.empty((n_sims, 12), dtype=int)
    thirds_key = np.empty((n_sims, 12))
    ordering_counts = {}  # g -> {(t1,t2,t3,t4) global-index tuple: count}

    for gi, g in enumerate(tc.GROUP_LETTERS):
        members = np.array(GROUP_MEMBERS[g])  # 4 global indices
        pts = np.zeros((n_sims, 4))
        gd = np.zeros((n_sims, 4))
        gf = np.zeros((n_sims, 4))
        for a, b in GROUP_FIXTURES:
            diff = R[members[a]] - R[members[b]]
            lam_a = GROUP_GOAL_MU * np.exp(GROUP_GOAL_C * diff)
            lam_b = GROUP_GOAL_MU * np.exp(-GROUP_GOAL_C * diff)
            ga = rng.poisson(lam_a, size=n_sims)
            gb = rng.poisson(lam_b, size=n_sims)
            gd[:, a] += ga - gb
            gd[:, b] += gb - ga
            gf[:, a] += ga
            gf[:, b] += gb
            pts[:, a] += np.where(ga > gb, 3, np.where(ga == gb, 1, 0))
            pts[:, b] += np.where(gb > ga, 3, np.where(gb == ga, 1, 0))

        # ranking key: points, then GD, then GF, then random tiebreak — all in one float.
        noise = rng.random((n_sims, 4)) * 0.01
        key = pts * 1e6 + gd * 1e3 + gf + noise
        order = np.argsort(-key, axis=1)  # (n_sims,4) local positions ordered best..worst
        ranked_global = members[order]    # team indices ordered 1st..4th
        standings[g] = ranked_global

        for pos in range(4):
            np.add.at(placement_counts, (ranked_global[:, pos], pos), 1)

        # exact-ordering distribution (for the perfect-group bonus): count distinct rows
        uniq, counts = np.unique(ranked_global, axis=0, return_counts=True)
        ordering_counts[g] = {tuple(int(x) for x in row): int(c)
                              for row, c in zip(uniq, counts)}

        # capture this group's 3rd-placed team and its ranking key for the best-8 race
        third_local = order[:, 2]
        thirds_idx[:, gi] = members[third_local]
        thirds_key[:, gi] = np.take_along_axis(key, third_local[:, None], axis=1)[:, 0]

    return standings, thirds_idx, thirds_key, placement_counts, ordering_counts


def _select_advancing_thirds(thirds_idx, thirds_key, n_sims):
    """Per sim, the 8 best of the 12 group-thirds. Returns (advancing group-letter sets,
    and a (n_sims) list of dict winner_slot-> needs annex_c). Here we return the sorted
    8-letter combos and the mapping group-letter -> that group's third team index."""
    # top-8 columns (group indices 0..11) by key, per sim
    top8_cols = np.argsort(-thirds_key, axis=1)[:, :8]
    return top8_cols


def _resolve_r32_entrants(wiring, annex_c, standings, thirds_idx, top8_cols, n_sims):
    """Build R32 entrants as a team-index array (n_sims, 32) in template slot order."""
    letters = tc.GROUP_LETTERS
    entrants = np.empty((n_sims, 32), dtype=int)

    # fixed slots: gather from standings; third slots: filled per-sim from annex_c.
    third_slot_positions = []  # (slot_col, winner_slot_str)
    for col, spec in enumerate(wiring.r32_slots):
        if spec[0] == "fixed":
            _, g_idx, pos = spec
            entrants[:, col] = standings[letters[g_idx]][:, pos - 1]
        else:
            third_slot_positions.append((col, spec[1]))

    # which group's third sits in each "winner_slot" -> team index, per sim, via annex_c
    # combo string per sim (sorted 8 advancing group letters)
    advancing_letters = np.array(list(letters))[top8_cols]  # (n_sims, 8) letters
    # map group letter -> column in thirds_idx (it's just the group index)
    for s in range(n_sims):
        combo = "".join(sorted(advancing_letters[s]))
        assignment = annex_c[combo]  # {winner_slot: third_slot like "3C"}
        for col, winner_slot in third_slot_positions:
            third_group = assignment[winner_slot][1]  # letter
            gi = letters.index(third_group)
            entrants[s, col] = thirds_idx[s, gi]
    return entrants


def _simulate_knockout(R, wiring, entrants, n_sims, rng):
    """Play R32->Final. Returns reach[round] = boolean (n_sims, 48) for R16..CHAMP."""
    reach = {r: np.zeros((n_sims, N_TEAMS), dtype=bool) for r in ADVANCEMENT_ROUNDS}

    def play(a, b):
        p = 1.0 / (1.0 + np.exp(-KO_SCALE * (R[a] - R[b])))
        a_wins = rng.random(a.shape[0]) < p
        return np.where(a_wins, a, b)

    # R32: 16 matches -> winners reach R16
    winners = np.empty((n_sims, 16), dtype=int)
    for m in range(16):
        winners[:, m] = play(entrants[:, 2 * m], entrants[:, 2 * m + 1])
    for m in range(16):
        np.add.at(reach["R16"], (np.arange(n_sims), winners[:, m]), True)

    round_to_label = {"R16": "QF", "QF": "SF", "SF": "F", "FINAL": "CHAMP"}
    for r in wiring.round_order:
        pairs = wiring.children[r]
        nxt = np.empty((n_sims, len(pairs)), dtype=int)
        for m, (ia, ib) in enumerate(pairs):
            nxt[:, m] = play(winners[:, ia], winners[:, ib])
        label = round_to_label[r]
        for m in range(nxt.shape[1]):
            np.add.at(reach[label], (np.arange(n_sims), nxt[:, m]), True)
        winners = nxt
    return reach


def simulate(R, wiring, annex_c, n_sims, rng):
    """Full tournament MC. Returns (placement_probs (48,4), reach_prob dict round->(48,),
    ordering_probs {group: {ordering_tuple: prob}})."""
    standings, thirds_idx, thirds_key, placement_counts, ordering_counts = \
        _simulate_groups(R, n_sims, rng)
    top8_cols = _select_advancing_thirds(thirds_idx, thirds_key, n_sims)
    entrants = _resolve_r32_entrants(wiring, annex_c, standings, thirds_idx, top8_cols, n_sims)
    reach = _simulate_knockout(R, wiring, entrants, n_sims, rng)
    placement_probs = placement_counts / n_sims
    reach_probs = {r: reach[r].mean(axis=0) for r in ADVANCEMENT_ROUNDS}
    ordering_probs = {
        g: {order: c / n_sims for order, c in counts.items()}
        for g, counts in ordering_counts.items()
    }
    return placement_probs, reach_probs, ordering_probs


# --- Joint calibration: within-group P(1st) + cross-group champion mass -----------------
# Two orthogonal targets fit on orthogonal rating subspaces:
#   * within-group SHAPE  -> simulated P(finish 1st) matches the group-winner market
#     (the market IS the answer to P(1st); a round-robin over w ∝ P(win) over-concentrates
#      on favorites, so we calibrate the strengths to reproduce the market instead).
#   * group-level MEAN    -> simulated champion mass per group matches the champion market.
def calibrate_ratings(group_winner_probs, champion_probs, wiring, annex_c,
                      n_sims=CALIB_SIMS, iters=CALIB_ITERS, lr_within=0.3, lr_group=0.4,
                      seed=0, verbose=False):
    """Fit a full per-team rating array so the simulator reproduces both markets."""
    letters = tc.GROUP_LETTERS
    group_idx = {g: [TEAM_IDX[t] for t in tc.teams_in(g)] for g in letters}

    market_P1 = np.array([
        max(group_winner_probs[tc.group_of(t)][t], 1e-4) for t in TEAMS
    ])
    champ = {t: champion_probs.get(t, 0.0) for t in TEAMS}
    total = sum(champ.values())
    champ = {t: champ[t] / total for t in TEAMS}
    market_mass = np.clip(
        np.array([sum(champ[t] for t in tc.teams_in(g)) for g in letters]), 1e-5, None
    )

    R = base_ratings(group_winner_probs)  # init from log(w), offsets 0
    rng = np.random.default_rng(seed)
    for it in range(iters):
        place, reach, _ = simulate(R, wiring, annex_c, n_sims, rng)
        sim_P1 = np.clip(place[:, 0], 1e-4, None)

        # within-group shape update (gauge: zero mean inside each group), clipped
        upd = np.clip(lr_within * (np.log(market_P1) - np.log(sim_P1)), -CALIB_CLIP, CALIB_CLIP)
        for g in letters:
            idx = group_idx[g]
            upd[idx] -= upd[idx].mean()
        R = R + upd

        # group-level mean update from champion mass, clipped
        sim_mass = np.clip(
            np.array([reach["CHAMP"][group_idx[g]].sum() for g in letters]), 1e-5, None
        )
        delta = np.clip(lr_group * (np.log(market_mass) - np.log(sim_mass)), -CALIB_CLIP, CALIB_CLIP)
        for gi, g in enumerate(letters):
            R[group_idx[g]] += delta[gi]
        R -= R.mean()  # global gauge

        if verbose:
            p1_err = np.abs(sim_P1 - market_P1).max()
            mass_err = np.abs(sim_mass - market_mass).sum()
            print(f"  calib {it:2d}: max|ΔP1|={p1_err:.3f}  L1 champ-mass={mass_err:.4f}")
    return R


# --- Public API -------------------------------------------------------------------------
def team_ratings(mock=False, group_winner_probs=None, champion_probs=None, **calib_kw):
    """Calibrated ratings array (48,) plus the offsets, ready to feed simulate()."""
    if group_winner_probs is None:
        group_winner_probs = odds.all_group_winner_probs(mock=mock, normalize_to_one=True)
    if champion_probs is None:
        champion_probs = odds.champion_probs(mock=mock, normalize_to_one=True)
    wiring = KnockoutWiring(bs.load_templates())
    annex_c = bs.load_annex_c()
    R = calibrate_ratings(group_winner_probs, champion_probs, wiring, annex_c, **calib_kw)
    return R, wiring, annex_c


def _probs_payload(mock, n_sims, seed, **calib_kw):
    R, wiring, annex_c = team_ratings(mock=mock, **calib_kw)
    rng = np.random.default_rng(seed)
    placement, reach, ordering = simulate(R, wiring, annex_c, n_sims, rng)
    return R, placement, reach, ordering


def _ordering_to_names(ordering):
    """Convert {group: {idx-tuple: p}} to {group: {team-name-tuple (1st..4th): p}}."""
    return {
        g: {tuple(TEAMS[i] for i in order): p for order, p in dist.items()}
        for g, dist in ordering.items()
    }


def group_placement_probs(mock=False, n_sims=DEFAULT_SIMS, seed=1, **calib_kw):
    """{team: {1:p, 2:p, 3:p, 4:p}} — P(team finishes each position in its group)."""
    _, placement, _, _ = _probs_payload(mock, n_sims, seed, **calib_kw)
    return {
        t: {pos + 1: float(placement[TEAM_IDX[t], pos]) for pos in range(4)}
        for t in TEAMS
    }


def reach_probs(mock=False, n_sims=DEFAULT_SIMS, seed=1, **calib_kw):
    """{team: {R16,QF,SF,F,CHAMP: p}} — marginal P(team reaches each knockout round)."""
    _, _, reach, _ = _probs_payload(mock, n_sims, seed, **calib_kw)
    return {
        t: {r: float(reach[r][TEAM_IDX[t]]) for r in ADVANCEMENT_ROUNDS}
        for t in TEAMS
    }


def all_probs(mock=False, n_sims=DEFAULT_SIMS, seed=1, **calib_kw):
    """Compute placement, reach, and exact-ordering tables in one simulation pass.

    Returns (placement_tbl, reach_tbl, ordering_tbl):
      placement_tbl: {team: {1..4: p}}
      reach_tbl:     {team: {R16,QF,SF,F,CHAMP: p}}
      ordering_tbl:  {group: {(1st,2nd,3rd,4th) team-name tuple: p}}
    """
    _, placement, reach, ordering = _probs_payload(mock, n_sims, seed, **calib_kw)
    placement_tbl = {
        t: {pos + 1: float(placement[TEAM_IDX[t], pos]) for pos in range(4)} for t in TEAMS
    }
    reach_tbl = {
        t: {r: float(reach[r][TEAM_IDX[t]]) for r in ADVANCEMENT_ROUNDS} for t in TEAMS
    }
    return placement_tbl, reach_tbl, _ordering_to_names(ordering)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="WC2026 reach-probability model")
    ap.add_argument("--mock", action="store_true", help="use offline odds snapshot")
    ap.add_argument("--sims", type=int, default=DEFAULT_SIMS)
    args = ap.parse_args()

    placement, reach, _ordering = all_probs(mock=args.mock, n_sims=args.sims)
    print("\n=== Champion / deep-round reach probs (top 16 by P(champ)) ===")
    rows = sorted(reach.items(), key=lambda kv: -kv[1]["CHAMP"])[:16]
    print(f"{'team':<24}{'R16':>7}{'QF':>7}{'SF':>7}{'F':>7}{'CHAMP':>8}")
    for t, pr in rows:
        print(f"{t:<24}" + "".join(f"{pr[r]:>7.3f}" for r in ['R16', 'QF', 'SF', 'F'])
              + f"{pr['CHAMP']:>8.3f}")
    print(f"\nSum CHAMP = {sum(pr['CHAMP'] for pr in reach.values()):.3f} (want ~1.0)")
    print(f"Sum F     = {sum(pr['F'] for pr in reach.values()):.3f} (want ~2.0)")
    print(f"Sum SF    = {sum(pr['SF'] for pr in reach.values()):.3f} (want ~4.0)")
    print(f"Sum R16   = {sum(pr['R16'] for pr in reach.values()):.3f} (want ~16.0)")
