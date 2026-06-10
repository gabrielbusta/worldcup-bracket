"""Tests for bracket_structure.py — the resolver over the two shipped JSONs."""

import itertools
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bracket_structure as bs  # noqa: E402

ALL_GROUPS = list("ABCDEFGHIJKL")
# A simple, valid choice of 8 advancing thirds for the happy-path tests.
SAMPLE_THIRDS = list("ABCDEFGH")


@pytest.fixture(scope="module")
def templates():
    return bs.load_templates()


@pytest.fixture(scope="module")
def annex_c():
    return bs.load_annex_c()


def test_annex_c_has_all_495_combos(annex_c):
    expected = {"".join(c) for c in itertools.combinations(ALL_GROUPS, 8)}
    assert len(annex_c) == 495
    assert set(annex_c) == expected


def test_combo_key_sorts_and_validates():
    assert bs.combo_key("HGFEDCBA") == "ABCDEFGH"
    with pytest.raises(ValueError):
        bs.combo_key("ABC")  # not 8


def test_resolve_bracket_has_32_distinct_entrants(templates, annex_c):
    b = bs.resolve_bracket(SAMPLE_THIRDS, templates, annex_c)
    assert len(b.entrants) == 32
    assert len(set(b.entrants)) == 32


def test_entrants_are_12_winners_12_runners_8_thirds(templates, annex_c):
    b = bs.resolve_bracket(SAMPLE_THIRDS, templates, annex_c)
    winners = sorted(c for c in b.entrants if c.startswith("1"))
    runners = sorted(c for c in b.entrants if c.startswith("2"))
    thirds = sorted(c for c in b.entrants if c.startswith("3"))
    assert winners == [f"1{g}" for g in ALL_GROUPS]
    assert runners == [f"2{g}" for g in ALL_GROUPS]
    assert thirds == [f"3{g}" for g in SAMPLE_THIRDS]


def test_advancing_thirds_match_resolved_thirds(templates, annex_c):
    # For EVERY valid combo, the 8 resolved 3rd-slots must be exactly that combo's groups.
    for combo in itertools.combinations(ALL_GROUPS, 8):
        b = bs.resolve_bracket(combo, templates, annex_c)
        thirds = sorted(c[1] for c in b.entrants if c.startswith("3"))
        assert thirds == sorted(combo), combo


def test_third_slots_respect_pools(templates, annex_c):
    # Each winner-slot's assigned third must come from that slot's eligible pool.
    pools = templates["third_place_pools"]
    for combo in itertools.combinations(ALL_GROUPS, 8):
        b = bs.resolve_bracket(combo, templates, annex_c)
        for winner_slot, third_slot in b.third_assignment.items():
            assert third_slot[1] in pools[winner_slot], (combo, winner_slot, third_slot)


def test_no_rematch_winner_vs_own_group_third(templates, annex_c):
    # A group winner must never face the third from its OWN group in R32.
    wg = templates["winner_group"]
    for combo in itertools.combinations(ALL_GROUPS, 8):
        b = bs.resolve_bracket(combo, templates, annex_c)
        for winner_slot, third_slot in b.third_assignment.items():
            assert third_slot[1] != wg[winner_slot], (combo, winner_slot)


def test_round_counts(templates, annex_c):
    b = bs.resolve_bracket(SAMPLE_THIRDS, templates, annex_c)
    assert len(b.feeders["R32"]) == 16
    assert len(b.feeders["R16"]) == 8
    assert len(b.feeders["QF"]) == 4
    assert len(b.feeders["SF"]) == 2
    assert len(b.feeders["FINAL"]) == 2  # final + point-less 3rd-place playoff


def test_half_split_is_even(templates, annex_c):
    b = bs.resolve_bracket(SAMPLE_THIRDS, templates, annex_c)
    r32_halves = [b.match_half[m] for m in b.feeders["R32"]]
    assert r32_halves.count(0) == 8
    assert r32_halves.count(1) == 8


def test_every_entrant_has_path_of_length_5(templates, annex_c):
    b = bs.resolve_bracket(SAMPLE_THIRDS, templates, annex_c)
    for code in b.entrants:
        path = bs.path_to_final(b, code)
        assert len(path) == 5, (code, path)
        assert path[0] in b.feeders["R32"]
        assert path[-1].endswith("final")


def test_path_stays_in_one_half(templates, annex_c):
    b = bs.resolve_bracket(SAMPLE_THIRDS, templates, annex_c)
    for code in b.entrants:
        path = bs.path_to_final(b, code)
        # every match before the final lives in the entrant's half
        halves = {b.match_half[m] for m in path if not m.endswith("final")}
        assert len(halves) == 1, (code, path, halves)
