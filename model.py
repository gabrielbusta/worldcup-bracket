"""
model.py — the EV-maximizing optimizer (plan §4), decomposed into two steps.

Step 1 — Group placement (per group, exact).
    For each group choose the 1/2/3/4 ordering maximizing group-stage EV:
        50 * Σ_pos P(team@pos finishes pos)  +  30 * P(this exact ordering)
    The 50-pt term uses marginal placement probs; the 30-pt perfect-group bonus uses the
    JOINT P(exact ordering) straight from the simulator (positions are dependent, so this
    is exact rather than the product-of-marginals approximation). 24 perms/group -> enumerate.

Step 2 — Which 8 thirds advance + the knockout bracket (advancement EV).
    The objective is linear in fixed coefficients ADV_PTS[r] * P_real(team reaches r):
        maximize  Σ_matches Σ_feasible-winners  win[m,t] * ADV_PTS[grant(m)] * P_real(t, grant(m))
    where winning a match at one level "grants" reaching the next round, so a champion banks
    R16+QF+SF+F+CHAMP exactly once each.

    `adv3` (which 8 of 12 thirds advance) can't sit cleanly inside one MILP because the
    annex_c third->slot assignment is a forced 495-row table lookup keyed on the WHOLE combo.
    So we ENUMERATE the C(12,8)=495 combos (small); for each, bracket_structure resolves the
    concrete R32 tree and we optimize the bracket. The per-combo bracket optimum is computed
    by an exact tree DP (fast) and the SAME problem is also expressible as the Pyomo/HiGHS
    MILP the plan calls for — `build_knockout_milp` — which we use on the winning combo and
    cross-validate against the DP (see tests).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import bracket_structure as bs
import team_codes as tc
from scoring import (
    ADVANCEMENT_POINTS,
    GROUP_CORRECT_POSITION_POINTS,
    GROUP_PERFECT_BONUS,
    THIRD_PLACE_ADVANCERS,
)

# Winning a match at round r grants REACHING the next round (where the points are banked).
WIN_GRANTS = {"R32": "R16", "R16": "QF", "QF": "SF", "SF": "F", "FINAL": "CHAMP"}


# ============================== Step 1: group placement =================================
@dataclass
class GroupPlacement:
    group: str
    ordering: tuple        # (1st, 2nd, 3rd, 4th) team names
    ev: float
    ev_positions: float    # the 50-pt component
    ev_perfect: float      # the 30-pt component


def optimize_group(group, placement_probs, ordering_probs):
    """Best 1..4 ordering for one group (enumerate all 24 permutations)."""
    teams = tc.teams_in(group)
    best = None
    for perm in itertools.permutations(teams):
        ev_pos = GROUP_CORRECT_POSITION_POINTS * sum(
            placement_probs[perm[p]][p + 1] for p in range(4)
        )
        ev_perfect = GROUP_PERFECT_BONUS * ordering_probs[group].get(perm, 0.0)
        ev = ev_pos + ev_perfect
        if best is None or ev > best.ev:
            best = GroupPlacement(group, perm, ev, ev_pos, ev_perfect)
    return best


def optimize_all_groups(placement_probs, ordering_probs):
    """Run Step 1 for every group. Returns (seeding code->team, list[GroupPlacement])."""
    placements = [optimize_group(g, placement_probs, ordering_probs) for g in tc.GROUP_LETTERS]
    seeding = {}
    for gp in placements:
        for pos, team in enumerate(gp.ordering, start=1):
            seeding[tc.position_code(pos, gp.group)] = team
    return seeding, placements


# ============================== Step 2: knockout bracket ================================
def _children_match_ids(resolved, mid):
    """The two child match ids of a non-R32 match (from its 'W..' feeders)."""
    r = resolved.match_round[mid]
    a, b = resolved.feeders[r][mid]
    return "M" + a[1:], "M" + b[1:]


def _final_match_id(resolved):
    return next(m for m in resolved.feeders["FINAL"] if m.endswith("final"))


def _subtree_teams(resolved, occ, mid, cache):
    """Set of teams that can reach (win) a given match, given R32 occupants `occ`."""
    if mid in cache:
        return cache[mid]
    r = resolved.match_round[mid]
    if r == "R32":
        a, b = resolved.feeders[r][mid]
        teams = {occ[a], occ[b]}
    else:
        ca, cb = _children_match_ids(resolved, mid)
        teams = _subtree_teams(resolved, occ, ca, cache) | _subtree_teams(resolved, occ, cb, cache)
    cache[mid] = teams
    return teams


def _occupants(resolved, seeding):
    """Map each R32 feeder position code (e.g. '1E','3C') to the team in our seeding."""
    occ = {}
    for a, b in resolved.feeders["R32"].values():
        occ[a] = seeding[a]
        occ[b] = seeding[b]
    return occ


def knockout_ev_dp(resolved, occ, reach):
    """Exact tree DP: best bracket EV for a FIXED combo. Returns (ev, winners, champion).

    winners maps every knockout match id -> the team we advance out of it.
    """
    final_id = _final_match_id(resolved)
    memo = {}  # mid -> {team: best subtree EV given that team wins mid}

    def dp(mid):
        if mid in memo:
            return memo[mid]
        r = resolved.match_round[mid]
        grant = WIN_GRANTS[r]
        pts = ADVANCEMENT_POINTS[grant]
        if r == "R32":
            a, b = resolved.feeders[r][mid]
            ta, tb = occ[a], occ[b]
            memo[mid] = {ta: pts * reach[ta][grant], tb: pts * reach[tb][grant]}
            return memo[mid]
        ca, cb = _children_match_ids(resolved, mid)
        dpa, dpb = dp(ca), dp(cb)
        best_a = max(dpa.values())
        best_b = max(dpb.values())
        res = {}
        for t, va in dpa.items():       # t emerges from child a; b contributes its best
            res[t] = pts * reach[t][grant] + va + best_b
        for t, vb in dpb.items():       # t emerges from child b; a contributes its best
            res[t] = pts * reach[t][grant] + vb + best_a
        memo[mid] = res
        return res

    top = dp(final_id)
    champion = max(top, key=top.get)
    ev = top[champion]

    winners = {}

    def reconstruct(mid, winner):
        winners[mid] = winner
        if resolved.match_round[mid] == "R32":
            return
        ca, cb = _children_match_ids(resolved, mid)
        dpa, dpb = memo[ca], memo[cb]
        if winner in dpa:
            reconstruct(ca, winner)
            reconstruct(cb, max(dpb, key=dpb.get))
        else:
            reconstruct(cb, winner)
            reconstruct(ca, max(dpa, key=dpa.get))

    reconstruct(final_id, champion)
    return ev, winners, champion


@dataclass
class KnockoutSolution:
    combo: str                 # the 8-letter advancing-thirds combo
    advancing_thirds: list     # group letters whose 3rd advances
    ev: float                  # knockout (advancement) EV
    winners: dict              # match id -> team advanced
    champion: str
    resolved: object           # the ResolvedBracket for this combo


def optimize_knockout(seeding, reach, templates=None, annex_c=None, verbose=False):
    """Enumerate all 495 third-advancer combos; return the best knockout solution."""
    templates = templates if templates is not None else bs.load_templates()
    annex_c = annex_c if annex_c is not None else bs.load_annex_c()

    best = None
    for combo_tuple in itertools.combinations(tc.GROUP_LETTERS, THIRD_PLACE_ADVANCERS):
        resolved = bs.resolve_bracket(combo_tuple, templates, annex_c)
        occ = _occupants(resolved, seeding)
        ev, winners, champion = knockout_ev_dp(resolved, occ, reach)
        if best is None or ev > best.ev:
            best = KnockoutSolution(
                combo="".join(combo_tuple),
                advancing_thirds=list(combo_tuple),
                ev=ev,
                winners=winners,
                champion=champion,
                resolved=resolved,
            )
    if verbose:
        print(f"best combo {best.combo}: knockout EV = {best.ev:.2f}, champ = {best.champion}")
    return best


# --------- The Pyomo/HiGHS MILP for a single (fixed-combo) bracket (plan §4, §8) ---------
def build_knockout_milp(resolved, occ, reach):
    """Pyomo MILP equivalent of `knockout_ev_dp` for one fixed combo.

    Variables: win[m,t] (binary) = team t advances out of match m, for t in subtree(m).
    Constraints: exactly one winner per match; a team can win a match only if it won the
    child it came from. Objective: Σ win[m,t] * ADV_PTS[grant(m)] * P_real(t, grant(m)).
    """
    import pyomo.environ as pyo

    cache = {}
    all_matches = [m for m in resolved.match_round if not m.endswith("3rdplace")]
    subtree = {m: _subtree_teams(resolved, occ, m, cache) for m in all_matches}

    pairs = [(m, t) for m in all_matches for t in subtree[m]]
    model = pyo.ConcreteModel()
    model.WIN = pyo.Set(initialize=pairs, dimen=2)
    model.win = pyo.Var(model.WIN, domain=pyo.Binary)

    # exactly one winner per match
    def one_winner_rule(m, mid):
        return sum(m.win[mid, t] for t in subtree[mid]) == 1
    model.one_winner = pyo.Constraint(all_matches, rule=one_winner_rule)

    # feeder consistency: win[m,t] <= win[child_containing_t, t]
    feeder_cons = []
    for mid in all_matches:
        if resolved.match_round[mid] == "R32":
            continue
        ca, cb = _children_match_ids(resolved, mid)
        for t in subtree[mid]:
            child = ca if t in subtree[ca] else cb
            feeder_cons.append((mid, child, t))
    model.FEED = pyo.Set(initialize=range(len(feeder_cons)))

    def feeder_rule(m, k):
        mid, child, t = feeder_cons[k]
        return m.win[mid, t] <= m.win[child, t]
    model.feeder = pyo.Constraint(model.FEED, rule=feeder_rule)

    def obj_rule(m):
        return sum(
            m.win[mid, t] * ADVANCEMENT_POINTS[WIN_GRANTS[resolved.match_round[mid]]]
            * reach[t][WIN_GRANTS[resolved.match_round[mid]]]
            for (mid, t) in pairs
        )
    model.obj = pyo.Objective(rule=obj_rule, sense=pyo.maximize)
    return model


def solve_knockout_milp(resolved, occ, reach, solver_name="appsi_highs"):
    """Solve the single-combo MILP with HiGHS. Returns (ev, winners, champion)."""
    import pyomo.environ as pyo

    model = build_knockout_milp(resolved, occ, reach)
    solver = pyo.SolverFactory(solver_name)
    assert solver.available(), f"solver {solver_name} unavailable"
    results = solver.solve(model)
    tc_ = results.solver.termination_condition
    assert str(tc_) == "optimal", f"non-optimal termination: {tc_}"

    winners = {}
    for (mid, t) in model.WIN:
        if pyo.value(model.win[mid, t]) > 0.5:
            winners[mid] = t
    final_id = _final_match_id(resolved)
    champion = winners[final_id]
    ev = pyo.value(model.obj)
    return ev, winners, champion


# ================================ Full pipeline =========================================
@dataclass
class Solution:
    seeding: dict
    group_placements: list
    knockout: KnockoutSolution
    group_ev: float
    knockout_ev: float
    total_ev: float
    reach: dict            # {team: {R16,QF,SF,F,CHAMP: p}} used for EV breakdowns
    placement_probs: dict  # {team: {1..4: p}}


def optimize(mock=False, n_sims=None, seed=1, verbose=False, **calib_kw):
    """End-to-end: simulate probabilities, run Step 1 then Step 2, return the full bracket."""
    import probabilities as pb

    kwargs = {} if n_sims is None else {"n_sims": n_sims}
    placement_probs, reach, ordering_probs = pb.all_probs(
        mock=mock, seed=seed, **kwargs, **calib_kw
    )
    seeding, placements = optimize_all_groups(placement_probs, ordering_probs)
    group_ev = sum(p.ev for p in placements)
    knockout = optimize_knockout(seeding, reach, verbose=verbose)
    return Solution(
        seeding=seeding,
        group_placements=placements,
        knockout=knockout,
        group_ev=group_ev,
        knockout_ev=knockout.ev,
        total_ev=group_ev + knockout.ev,
        reach=reach,
        placement_probs=placement_probs,
    )


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="WC2026 bracket optimizer")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--sims", type=int, default=None)
    args = ap.parse_args()

    sol = optimize(mock=args.mock, n_sims=args.sims, verbose=True)
    print("\n=== GROUP PLACEMENTS ===")
    for gp in sol.group_placements:
        print(f"  {gp.group}: {' > '.join(gp.ordering)}   EV={gp.ev:.1f}")
    print(f"\nAdvancing thirds: {', '.join(sol.knockout.advancing_thirds)}")
    print(f"Champion pick: {sol.knockout.champion}")
    print(f"\nGroup EV    = {sol.group_ev:8.1f}")
    print(f"Knockout EV = {sol.knockout_ev:8.1f}")
    print(f"TOTAL EV    = {sol.total_ev:8.1f}")
