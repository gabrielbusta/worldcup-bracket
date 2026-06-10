"""
solve.py — run the optimizer and pretty-print the full FIFA Bracket Challenge entry.

This is the presentation layer over model.optimize(): it shows the predicted group tables,
the chosen 8 advancing thirds, the complete knockout bracket (R32 -> Final) with the team we
advance out of every match, and an expected-points breakdown by stage and by knockout round.

Usage:
    python solve.py --mock          # offline, uses the embedded odds snapshot
    python solve.py                 # live: pulls current Polymarket odds
    python solve.py --sims 60000    # more Monte-Carlo precision
"""

from __future__ import annotations

import argparse

import model as M
from scoring import ADVANCEMENT_POINTS, ADVANCEMENT_ROUNDS

# Human labels for the knockout rounds + the round a match's winner reaches.
ROUND_TITLE = {
    "R32": "Round of 32", "R16": "Round of 16", "QF": "Quarterfinals",
    "SF": "Semifinals", "FINAL": "Final",
}


def match_entrants(resolved, seeding, winners, mid):
    """The two teams contesting a match (for display)."""
    r = resolved.match_round[mid]
    a, b = resolved.feeders[r][mid]
    if r == "R32":
        return seeding[a], seeding[b]
    ca, cb = M._children_match_ids(resolved, mid)
    return winners[ca], winners[cb]


def print_group_stage(sol):
    print("=" * 64)
    print("GROUP STAGE — predicted final tables (1st > 2nd > 3rd > 4th)")
    print("=" * 64)
    for gp in sol.group_placements:
        order = "  >  ".join(gp.ordering)
        print(f"  Group {gp.group}:  {order}")
        print(f"            EV {gp.ev:6.1f}   "
              f"(positions {gp.ev_positions:.1f} + perfect-bonus {gp.ev_perfect:.1f})")


def print_knockout(sol):
    res = sol.knockout
    resolved = res.resolved
    winners = res.winners
    seeding = sol.seeding
    reach = sol.reach

    print("\n" + "=" * 64)
    print("KNOCKOUT BRACKET — team we advance out of each match (★ = pick)")
    print("=" * 64)
    print(f"  Advancing thirds (8 best): {', '.join(res.advancing_thirds)}")

    for rnd in ("R32", "R16", "QF", "SF", "FINAL"):
        match_ids = [m for m in resolved.feeders[rnd] if not m.endswith("3rdplace")]
        print(f"\n  --- {ROUND_TITLE[rnd]} ---")
        grant = M.WIN_GRANTS[rnd]
        for mid in match_ids:
            ta, tb = match_entrants(resolved, seeding, winners, mid)
            w = winners[mid]
            ev = ADVANCEMENT_POINTS[grant] * reach[w][grant]
            mark_a = "★" if w == ta else " "
            mark_b = "★" if w == tb else " "
            label = mid.split("_")[0]
            print(f"   {label:>5}: {mark_a}{ta:<22} vs {mark_b}{tb:<22}"
                  f"  -> {w:<22} (+{ev:5.1f} EV, reach {grant} p={reach[w][grant]:.2f})")


def print_ev_breakdown(sol):
    res = sol.knockout
    resolved = res.resolved
    winners = res.winners
    reach = sol.reach

    # advancement EV by round
    by_round = {r: 0.0 for r in ADVANCEMENT_ROUNDS}
    for mid, w in winners.items():
        grant = M.WIN_GRANTS[resolved.match_round[mid]]
        by_round[grant] += ADVANCEMENT_POINTS[grant] * reach[w][grant]

    print("\n" + "=" * 64)
    print("EXPECTED-POINTS BREAKDOWN")
    print("=" * 64)
    print(f"  Group stage                      {sol.group_ev:8.1f}")
    print("  Knockout advancement, by round banked:")
    for r in ADVANCEMENT_ROUNDS:
        print(f"      reach {r:<6} ({ADVANCEMENT_POINTS[r]:>3} pts)        {by_round[r]:8.1f}")
    print(f"  Knockout advancement (total)     {sol.knockout_ev:8.1f}")
    print("  " + "-" * 40)
    print(f"  TOTAL EXPECTED POINTS            {sol.total_ev:8.1f}")
    print(f"\n  Champion pick: {res.champion}  "
          f"(P(actually champion) = {reach[res.champion]['CHAMP']:.3f})")


def main():
    ap = argparse.ArgumentParser(description="Solve & print the WC2026 bracket entry")
    ap.add_argument("--mock", action="store_true", help="use offline odds snapshot")
    ap.add_argument("--sims", type=int, default=None, help="Monte-Carlo sims")
    args = ap.parse_args()

    mode = "MOCK snapshot" if args.mock else "LIVE Polymarket odds"
    print(f"\nFIFA World Cup 2026 — Bracket Challenge optimizer  [{mode}]")
    print("Optimizing (simulating tournament + solving)…")
    sol = M.optimize(mock=args.mock, n_sims=args.sims)

    print_group_stage(sol)
    print_knockout(sol)
    print_ev_breakdown(sol)


if __name__ == "__main__":
    main()
