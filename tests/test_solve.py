"""Smoke tests for solve.py — the presentation layer over model.optimize()."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import model as M  # noqa: E402
import solve  # noqa: E402


def test_match_entrants_pull_winners_forward():
    sol = M.optimize(mock=True, n_sims=3000, seed=0, iters=6)
    res = sol.knockout
    resolved = res.resolved
    # an R16 match's two entrants must be the winners of its two R32 feeder matches
    r16_id = next(iter(resolved.feeders["R16"]))
    ca, cb = M._children_match_ids(resolved, r16_id)
    ta, tb = solve.match_entrants(resolved, sol.seeding, res.winners, r16_id)
    assert {ta, tb} == {res.winners[ca], res.winners[cb]}


def test_print_functions_run(capsys):
    sol = M.optimize(mock=True, n_sims=3000, seed=0, iters=6)
    solve.print_group_stage(sol)
    solve.print_knockout(sol)
    solve.print_ev_breakdown(sol)
    out = capsys.readouterr().out
    assert "GROUP STAGE" in out
    assert "KNOCKOUT BRACKET" in out
    assert "TOTAL EXPECTED POINTS" in out
    assert sol.knockout.champion in out


def test_ev_breakdown_rounds_sum_to_knockout_ev():
    # the per-round banked EV printed must add up to the reported knockout EV
    sol = M.optimize(mock=True, n_sims=3000, seed=0, iters=6)
    from scoring import ADVANCEMENT_POINTS
    total = 0.0
    for mid, w in sol.knockout.winners.items():
        grant = M.WIN_GRANTS[sol.knockout.resolved.match_round[mid]]
        total += ADVANCEMENT_POINTS[grant] * sol.reach[w][grant]
    assert abs(total - sol.knockout_ev) < 1e-6
