"""A closing line is never another player's quotes.

Ethan's NFL close-line repair, 6 November: A.J. Brown and Amon-Ra St. Brown
played different games in Week 1, and the dry run showed both at the same
four books on the same four numbers (BetMGM 63.5, DraftKings 61.5, FanDuel
59.5, Hard Rock 62.5), both "closing" at 62.0. Their settled closes had
been 64.5 (A.J. Brown) and 78.5 (St. Brown).

How. From 22 August the odds adapter fell back to a first initial and a
surname ("a brown", both men) when a player's own quotes were missing from
a pull, and until 15 September nothing checked the price came from his own
game. A.J. Brown played the season's opener on Wednesday 9 September; on
the Sunday his quotes were long gone, and the 17:30 UTC pull handed his
prop St. Brown's. The snapshot writer recorded them under both names, from
the same pull at the same instant, and the repair, reading the whole week
latest day first, took that copy for A.J. Brown's close. The owner rule's
dry run on the box put him back at his own 64.5 (`_the_real_week1`). What
these hold:

  * a quote set filed under two players who share a first initial and a
    surname, at one instant in one market, is the close only of the man it
    belongs to: his own reads either side of it say which, the nearest
    (St. Brown's own reads that Sunday, against A.J. Brown's own 64.5 from
    before his Wednesday game), and every reader leaves it out for the
    others, and only that (a different set, a different instant, or two
    players whose keys differ are left alone);
  * when no read can say whose it was, a man whose own reads sit plainly
    elsewhere still loses it and the rest keep it: taking it from every
    name would clear the real close of the man the books priced;
  * the readers see a copy whole even when the man copied from holds no
    bet (his rows are streamed beside the bettor's);
  * the repair reads the day the player played, as settling does, re-reads
    a close that was a copy from the player's own quotes, and clears it when
    he has none (its old value came from the same copy);
  * the dry run names the read it left out and whose name it was filed under;
  * the adapter's fallback fires only when the key is one man's on the slate
    too, and only from a game the prop's team is proven to be in.

Run directly: `python3 tests/test_a_close_is_never_another_players_quotes.py`
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import db, ledger, linemoves                             # noqa: E402
from engine.sources import oddsapi as oa                             # noqa: E402
from engine.sources.oddsapi import normalize_name                    # noqa: E402

#: 2026-09-13 17:30 UTC, Week 1's Sunday: the read that was copied.
T = dt.datetime(2026, 9, 13, 17, 30, tzinfo=dt.timezone.utc).timestamp()
AJ, ARSB, AMARI = "A.J. Brown", "Amon-Ra St. Brown", "Amari Brown"
COPY = (("BetMGM", 63.5, -115, -105), ("DraftKings", 61.5, -110, -110),
        ("FanDuel", 59.5, -112, -108), ("Hard Rock", 62.5, -115, -105))


def _rows(player, quotes, ts, start, market="rec_yds"):
    return [{"ts": ts, "player": player, "market": market, "book": b, "line": ln,
             "over_odds": o, "under_odds": u, "start_ts": start} for b, ln, o, u in quotes]


def _week1():
    """THE MIRROR IMAGE of the real Week 1 (`_the_real_week1`, below), kept
    to pin the rule the other way round: here A.J. Brown is the man the
    books quoted at 17:30 UTC (his game at 4:25 p.m. Eastern), and St. Brown
    (his game that night) and an unpriced third "a brown" are the men his
    quotes were handed to; each man's own earlier read sits before it. In
    the real week the roles ran the other way."""
    aj_start, arsb_start = T + 3 * 3600 - 300, T + 7 * 3600
    return (_rows(AJ, (("DraftKings", 62.5, -110, -110), ("FanDuel", 62.5, -115, -105)), T - 3600, aj_start)
            + _rows(AJ, COPY, T, aj_start)
            + _rows(ARSB, (("DraftKings", 78.5, -110, -110), ("FanDuel", 78.5, -112, -108)),
                    T - 7200, arsb_start)
            + _rows(ARSB, COPY, T, arsb_start)
            + _rows(AMARI, COPY, T, arsb_start))


def test_the_owner_keeps_his_quotes_and_the_men_they_were_copied_to_lose_them():
    idx = linemoves.closing_lines_by_date(_week1())
    aj, arsb, amari = normalize_name(AJ), normalize_name(ARSB), normalize_name(AMARI)
    # A.J. Brown's own read an hour before (62.5) sits by the 17:30 set
    # (62.0): the set is his, and his close. St. Brown's own read (78.5)
    # sits far off: his close is that read of his own.
    assert idx[(aj, "rec_yds", "2026-09-13")] == 62.0, dict(idx)
    assert idx[(arsb, "rec_yds", "2026-09-13")] == 78.5, dict(idx)
    # What an unchecked reader banked from the copy is kept for the repair
    # (the 6 November dry run's 62.0), for the men it was copied to only.
    day = "2026-09-13"
    assert idx.copied == {(arsb, "rec_yds", day): 62.0, (amari, "rec_yds", day): 62.0}, idx.copied
    assert idx.twins[(arsb, "rec_yds", T)] == (aj, amari), "the others, sorted"
    assert (aj, "rec_yds", T) not in idx.twins, "never left out for the man whose quotes they were"
    # Amari Brown's only read was the copy: no close at all.
    assert (amari, "rec_yds", day) not in idx


def test_a_copy_no_read_can_place_stays_with_the_men_it_might_be():
    """OKC's Jalen and Jaylin Williams ("j williams"), one game: if the books
    never quoted the bench man, every read of both is one set and nothing
    says whose. Neither loses it, since taking it from both would clear the
    real close of the man the books priced. A third "j williams" whose own
    read sits far off (9.5) still loses it. Twins whose own reads sit as
    near (14.5 each) keep it too."""
    start, day = T + 6 * 3600, "2026-09-13"
    q = (("DraftKings", 22.5, -115, -105), ("FanDuel", 22.5, -110, -110))
    jalen, jaylin, jeremy = "Jalen Williams", "Jaylin Williams", "Jeremy Williams"
    rows = _rows(jeremy, (("DraftKings", 9.5, -110, -110),), T - 5 * 3600, start, market="pts")
    for k in range(1, 5):
        for who in (jalen, jaylin, jeremy):
            rows += _rows(who, q, T - k * 3600, start, market="pts")
    idx = linemoves.closing_lines_by_date(rows)
    nj, ny, nr = normalize_name(jalen), normalize_name(jaylin), normalize_name(jeremy)
    assert idx[(nj, "pts", day)] == 22.5 and idx[(ny, "pts", day)] == 22.5, dict(idx)
    assert {k[0] for k in idx.twins} == {nr}, idx.twins
    assert idx[(nr, "pts", day)] == 9.5, "his own read, the sets that were not his left out"
    twins = ("Amen Thompson", "Ausar Thompson")
    rows = []
    for who in twins:
        rows += _rows(who, (("DraftKings", 14.5, -110, -110),), T - 7200, start, market="pts")
        rows += _rows(who, q, T - 3600, start, market="pts")
    assert not linemoves.closing_lines_by_date(rows).twins, "two as near: the rows cannot say"


def test_a_copy_before_either_mans_own_read_waits_for_the_next():
    aj_start, arsb_start = T + 3 * 3600, T + 7 * 3600
    rows = (_rows(AJ, COPY, T - 7200, aj_start) + _rows(ARSB, COPY, T - 7200, arsb_start)
            + _rows(AJ, (("DraftKings", 62.5, -110, -110),), T - 3600, aj_start)
            + _rows(ARSB, (("DraftKings", 78.5, -110, -110),), T - 3600, arsb_start))
    twins = linemoves.closing_lines_by_date(rows).twins
    assert set(twins) == {(normalize_name(ARSB), "rec_yds", T - 7200)}, twins


def test_a_half_point_line_is_told_apart_by_its_price():
    # An anytime touchdown is 0.5 for everyone: A.J. Brown's own +150
    # against Amari Brown's own +600, and the copied set at +155.
    m, start = "anytime_td", T + 7200
    rows = (_rows(AJ, (("DraftKings", 0.5, 150, -190),), T - 3600, start, market=m)
            + _rows(AMARI, (("DraftKings", 0.5, 600, -1000),), T - 3600, start, market=m)
            + _rows(AJ, (("DraftKings", 0.5, 155, -195),), T, start, market=m)
            + _rows(AMARI, (("DraftKings", 0.5, 155, -195),), T, start, market=m))
    odds = linemoves.closing_odds_by_date(rows)
    assert set(odds.twins) == {(normalize_name(AMARI), m, T)}, odds.twins


def test_what_is_not_a_copy_is_left_alone():
    start = T + 7200
    # Same instant, same loose key, different quotes: two real prices.
    rows = _rows(AJ, COPY, T, start) + _rows(ARSB, COPY[:3], T, start)
    assert not linemoves.closing_lines_by_date(rows).twins
    # Same quotes, different instants: a line that did not move.
    rows = _rows(AJ, COPY, T, start) + _rows(ARSB, COPY, T - 60, start)
    assert not linemoves.closing_lines_by_date(rows).twins
    # Same quotes, same instant, keys that differ ("p nacua", "a brown"):
    # the adapter never joins those, so they are two players' own numbers.
    rows = _rows("Puka Nacua", COPY, T, start) + _rows(ARSB, COPY, T, start)
    assert not linemoves.closing_lines_by_date(rows).twins
    # And the price reader leaves out the same copy the line reader does.
    odds = linemoves.closing_odds_by_date(_week1())
    assert not any(k[0] == normalize_name(AMARI) for k in odds), dict(odds)
    assert (normalize_name(AJ), "rec_yds", "2026-09-13", 62.5) in odds
    assert (normalize_name(ARSB), "rec_yds", T) in odds.twins and \
        (normalize_name(AJ), "rec_yds", T) not in odds.twins, "placed as the line reader places it"


def test_copies_are_judged_a_pull_at_a_time():
    """For the box's memory: each pull is judged when the stream moves past
    it and forgotten, a few held open at once because two builds can append
    to the file together, and a copy is found all the same."""
    c = linemoves._Copies()
    aj, arsb, puka = normalize_name(AJ), normalize_name(ARSB), normalize_name("Puka Nacua")
    # A.J. Brown's own read first: the forty copies after it are his.
    for b, ln, o, u in COPY[:2]:
        c.add(aj, {"ts": T - 600, "market": "rec_yds", "book": b, "line": ln,
                   "over_odds": o, "under_odds": u})
    for i in range(40):
        for name in (aj, arsb):
            for b, ln, o, u in COPY[:2]:
                c.add(name, {"ts": T + i, "market": "rec_yds", "book": b, "line": ln,
                             "over_odds": o, "under_odds": u})
        # Another build's pull, interleaved with this one's.
        c.add(puka, {"ts": T + 5000 + i, "market": "rec_yds", "book": "FanDuel", "line": 70.5,
                     "over_odds": -110, "under_odds": -110})
        assert len(c._open) <= c.KEEP + 1, len(c._open)
    got = c.found()
    assert all((arsb, "rec_yds", T + i) in got for i in range(40)), "each left out for the man it went to"
    assert not any(k[0] == aj for k in got), "and never for the man whose quotes they were"
    assert not any(k[0] == puka for k in got), "a pull with one name in it holds no copy"
    assert c._open == {}, "everything judged and let go"
    assert len(c._last) == 2, "one read of his own kept per name and market, not every pull"


def test_copies_no_read_can_place_are_held_only_so_many_at_once():
    """A pair the rows can never place (every read of both one set) waits
    for a read that never comes; past ``WAITING`` the oldest half is judged
    on what has been read, so a season of pulls cannot pile up."""
    c = linemoves._Copies()
    c.WAITING = 6
    jalen, jaylin = normalize_name("Jalen Williams"), normalize_name("Jaylin Williams")
    for i in range(60):
        for name in (jalen, jaylin):
            c.add(name, {"ts": T + i, "market": "pts", "book": "DraftKings", "line": 22.5,
                         "over_odds": -110, "under_odds": -110})
        assert len(c._waiting) <= c.WAITING, len(c._waiting)
    assert c.found() == {}, "neither name loses a read nothing can place"
    assert c._waiting == []


def _file(rows):
    p = Path(tempfile.mkdtemp()) / "line_history.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def test_the_readers_see_a_copy_whole_when_the_man_copied_from_holds_no_bet():
    p = _file(_week1())
    want = {(normalize_name(ARSB), "rec_yds")}
    plain = {r["player"] for r in ledger._wanted_rows(linemoves.stream_wanted(want, p), want)}
    kin = {r["player"] for r in ledger._wanted_rows(linemoves.stream_wanted(want, p, siblings=True), want,
                                                    siblings=True)}
    assert plain == {ARSB}, "without siblings the filter is exactly what it was"
    assert kin == {AJ, ARSB, AMARI}, kin
    saved = linemoves.HISTORY_PATH
    linemoves.HISTORY_PATH = p
    try:
        idx = ledger._snapshot_closes(want)
    finally:
        linemoves.HISTORY_PATH = saved
    assert idx[(normalize_name(ARSB), "rec_yds", "2026-09-13")] == 78.5
    assert idx.copied, "the copy was seen though A.J. Brown holds no bet"


def _journal_and_history(bets, games=None, logs=None):
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    for player, team, line, close in bets:
        L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
                  "stake_units, stake_dollars, status, category, team, book, actual, pnl_units, "
                  "closing_line) VALUES ('2026-09-10T12:00:00', 'nfl', '2026-W01', NULL, ?, 'rec_yds', "
                  "'OVER', ?, -110, 1, 10, 'won', 'likely', ?, 'DraftKings', 90, 0.91, ?)",
                  (player, line, team, close))
    L.commit()
    H = db.connect(t / "h.db")
    H.executemany("INSERT INTO games (sport, season, period, game_id, home, away, date) VALUES "
                  "('nfl', 2026, '001', ?, ?, ?, ?)",
                  games or [("g1", "PHI", "DAL", "2026-09-13"), ("g2", "DET", "CHI", "2026-09-13"),
                            ("g3", "NYG", "WAS", "2026-09-13"), ("g4", "MIN", "ATL", "2026-09-14")])
    H.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES ('nfl', 2026, '001', ?, ?, ?, ?, 'WR', 1, "
                  "'rec_yds', 90)",
                  logs or [("g1", AJ, "PHI", "DAL"), ("g2", ARSB, "DET", "CHI"), ("g3", AMARI, "NYG", "WAS")])
    H.commit()
    return L, H


def test_the_repair_rereads_a_copied_close_and_clears_one_with_nothing_of_its_own():
    # What the 6 November write banked: the copy's 62.0 for all three men.
    L, H = _journal_and_history([(AJ, "PHI", 59.5, 62.0), (ARSB, "DET", 77.5, 62.0),
                                 (AMARI, "NYG", 39.5, 62.0)])
    p = _file(_week1())
    saved = linemoves.HISTORY_PATH
    linemoves.HISTORY_PATH = p
    try:
        dry = ledger.repair_closing_lines(L, apply=False, hist_conn=H, sport="nfl")
        # In the mirror, A.J. Brown's 62.0 was his own quotes: it stands.
        assert (dry["copied"], dry["cleared"], dry["agreed"]) == (1, 1, 1), dry
        assert dry["settled"] == sum(dry[k] for k in ("agreed", "overwritten", "filled", "unchecked",
                                                      "game_lines", "never", "copied", "cleared")), dry
        got = {row[1]: row[-1] for row in dry["copied_sample"]}
        assert got == {ARSB: 78.5, AMARI: None}, got
        why = dict(zip((row[1] for row in dry["copied_sample"]), dry["copied_why"]))
        assert "Amari Brown" in why[ARSB] and "A J Brown" in why[ARSB] and "left out" in why[ARSB], why[ARSB]
        assert why[AMARI].startswith("snapshots: every pre-game read was another player's quotes too"), why
        assert [r[0] for r in L.execute("SELECT closing_line FROM bets ORDER BY id")] == [62.0, 62.0, 62.0], \
            "a dry run writes nothing"
        done = ledger.repair_closing_lines(L, apply=True, hist_conn=H, sport="nfl")
        assert (done["copied"], done["cleared"]) == (1, 1), done
        rows = L.execute("SELECT player, closing_line, status, pnl_units FROM bets ORDER BY id").fetchall()
        assert [(r[0], r[1]) for r in rows] == [(AJ, 62.0), (ARSB, 78.5), (AMARI, None)], rows
        assert all((r[2], r[3]) == ("won", 0.91) for r in rows), "grades and money never move"
        again = ledger.repair_closing_lines(L, apply=False, hist_conn=H, sport="nfl")
        assert (again["agreed"], again["copied"], again["cleared"], again["never"]) == (2, 0, 0, 1), again
    finally:
        linemoves.HISTORY_PATH = saved


#: THE REAL WEEK 1, as the box's dry run of 6 November and the schedule
#: tell it. A.J. Brown, traded to New England, played the season's opener at
#: Seattle on Wednesday 9 September (8:20 p.m. Eastern, 00:20 UTC on the
#: 10th); his own books' last read before it, at 21:20 UTC, put him at 64.5,
#: the close settling banked. Amon-Ra St. Brown played that Sunday. Four days
#: after A.J. Brown's game the 17:30 UTC pull of the 13th handed his prop
#: St. Brown's quotes (the "a brown" key), the file kept them under both
#: names, and the first repair (the whole week, latest day first) took them
#: for A.J. Brown's close. A.J. Brown's own 64.5 sits near enough to that
#: 62.0 to have been his, so it is St. Brown's nearer read of his own that
#: places the set: the nearest own read wins, not the first near one. The
#: books and lines of the two reads are the box's; the prices, St. Brown's
#: earlier read, his kickoff and his opponent are stand-ins.
AJ_OPENER = dt.datetime(2026, 9, 10, 0, 20, tzinfo=dt.timezone.utc).timestamp()
AJ_OWN = (("BetMGM", 65.5, -115, -105), ("DraftKings", 63.5, -110, -110), ("FanDuel", 64.5, -112, -108),
          ("Hard Rock", 65.5, -115, -105), ("theScore Bet", 64.5, -110, -110))


def _the_real_week1():
    arsb_start = T + 3 * 3600 - 300
    return (_rows(AJ, AJ_OWN, AJ_OPENER - 3 * 3600, AJ_OPENER)
            + _rows(ARSB, (("DraftKings", 61.5, -110, -110), ("FanDuel", 62.5, -112, -108)),
                    T - 3600, arsb_start)
            # The copy carries the game its price came from: St. Brown's.
            + _rows(AJ, COPY, T, arsb_start)
            + _rows(ARSB, COPY, T, arsb_start))


def test_the_real_week1_gives_aj_brown_his_own_close_back():
    """The box's dry run, 6 November: A.J. Brown's two closes 62.0 -> 64.5,
    COPIED, from his own read three hours before his Wednesday opener; St.
    Brown's 62.0 left alone, his own quotes; nothing cleared."""
    rows = _the_real_week1()
    idx = linemoves.closing_lines_by_date(rows)
    aj, arsb = normalize_name(AJ), normalize_name(ARSB)
    assert idx[(aj, "rec_yds", "2026-09-09")] == 64.5, dict(idx)
    assert idx[(arsb, "rec_yds", "2026-09-13")] == 62.0, dict(idx)
    assert (aj, "rec_yds", "2026-09-13") not in idx, "four days after his game, nothing of his own"
    assert idx.copied == {(aj, "rec_yds", "2026-09-13"): 62.0}, idx.copied
    assert idx.twins == {(aj, "rec_yds", T): (arsb,)}, idx.twins
    # The journal as the first write left it: 62.0 for both men's bets.
    L, H = _journal_and_history([(AJ, "NE", 59.5, 62.0), (ARSB, "DET", 77.5, 62.0)],
                                games=[("g0", "SEA", "NE", "2026-09-09"), ("g2", "DET", "CHI", "2026-09-13")],
                                logs=[("g0", AJ, "NE", "SEA"), ("g2", ARSB, "DET", "CHI")])
    saved = linemoves.HISTORY_PATH
    linemoves.HISTORY_PATH = _file(rows)
    try:
        dry = ledger.repair_closing_lines(L, apply=False, hist_conn=H, sport="nfl")
        assert (dry["copied"], dry["cleared"], dry["agreed"]) == (1, 0, 1), dry
        assert [(row[1], row[-1]) for row in dry["copied_sample"]] == [(AJ, 64.5)], dry["copied_sample"]
        ledger.repair_closing_lines(L, apply=True, hist_conn=H, sport="nfl")
        got = L.execute("SELECT player, closing_line FROM bets ORDER BY id").fetchall()
        assert [tuple(r) for r in got] == [(AJ, 64.5), (ARSB, 62.0)], got
    finally:
        linemoves.HISTORY_PATH = saved


