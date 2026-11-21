"""Report Picks leads with the likeliest tickets today (ZM, 20 November 2026).

Ethan, 2026-11-19: "make better picks and make better selections with the information we're given ... make
everything better". A night posts every game's two- and three-leg parlays, a fold a game, and the record says the
likeliest of them hit most (the two-leg tickets: 26 of 36 in hockey and basketball). What these hold:

  * above the games, each game still to play offers its likeliest ticket by our numbers, and the three likeliest of
    those are listed, a line each: the game and how many legs, the legs in words, our chance, the price to take it at;
  * one a game, never a started or finished game's, never a scorer pair, never a ticket our own card says to pass
    on (no book likely pays enough: `playable` false), never a ticket without legs;
  * fewer than two games to choose from is no ranking: nothing is drawn;
  * a line is a door to its game's fold (the full card lives there, drawn once), and the strip sits between the
    day's summary and the games' chips, on the members' tab only.

    python3 tests/test_report_picks_leads_with_the_likeliest_tickets.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

BOOK = __import__("test_report_bets_have_their_own_book_and_page")      # its page source, stubs and node runner
PAGE, STUBS, _node = BOOK.PAGE, BOOK.STUBS, BOOK._node
CSS = (ROOT / "web" / "css" / "reportpicks.css").read_text(encoding="utf-8")

HARNESS = STUBS + """
  const state = { sport: 'nba' };
  const teamName = (t) => ({ BOS: 'Celtics', IND: 'Pacers', NYK: 'Knicks', PHI: '76ers', LAL: 'Lakers',
                             GSW: 'Warriors', MIA: 'Heat', CHI: 'Bulls', DEN: 'Nuggets', UTA: 'Jazz' })[t] || t;
  const RES_GAME_MARKETS = new Set(["moneyline", "total", "spread", "team_total"]);
  const whenLabel = () => 'Tonight 7:30 PM';
  const gameId = (g) => `${g.date}_${g.away}@${g.home}`;
  const likelyOpen = () => '';
  const deckPickRow = (r) => `<row>${r.player}</row>`;
  const resFinal = () => null;
  const reportResults = () => null;
  const spoiledG = () => false;
