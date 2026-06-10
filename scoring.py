"""
scoring.py — OFFICIAL FIFA World Cup 2026 Bracket Challenge point values
(verified from play.fifa.com Help tab).

Scoring is a SURVIVAL/ADVANCEMENT model, not per-match:
a picked team banks points for EACH round it actually reaches, cumulatively.
All values live here so the optimizer never hard-codes a number.
"""

# --- Stage A: Group stage ----------------------------------------------------
GROUP_CORRECT_POSITION_POINTS = 50   # per team placed in its EXACT finishing slot
GROUP_PERFECT_BONUS           = 30   # bonus per group if all four positions correct
GROUP_SCORING_POSITIONS       = [1, 2, 3, 4]   # confirm in-app: all 4 vs top 3

# --- Stage B: Knockout advancement (points banked for REACHING a round) ------
# Note: no points for reaching the Round of 32 (it's the entry round).
ADVANCEMENT_POINTS = {
    "R16":   20,   # reached Round of 16 (won the R32 match)
    "QF":    30,   # reached Quarterfinals
    "SF":    40,   # reached Semifinals
    "F":     75,   # reached the Final
    "CHAMP": 100,  # won the tournament
}
ADVANCEMENT_ROUNDS = ["R16", "QF", "SF", "F", "CHAMP"]

# FIFA awards no points for the 3rd-place playoff.
THIRD_PLACE_PLAYOFF_POINTS = 0

# Number of best third-placed teams that advance to the Round of 32.
THIRD_PLACE_ADVANCERS = 8
