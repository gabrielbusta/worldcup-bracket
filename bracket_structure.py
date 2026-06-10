"""
bracket_structure.py — thin loader + path-walk helpers over the two shipped JSONs
(`knockout_templates.json`, `annex_c.json`).

These two files are the AUTHORITATIVE bracket topology, extracted/validated from the
official FIFA WC26 Competition Regulations (Articles 12.6-12.11 + Annexe C). This module
does NOT re-derive or "repair" them — it only loads them and resolves a concrete bracket
once you know which 8 third-placed teams advance.

The core service this module provides to the optimizer:

    resolve_bracket(advancing_third_groups) -> ResolvedBracket

Given the 8 groups whose third-placed team advances, it:
  1. looks up annex_c.json[combo] to place each advancing 3rd into its R32 third-slot,
  2. fills every R32 match's two feeder POSITION CODES (e.g. "1E" vs "3H"),
  3. exposes the fixed R16->Final winner-of-match wiring, and
  4. computes a slot -> half-bracket incidence (which SF each R32 match descends to),

so that "P(team reaches round r)" is computable along the REAL tournament tree.

Position codes used throughout:
  "1A".."1L"  group winner          "2A".."2L"  group runner-up
  "3A".."3L"  group third           "W<match>"  winner of that match (e.g. "W74")
  "L<match>"  loser  of that match (only the point-less 3rd-place playoff uses these)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES_PATH = os.path.join(_HERE, "knockout_templates.json")
_ANNEX_C_PATH = os.path.join(_HERE, "annex_c.json")

# Knockout rounds in advancement order. R32 is the entry round (no points); the rounds a
# team can BANK points for are R16..CHAMP. The match dict keys mirror knockout_templates.
ROUND_ORDER = ["R32", "R16", "QF", "SF", "FINAL"]

# Map a won match to the round its winner ENTERS (used to attach advancement points).
# Winning an R32 match => you reach R16, winning an R16 match => you reach QF, etc.
WIN_REACHES = {"R32": "R16", "R16": "QF", "QF": "SF", "SF": "FINAL"}


def _load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_templates():
    """Load knockout_templates.json verbatim."""
    return _load_json(_TEMPLATES_PATH)


def load_annex_c():
    """Load annex_c.json verbatim (the 495-combo third-place assignment table)."""
    return _load_json(_ANNEX_C_PATH)


def combo_key(advancing_third_groups):
    """Sorted 8-letter combo key into annex_c.json, e.g. {'H','A',...} -> 'ABCDEFGH'."""
    groups = sorted(set(advancing_third_groups))
    if len(groups) != 8:
        raise ValueError(
            f"exactly 8 third-placed groups must advance, got {len(groups)}: {groups}"
        )
    return "".join(groups)


@dataclass
class ResolvedBracket:
    """A fully concrete knockout tree for one choice of advancing thirds.

    Attributes:
        advancing_third_groups: sorted list of the 8 group letters whose 3rd advanced.
        third_assignment: {winner_slot -> third_slot}, the annex_c row used (e.g.
            "1E" -> "3C" means the team seeded 1E plays the 3rd from group C in R32).
        feeders: {round -> {match_id -> (feeder_a, feeder_b)}}. For R32 both feeders are
            concrete position codes; for later rounds they are "W<match>" references.
        entrants: the 32 R32 entrant position codes (12 winners, 12 runners, 8 thirds).
        match_round: {match_id -> round name}.
        match_half: {match_id -> 0 or 1}, which half-bracket (SF M101 vs M102) it feeds.
    """

    advancing_third_groups: list
    third_assignment: dict
    feeders: dict
    entrants: list
    match_round: dict = field(default_factory=dict)
    match_half: dict = field(default_factory=dict)

    def matches_in(self, round_name):
        """Match ids in a given round, in template order."""
        return list(self.feeders[round_name].keys())

    def feeders_of(self, match_id):
        """The two feeder slots of a match (position codes or W-refs)."""
        round_name = self.match_round[match_id]
        return self.feeders[round_name][match_id]


def _resolve_r32(templates, annex_c, advancing_third_groups):
    """Return ({match_id -> (feeder_a, feeder_b)}, third_assignment) for R32.

    The eight "3rd:POOL" slots are replaced with concrete "3X" codes via the annex_c row
    for this combo. The winner slot in each such match (the "1X" entry) is the lookup key.
    """
    combo = combo_key(advancing_third_groups)
    if combo not in annex_c:
        raise KeyError(f"combo {combo!r} not found in annex_c.json")
    assignment = annex_c[combo]  # {winner_slot -> third_slot}

    resolved = {}
    for match_id, (slot_a, slot_b) in templates["R32"].items():
        new_slots = []
        winner_slot = None
        for slot in (slot_a, slot_b):
            if not slot.startswith("3rd:"):
                # carry through "1X" / "2X"; remember the group winner as the lookup key
                if slot.startswith("1"):
                    winner_slot = slot
                new_slots.append(slot)
            else:
                new_slots.append(None)  # placeholder, filled below
        if None in new_slots:
            if winner_slot is None or winner_slot not in assignment:
                raise KeyError(
                    f"{match_id}: no annex_c third assignment for winner slot {winner_slot!r}"
                )
            third_slot = assignment[winner_slot]
            new_slots = [third_slot if s is None else s for s in new_slots]
        resolved[match_id] = tuple(new_slots)
    return resolved, assignment


def _build_match_metadata(templates, r32_feeders):
    """Build {round->{match->feeders}}, match_round, and match_half (descends-to-SF)."""
    feeders = {"R32": r32_feeders}
    match_round = {mid: "R32" for mid in r32_feeders}
    for round_name in ("R16", "QF", "SF"):
        feeders[round_name] = {}
        for match_id, slots in templates[round_name].items():
            feeders[round_name][match_id] = tuple(slots)
            match_round[match_id] = round_name
    # FINAL holds the (point-less) 3rd-place playoff and the actual final.
    feeders["FINAL"] = {}
    for match_id, slots in templates["FINAL"].items():
        feeders["FINAL"][match_id] = tuple(slots)
        match_round[match_id] = "FINAL"

    # Half-bracket incidence: SF M101 -> half 0, M102 -> half 1. Walk feeders down from
    # each SF to tag every ancestor match with the half it ultimately feeds.
    sf_matches = list(templates["SF"].keys())  # ["M101", "M102"]
    match_half = {}

    def _tag(match_id, half):
        match_half[match_id] = half
        for feeder in feeders[match_round[match_id]][match_id]:
            if isinstance(feeder, str) and feeder.startswith("W"):
                _tag("M" + feeder[1:], half)

    for half, sf in enumerate(sf_matches):
        _tag(sf, half)
    return feeders, match_round, match_half


def resolve_bracket(advancing_third_groups, templates=None, annex_c=None):
    """Resolve a concrete knockout tree given the 8 advancing third-placed groups."""
    templates = templates if templates is not None else load_templates()
    annex_c = annex_c if annex_c is not None else load_annex_c()

    r32_feeders, third_assignment = _resolve_r32(templates, annex_c, advancing_third_groups)
    feeders, match_round, match_half = _build_match_metadata(templates, r32_feeders)

    entrants = []
    for slots in r32_feeders.values():
        entrants.extend(slots)

    return ResolvedBracket(
        advancing_third_groups=sorted(set(advancing_third_groups)),
        third_assignment=third_assignment,
        feeders=feeders,
        entrants=entrants,
        match_round=match_round,
        match_half=match_half,
    )


def r32_slot_of_code(bracket, code):
    """Return (match_id, index 0/1) where position `code` enters R32, or None."""
    for match_id, slots in bracket.feeders["R32"].items():
        for idx, slot in enumerate(slots):
            if slot == code:
                return match_id, idx
    return None


def path_to_final(bracket, code):
    """The ordered list of match ids a given R32 entrant must win to lift the trophy.

    Walks R32 -> R16 -> QF -> SF -> final by following which match's winner feeds the next.
    Returns [m_r32, m_r16, m_qf, m_sf, m_final]. Useful for sanity checks and for building
    the reach-variable chaining in the model.
    """
    loc = r32_slot_of_code(bracket, code)
    if loc is None:
        raise KeyError(f"position code {code!r} is not an R32 entrant")
    match_id = loc[0]
    path = [match_id]
    # Follow "W<match_id>" upward through the rounds until the final.
    final_id = next(m for m in bracket.feeders["FINAL"] if m.endswith("final"))
    while match_id != final_id:
        win_ref = "W" + match_id[1:]  # "M74" -> "W74"
        nxt = None
        for round_name in ("R16", "QF", "SF", "FINAL"):
            for cand_id, slots in bracket.feeders[round_name].items():
                if win_ref in slots:
                    nxt = cand_id
                    break
            if nxt:
                break
        if nxt is None:
            raise RuntimeError(f"dead end walking from {match_id} (ref {win_ref})")
        match_id = nxt
        path.append(match_id)
    return path
