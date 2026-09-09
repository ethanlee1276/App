"""`/api/team` — the door onto a team's record and its head-to-heads.

Ethan, 2026-09-09: *"I should be able to search for the Los Angeles Rams,
and look at how they've played against any team in the past."*

CALLED, not read. `Handler._team` is a method with one dependency —
`engine.db.connect` — so the test hands it a database it built itself
and a `_send` that keeps what came back. Reading the source for the
string "resolve" would prove nothing about what a browser receives, and
what a browser receives is the whole point of an endpoint.

The connection is patched rather than opened, for the house rule: the
suite must not read the machine it runs on. Whatever finals happen to be
ingested here would make these assertions true or false by accident.

The three shapes this returns, and why they are three:

  * `resolved` — the name means more than one team. "Los Angeles" is two
    clubs and the page has to ASK. Picking one is how a lookup becomes a
    wrong answer nobody can see.
  * `profile` + `opponents` — a team on its own, and the list of who it
    has actually played, so the picker never offers a page that opens
    empty.
  * `head_to_head` — added when an opponent is named, in the same
    request, because two round trips to draw one page is two chances to
    show half of it.

Run directly: `python3 tests/test_team_endpoint.py`
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import server                                                # noqa: E402
from engine import db                                        # noqa: E402


_GAMES = (
    # (season, period, home, away, home_score, away_score, spread, total)
    (2025, "021", "SEA", "LA", 31, 27, -2.5, 45.5),
    (2024, "010", "LA", "SEA", 24, 21, -7.0, 44.0),
    (2024, "011", "LA", "LAC", 30, 13, -6.5, 41.0),
    (2023, "005", "SEA", "LA", 20, 17, -10.0, 36.5),
    # A Raiders game, so "LA" is genuinely ambiguous by prefix: "Las
    # Vegas" begins with those two letters. Without a second la- team in
    # the pool the exact-abbreviation escape below can never be exercised.
    (2023, "006", "LV", "SEA", 20, 17, -3.0, 40.0),
    # A fixture: a line, and no result yet.
    (2026, "001", "LA", "SEA", None, None, -3.0, 47.0),
)


class _Fake:
    """Just enough Handler to run one method."""

    def __init__(self):
        self.sent = None

    def _send(self, code, body, kind):
        self.sent = (code, body, kind)


def _call(**params):
    conn = db.connect(":memory:")
    conn.executemany(
        "INSERT INTO games (sport, season, period, game_id, home, away, "
        "home_score, away_score, spread, total) "
        "VALUES ('nfl',?,?,?,?,?,?,?,?,?)",
        [(s, p, f"{h}{a}{s}{p}", h, a, hs, a_s, sp, to)
         for (s, p, h, a, hs, a_s, sp, to) in _GAMES])
    conn.commit()
    real = db.connect
    db.connect = lambda *a, **k: conn                 # noqa: E731
    fake = _Fake()
    try:
        server.Handler._team(fake, {k: [v] for k, v in params.items()})
    finally:
        db.connect = real
    code, body, kind = fake.sent
    assert kind == ".json", kind
    return code, json.loads(body)


# ------------------------------------------------------------- the guards

def test_a_bad_sport_or_a_missing_team_is_a_400_not_a_crash():
    assert _call(sport="", team="LA")[0] == 400
    assert _call(sport="not-a-sport", team="LA")[0] == 400
    assert _call(sport="nfl", team="")[0] == 400
    assert _call(sport="nfl", team="   ")[0] == 400


def test_a_name_nobody_recognises_comes_back_empty_and_says_so():
    code, out = _call(sport="nfl", team="Cleveland Rams")
    assert code == 200
    assert out["resolved"] == [] and out["query"] == "Cleveland Rams"
    assert "profile" not in out


def test_a_sport_with_no_finals_says_that_rather_than_showing_nothing():
    """MLB history is not ingested on every machine. "We hold no finals
    for this league" and "this team has no games" are different
    sentences, and a blank table says neither."""
    code, out = _call(sport="mlb", team="Dodgers")
    assert code == 200 and out["no_finals"] is True
    assert out["resolved"] == []


# ---------------------------------------------------------- the three shapes

def test_an_ambiguous_city_comes_back_as_a_choice():
    code, out = _call(sport="nfl", team="Los Angeles")
    assert code == 200
    got = {r["team"] for r in out["resolved"]}
    assert got == {"LA", "LAC"}, out["resolved"]
    assert "profile" not in out, "it picked one instead of asking"
    assert all(r["name"] for r in out["resolved"]), "the choice is unlabelled"


def test_an_exact_name_is_answered_even_though_it_also_prefix_matches():
    """"Los Angeles Rams" is unambiguous, and would be thrown into the
    chooser by a rule that only counted how many candidates came back."""
    code, out = _call(sport="nfl", team="Los Angeles Rams")
    assert code == 200 and out["team"] == "LA"
    assert out["name"] == "Los Angeles Rams"
    assert out["profile"]["career"]["record"] == "2-2", out["profile"]


def test_typing_the_abbreviation_is_an_answer_even_when_a_city_shares_it():
    """"LA" is the Rams' key AND the first two letters of Las Vegas, so
    the resolver hands back two candidates. He typed the abbreviation
    exactly, which is not ambiguity — it is the most precise thing he
    could have typed, and throwing it into a chooser makes the shortest
    query the most annoying one."""
    from engine import teamdex
    pool = ["LA", "LAC", "SEA", "LV"]
    assert len(teamdex.resolve("LA", "nfl", pool)) > 1, \
        "the fixture no longer makes this ambiguous"
    code, out = _call(sport="nfl", team="LA")
    assert code == 200 and out.get("team") == "LA", out
    assert "resolved" not in out


def test_the_profile_carries_the_ranks_with_the_field_they_are_from():
    code, out = _call(sport="nfl", team="rams")
    row = {r["season"]: r for r in out["profile"]["seasons"]}[2024]
    assert row["record"] == "2-0"
    assert row["offense_rank"] and row["teams_ranked"], row
    assert row["defense_rank"] <= row["teams_ranked"]


def test_the_opponent_list_is_only_teams_there_are_games_against():
    code, out = _call(sport="nfl", team="LA")
    assert [o["team"] for o in out["opponents"]] == ["SEA", "LAC"], out["opponents"]
    assert out["opponents"][0]["games"] == 3


def test_naming_an_opponent_adds_the_head_to_head_to_the_same_answer():
    code, out = _call(sport="nfl", team="LA", vs="Seattle Seahawks")
    h = out["head_to_head"]
    assert h["opponent"] == "SEA"
    assert h["summary"]["record"] == "1-2", h["summary"]
    assert [g["season"] for g in h["games"]] == [2025, 2024, 2023]
    # The 2026 fixture has a line and no score. It is not a loss.
    assert 2026 not in [g["season"] for g in h["games"]]
    # …and the profile is still in the same response, so the page draws
    # the whole thing from one request.
    assert out["profile"]["career"]["record"] == "2-2"


def test_an_opponent_nobody_recognises_is_named_back_rather_than_ignored():
    """Silently dropping the `vs` would show him the team page he did not
    ask for and look like the history was empty."""
    code, out = _call(sport="nfl", team="LA", vs="Toronto Argonauts")
    assert "head_to_head" not in out
    assert out["vs_unknown"] == "Toronto Argonauts"


def test_the_history_is_open_to_everyone():
    """Same reasoning as the receipts CSV and the profit calendar: every
    number is a finished scoreline that is already public, and a stranger
    who arrives having searched two team names is the best advertisement
    this site has. The picks are the product; who beat whom in 2023 is
    not."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _team(self, q):")
    body = src[i:src.index("\n    def ", i + 1)]
    for gate in ("_entitled", "_require_account", "402", "401"):
        assert gate not in body, f"the team page grew a {gate} gate"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
