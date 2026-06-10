"""
team_codes.py — the 2026 FIFA World Cup draw: name <-> group <-> position-code mapping.

Single source of truth for WHICH teams are in WHICH group, used everywhere downstream
(odds.py joins Polymarket names against this; the model emits position codes against it).

Draw pulled from Polymarket's per-group "World Cup Group X Winner" markets
(gamma-api.polymarket.com, 2026-06-09), which list the four teams in each group A-L.
Canonical names are kept exactly as Polymarket spells them so `odds.py` joins cleanly;
ALIASES maps the common FIFA / alternate spellings onto the canonical string.

Terminology:
  * A team's GROUP (letter A-L) is FIXED by the draw — encoded here.
  * A team's POSITION CODE ("1A" = winner of A, "2A" = runner-up, "3A" = third, "4A" =
    fourth) is a DECISION the optimizer makes, not a fixed property — so this module maps
    team<->group and provides helpers to build/parse position codes, but does NOT assign
    a team to a rank. bracket_structure.py consumes the codes "1A".."4L".
"""

from __future__ import annotations

# Group letter -> the four teams drawn into it (order as listed by Polymarket; the
# intra-group finishing order is what the optimizer decides, so this order is not
# significant beyond membership).
GROUPS = {
    "A": ["Mexico", "South Africa", "South Korea", "Czechia"],
    "B": ["Switzerland", "Canada", "Bosnia and Herzegovina", "Qatar"],
    "C": ["Brazil", "Morocco", "Scotland", "Haiti"],
    "D": ["USA", "Türkiye", "Paraguay", "Australia"],
    "E": ["Germany", "Ecuador", "Ivory Coast", "Curaçao"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Uruguay", "Saudi Arabia", "Cape Verde"],
    "I": ["France", "Norway", "Senegal", "Iraq"],
    "J": ["Argentina", "Austria", "Algeria", "Jordan"],
    "K": ["Portugal", "Colombia", "DR Congo", "Uzbekistan"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

GROUP_LETTERS = list(GROUPS.keys())
POSITIONS = [1, 2, 3, 4]  # 1=winner, 2=runner-up, 3=third, 4=fourth

# Flat list of all 48 canonical team names.
TEAMS = [team for teams in GROUPS.values() for team in teams]

# team name -> its group letter.
TEAM_TO_GROUP = {team: letter for letter, teams in GROUPS.items() for team in teams}

# Alternate spellings -> canonical name (lowercased keys; see `normalize`). Add entries
# here as new sources (FIFA app, other books) surface different spellings.
ALIASES = {
    "korea republic": "South Korea",
    "south korea": "South Korea",
    "republic of korea": "South Korea",
    "côte d'ivoire": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "ivory coast": "Ivory Coast",
    "cabo verde": "Cape Verde",
    "cape verde": "Cape Verde",
    "turkey": "Türkiye",
    "turkiye": "Türkiye",
    "türkiye": "Türkiye",
    "united states": "USA",
    "united states of america": "USA",
    "usa": "USA",
    "us": "USA",
    "czech republic": "Czechia",
    "czechia": "Czechia",
    "bosnia and herzegovina": "Bosnia and Herzegovina",
    "bosnia-herzegovina": "Bosnia and Herzegovina",
    "bosnia & herzegovina": "Bosnia and Herzegovina",
    "dr congo": "DR Congo",
    "democratic republic of congo": "DR Congo",
    "dr congo (democratic republic)": "DR Congo",
    "congo dr": "DR Congo",
}


def normalize(name):
    """Map any known spelling of a team to its canonical name. Raises if unknown."""
    key = name.strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    # already canonical?
    for team in TEAMS:
        if team.lower() == key:
            return team
    raise KeyError(f"unknown team name: {name!r} (add it to team_codes.ALIASES)")


def group_of(team):
    """Group letter for a team (accepts any known spelling)."""
    return TEAM_TO_GROUP[normalize(team)]


def teams_in(group):
    """The four teams in a group letter."""
    return list(GROUPS[group])


def position_code(rank, group):
    """Build a position code, e.g. (1, 'A') -> '1A'. rank in 1..4."""
    if rank not in POSITIONS:
        raise ValueError(f"rank must be 1..4, got {rank}")
    if group not in GROUPS:
        raise ValueError(f"unknown group {group!r}")
    return f"{rank}{group}"


def parse_code(code):
    """Parse a position code '1A' -> (1, 'A'). Accepts 1..4 + group letter."""
    rank = int(code[0])
    group = code[1:]
    if rank not in POSITIONS or group not in GROUPS:
        raise ValueError(f"bad position code {code!r}")
    return rank, group


def all_position_codes(positions=POSITIONS):
    """All position codes for the given ranks across every group (e.g. all '1X' winners)."""
    return [f"{r}{g}" for g in GROUP_LETTERS for r in positions]


def _self_check():
    assert len(TEAMS) == 48, len(TEAMS)
    assert len(set(TEAMS)) == 48, "duplicate team name in GROUPS"
    assert len(GROUPS) == 12
    assert all(len(v) == 4 for v in GROUPS.values())
    # every alias resolves to a real team
    for canonical in ALIASES.values():
        assert canonical in TEAMS, canonical


_self_check()


if __name__ == "__main__":
    for letter in GROUP_LETTERS:
        print(f"Group {letter}: " + ", ".join(GROUPS[letter]))
    print(f"\n{len(TEAMS)} teams across {len(GROUPS)} groups.")
