"""Tests for odds.py — mock-mode parsing/normalization (no network)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import odds  # noqa: E402
import team_codes as tc  # noqa: E402


def test_mock_covers_all_12_groups_4_teams_each():
    probs = odds.all_group_winner_probs(mock=True, normalize_to_one=False)
    assert set(probs) == set(tc.GROUP_LETTERS)
    for g, teams in probs.items():
        assert len(teams) == 4, g
        assert set(teams) == set(tc.teams_in(g)), g


def test_mock_group_teams_match_the_draw():
    # every team named in the odds snapshot is a real member of that group
    for g in tc.GROUP_LETTERS:
        for team in odds.group_winner_probs(g, mock=True):
            assert tc.group_of(team) == g, (g, team)


def test_normalize_to_one_sums_to_one_per_group():
    for g in tc.GROUP_LETTERS:
        probs = odds.group_winner_probs(g, mock=True, normalize_to_one=True)
        assert sum(probs.values()) == pytest.approx(1.0, abs=1e-9)


def test_unnormalized_preserves_raw_snapshot():
    a = odds.group_winner_probs("A", mock=True, normalize_to_one=False)
    assert a["Mexico"] == pytest.approx(0.555)


def test_champion_probs_are_canonical_real_teams():
    champs = odds.champion_probs(mock=True)
    for team in champs:
        assert team in tc.TEAMS, team
    # the favorites are present
    assert champs["Spain"] > 0.1
    assert champs["France"] > 0.1


def test_champion_all_48_teams_priced():
    # live market prices every team; mock mirrors that
    champs = odds.champion_probs(mock=True)
    assert set(champs) == set(tc.TEAMS)


def test_champion_raw_sum_carries_overround():
    # all 48 priced + bookmaker vig => raw sum slightly above 1; normalizing fixes it
    champs = odds.champion_probs(mock=True, normalize_to_one=False)
    assert 1.0 <= sum(champs.values()) < 1.1
    normed = odds.champion_probs(mock=True, normalize_to_one=True)
    assert sum(normed.values()) == pytest.approx(1.0, abs=1e-9)


def test_parse_binary_markets_decodes_stringified_json():
    event = {
        "markets": [
            {
                "groupItemTitle": "Mexico",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.555", "0.445"]',
                "clobTokenIds": '["111", "222"]',
            },
            {  # inactive market -> skipped
                "groupItemTitle": "Ghost",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": None,
                "clobTokenIds": None,
            },
        ]
    }
    parsed = odds.parse_binary_markets(event)
    assert parsed == [("Mexico", 0.555, ["111", "222"])]


def test_normalize_probs_drops_non_teams():
    raw = {"Mexico": 0.5, "Italy": 0.01, "Team AM": 0.0}
    clean = odds._normalize_probs(raw)
    assert "Mexico" in clean
    assert "Italy" not in clean  # not a 2026 WC team
    assert "Team AM" not in clean
