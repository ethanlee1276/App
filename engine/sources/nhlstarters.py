"""Tonight's starting goalies, as ESPN's NHL scoreboard names them.

Ethan, 2026-10-03, on what NHL still needed: "starting goalies". The model
guesses a probable starter from who started most of his team's last ten
games (engine/nhl/model.probable_starter), and Scalpy will not bet a
goalie-dependent prop until that guess is settled. Teams announce starters
on the morning of a game; ESPN's public scoreboard (the same keyless host
as the injury report) carries them as each side's ``probables`` once they
are known — no sportsbook, no login, nothing scraped.

A name is used only when it is a goalie on that team in our own history
(nhl_build checks), so a misspelling or a call-up we have never seen
falls back to the ten-game guess instead of inventing a starter. A
"confirmed" status settles the starter outright; a plain probable replaces
the guess's NAME and is settled unless he started last night (the
back-to-back rule still applies — nhl_build).

Pure parser, read by key name, tolerant of the field being absent (it is,
until a team announces). This sandbox cannot reach ESPN; `ingest.py nhl
--probe` shows what the box sees.
"""
from __future__ import annotations

from .fetch import DataUnavailable, fetch_json

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"


def fetch_scoreboard(date: str, ttl: int = 900) -> dict:
    return fetch_json(f"{SCOREBOARD}?dates={date.replace('-', '')}", f"espn_nhl_starters_{date}.json", ttl=ttl)


def _txt(v) -> str:
    return str(v or "").strip()


def parse_probables(payload: dict) -> dict:
    """{team abbreviation: {"name", "status"}} for every side ESPN names a
    goalie for. Status is "confirmed" or "probable"."""
    from .oddsapi import NHL_TEAM_ABBR
    out: dict = {}
    for ev in (payload or {}).get("events") or []:
        for comp in (ev or {}).get("competitions") or []:
            for side in (comp or {}).get("competitors") or []:
                team = (side or {}).get("team") or {}
                abbr = NHL_TEAM_ABBR.get(_txt(team.get("displayName")), "")
                for pr in (side or {}).get("probables") or []:
                    if not isinstance(pr, dict):
                        continue
                    kind = (_txt(pr.get("name")) + " " + _txt(pr.get("displayName"))).lower()
                    ath = (pr or {}).get("athlete") or {}
                    if not isinstance(ath, dict):
                        ath = {"displayName": ath}
                    # ESPN sends the position as an object on some boards
                    # and as plain text ("G") on the hockey one — the box
                    # probe crashed on the second (2026-10-03).
                    raw_pos = ath.get("position")
                    pos = _txt(raw_pos.get("abbreviation") if isinstance(raw_pos, dict) else raw_pos).upper()
                    if "goalie" not in kind and pos != "G":
                        continue
                    name = _txt(ath.get("displayName") or ath.get("fullName"))
                    if not (abbr and name):
                        continue
                    st = (pr.get("status") or {}) if isinstance(pr, dict) else {}
                    word = (_txt(st.get("name")) + " " + _txt(st.get("type")) + " "
                            + _txt(st.get("description"))).lower() if isinstance(st, dict) else _txt(st).lower()
                    out[abbr] = {"name": name, "status": "confirmed" if "confirm" in word else "probable"}
    return out


def tonight(date: str, fetch=None) -> dict:
    """parse_probables for one date; {} when ESPN cannot be read (a gap on
    our side — the ten-game guess stands)."""
    try:
        return parse_probables((fetch or fetch_scoreboard)(date))
    except DataUnavailable:
        return {}
    except Exception:                                     # noqa: BLE001
        # A shape we have not seen must cost the starters, never the board.
        return {}
