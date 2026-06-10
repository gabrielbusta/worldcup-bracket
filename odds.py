"""
odds.py — Polymarket Gamma/CLOB client for the 2026 World Cup, with offline mock mode.

Two markets matter to the optimizer (plan §3):
  * Per-group "World Cup Group X Winner"  -> P(team wins its group)  [group-stage seeding]
  * "World Cup Winner" (outright)         -> P(team is champion)     [feeds probabilities.py]

Real JSON shape (confirmed against gamma-api 2026-06-09):
  GET /events?slug=<slug>  -> a LIST with one event object.
  event["markets"] is a list of BINARY markets, one per team. Each market has:
     groupItemTitle : the team name (e.g. "Mexico")
     outcomes       : stringified '["Yes", "No"]'
     outcomePrices  : stringified '["0.555", "0.445"]'  -> P(Yes) = win = float(prices[0])
     clobTokenIds   : stringified '[yes_token, no_token]'
  So P(team) = the market's "Yes" price; the four group markets together give the group.

Team names are normalized via team_codes (Polymarket's spellings are the canonical ones,
with ALIASES covering "Turkiye"->"Türkiye", "Bosnia-Herzegovina"->..., etc.). Champion-
market entries that aren't real WC teams (stale "Italy", liquidity-less "Team AM"/"Team AI")
are dropped.

--mock runs entirely offline from the 2026-06-09 snapshot embedded below; live mode hits
the API (works on your machine; the Anthropic sandbox can't reach gamma-api — plan §9).
"""

from __future__ import annotations

import argparse
import json

import team_codes as tc

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

GROUP_SLUG = "world-cup-group-{letter}-winner"  # letter lowercased
CHAMPION_SLUG = "world-cup-winner"

# --- Embedded snapshot (2026-06-09) for --mock / offline tests --------------------------
# Source + provenance recorded in SOURCES.md. These are the live "Yes" prices at pull time.
MOCK_GROUP_WINNER = {
    "A": {"Mexico": 0.555, "South Korea": 0.215, "Czechia": 0.185, "South Africa": 0.0635},
    "B": {"Switzerland": 0.565, "Canada": 0.305, "Bosnia and Herzegovina": 0.125, "Qatar": 0.0255},
    "C": {"Brazil": 0.725, "Morocco": 0.205, "Scotland": 0.0815, "Haiti": 0.007},
    "D": {"USA": 0.385, "Türkiye": 0.345, "Paraguay": 0.175, "Australia": 0.0945},
    "E": {"Germany": 0.675, "Ecuador": 0.205, "Ivory Coast": 0.1265, "Curaçao": 0.0055},
    "F": {"Netherlands": 0.535, "Japan": 0.265, "Sweden": 0.155, "Tunisia": 0.061},
    "G": {"Belgium": 0.695, "Egypt": 0.165, "Iran": 0.1225, "New Zealand": 0.0365},
    "H": {"Spain": 0.785, "Uruguay": 0.195, "Saudi Arabia": 0.0185, "Cape Verde": 0.0105},
    "I": {"France": 0.645, "Norway": 0.255, "Senegal": 0.095, "Iraq": 0.0105},
    "J": {"Argentina": 0.715, "Austria": 0.185, "Algeria": 0.0955, "Jordan": 0.0145},
    "K": {"Portugal": 0.625, "Colombia": 0.315, "DR Congo": 0.0425, "Uzbekistan": 0.023},
    "L": {"England": 0.685, "Croatia": 0.225, "Ghana": 0.061, "Panama": 0.027},
}

# Outright champion "Yes" prices (2026-06-09 LIVE pull — all 48 teams priced; raw sum
# ~1.017 carries the bookmaker overround). probabilities.py renormalizes across all 48.
MOCK_CHAMPION = {
    "Spain": 0.1605, "France": 0.1605, "England": 0.1055, "Portugal": 0.1015,
    "Argentina": 0.0855, "Brazil": 0.0845, "Germany": 0.0525, "Netherlands": 0.0395,
    "Norway": 0.0245, "Belgium": 0.0215, "Colombia": 0.0195, "Japan": 0.0175,
    "Morocco": 0.0175, "Mexico": 0.0135, "Switzerland": 0.0115, "USA": 0.0115,
    "Türkiye": 0.0115, "Uruguay": 0.0105, "Croatia": 0.0095, "Ecuador": 0.0085,
    "Senegal": 0.0065, "Ivory Coast": 0.0045, "Austria": 0.0045, "Canada": 0.0035,
    "Sweden": 0.0035, "South Korea": 0.0025, "Paraguay": 0.0025, "Scotland": 0.0025,
    "Czechia": 0.0025, "Egypt": 0.0025, "Iran": 0.0015, "Ghana": 0.0015,
    "Algeria": 0.0015, "Bosnia and Herzegovina": 0.0015, "DR Congo": 0.0015,
    "Australia": 0.0015, "New Zealand": 0.0005, "Haiti": 0.0005, "Jordan": 0.0005,
    "Curaçao": 0.0005, "Tunisia": 0.0005, "Uzbekistan": 0.0005, "Panama": 0.0005,
    "Iraq": 0.0005, "South Africa": 0.0005, "Cape Verde": 0.0005, "Qatar": 0.0005,
    "Saudi Arabia": 0.0005,
}


