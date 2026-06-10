"""Tests for probabilities.py — the Monte-Carlo reach/placement model (mock odds)."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bracket_structure as bs  # noqa: E402
import odds  # noqa: E402
import probabilities as pb  # noqa: E402
import team_codes as tc  # noqa: E402
from scoring import ADVANCEMENT_ROUNDS  # noqa: E402


@pytest.fixture(scope="module")
def sim_payload():
    """One small full-tournament sim pass (fast: tiny calibration + sim)."""
    gwp = odds.all_group_winner_probs(mock=True, normalize_to_one=True)
    champ = odds.champion_probs(mock=True, normalize_to_one=True)
    wiring = pb.KnockoutWiring(bs.load_templates())
    annex_c = bs.load_annex_c()
    R = pb.calibrate_ratings(gwp, champ, wiring, annex_c, n_sims=2500, iters=6, seed=0)
    rng = np.random.default_rng(7)
    placement, reach, _ = pb.simulate(R, wiring, annex_c, 6000, rng)
    return placement, reach


def test_per_round_counts_are_exact(sim_payload):
    # by construction each sim has exactly 16/8/4/2/1 teams reaching each round
    _, reach = sim_payload
    expected = {"R16": 16, "QF": 8, "SF": 4, "F": 2, "CHAMP": 1}
    for r, want in expected.items():
        assert reach[r].sum() == pytest.approx(want, abs=1e-9), r


def test_reach_chain_is_monotone(sim_payload):
    _, reach = sim_payload
    order = ADVANCEMENT_ROUNDS  # R16, QF, SF, F, CHAMP
    for i in range(len(order) - 1):
        # every team's P(reach deeper) <= P(reach shallower)
        assert np.all(reach[order[i + 1]] <= reach[order[i]] + 1e-9), (order[i], order[i + 1])


def test_placement_probs_sum_to_one_per_team(sim_payload):
    placement, _ = sim_payload  # (48, 4)
    assert np.allclose(placement.sum(axis=1), 1.0, atol=1e-9)


def test_each_position_filled_once_per_group(sim_payload):
    placement, _ = sim_payload
    for g in tc.GROUP_LETTERS:
        idx = [pb.TEAM_IDX[t] for t in tc.teams_in(g)]
        # for each finishing position, the 4 teams' probs sum to exactly 1
        assert np.allclose(placement[idx, :].sum(axis=0), 1.0, atol=1e-9), g


def test_reach_requires_qualification(sim_payload):
    # a team can only reach R16 if it actually finished 1st/2nd, or 3rd-and-advanced;
    # so P(reach R16) <= P(finish 1st)+P(2nd)+P(3rd)
    placement, reach = sim_payload
    for t in tc.TEAMS:
        i = pb.TEAM_IDX[t]
        top3 = placement[i, 0] + placement[i, 1] + placement[i, 2]
        assert reach["R16"][i] <= top3 + 1e-9, t


def test_calibration_tracks_both_markets():
    # higher-fidelity calibration: simulated P(1st) ≈ group market AND champion mass ≈ market
    gwp = odds.all_group_winner_probs(mock=True, normalize_to_one=True)
    champ = odds.champion_probs(mock=True, normalize_to_one=True)
    wiring = pb.KnockoutWiring(bs.load_templates())
    annex_c = bs.load_annex_c()
    R = pb.calibrate_ratings(gwp, champ, wiring, annex_c, n_sims=10000, iters=30, seed=0)
    rng = np.random.default_rng(3)
    place, reach, _ = pb.simulate(R, wiring, annex_c, 40000, rng)

    # per-team P(finish 1st) should match the group-winner market closely
    for t in tc.TEAMS:
        sim_p1 = place[pb.TEAM_IDX[t], 0]
        assert abs(sim_p1 - gwp[tc.group_of(t)][t]) < 0.05, (t, sim_p1)

    # per-group champion mass should match the champion market
    champ_sim = {t: reach["CHAMP"][pb.TEAM_IDX[t]] for t in tc.TEAMS}
    for g in tc.GROUP_LETTERS:
        market = sum(champ[t] for t in tc.teams_in(g))
        sim = sum(champ_sim[t] for t in tc.teams_in(g))
        assert abs(market - sim) < 0.03, (g, market, sim)


def test_favorites_outrank_minnows(sim_payload):
    _, reach = sim_payload
    champ = {t: reach["CHAMP"][pb.TEAM_IDX[t]] for t in tc.TEAMS}
    assert champ["Spain"] > champ["Haiti"]
    assert champ["France"] > champ["New Zealand"]
    assert champ["Brazil"] > champ["Curaçao"]


def test_knockout_wiring_shapes():
    wiring = pb.KnockoutWiring(bs.load_templates())
    assert len(wiring.r32_slots) == 32
    assert len(wiring.children["R16"]) == 8
    assert len(wiring.children["QF"]) == 4
    assert len(wiring.children["SF"]) == 2
    assert len(wiring.children["FINAL"]) == 1
    n_third = sum(1 for s in wiring.r32_slots if s[0] == "third")
    assert n_third == 8
