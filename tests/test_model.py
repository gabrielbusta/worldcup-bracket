"""Tests for model.py — Step 1 group placement and Step 2 knockout optimization."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bracket_structure as bs  # noqa: E402
import model as M  # noqa: E402
import team_codes as tc  # noqa: E402


# ---- a deterministic, valid reach table for fast unit tests (no simulation) ----
def rigged_reach(strength):
    """Build a monotone reach table from a per-team strength in (0,1]."""
    reach = {}
    for t in tc.TEAMS:
        s = strength[t]
        reach[t] = {"R16": s, "QF": s * 0.8, "SF": s * 0.6, "F": s * 0.4, "CHAMP": s * 0.25}
    return reach


def uniform_strength(value=0.5):
    return {t: value for t in tc.TEAMS}


# =============================== Step 1 =================================
def test_optimize_group_returns_permutation():
    place = {t: {1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25} for t in tc.TEAMS}
    ordering = {g: {} for g in tc.GROUP_LETTERS}
    gp = M.optimize_group("A", place, ordering)
    assert sorted(gp.ordering) == sorted(tc.teams_in("A"))


def test_optimize_group_picks_highest_ev_ordering():
    teams = tc.teams_in("A")  # [Mexico, South Africa, South Korea, Czechia]
    # rig marginals so the unique best assignment is exactly this order
    place = {t: {1: 0.1, 2: 0.1, 3: 0.1, 4: 0.1} for t in tc.TEAMS}
    place[teams[0]] = {1: 0.9, 2: 0.0, 3: 0.0, 4: 0.1}
    place[teams[1]] = {1: 0.0, 2: 0.9, 3: 0.0, 4: 0.1}
    place[teams[2]] = {1: 0.0, 2: 0.0, 3: 0.9, 4: 0.1}
    place[teams[3]] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.9}
    ordering = {g: {} for g in tc.GROUP_LETTERS}
    gp = M.optimize_group("A", place, ordering)
    assert gp.ordering == (teams[0], teams[1], teams[2], teams[3])


def test_perfect_bonus_counts():
    teams = tc.teams_in("A")
    place = {t: {1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25} for t in tc.TEAMS}
    perfect = (teams[0], teams[1], teams[2], teams[3])
    ordering = {g: {} for g in tc.GROUP_LETTERS}
    ordering["A"] = {perfect: 1.0}  # this exact ordering always happens
    gp = M.optimize_group("A", place, ordering)
    assert gp.ordering == perfect
    assert gp.ev_perfect == pytest.approx(30.0)


def test_optimize_all_groups_builds_full_seeding():
    place = {t: {1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25} for t in tc.TEAMS}
    ordering = {g: {} for g in tc.GROUP_LETTERS}
    seeding, placements = M.optimize_all_groups(place, ordering)
    assert len(seeding) == 48
    assert len(placements) == 12
    # every position code present and pointing at a team in that group
    for g in tc.GROUP_LETTERS:
        for pos in (1, 2, 3, 4):
            code = tc.position_code(pos, g)
            assert seeding[code] in tc.teams_in(g)
    # seeding is a bijection onto the 48 teams
    assert sorted(seeding.values()) == sorted(tc.TEAMS)


# =============================== Step 2 =================================
@pytest.fixture(scope="module")
def templates_annex():
    return bs.load_templates(), bs.load_annex_c()


@pytest.fixture(scope="module")
def trivial_seeding():
    place = {t: {1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25} for t in tc.TEAMS}
    ordering = {g: {} for g in tc.GROUP_LETTERS}
    seeding, _ = M.optimize_all_groups(place, ordering)
    return seeding


def test_winners_have_correct_round_structure(templates_annex, trivial_seeding):
    templates, annex = templates_annex
    reach = rigged_reach({t: 0.3 + 0.01 * i for i, t in enumerate(tc.TEAMS)})
    res = bs.resolve_bracket("ABCDEFGH", templates, annex)
    occ = M._occupants(res, trivial_seeding)
    ev, winners, champ = M.knockout_ev_dp(res, occ, reach)
    # 16+8+4+2+1 = 31 match winners
    assert len(winners) == 31
    by_round = {"R32": 0, "R16": 0, "QF": 0, "SF": 0, "FINAL": 0}
    for mid in winners:
        by_round[res.match_round[mid]] += 1
    assert by_round == {"R32": 16, "R16": 8, "QF": 4, "SF": 2, "FINAL": 1}
    final_id = M._final_match_id(res)
    assert winners[final_id] == champ


def test_dp_matches_milp(templates_annex, trivial_seeding):
    templates, annex = templates_annex
    reach = rigged_reach({t: 0.2 + 0.015 * i for i, t in enumerate(tc.TEAMS)})
    res = bs.resolve_bracket("BDFHIJKL", templates, annex)
    occ = M._occupants(res, trivial_seeding)
    dp_ev, dp_w, dp_champ = M.knockout_ev_dp(res, occ, reach)
    mi_ev, mi_w, mi_champ = M.solve_knockout_milp(res, occ, reach)
    assert dp_ev == pytest.approx(mi_ev, abs=1e-6)
    assert dp_champ == mi_champ
    assert dp_w == mi_w


def test_champion_path_is_self_consistent(templates_annex, trivial_seeding):
    # the champion must win the final, both SF matches' winners are the finalists, etc.
    templates, annex = templates_annex
    reach = rigged_reach({t: 0.2 + 0.015 * i for i, t in enumerate(tc.TEAMS)})
    res = bs.resolve_bracket("ABCDEFGH", templates, annex)
    occ = M._occupants(res, trivial_seeding)
    _, winners, champ = M.knockout_ev_dp(res, occ, reach)
    # walk champion's path: it must be the winner of every match on its route to the final
    path = bs.path_to_final(res, next(c for c, t in occ.items() if t == champ))
    for mid in path:
        assert winners[mid] == champ, mid


def test_strong_team_becomes_champion(templates_annex, trivial_seeding):
    # give one team overwhelming reach prob; it must be our champion pick (it's feasible)
    templates, annex = templates_annex
    strength = uniform_strength(0.05)
    hero = trivial_seeding["1H"]  # Spain's slot in this trivial seeding
    strength[hero] = 1.0
    reach = rigged_reach(strength)
    res = bs.resolve_bracket("ABCDEFGH", templates, annex)
    occ = M._occupants(res, trivial_seeding)
    _, winners, champ = M.knockout_ev_dp(res, occ, reach)
    assert champ == hero


def test_full_pipeline_mock_runs():
    sol = M.optimize(mock=True, n_sims=4000, seed=0, iters=6)
    assert len(sol.seeding) == 48
    assert sol.total_ev == pytest.approx(sol.group_ev + sol.knockout_ev)
    assert sol.knockout.champion in tc.TEAMS
    assert len(sol.knockout.advancing_thirds) == 8
