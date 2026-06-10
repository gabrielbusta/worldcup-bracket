"""Tests for team_codes.py — the 2026 World Cup draw mapping."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import team_codes as tc  # noqa: E402


def test_48_unique_teams_in_12_groups_of_4():
    assert len(tc.TEAMS) == 48
    assert len(set(tc.TEAMS)) == 48
    assert len(tc.GROUPS) == 12
    assert all(len(v) == 4 for v in tc.GROUPS.values())


def test_group_letters_are_a_through_l():
    assert tc.GROUP_LETTERS == list("ABCDEFGHIJKL")


def test_group_of_known_teams():
    assert tc.group_of("Mexico") == "A"
    assert tc.group_of("Brazil") == "C"
    assert tc.group_of("England") == "L"


def test_normalize_aliases():
    assert tc.normalize("Korea Republic") == "South Korea"
    assert tc.normalize("Côte d'Ivoire") == "Ivory Coast"
    assert tc.normalize("Cabo Verde") == "Cape Verde"
    assert tc.normalize("Turkey") == "Türkiye"
    assert tc.normalize("United States") == "USA"
    assert tc.normalize("Czech Republic") == "Czechia"


def test_normalize_unknown_raises():
    with pytest.raises(KeyError):
        tc.normalize("Atlantis")


def test_position_code_roundtrip():
    for g in tc.GROUP_LETTERS:
        for r in tc.POSITIONS:
            code = tc.position_code(r, g)
            assert tc.parse_code(code) == (r, g)


def test_all_winner_codes():
    winners = tc.all_position_codes(positions=[1])
    assert winners == [f"1{g}" for g in tc.GROUP_LETTERS]
    assert len(winners) == 12


def test_each_team_maps_back_to_its_group_membership():
    for team in tc.TEAMS:
        g = tc.group_of(team)
        assert team in tc.teams_in(g)
