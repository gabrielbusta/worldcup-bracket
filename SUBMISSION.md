# FIFA World Cup 2026 — Bracket Challenge Submission

**Generated:** 2026-06-11 (lockout day), from **live Polymarket odds** (60,000-sim Monte-Carlo).
**Total expected points:** ~1702  (group 1308 + knockout 394)
**Champion pick:** 🏆 **Spain**  (P(actually champion) ≈ 0.155)

> Reproduce with: `conda run -n worldcup-bracket python solve.py --sims 60000`
> Re-run near the 11 June lockout for final odds — see `SOURCES.md`.

---

## Stage A — Group tables (enter 1st → 4th for each group)

| Group | 1st | 2nd | 3rd | 4th |
|-------|-----|-----|-----|-----|
| A | Mexico | South Korea | Czechia | South Africa |
| B | Switzerland | Canada | Bosnia and Herzegovina | Qatar |
| C | Brazil | Morocco | Scotland | Haiti |
| D | USA | Türkiye | Paraguay | Australia |
| E | Germany | Ecuador | Ivory Coast | Curaçao |
| F | Netherlands | Japan | Sweden | Tunisia |
| G | Belgium | Egypt | Iran | New Zealand |
| H | Spain | Uruguay | Saudi Arabia | Cape Verde |
| I | France | Norway | Senegal | Iraq |
| J | Argentina | Austria | Algeria | Jordan |
| K | Portugal | Colombia | DR Congo | Uzbekistan |
| L | England | Croatia | Ghana | Panama |

### 8 best third-placed teams (advance to R32)
**A, B, C, D, E, F, G, H** → Czechia, Bosnia and Herzegovina, Scotland, Paraguay, Ivory Coast, Sweden, Iran, Saudi Arabia

> ⚠️ **This pick is expected-points-NEUTRAL.** Every one of the 8 R32 third-slots faces a
> group winner, so the optimal bracket never advances a third — which 8 you pick doesn't
> change your score. We list A–H by default. If you'd rather submit a realistic-looking set,
> pick the 8 third-placed teams you think are genuinely most likely to qualify; it won't
> affect EV. (See the v1 finding in the build notes.)

---

## Stage B — Knockout picks (team you advance out of each match)

### Round of 32
| Match | Pick | over |
|-------|------|------|
| M73 | **Canada** | South Korea |
| M74 | **Germany** | Scotland (3rd) |
| M75 | **Netherlands** | Morocco |
| M76 | **Brazil** | Japan |
| M77 | **France** | Sweden (3rd) |
| M78 | **Norway** | Ecuador |
| M79 | **Mexico** | Saudi Arabia (3rd) |
| M80 | **England** | Ivory Coast (3rd) |
| M81 | **USA** | Bosnia and Herzegovina (3rd) |
| M82 | **Belgium** | Czechia (3rd) |
| M83 | **Colombia** | Croatia |
| M84 | **Spain** | Austria |
| M85 | **Switzerland** | Iran (3rd) |
| M86 | **Argentina** | Uruguay |
| M87 | **Portugal** | Paraguay (3rd) |
| M88 | **Türkiye** | Egypt |

### Round of 16
| Match | Pick | over |
|-------|------|------|
| M89 | **France** | Germany |
| M90 | **Netherlands** | Canada |
| M91 | **Brazil** | Norway |
| M92 | **England** | Mexico |
| M93 | **Spain** | Colombia |
| M94 | **Belgium** | USA |
| M95 | **Argentina** | Türkiye |
| M96 | **Portugal** | Switzerland |

### Quarterfinals
| Match | Pick | over |
|-------|------|------|
| M97 | **France** | Netherlands |
| M98 | **Spain** | Belgium |
| M99 | **England** | Brazil |
| M100 | **Portugal** | Argentina |

### Semifinals
| Match | Pick | over |
|-------|------|------|
| M101 | **Spain** | France |
| M102 | **England** | Portugal |

### Final
| Match | Pick | over |
|-------|------|------|
| M104 | 🏆 **Spain** | England |

---

## Expected-points breakdown
| Stage | EV |
|-------|----|
| Group stage | 1308.1 |
| Reach R16 (20 pts each) | 188.8 |
| Reach QF (30) | 105.3 |
| Reach SF (40) | 53.1 |
| Reach Final (75) | 31.5 |
| Champion (100) | 15.5 |
| **TOTAL** | **~1702** |

*Final four pick: Spain, France, England, Portugal. Spain over England in the final.*