def test_the_repair_reads_the_day_the_player_played_as_settling_does():
    _L, H = _journal_and_history([])
    b = {"sport": "nfl", "date": "2026-W01", "player": ARSB}
    assert ledger._week_team(H, b) == "DET"
    assert ledger.close_dates(H, b) == ["2026-09-14", "2026-09-13"], "the whole week, latest first"
    assert ledger.close_dates(H, b, "DET") == ["2026-09-13"], "the day he played"
    assert ledger._week_team(H, {"sport": "nba", "date": "2026-11-05", "player": ARSB}) is None, \
        "a daily sport's date is already the day"
    import inspect
    for fn in (ledger.repair_closing_lines, ledger.repair_closing_odds):
        assert "_week_team(hist_conn, b" in inspect.getsource(fn), fn.__name__


# --- the adapter: one man's key, and his own game ------------------------------
from engine.data_loader import Slate                                # noqa: E402
from engine.models import (DefenseProfile, Game, GameLog, Prop, REC_YDS,  # noqa: E402
                           SportsbookLine, Team, Weather)


def _book(key, title, who, pt):
    return {"key": key, "title": title, "markets": [
        {"key": "player_reception_yds", "outcomes": [
            {"name": "Over", "description": who, "price": -110, "point": pt},
            {"name": "Under", "description": who, "price": -110, "point": pt}]}]}


