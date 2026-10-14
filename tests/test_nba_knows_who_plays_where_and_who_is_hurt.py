"""The NBA board knows who plays where tonight, and who is hurt.

Ethan, 2026-10-13: "We worked so hard on nfl so ik CFB and mlb and nba
and ufc is missing stuff." Two things the NFL board has had for weeks
that the basketball build never did, a week before opening night:

  * WHERE HE PLAYS NOW. The logs file a man under the club he played for,
    so every summer move was still under his old team: projected for a
    game he is not in, and — because the prop named no team — priced off
    whichever game the book named him in. ESPN's current rosters (the
    Rosters page's own feed) now place each man before his logs are read,
    a man the roster places keeps only his games for that club, and the
    prop carries its team so `oddsapi._wrong_game` refuses a price from
    another game.
  * WHO IS HURT. ESPN's injury board, fetched for the Injuries page all
    along and read by no build ("the one gap worth money",
    docs/WNBA_MODEL.md). Ruled out is a grade-D restriction with the reason
    on the card; listed and playable is held until the lineup confirms,
    on the Edge board and on Most Likely. A teammate's card says who is
    out and what the logs show when he sat — evidence only, the number
    does not move.

Run directly: `python3 tests/test_nba_knows_who_plays_where_and_who_is_hurt.py`
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import nba_build                                        # noqa: E402
from engine import db as D                              # noqa: E402


def _logs(player, team, dates, season=2025, sport="nba", mins=30.0, pts=20.0):
    out = []
    for i, d in enumerate(dates):
        for m, v in (("min", mins), ("pts", pts), ("reb", 5.0), ("ast", 4.0), ("fg3m", 2.0)):
            out.append({"sport": sport, "season": season, "period": d,
                        "game_id": f"{team}{d}", "player": player, "team": team,
                        "opponent": "OPP", "position": "S", "home": 1,
                        "market": m, "value": v})
    return out


DATES = [f"2026-03-{d:02d}" for d in range(1, 9)]


def _conn(rows):
    conn = D.connect(":memory:")
    D.upsert_player_logs(conn, rows)
    return conn


# --- where he plays now --------------------------------------------------
def test_a_summer_move_leaves_his_old_club_and_waits_for_three_games_with_the_new_one():
    conn = _conn(_logs("Mover", "MIA", DATES) + _logs("Stayer", "MIA", DATES)
                 + _logs("Unlisted", "MIA", DATES))
    roster = {"mover": "BOS", "stayer": "MIA"}
    moved: set = set()
    hist = nba_build.player_history(conn, {"MIA", "BOS"}, seasons=[2026, 2025],
                                    roster=roster, moved=moved)
    # His games for Miami are not Boston's form, and he has none for Boston.
    assert "Mover" not in hist and moved == {"Mover"}
    assert hist["Stayer"]["team"] == "MIA" and len(hist["Stayer"]["minutes"]) == 8
    # A name the roster does not carry keeps his history's team: a spelling
    # the two feeds disagree on must never cost a man his board.
    assert hist["Unlisted"]["team"] == "MIA"
    # Without a roster the board is exactly what it was.
    old = nba_build.player_history(conn, {"MIA", "BOS"}, seasons=[2026, 2025])
    assert old["Mover"]["team"] == "MIA"


def test_once_he_has_played_for_the_new_club_only_those_games_are_his_form():
    rows = (_logs("Mover", "MIA", DATES[:5], pts=10.0)
            + _logs("Mover", "BOS", ["2026-03-20", "2026-03-22", "2026-03-24"], pts=30.0))
    hist = nba_build.player_history(_conn(rows), {"MIA", "BOS"}, seasons=[2026, 2025],
                                    roster={"mover": "BOS"})
    h = hist["Mover"]
    assert h["team"] == "BOS"
    assert h["pts"] == [30.0, 30.0, 30.0] and h["dates"][0] == "2026-03-24"


def test_a_man_whose_new_club_is_idle_tonight_is_not_on_his_old_clubs_board():
    hist = nba_build.player_history(_conn(_logs("Mover", "MIA", DATES)), {"MIA", "NYK"},
                                    seasons=[2026, 2025], roster={"mover": "LAL"})
    assert hist == {}


def test_the_wnba_feeds_spellings_meet_on_the_leagues_own_codes():
    rows = _logs("A'ja Wilson", "LV", DATES, season=2026, sport="wnba")
    hist = nba_build.player_history(_conn(rows), {"LV", "NY"}, sport="wnba",
                                    seasons=[2026], roster={"aja wilson": "LVA"})
    assert hist["A'ja Wilson"]["team"] == "LV"


def test_current_teams_reads_the_rosters_and_drops_a_name_on_two_of_them():
    feed = {"LV": [{"player": "A’ja Wilson"}],
            "NY": [{"player": "Breanna Stewart"}, {"player": "Same Name"}],
            "LA": [{"player": "Same Name"}]}
    teams, missed = nba_build.current_teams("wnba", fetch=lambda: (feed, ["CON"]))
    assert teams == {"aja wilson": "LVA", "breanna stewart": "NYL"}
    assert missed == ["CON"]
    # A club code the league's map does not hold moves nobody: one alias
    # the feeds disagree on would otherwise empty a whole club's board.
    odd, _ = nba_build.current_teams("nba", fetch=lambda: ({"XYZ": [{"player": "Some Guard"}],
                                                            "GS": [{"player": "Splash"}]}, []))
    assert odd == {"splash": "GSW"}

    def dark():
        raise RuntimeError("espn 403")
    assert nba_build.current_teams("nba", fetch=dark) == ({}, [])


def test_the_prop_names_its_team_so_a_price_from_another_game_is_refused():
    from engine.sources.oddsapi import _wrong_game
    prop = nba_build._Prop("Mover", "pts", "MIA")
    assert prop.team == "MIA"
    assert _wrong_game(prop, ("BOS", "NYK")) is True
    assert _wrong_game(prop, ("MIA", "BOS")) is False
    assert _wrong_game(nba_build._Prop("Mover", "pts"), ("BOS", "NYK")) is False


# --- who is hurt ------------------------------------------------------------
def _espn_injuries():
    def item(name, status, date, detail="Ankle"):
        return {"athlete": {"displayName": name}, "status": status, "date": date,
                "details": {"type": detail} if detail else {}}
    return {"injuries": [{"displayName": "Boston Celtics", "injuries": [
        item("Star Wing", "Out", "2026-10-01T00:00Z"),
        item("Star Wing", "Day-To-Day", "2026-10-12T00:00Z"),
        item("Big Man", "Out", "2026-10-12T00:00Z", "Knee"),
        item("Healthy Guard", "Active", "2026-01-01T00:00Z", None),
    ]}]}


def test_the_injury_board_is_read_newest_filing_first_and_cleared_notices_are_not_injuries():
    inj = nba_build.hoops_injuries("nba", fetch=_espn_injuries)
    assert inj["star wing"]["status"] == "Day-To-Day"
    assert inj["big man"]["status"] == "Out" and inj["big man"]["injury"] == "Knee"
    assert "healthy guard" not in inj

    def dark():
        raise RuntimeError("espn 403")
    assert nba_build.hoops_injuries("nba", fetch=dark) == {}


def _prop(**kw):
    p = {"player": "Star Wing", "team": "BOS", "opponent": "MIA", "market": "pts",
         "line": 20.5, "over_odds": -110, "under_odds": -110, "book": "fanduel",
         "minutes": [34.0] * 12, "values": [21.5] * 12, "is_starter": True,
         "spread": -2.0, "is_favorite": True, "rest": "1day", "freshness": 0.9}
    p.update(kw)
    return p


def test_a_listed_player_is_held_and_a_ruled_out_one_is_grade_d_with_the_reason():
    from engine.nba.pipeline import evaluate_prop
    clean = evaluate_prop(_prop())
    held = evaluate_prop(_prop(injury_status="Day-To-Day"))
    out = evaluate_prop(_prop(injury_status="Out", restriction=True))
    assert not any("listed" in f for f in clean.get("fails", []))
    assert held["kind"] == "near_miss"
    assert "listed Day-To-Day — held until the lineup confirms" in held["fails"]
    # The number stands: a designation holds the bet, it does not move it.
    assert held["projection"] == clean["projection"]
    assert out["kind"] == "near_miss" and out["minutes_grade"] == "D"
    assert "listed Out — not expected to play" in out["fails"]


def test_the_designation_rides_to_most_likely_which_holds_it():
    from engine import likely
    from engine.nba.pipeline import shared_recommendations
    recs = shared_recommendations([_prop(injury_status="Day-To-Day"), _prop(player="Other")])
    by = {r["player"]: r for r in recs}
    assert by["Star Wing"]["injury_status"] == "Day-To-Day"
    assert by["Other"]["injury_status"] == ""
    row = {"model_prob": 0.6, "implied_prob": 0.58, "odds": -130, "book": "fanduel",
           "raw_prob": 0.6, "market_prob": 0.58, "injury_status": "Day-To-Day"}
    assert likely.admissible(row).startswith("listed Day-To-Day")


def _team_hist():
    """Boston's last ten games: the star missed four of them, and the wing's
    share of the points rose in those four."""
    dates = [f"2026-02-{d:02d}" for d in range(10, 20)]
    sat = set(dates[2:6])
    hist = {}

    def add(name, by):
        hist[name] = {"team": "BOS", "starter": True, "by_week": by,
                      "minutes": [by[d].get("min", 0.0) for d in sorted(by, reverse=True)][:20]}
    add("Star", {d: {"min": 34.0, "pts": 30.0} for d in dates if d not in sat})
    add("Wing", {d: {"min": 30.0, "pts": 26.0 if d in sat else 16.0} for d in dates})
    add("Big", {d: {"min": 28.0, "pts": 14.0} for d in dates})
    return hist


def test_a_teammates_card_says_who_is_out_and_what_the_logs_show_when_he_sat():
    hist = _team_hist()
    injuries = {"star": {"player": "Star", "status": "Out", "injury": "Knee"}}
    gone = nba_build.absences(hist, injuries)
    assert [n for n, _m in gone["BOS"]] == ["Star"]
    note = nba_build.lineup_note("Wing", "pts", "BOS", gone, hist)
    assert note.startswith("Out tonight: Star (34 min a game).")
    assert "does not move for it" in note
    # 16/(30+16+14) = 27% with him, 26/(26+14) = 65% without, over 4 and 6.
    assert "In the 4 games Star missed, Wing took 65% of the team's points, against 27%" in note
    # The man who is out gets no note about himself; a market the on/off
    # module does not count gets the names without numbers.
    assert nba_build.lineup_note("Star", "pts", "BOS", gone, hist) == ""
    pra = nba_build.lineup_note("Wing", "pra", "BOS", gone, hist)
    assert pra.startswith("Out tonight: Star") and "In the" not in pra
    assert nba_build.lineup_note("Wing", "pts", "MIA", gone, hist) == ""


def test_a_man_out_for_weeks_is_already_in_his_teammates_games_and_is_not_news():
    hist = _team_hist()
    # His last game was the club's fourth-newest: three games already played
    # without him are in every teammate's form.
    hist["Star"]["by_week"] = {d: v for d, v in hist["Star"]["by_week"].items()
                               if d <= "2026-02-16"}
    out = {"star": {"player": "Star", "status": "Out", "injury": "Knee"}}
    assert nba_build.absences(hist, out) == {}
    hist["Star"]["by_week"]["2026-02-17"] = {"min": 30.0, "pts": 20.0}
    assert [n for n, _m in nba_build.absences(hist, out)["BOS"]] == ["Star"]


def test_games_before_the_absent_man_arrived_are_not_games_he_sat():
    hist = _team_hist()
    # He joined after the first five dates: the four early "misses" were
    # games he was not on the team for, so only the one he sat since counts.
    hist["Star"]["by_week"] = {d: v for d, v in hist["Star"]["by_week"].items()
                               if d >= "2026-02-16"}
    gone = nba_build.absences(hist, {"star": {"player": "Star", "status": "Out", "injury": ""}})
    note = nba_build.lineup_note("Wing", "pts", "BOS", gone, hist)
    assert "In the" not in note, note


# --- the whole build, through main() ---------------------------------------
def _run_build(tmp, rows, roster, injuries, captured):
    import datetime
    from engine import gate as _gate, ledger as _ledger
    from engine.models import SportsbookLine
    from engine.sources import espnhoops, oddsapi

    date = "2026-08-31"
    path = os.path.join(tmp, "history.db")
    c = D.connect(path)
    D.upsert_player_logs(c, rows)
    c.commit()
    c.close()

    def scoreboard(day, ttl=None, league="wnba"):
        if str(day)[:10] != date:
            return {"events": []}
        return {"events": [{"id": "401", "date": f"{date}T23:00Z", "competitions": [{
            "competitors": [
                {"homeAway": "home", "score": "0",
                 "team": {"abbreviation": "LV", "displayName": "Las Vegas Aces"}},
                {"homeAway": "away", "score": "0",
                 "team": {"abbreviation": "NY", "displayName": "New York Liberty"}}],
            "status": {"type": {"state": "pre", "completed": False}}}]}]}

    class Res:
        matched, events_used, from_cache, cache_misses, wrong_game = 0, 1, True, 0, 1
        dropped_events: list = []

    def attach(slate, sport="nba", cache_only=False, **kw):
        res = Res()
        for pr in slate.props:
            captured.append((pr.player, pr.market, pr.team))
            pr.lines = [SportsbookLine(book="fanduel", line=12.5, over_odds=-110,
                                       under_odds=-110)]
            res.matched += 1
        return res

    def plain_publish(payload, out_path, name=""):
        with open(out_path, "w") as f:
            json.dump(payload, f)
        return str(out_path), str(out_path)

    real_connect, real_lconnect = D.connect, _ledger.connect
    patches = [
        (espnhoops, "fetch_scoreboard", scoreboard),
        (nba_build, "connect", lambda *a, **k: real_connect(path)),
        (D, "connect", lambda *a, **k: real_connect(path)),
        (_ledger, "connect", lambda p=None: real_lconnect(":memory:")),
        (_ledger, "export_json", lambda *a, **k: None),
        (_gate, "publish", plain_publish),
        (oddsapi, "apply_odds_to_slate", attach),
        (nba_build, "current_teams", lambda league, fetch=None: (roster, [])),
        (nba_build, "hoops_injuries", lambda league, fetch=None: injuries),
    ]
    saved = [(m, n, getattr(m, n)) for m, n, _ in patches]
    out_path = os.path.join(tmp, "wnba.json")
    argv = sys.argv
    sys.argv = ["nba_build.py", date, "--league", "wnba", "--cached-odds", "--out", out_path]
    try:
        for m, n, v in patches:
            setattr(m, n, v)
        nba_build.main()
    finally:
        sys.argv = argv
        for m, n, v in saved:
            setattr(m, n, v)
    assert datetime.date.fromisoformat(date)
    with open(out_path) as f:
        return json.load(f)


def test_the_build_places_movers_names_the_team_on_every_prop_and_holds_the_listed():
    dates = [f"2026-08-{d:02d}" for d in range(10, 20)]
    rows = (_logs("Lv Star", "LV", dates, season=2026, sport="wnba", pts=14.0)
            + _logs("Lv Wing", "LV", dates, season=2026, sport="wnba", pts=13.0)
            + _logs("Hurt Guard", "LV", dates, season=2026, sport="wnba", pts=12.0)
            + _logs("Ny Guard", "NY", dates, season=2026, sport="wnba", pts=13.0)
            + _logs("Mover", "NY", dates, season=2026, sport="wnba", pts=15.0))
    roster = {"lv star": "LVA", "lv wing": "LVA", "hurt guard": "LVA", "ny guard": "NYL",
              "mover": "LVA"}
    injuries = {"lv wing": {"player": "Lv Wing", "status": "Day-To-Day", "injury": "Ankle"},
                "hurt guard": {"player": "Hurt Guard", "status": "Out", "injury": "Knee"}}
    tmp = tempfile.mkdtemp()
    captured: list = []
    try:
        board = _run_build(tmp, rows, roster, injuries, captured)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    teams = {p: t for p, _m, t in captured}
    assert teams == {"Lv Star": "LV", "Lv Wing": "LV", "Hurt Guard": "LV", "Ny Guard": "NY"}
    av = board["availability"]
    assert av["moved"] == ["Mover"] and av["listed"] == 2 and av["out"] == 1
    assert av["rosters_read"] and av["injuries_read"]
    assert "from a game the player's team is not in, refused" in board["meta"]["odds"]
    recs = board["recommendations"]
    for r in recs:
        if r["player"] == "Lv Wing":
            assert r["injury_status"] == "Day-To-Day" and not r["recommended"]
        if r["player"] == "Hurt Guard":
            assert r["injury_status"] == "Out" and not r["recommended"]
    assert not any(r.get("player") in ("Lv Wing", "Hurt Guard")
                   for r in board.get("most_likely") or [])
    # The out guard's teammates are told on their cards — the teammate card
    # every league's pick draws, since 2026-10-14 — he is not told about
    # himself, and the other club hears nothing.
    told = {r["player"] for r in recs
            if "Out tonight: Hurt Guard" in ((r.get("mate_card") or {}).get("headline") or "")}
    assert not any("Out tonight" in x for r in recs for x in r.get("reasons") or []), "said once, on the card"
    assert told and told <= {"Lv Star", "Lv Wing"}, told
    assert "Ny Guard" not in told and "Hurt Guard" not in told


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
