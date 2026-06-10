# Data Sources

Every external URL we've pulled real data from, so it can be re-checked. Polymarket
prices are live and move — the snapshots below are timestamped; re-pull near the
2026-06-11 lockout for final numbers.

---

## 2026 World Cup draw (groups A–L, 48 teams) → `team_codes.py`

Pulled **2026-06-09** from Polymarket's per-group "World Cup Group X Winner" markets via
the Gamma API. Each market's `outcomes` field lists the four teams in that group.

Discovery page (Polymarket sports hub, World Cup):
- https://polymarket.com/sports/world-cup/games

Per-group market API endpoints (Gamma) — slug pattern `world-cup-group-<letter>-winner`:
- https://gamma-api.polymarket.com/events?slug=world-cup-group-a-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-b-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-c-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-d-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-e-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-f-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-g-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-h-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-i-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-j-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-k-winner
- https://gamma-api.polymarket.com/events?slug=world-cup-group-l-winner

Human-readable equivalents (same data, rendered): `https://polymarket.com/event/world-cup-group-<letter>-winner`

### Group-winner price snapshot (2026-06-09, implied P(win group))
| Group | Teams (price) |
|-------|---------------|
| A | Mexico 0.555, South Korea 0.215, Czechia 0.185, South Africa 0.0635 |
| B | Switzerland 0.565, Canada 0.305, Bosnia and Herzegovina 0.125, Qatar 0.0255 |
| C | Brazil 0.725, Morocco 0.205, Scotland 0.0815, Haiti 0.007 |
| D | USA 0.385, Türkiye 0.345, Paraguay 0.175, Australia 0.0945 |
| E | Germany 0.675, Ecuador 0.205, Ivory Coast 0.1265, Curaçao 0.0055 |
| F | Netherlands 0.535, Japan 0.265, Sweden 0.155, Tunisia 0.061 |
| G | Belgium 0.695, Egypt 0.165, Iran 0.1225, New Zealand 0.0365 |
| H | Spain 0.785, Uruguay 0.195, Saudi Arabia 0.0185, Cape Verde 0.0105 |
| I | France 0.645, Norway 0.255, Senegal 0.095, Iraq 0.0105 |
| J | Argentina 0.715, Austria 0.185, Algeria 0.0955, Jordan 0.0145 |
| K | Portugal 0.625, Colombia 0.315, DR Congo 0.0425, Uzbekistan 0.023 |
| L | England 0.685, Croatia 0.225, Ghana 0.061, Panama 0.027 |

> Note: prices are "win the group" only — they seed group-stage placement but are NOT the
> champion odds (see the outright market below).

---

## Champion outright ("World Cup Winner") → `odds.py` / `probabilities.py`

Pulled **2026-06-09** (live). Binary markets (one "Yes/No" per team); **all 48 teams are
priced**. Stale/placeholder entries (`Italy`, `Team AM`, `Team AI`) are dropped by
`odds._normalize_probs`. `P(champion) = outcomePrices[0]`. The exact 48-team snapshot is
embedded as `odds.MOCK_CHAMPION` (so `--mock` reproduces it offline).

- https://gamma-api.polymarket.com/events?slug=world-cup-winner
- Rendered: https://polymarket.com/event/world-cup-winner

Top of book: Spain 0.1605, France 0.1605, England 0.1055, Portugal 0.1015,
Argentina 0.0855, Brazil 0.0845, Germany 0.0525, Netherlands 0.0395, … (full list in
`odds.MOCK_CHAMPION`).

> Raw sum ≈ 1.017 (bookmaker overround). `probabilities.py` renormalizes across all 48.

> ⚠️ The earlier WebFetch-derived list showed only ~24 teams — the page summarizer
> truncated it. The **live API returns all 48**; trust the live pull / `MOCK_CHAMPION`.

---

## API reference docs (no data pulled, used for client design)

- Polymarket Gamma API base: https://gamma-api.polymarket.com
- Polymarket CLOB API base: https://clob.polymarket.com
- CLOB midpoint endpoint: https://clob.polymarket.com/midpoint?token_id=<id>

---

## To add (still TODO)
- [x] "World Cup Winner" outright champion market (slug + URL) → done, see above
- [ ] Official FIFA group/bracket confirmation URL (cross-check the Polymarket draw)
- [ ] Re-pull all snapshots near the 2026-06-11 lockout for final numbers