EVENT = {"id": "e1", "home_team": "Green Bay Packers", "away_team": "Chicago Bears",
         "bookmakers": [_book("draftkings", "DraftKings", "Jaylen Johnson", 41.5),
                        _book("fanduel", "FanDuel", "Jaylen Johnson", 42.5)]}


def _prop(who, team, opp):
    return Prop(player=who, team=team, opponent=opp, position="WR", market=REC_YDS,
                logs=[GameLog(week=w, opponent="X", value=40) for w in range(1, 6)], career_avg=40,
                vs_opponent_avg=None, lines=[SportsbookLine(book="proxy", line=40.0)], usage_role="wr2")


def _attach(props):
    teams = {"GB": Team("GB", "GB", DefenseProfile("GB")), "CHI": Team("CHI", "CHI", DefenseProfile("CHI"))}
    slate = Slate(date="2026-W02", teams=teams, props=props,
                  games=[Game(home="GB", away="CHI", weather=Weather(dome=False), spread=-2.5, total=44.0)])
    saved = (oa.list_events, oa.fetch_event_odds)
    oa.list_events = lambda key, ttl=300, sport="nfl", cache_only=False: [EVENT]
    oa.fetch_event_odds = (lambda eid, key, markets=None, books=None, ttl=300, sport="nfl", cache_only=False:
                           (EVENT, oa.Quota("491", "9")))
    try:
        return slate, oa.apply_odds_to_slate(slate, api_key="k", cache_only=True)
    finally:
        oa.list_events, oa.fetch_event_odds = saved