"""


#: The board's own words for its market keys, as a published leg carries them (gameparlays.LEG_KEYS).
LABELS = {"reb": "Rebounds", "ast": "Assists", "fg3m": "3-Pointers Made", "stl": "Steals"}


def _leg(player, market, side, line, team="BOS"):
    return {"player": player, "team": team, "market": market, "market_label": LABELS.get(market, ""),
            "side": side, "line": line, "odds": -150, "p": 0.7}


def _board():
    two = lambda joint, legs, **kw: dict({"legs": legs, "joint": joint, "take_words": "+120", "playable": True}, **kw)  # noqa: E731
    games = [
        # Still to play, its likeliest a two-leg ticket at 58% (the three-leg one is 34%).
        {"away": "IND", "home": "BOS", "twos": [two(0.58, [_leg("Jaylen Brown", "assists", "OVER", 3.5),
                                                            _leg("Pascal Siakam", "reb", "OVER", 5.5, "IND")])],
         "threes": [two(0.34, [_leg("Jaylen Brown", "assists", "OVER", 3.5), _leg("Derrick White", "fg3m", "OVER", 1.5),
                               _leg("Andrew Nembhard", "ast", "OVER", 4.5, "IND")])]},
        # Still to play: its best a three-leg ticket at 41%.
        {"away": "MIA", "home": "CHI", "twos": [],
         "threes": [two(0.41, [_leg("Bam Adebayo", "reb", "UNDER", 10.5, "MIA"), _leg("Josh Giddey", "stl", "UNDER", 1.5, "CHI"),
                               _leg("Tyler Herro", "fg3m", "UNDER", 3.5, "MIA")], take_words="+210")]},
        # Still to play: likeliest by our numbers, but no book pays enough (our card says pass): not offered.
        {"away": "DEN", "home": "UTA", "twos": [two(0.66, [_leg("Nikola Jokic", "ast", "OVER", 7.5, "DEN"),
                                                            _leg("Aaron Gordon", "reb", "OVER", 4.5, "DEN")], playable=False),
                                                 two(0.52, [_leg("Jamal Murray", "fg3m", "OVER", 1.5, "DEN"),
                                                            _leg("Lauri Markkanen", "reb", "OVER", 6.5, "UTA")])]},
        # Under way: a started game is no selection.
        {"away": "LAL", "home": "GSW", "twos": [two(0.70, [_leg("LeBron James", "reb", "OVER", 6.5, "LAL")] * 2)]},
        # Still to play, a game of scorer pairs only: none in the running.
        {"away": "NYK", "home": "PHI", "twos": [], "threes": [], "scorers": [two(0.2, [_leg("Joel Embiid", "points", "OVER", 9.5)] * 2)]},
    ]
    sched = [{"away": g["away"], "home": g["home"], "date": "2026-11-20"} for g in games]
    sched[3]["live"] = {"state": "live"}
    return {"games": sched, "report_bets": [], "game_parlays": {"games": games}}


def _run(board, keys):
    js = HARNESS + PAGE + f"""
      const d = {json.dumps(board)};
      const byGame = new Map(d.game_parlays.games.map((x) => [`${{x.away}}@${{x.home}}`, {{ bets: [], tix: x }}]));
      const keys = {json.dumps(keys)};
      const top = rpTopTickets(d, byGame, keys);
      process.stdout.write(JSON.stringify([top.map((x) => [x.key, x.kind, x.t.joint]), rpTopHTML(top),
                                           rpTodayHTML(d, byGame, keys)]));"""
    return _node(js)


def test_the_three_likeliest_tickets_of_the_games_still_to_play_one_a_game():
    b = _board()
    got = _run(b, ["IND@BOS", "MIA@CHI", "DEN@UTA", "LAL@GSW", "NYK@PHI"])
    if got is None:
        print("      (skipped: no Node)")
        return
    top, html, today = got
    assert top == [["IND@BOS", "two", 0.58], ["DEN@UTA", "two", 0.52], ["MIA@CHI", "three", 0.41]], top
    assert "LeBron James" not in html, "a game under way is no selection"
    assert "Nikola Jokic" not in html, "a ticket our own card says to pass on is not offered"
    assert "Joel Embiid" not in html, "scorer pairs are long by design"
    assert html.count('class="rpk-top-row"') == 3
    first = html[html.index('data-rpk-jump="rpk-IND-BOS"'):html.index("</button>")]
    assert "Pacers at Celtics · two legs" in first
    assert "Jaylen Brown over 3.5 assists + Pascal Siakam over 5.5 rebounds" in first
    assert "<b>58%</b> by our numbers · take it at +120 or better" in first
    assert "Heat at Bulls · three legs" in html and "take it at +210 or better" in html
    # The leg's own word for its market, before the engine's words have arrived with the record ("fg3m" was the key).
    assert "Jamal Murray over 1.5 3-pointers made + Lauri Markkanen over 6.5 rebounds" in html
    assert "fg3m" not in html and " reb " not in html
    assert html.index("rpk-IND-BOS") < html.index("rpk-DEN-UTA") < html.index("rpk-MIA-CHI"), "likeliest first"
    assert "The likeliest tickets today<span>by our numbers, one a game</span>" in html
    # On the tab: after the day's line, before the chips and the games.
    assert today.index('class="rpk-summary"') < today.index('class="rpk-top"') < today.index('class="std-chips') \
        < today.index('class="rpk-group"')


def test_fewer_than_two_games_to_choose_from_draws_nothing():
    b = _board()
    got = _run(b, ["IND@BOS", "LAL@GSW", "NYK@PHI"])
    if got is None:
        return
    top, html, today = got
    assert top == [] and html == "" and 'class="rpk-top"' not in today


def test_each_line_is_a_door_to_its_game_and_the_strip_is_the_members_only():
    # The page binds every [data-rpk-jump] after drawing: open the game's fold and scroll to it.
    i = PAGE.index('host.querySelectorAll("[data-rpk-jump]").forEach')
    assert 'if (el.tagName === "DETAILS") el.open = true;' in PAGE[i:i + 400]
    assert "${rpTopHTML(rpTopTickets(d, byGame, keys))}${jump}${groups}" in PAGE
    # Drawn inside the Today tab's own HTML, which a locked board never builds (its lock card stands instead).
    j = PAGE.index("const today = locked")
    assert PAGE.index("memberLockHTML(", j) < PAGE.index(": rpTodayHTML(d, byGame, keys);", j)
    for rule in (".rpk-top {", ".rpk-top-row + .rpk-top-row { border-top: 1px solid var(--border-soft); }",
                 ".rpk-top-row:hover .rpk-top-legs, .rpk-top-row:focus-visible .rpk-top-legs { color: var(--gold); }"):
        assert rule in CSS, rule


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as e:                                   # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    if fails:
        sys.exit(1)
    print(f"\n{len(tests)} tests passed.")