# --- HTTP (live mode) -------------------------------------------------------------------
def _http_get_json(url, params=None, retries=3, timeout=15):
    """GET JSON with a few retries. `requests` is imported lazily so --mock needs no net."""
    import time

    import requests

    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as err:  # noqa: BLE001 - surface after retries
            last_err = err
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed after {retries} tries: {last_err}")


def fetch_event(slug):
    """Fetch one event object by slug from the Gamma API (raises if not found)."""
    data = _http_get_json(f"{GAMMA_BASE}/events", params={"slug": slug})
    if not data:
        raise KeyError(f"no event for slug {slug!r}")
    return data[0] if isinstance(data, list) else data


def parse_binary_markets(event):
    """Yield (team_title, p_yes, token_ids) for each binary market in an event.

    The stringified JSON fields (`outcomes`/`outcomePrices`/`clobTokenIds`) are decoded.
    A market whose "Yes" price is missing/None (inactive) is skipped.
    """
    out = []
    for market in event.get("markets", []):
        title = market.get("groupItemTitle") or market.get("question", "")
        prices_raw = market.get("outcomePrices")
        if not prices_raw:
            continue
        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
        if not prices or prices[0] in (None, ""):
            continue
        p_yes = float(prices[0])
        tokens_raw = market.get("clobTokenIds")
        tokens = json.loads(tokens_raw) if isinstance(tokens_raw, str) else (tokens_raw or [])
        out.append((title, p_yes, tokens))
    return out


# --- Public API -------------------------------------------------------------------------
def _normalize_probs(raw):
    """Map raw {title: p} to {canonical_team: p}, dropping titles that aren't WC teams."""
    clean = {}
    for title, p in raw.items():
        try:
            team = tc.normalize(title)
        except KeyError:
            continue  # stale / placeholder market (e.g. "Italy", "Team AM")
        clean[team] = clean.get(team, 0.0) + p
    return clean


def group_winner_probs(group, mock=False, normalize_to_one=True):
    """{team: P(win group)} for one group letter.

    normalize_to_one rescales the four teams to sum to 1 (strips bookmaker vig and any
    "Other" residue) — what the group-stage EV step wants.
    """
    if mock:
        raw = dict(MOCK_GROUP_WINNER[group])
    else:
        event = fetch_event(GROUP_SLUG.format(letter=group.lower()))
        raw = {title: p for title, p, _ in parse_binary_markets(event)}
        raw = _normalize_probs(raw)
    if normalize_to_one:
        total = sum(raw.values())
        if total > 0:
            raw = {t: p / total for t, p in raw.items()}
    return raw


def all_group_winner_probs(mock=False, normalize_to_one=True):
    """{group_letter: {team: P(win group)}} for all 12 groups."""
    return {
        g: group_winner_probs(g, mock=mock, normalize_to_one=normalize_to_one)
        for g in tc.GROUP_LETTERS
    }


def champion_probs(mock=False, normalize_to_one=False):
    """{team: P(champion)} from the outright market (canonical names, non-teams dropped).

    Left UN-normalized by default: champion prices carry vig and omit longshot teams, so
    probabilities.py is the right place to apply a floor + renormalize against all 48.
    """
    if mock:
        raw = dict(MOCK_CHAMPION)
    else:
        event = fetch_event(CHAMPION_SLUG)
        raw = {title: p for title, p, _ in parse_binary_markets(event)}
        raw = _normalize_probs(raw)
    if normalize_to_one:
        total = sum(raw.values())
        if total > 0:
            raw = {t: p / total for t, p in raw.items()}
    return raw


def _print_report(mock):
    mode = "MOCK (2026-06-09 snapshot)" if mock else "LIVE (gamma-api.polymarket.com)"
    print(f"=== Group winners — {mode} ===")
    for g, probs in all_group_winner_probs(mock=mock).items():
        ranked = sorted(probs.items(), key=lambda kv: -kv[1])
        line = ", ".join(f"{t} {p:.3f}" for t, p in ranked)
        print(f"  {g}: {line}")
    champs = champion_probs(mock=mock)
    print(f"\n=== Champion odds ({len(champs)} priced teams) — {mode} ===")
    for t, p in sorted(champs.items(), key=lambda kv: -kv[1]):
        print(f"  {t:<26} {p:.4f}")
    print(f"  (sum of priced champion P = {sum(champs.values()):.3f}; rest are longshots)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Polymarket WC2026 odds client")
    ap.add_argument("--mock", action="store_true", help="use embedded offline snapshot")
    args = ap.parse_args()
    _print_report(mock=args.mock)
