"""Half the Rams squad was listed twice, and a percentage was summed.

Ethan, 2026-09-10, on the team page: "It looks a lot better, but we could
still be showing more data" — and the screenshot beside that sentence
shows two defects the page had been drawing since the squad shipped.

ONE — EVERY SKILL PLAYER APPEARED TWICE. `player_game_logs` holds two NFL
feeds under one schema and they do not spell a name the same way. The
weekly box score (`ingest.weekly_result_rows`) writes "Kyren Williams"
with a position; the play-by-play (`sources.nflpbp.xfp_player_rows`)
writes "K.Williams" with an EMPTY one, and says so in its own docstring:
"Player names in pbp are abbreviated". `teamdex.squad` grouped on the raw
string, so each man came out as two players — once under RB, WR or TE,
and once in a nameless "—" bucket at the bottom of the page holding
K.Williams, B.Corum, P.Nacua, D.Adams, C.Parkinson and D.Allen. Fourteen
of them, under a heading that was just a dash.

`fantasy._short_key` — (first initial, surname, team) — is the join the
fantasy layer and the usage maps already use for exactly this pair of
feeds, and both spellings produce it. Nothing is dropped by folding on
it: a row that joins nothing keeps its own key and its own entry, which
is what a college feed with no roster position needs.

TWO — A RATE WAS BEING SUMMED. "Nick Vannett 7 G · Snap Pct 0/g · 0.3
total". `snap_pct` is a share of snaps, 0 to 1 (`ingest.snap_count_rows`
divides by 100 when a vintage publishes 0-100). Seven games at four
percent added to 0.3 of nothing, and the per-game figure rounded to
zero — so the one row that had a real fact on it printed two numbers that
were both false. A rate's honest summary is its mean, printed as a
percentage, with no total at all.

Run directly: `python3 tests/test_team_squad_identity.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db, teamdex                              # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _logs(*rows):
    """(player, position, market, value, game_id) → a history DB."""
    conn = db.connect(":memory:")
    db.upsert_player_logs(conn, [{
        "sport": "nfl", "season": 2025, "period": "001", "game_id": g,
        "player": p, "team": "LA", "opponent": "SEA", "position": pos,
        "home": 1, "market": m, "value": v} for p, pos, m, v, g in rows])
    conn.commit()
    return conn


def _flat(conn, team="LA"):
    """[(position, player)] for every row the page will draw."""
    sq = teamdex.squad(conn, "nfl", team)
    return [(g["position"], w["player"])
            for g in sq["positions"] for w in g["players"]]


def _who(conn, name, team="LA"):
    for g in teamdex.squad(conn, "nfl", team)["positions"]:
        for w in g["players"]:
            if w["player"] == name:
                return w
    return None


# --- one: two feeds, one player ---------------------------------------------
def test_the_play_by_play_spelling_folds_into_the_box_score_player():
    """The whole report in one assertion: Kyren Williams is one player."""
    conn = _logs(("Kyren Williams", "RB", "rush_yds", 90, "g1"),
                 ("K.Williams", "", "xfp", 15.4, "g1"))
    assert _flat(conn) == [("RB", "Kyren Williams")], \
        "the abbreviated row is still a second player"


def test_the_full_name_wins_the_row_even_when_the_short_one_is_seen_first():
    """Ordering inside the table is not a promise, so the display name
    cannot depend on which feed was ingested first."""
    for order in (0, 1):
        rows = [("K.Nacua", "", "xfp", 19.0, "g1"),
                ("Kolby Nacua", "WR", "rec_yds", 110, "g1")]
        conn = _logs(*(rows if order else rows[::-1]))
        assert _flat(conn) == [("WR", "Kolby Nacua")], order


def test_the_folded_player_keeps_both_feeds_numbers():
    """The point of folding is that the row gets RICHER, not that a
    column is thrown away."""
    conn = _logs(("Kyren Williams", "RB", "rush_yds", 90, "g1"),
                 ("K.Williams", "", "rz_car", 3, "g1"))
    got = {st["market"] for st in _who(conn, "Kyren Williams")["stats"]}
    assert got == {"rush_yds", "rz_car"}, got


def test_two_players_who_share_an_initial_and_a_surname_stay_apart():
    """The join key is deliberately loose. It must not be so loose that
    it merges two real people — 2025 logged two ('d','moore')."""
    conn = _logs(("Devin Moore", "WR", "rec_yds", 40, "g1"),
                 ("Dennis Moore", "WR", "rec_yds", 80, "g1"))
    assert sorted(p for _pos, p in _flat(conn)) == ["Dennis Moore",
                                                    "Devin Moore"]


def test_an_abbreviation_that_could_be_two_men_attaches_to_neither():
    """The refusal. With a Devin AND a Dennis Moore on the roster,
    "D.Moore" names nobody, and attaching his snaps to whichever came
    back first would be a coin toss printed as a fact — the same refusal
    `sources.livescores.ingest_finals` makes about an ambiguous
    fixture."""
    conn = _logs(("Devin Moore", "WR", "rec_yds", 40, "g1"),
                 ("Dennis Moore", "WR", "rec_yds", 80, "g1"),
                 ("D.Moore", "", "xfp", 12.0, "g1"))
    assert sorted(p for _pos, p in _flat(conn)) == [
        "D.Moore", "Dennis Moore", "Devin Moore"], _flat(conn)
    for name in ("Devin Moore", "Dennis Moore"):
        assert {st["market"] for st in _who(conn, name)["stats"]} == {"rec_yds"}, \
            f"{name} was handed somebody else's snaps"


def test_a_player_who_joins_nothing_keeps_his_own_row():
    """College box scores carry no position when the roster lookup
    misses. Dropping the unjoined would delete real players, so the rule
    folds rather than filters."""
    conn = _logs(("Someone Nobodyknows", "", "rush_yds", 30, "g1"))
    assert _flat(conn) == [("—", "Someone Nobodyknows")]


# --- two: a rate is not a total ---------------------------------------------
def test_a_snap_share_carries_no_total():
    conn = _logs(("Nick Vannett", "TE", "snap_pct", 0.04, "g1"),
                 ("Nick Vannett", "TE", "snap_pct", 0.06, "g2"))
    st = _who(conn, "Nick Vannett")["stats"][0]
    assert st["market"] == "snap_pct"
    assert st["rate"] is True
    assert st["total"] is None, "seven games of snap share summed to a number"
    assert st["per_game"] == 0.05, st


def test_a_counting_market_still_carries_one():
    conn = _logs(("Kyren Williams", "RB", "rush_yds", 90, "g1"),
                 ("Kyren Williams", "RB", "rush_yds", 70, "g2"))
    st = _who(conn, "Kyren Williams")["stats"][0]
    assert st["rate"] is False and st["total"] == 160.0 and st["per_game"] == 80.0


def test_a_rate_never_leads_a_row_that_has_a_real_number_on_it():
    """A tight end is read by his receiving yards, not by his snap
    share, however the alphabet or the totals happen to fall."""
    conn = _logs(("Tyler Higbee", "TE", "snap_pct", 0.8, "g1"),
                 ("Tyler Higbee", "TE", "rec_yds", 28.1, "g1"))
    assert _who(conn, "Tyler Higbee")["lead_market"] == "rec_yds"


def test_the_same_is_true_where_the_table_has_never_seen_the_position():
    """The branch above only runs for a position `LEAD_MARKET` knows.
    Everyone else falls through to "his own biggest number", and a rate
    has no size to be biggest — 0.8 of a snap share is not more than
    28.1 yards, it is a different kind of thing."""
    conn = _logs(("Utility Man", "LS", "snap_pct", 0.8, "g1"),
                 ("Utility Man", "LS", "rec_yds", 28.1, "g1"))
    assert _who(conn, "Utility Man")["lead_market"] == "rec_yds"


def test_a_rate_leads_when_it_is_all_he_has():
    """Not a filter. A man whose only logged fact is his snap share
    still appears, showing the one thing that is true of him."""
    conn = _logs(("Deep Reserve", "TE", "snap_pct", 0.04, "g1"))
    assert _who(conn, "Deep Reserve")["lead_market"] == "snap_pct"


def test_the_page_prints_a_rate_as_a_percentage_and_never_as_a_total():
    i = APP.index("function teamSquadHTML(")
    block = APP[i:APP.index("\nfunction ", i + 1)]
    assert "st.rate" in block, "the page still prints every stat one way"
    assert "Math.round(st.per_game * 100)" in block
    tot = block.index("total</span>")
    assert "st.rate" in block[:tot], \
        "the total branch is not behind the rate check"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
