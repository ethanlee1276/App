"""A read gets its pick on its own side when the data backs it, and never a forced one (2026-11-14).

Ethan, 2026-11-14: "make sure the most likley picks are being adjusted on our
game reports. it would not make any sense to make players favoitable and
breakout canidates and not give them props and some for players we thinnk
will do bad, it doesnt make sense to not take the unders." Then, the same
night, to "every favoriteable player gets an over": "we wanna make sure we
are not forcing picks and bets and only making them have over bets or under
bets based off all the data and shit backing those bets", and of the NFL's
read picks under its 60%: "hold them back".

A read leans over (breakout, good matchup) or under (tough, avoid). The Most
Likely list carries his number on that side only when it clears the list's
bar, so many cards said "No Most Likely pick" with nothing behind it. Now:

  * every read the list carries nothing for on its side gets ONE matchup pick
    (engine/matchpicks.READ_PICK_MIN) — the likeliest number on its side, the
    posted line or the rung the Most Likely board found, at a real sportsbook
    at −250 or better — only when the data backs it: our number at 55% on
    that side, and the books' price not far below it (`not_backed`);
  * a read the data does not back gets no pick, and its card says why
    (``read_no_pick``): a coin flip, our number against the read, or a number
    so far from the books that it is usually our error;
  * a market the list carries the other way gets no second, opposite pick;
  * the one Most Likely board checks the pick like every pick, and the card
    names its verdict — its tier, or held back and why
    (likelyboard._read_picks_follow_the_board); the report's player cards say
    the same (gamereport.read_pick).

    python3 tests/test_every_read_gets_its_pick_on_its_side.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import matchpicks as M                      # noqa: E402
from engine import gamereport as R                      # noqa: E402
from engine import likelyboard as LB                    # noqa: E402

GAME = {"home": "NYG", "away": "WAS", "date": "2099-11-12", "kickoff": "2099-11-12T20:15:00-05:00"}


def _prop(player, team, pos, market, line, hit_prob, side="Over", over=-110, under=-110, book="DraftKings"):
    return {"player": player, "team": team, "opponent": "WAS" if team == "NYG" else "NYG", "position": pos,
            "market": market, "market_label": market.replace("_", " ").title(), "line": line, "side": side,
            "hit_prob": hit_prob, "game_date": "2099-11-12",
            "all_lines": [{"book": book, "line": line, "over_odds": over, "under_odds": under}]}


def _read(player, team, pos, read, lean, **kw):
    x = {"player": player, "team": team, "opp": "WAS" if team == "NYG" else "NYG", "pos": pos, "read": read,
         "label": {"breakout": "Breakout candidate", "good": "Good matchup", "tough": "Tough matchup",
                   "avoid": "Avoid"}[read], "lean": lean,
         "usage": {"targets_pg": 7.0, "carries_pg": 15.0}, "pro": ["a soft secondary"], "con": ["a stout front"]}
    x.update(kw)
    return x


def _best(market, line, odds, book, p):
    return {"priced": True, "refused": "", "bar": 0.60,
            "best": {"market": market, "side": "over", "line": line, "odds": odds, "book": book,
                     "model_prob": p, "market_label": market.title()}}


PROPS = [_prop("Malik Nabers", "NYG", "WR", "receptions", 4.5, 0.58),
         _prop("Malik Nabers", "NYG", "WR", "rec_yds", 59.5, 0.51),
         # A struggle read takes his under: 40% over is 60% under.
         _prop("Rachaad White", "WAS", "RB", "rush_yds", 44.5, 0.40),
         _prop("Isaiah Likely", "NYG", "TE", "receptions", 3.5, 0.46),
         _prop("Cam Skattebo", "NYG", "RB", "rush_att", 15.5, 0.58),
         _prop("Terry McLaurin", "WAS", "WR", "receptions", 4.5, 0.52),
         _prop("Stefon Diggs", "WAS", "WR", "receptions", 3.5, 0.57),
         _prop("Wan'Dale Robinson", "NYG", "WR", "receptions", 4.5, 0.56),
         _prop("Wan'Dale Robinson", "NYG", "WR", "rec_yds", 44.5, 0.56),
         # A read with a coin flip behind it.
         _prop("Darius Slayton", "NYG", "WR", "receptions", 2.5, 0.52),
         # Our number far above the books' price: 70% against +150's 40%.
         _prop("Zach Ertz", "WAS", "TE", "receptions", 3.5, 0.70, over=150, under=-190)]


def _reads():
    return [
        _read("Malik Nabers", "NYG", "WR", "breakout", ["receptions", "rec_yds"]),
        _read("Rachaad White", "WAS", "RB", "tough", ["rush_yds"]),
        # Our number says his over loses more often than not.
        _read("Isaiah Likely", "NYG", "TE", "good", ["receptions"],
              no_pick=_best("receptions", 3.5, -110, "DraftKings", 0.46)),
        # The list already carries his read's side.
        _read("Cam Skattebo", "NYG", "RB", "good", ["rush_att"],
              pick={"player": "Cam Skattebo", "market": "rush_att", "side": "Over", "line": 13.5,
                    "odds": -190, "model_prob": 0.66, "market_label": "Carries"}),
        # The Most Likely board found a likelier rung on his side than the posted line.
        _read("Terry McLaurin", "WAS", "WR", "breakout", ["receptions"],
              no_pick=_best("receptions", 3.5, -175, "FanDuel", 0.62)),
        # A rung only an exchange hangs is not a price a reader can take.
        _read("Stefon Diggs", "WAS", "WR", "good", ["receptions"],
              no_pick=_best("receptions", 2.5, -150, "ProphetX", 0.66)),
        # The list carries his yards the other way: no opposite pick in that market.
        _read("Wan'Dale Robinson", "NYG", "WR", "good", ["rec_yds", "receptions"],
              pick_other_side={"player": "Wan'Dale Robinson", "market": "rec_yds", "side": "Under",
                               "line": 52.5, "odds": -150, "model_prob": 0.61, "market_label": "Rec Yds"}),
        _read("Darius Slayton", "NYG", "WR", "good", ["receptions"]),
        _read("Zach Ertz", "WAS", "TE", "good", ["receptions"]),
    ]


def _picks():
    reads = _reads()
    return reads, M.prop_picks(GAME, reads, PROPS, sport="nfl")


def test_a_read_the_data_backs_gets_one_pick_on_its_side():
    _reads_, got = _picks()
    by = {}
    for p in got:
        by.setdefault(p["player"], []).append(p)
    nab = by["Malik Nabers"]
    assert [(p["market"], p["side"], p["line"]) for p in nab] == [("receptions", "OVER", 4.5)], nab
    assert nab[0].get("read_pick"), "his read's own pick"
    white = by["Rachaad White"][0]
    assert (white["side"], white["model_prob"]) == ("UNDER", 0.6) and white.get("read_pick"), white
    mcl = by["Terry McLaurin"][0]
    assert (mcl["line"], mcl["odds"], mcl["book"], mcl["model_prob"]) == (3.5, -175, "FanDuel", 0.62), mcl
    dig = by["Stefon Diggs"][0]
    assert dig["book"] == "DraftKings" and dig["line"] == 3.5, "the exchange's rung is passed over"
    assert [p["market"] for p in by["Wan'Dale Robinson"]] == ["receptions"], "no under-and-over in his yards"
    assert sum(1 for p in got if p.get("read_pick")) == 5
    assert all(p["model_prob"] >= M.READ_PICK_MIN for p in got)


def test_no_forced_pick_and_the_read_says_why():
    reads, got = _picks()
    on = {p["player"] for p in got}
    for name in ("Isaiah Likely", "Darius Slayton", "Zach Ertz"):
        assert name not in on, name
    by = {x["player"]: x for x in reads}
    assert "our number disagrees with this read" in by["Isaiah Likely"]["read_no_pick"]["why"]
    assert "close to a coin flip" in by["Darius Slayton"]["read_no_pick"]["why"]
    assert "usually our error" in by["Zach Ertz"]["read_no_pick"]["why"]
    assert by["Zach Ertz"]["read_no_pick"]["model_prob"] == 0.7
    # A read with a pick carries no reason, and the list's own pick is never second-guessed.
    assert "read_no_pick" not in by["Malik Nabers"] and "read_no_pick" not in by["Cam Skattebo"]
    assert M.not_backed(0.58, -110, "over") == ""
    assert M.not_backed(0.58, 120, "over") == "", "within MARKET_FAR of +120's 45%"


def test_a_read_the_list_already_backs_is_not_forced_and_the_extras_still_ask_55():
    _reads_, got = _picks()
    sk = [p for p in got if p["player"] == "Cam Skattebo"]
    assert not any(p.get("read_pick") for p in sk), "his Most Likely pick is his read's pick"
    assert all(p["model_prob"] >= M.PROP_MIN_PROB for p in got if not p.get("read_pick"))


def test_each_read_carries_its_pick_and_the_one_boards_verdict():
    reads, got = _picks()
    n = M.stamp_reads(reads, got)
    by = {x["player"]: x for x in reads}
    assert n == 5 and by["Malik Nabers"]["matchup_pick"]["side"] == "OVER"
    assert "matchup_pick" not in by["Isaiah Likely"] and "matchup_pick" not in by["Cam Skattebo"]
    # The one board held White's under and tiered Nabers's over.
    result = {"scan_reads": {"WAS@NYG": {"players": reads}},
              "likely_board": {
                  "rows": [{"player": "Malik Nabers", "market": "receptions", "side": "OVER", "line": 4.5,
                            "model_prob": 0.58, "tier": "strong", "tier_label": "Strong"}],
                  "held": [{"player": "Rachaad White", "market": "rush_yds", "side": "UNDER", "line": 44.5,
                            "model_prob": 0.6, "tier": "held", "tight_hold": True,
                            "held_note": "held back: our chance is 60% — the NFL board asks 60% of a prop"}]}}
    LB.harmonize(result)
    assert by["Malik Nabers"]["matchup_pick"]["tier_label"] == "Strong"
    assert by["Rachaad White"]["matchup_pick"]["held_note"].startswith("held back: our chance is 60%")
    assert result["likely_board"]["read_picks_carded"] == 2
    # The price it is worth, never heavier than −250 (gamereport.take_at;
    # Ethan's method, rule 21: "Maximum playable price").
    assert R.read_pick(by["Malik Nabers"]) == ("Matchup pick (Strong): Over 4.5 receptions (−110, 58%) — "
                                               "take it at −138 or better")
    assert R.read_pick(by["Rachaad White"]).startswith(
        "Matchup pick, held back: Under 44.5 rush yds (−110, 60%) — our chance is 60%"), \
        R.read_pick(by["Rachaad White"])
    assert R.read_pick(by["Cam Skattebo"]) == ("Most Likely pick: Over 13.5 carries (−190, 66%) — take it at "
                                               "−194 or better")
    assert R.read_pick(by["Darius Slayton"]).startswith("No pick: our number on his over is 52%")
    assert R.read_pick(by["Isaiah Likely"]).startswith("No pick: our number disagrees with this read")
    rob = R.read_pick(dict(by["Wan'Dale Robinson"], matchup_pick=None))
    assert rob.startswith("Our Most Likely pick on him goes the other way: Under 52.5"), rob
    # Stamped again, a read never keeps another build's pick or reason.
    M.stamp_reads(reads, [])
    assert not any("matchup_pick" in x for x in reads)


def test_the_build_stamps_the_reads_and_the_report_draws_the_pick():
    reads = _reads()
    board = M.build([dict(GAME, scan={"units": {}})], {"WAS@NYG": {"players": reads}}, [], PROPS, sport="nfl")
    assert board and reads[0].get("matchup_pick"), "matchpicks.build stamps the game's reads"
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    watch = src[src.index("def sec_watch("):src.index("\ndef ", src.index("def sec_watch(") + 5)]
    assert "pick = read_pick(r)" in watch
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert '${v.pick ? `<p class="gr-person-pick">' in js
    lb = (ROOT / "engine" / "likelyboard.py").read_text(encoding="utf-8")
    # Since 2026-11-15 with the matchup picks the board took off under their
    # bar (test_matchup_picks_follow_the_board).
    assert 'board["read_picks_carded"] = _read_picks_follow_the_board(result, by, dropped)' in lb


def test_the_no_pick_card_names_the_lists_own_bar():
    src = (ROOT / "engine" / "likely.py").read_text(encoding="utf-8")
    assert 'bar=max(_floor(SPORT_MIN_PROB.get(sport)),' in src
    from engine import likely as L
    rep = L._lean_report([], {("A", "NYG", "receptions"): {"side": "over", "read": "good", "label": "Good"}},
                         {}, bar=0.6)
    assert rep[("A", "NYG")]["bar"] == 0.6 and rep[("A", "NYG")]["status"] == "none"
    from engine import gamescan as G
    sr = {"g": {"players": [{"player": "A", "team": "NYG"}]}}
    G.stamp_picks(sr, rep)
    assert sr["g"]["players"][0]["no_pick"]["bar"] == 0.6
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "return x.pick || x.matchup_pick ? 2 : x.pick_other_side ? 0 : 1;" in app


def test_the_card_draws_the_pick_the_hold_and_the_reason_in_words():
    import json
    import os
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("node"):
        return
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    i = app.index("function scanPickHTML(")
    fn = app[i:app.index("\n}\n", i) + 2]
    harness = ("const escapeHtml=(x)=>String(x==null?'':x);"
               "const oddsTxt=(o)=>(o>0?'+':'')+o;"
               "const wholePct=(x)=>Math.round(Number(x)*100)+'%';\n" + fn
               + "\nconst xs=JSON.parse(process.argv[2]);"
               "process.stdout.write(JSON.stringify(xs.map((x)=>scanPickHTML(x).replace(/<[^>]+>/g,''))));")
    path = os.path.join(tempfile.mkdtemp(), "p.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    mp = {"player": "W", "market": "rush_yds", "market_label": "Rushing Yards", "side": "UNDER", "line": 44.5,
          "odds": -110, "model_prob": 0.57, "read_pick": True}
    xs = [{"read": "tough", "matchup_pick": dict(mp, tier="held", held_note="held back: our chance is 57% — "
                                                 "the NFL board asks 60% of a prop or a game line")},
          {"read": "good", "matchup_pick": dict(mp, side="OVER", model_prob=0.63, tier="strong",
                                                tier_label="Strong")},
          {"read": "good", "read_no_pick": {"why": "our number on his over is 52%, close to a coin flip — a "
                                                   "pick needs 55%, so the read alone is not a bet"},
           "no_pick": {"priced": True, "bar": 0.6, "best": dict(mp, side="over", model_prob=0.52)}},
          {"read": "good", "no_pick": {"priced": True, "bar": 0.6,
                                       "best": dict(mp, side="over", model_prob=0.46)}}]
    out = subprocess.run(["node", path, json.dumps(xs)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    got = [" ".join(t.split()) for t in json.loads(out.stdout)]
    assert got[0].startswith("Matchup pick, held back: Under 44.5 Rushing Yards · -110 · 57%"), got[0]
    assert "the NFL board asks 60%" in got[0] and got[0].endswith("Tracked on paper, not posted."), got[0]
    assert got[1].startswith("Matchup pick · Strong: Over 44.5"), got[1]
    assert got[1].endswith("— the read’s side, and our number backs it — take it at -170 or better."), got[1]
    assert got[2] == ("No pick — our number on his over is 52%, close to a coin flip — a pick needs 55%, "
                      "so the read alone is not a bet."), got[2]
    assert "our number disagrees with this read: his likeliest over" in got[3], got[3]


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