def test_the_fallback_needs_the_key_to_be_one_mans_on_the_slate_too():
    # Only "Jaylen Johnson" is priced. With him alone on the slate under a
    # spelling the book does not use, the fallback still recovers him...
    slate, res = _attach([_prop("Jay Johnson", "GB", "CHI")])
    assert res.loose_matched == 1 and slate.props[0].lines[0].book != "proxy", res
    # ...but with a second "j johnson" on the slate (the same game, so the
    # old game check passes), neither takes the other's price.
    slate, res = _attach([_prop("Jaylen Johnson", "GB", "CHI"), _prop("Jordan Johnson", "CHI", "GB")])
    jordan = next(p for p in slate.props if p.player == "Jordan Johnson")
    assert res.loose_matched == 0 and [ln.book for ln in jordan.lines] == ["proxy"], \
        "Jordan Johnson took Jaylen Johnson's price"


def test_the_fallback_takes_a_price_only_from_a_game_proven_to_be_the_props():
    slate, res = _attach([_prop("Jay Johnson", "", "CHI")])          # a prop that names no team
    assert res.loose_matched == 0 and res.loose_refused == 1, res
    assert [ln.book for ln in slate.props[0].lines] == ["proxy"]


def test_the_dry_run_prints_the_copies_apart():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    i = src.index("def repair_close_lines(")
    block = src[i:i + 6000]
    assert "COPIED" in block and "CLEARED" in block and 'r.get("copied_sample")' in block


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} of {len(tests)} failed.")
    sys.exit(1 if fails else 0)
