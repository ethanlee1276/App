"""Every leaned read gets a pick on its own side when our number agrees (2026-11-14).

Ethan, 2026-11-14: "make sure the most likley picks are being adjusted on our
game reports. it would not make any sense to make players favoitable and
breakout canidates and not give them props and some for players we thinnk
will do bad, it doesnt make sense to not take the unders. so make sure thats
being done."

A read leans over (breakout, good matchup) or under (tough, avoid). The Most
Likely list carries his number on that side only when it clears the list's
bar — 55%, and the NFL's props 60% (likely.LANE_MIN_PROB) — and an under
almost never does, so the card said "No Most Likely pick". Now:

  * every read the list carries nothing for on its side gets ONE matchup
    pick (engine/matchpicks.READ_PICK_MIN): the likeliest number on its side,
    the posted line or the rung the Most Likely board found, at a real
    sportsbook at −250 or better, where our number is at least even;
  * under even our number disagrees with the read, and the card says so;
  * a market the list carries the other way gets no second, opposite pick;
  * the read carries its pick (`matchup_pick`), the game page and the
    report's player cards name it (gamereport.read_pick), and the no-pick
    card names the list's own bar.

    python3 tests/test_every_read_gets_its_pick_on_its_side.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import matchpicks as M                      # noqa: E402
from engine import gamereport as R                      # noqa: E402

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


PROPS = [_prop("Malik Nabers", "NYG", "WR", "receptions", 4.5, 0.53),
         _prop("Malik Nabers", "NYG", "WR", "rec_yds", 59.5, 0.51),
         _prop("Rachaad White", "WAS", "RB", "rush_yds", 44.5, 0.48),
         _prop("Isaiah Likely", "NYG", "TE", "receptions", 3.5, 0.46),
         _prop("Cam Skattebo", "NYG", "RB", "rush_att", 15.5, 0.58),
         _prop("Terry McLaurin", "WAS", "WR", "receptions", 4.5, 0.52),
         _prop("Stefon Diggs", "WAS", "WR", "receptions", 3.5, 0.51),
         _prop("Wan'Dale Robinson", "NYG", "WR", "receptions", 4.5, 0.51),
         _prop("Wan'Dale Robinson", "NYG", "WR", "rec_yds", 44.5, 0.56)]


def _reads():
    return [
        _read("Malik Nabers", "NYG", "WR", "breakout", ["receptions", "rec_yds"]),
        # A struggle read takes his under: 48% over is 52% under.
        _read("Rachaad White", "WAS", "RB", "tough", ["rush_yds"]),
        # Our number says his over loses more often than not.
        _read("Isaiah Likely", "NYG", "TE", "good", ["receptions"],
              no_pick={"priced": True, "refused": "", "bar": 0.60,
                       "best": {"market": "receptions", "side": "over", "line": 3.5, "odds": -110,
                                "book": "DraftKings", "model_prob": 0.46, "market_label": "Receptions"}}),
        # The list already carries his read's side.
        _read("Cam Skattebo", "NYG", "RB", "good", ["rush_att"],
              pick={"player": "Cam Skattebo", "market": "rush_att", "side": "Over", "line": 13.5,
                    "odds": -190, "model_prob": 0.66, "market_label": "Carries"}),
        # The Most Likely board found a likelier rung on his side than the posted line.
        _read("Terry McLaurin", "WAS", "WR", "breakout", ["receptions"],
              no_pick={"priced": True, "refused": "", "bar": 0.60,
                       "best": {"market": "receptions", "side": "over", "line": 3.5, "odds": -175,
                                "book": "FanDuel", "model_prob": 0.58, "market_label": "Receptions"}}),
        # A rung only an exchange hangs is not a price a reader can take.
        _read("Stefon Diggs", "WAS", "WR", "good", ["receptions"],
              no_pick={"priced": True, "refused": "", "bar": 0.60,
                       "best": {"market": "receptions", "side": "over", "line": 2.5, "odds": -150,
                                "book": "ProphetX", "model_prob": 0.66, "market_label": "Receptions"}}),
        # The list carries his yards the other way: no opposite pick in that market.
        _read("Wan'Dale Robinson", "NYG", "WR", "good", ["rec_yds", "receptions"],
              pick_other_side={"player": "Wan'Dale Robinson", "market": "rec_yds", "side": "Under",
                               "line": 52.5, "odds": -150, "model_prob": 0.61, "market_label": "Rec Yds"}),
    ]


def _picks():
    reads = _reads()
    return reads, M.prop_picks(GAME, reads, PROPS, sport="nfl")


def test_every_read_our_number_agrees_with_gets_one_pick_on_its_side():
    _reads_, got = _picks()
    by = {}
    for p in got:
        by.setdefault(p["player"], []).append(p)
    nab = by["Malik Nabers"][0]
    assert (nab["market"], nab["side"], nab["line"]) == ("receptions", "OVER", 4.5) and nab.get("read_pick")
    assert "under the 55%" in nab["read_note"], nab
    white = by["Rachaad White"][0]
    assert (white["side"], white["model_prob"]) == ("UNDER", 0.52) and white.get("read_pick"), white
    assert "Isaiah Likely" not in by, "under even, our number disagrees: no pick"
    mcl = by["Terry McLaurin"][0]
    assert (mcl["line"], mcl["odds"], mcl["book"], mcl["model_prob"]) == (3.5, -175, "FanDuel", 0.58), mcl
    dig = by["Stefon Diggs"][0]
    assert dig["book"] == "DraftKings" and dig["line"] == 3.5, "the exchange's rung is passed over"
    rob = by["Wan'Dale Robinson"]
    assert [p["market"] for p in rob] == ["receptions"], "no under-and-over in his yards"
    # Five reads needed one and every one got it, past the game's old cap of four.
    assert sum(1 for p in got if p.get("read_pick")) == 5 > M.PROP_PER_GAME - 1


def test_a_read_the_list_already_backs_is_not_forced_and_the_extras_still_ask_55():
    _reads_, got = _picks()
    sk = [p for p in got if p["player"] == "Cam Skattebo"]
    assert not any(p.get("read_pick") for p in sk), "his Most Likely pick is his read's pick"
    assert all(p["model_prob"] >= M.PROP_MIN_PROB for p in got if not p.get("read_pick"))


def test_each_read_carries_its_pick_and_the_card_says_it():
    reads, got = _picks()
    n = M.stamp_reads(reads, got)
    by = {x["player"]: x for x in reads}
    assert n == 5 and by["Malik Nabers"]["matchup_pick"]["side"] == "OVER"
    assert "matchup_pick" not in by["Isaiah Likely"] and "matchup_pick" not in by["Cam Skattebo"]
    assert R.read_pick(by["Malik Nabers"]) == "Matchup pick: Over 4.5 receptions (−110, 53%)"
    assert R.read_pick(by["Rachaad White"]).startswith("Matchup pick: Under 44.5 rush yds")
    assert R.read_pick(by["Cam Skattebo"]) == "Most Likely pick: Over 13.5 carries (−190, 66%)"
    assert R.read_pick(by["Isaiah Likely"]).startswith("No pick: our number disagrees with this read"), \
        R.read_pick(by["Isaiah Likely"])
    rob = R.read_pick(dict(by["Wan'Dale Robinson"], matchup_pick=None))
    assert rob.startswith("Our Most Likely pick on him goes the other way: Under 52.5"), rob
    # Stamped again, a read never keeps another build's pick.
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


def test_the_no_pick_card_names_the_lists_own_bar_and_the_page_draws_the_read_pick():
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
    assert "<b>Matchup pick:</b>" in app and "our number disagrees with this read" in app
    assert "return x.pick || x.matchup_pick ? 2 : x.pick_other_side ? 0 : 1;" in app


def test_the_card_draws_the_read_pick_and_the_disagreement_in_words():
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
          "odds": -110, "model_prob": 0.52, "read_pick": True}
    xs = [{"read": "tough", "matchup_pick": mp, "no_pick": {"priced": True, "bar": 0.6, "best": None}},
          {"read": "good", "matchup_pick": dict(mp, side="OVER", model_prob=0.63)},
          {"read": "good", "no_pick": {"priced": True, "bar": 0.6,
                                       "best": dict(mp, side="over", model_prob=0.46)}},
          {"read": "good", "no_pick": {"priced": True, "bar": 0.6,
                                       "best": dict(mp, side="over", model_prob=0.57)}}]
    out = subprocess.run(["node", path, json.dumps(xs)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    got = [" ".join(t.split()) for t in json.loads(out.stdout)]
    assert got[0].startswith("Matchup pick: Under 44.5 Rushing Yards · -110 · 52%"), got[0]
    assert "under the Most Likely list’s 60%" in got[0], got[0]
    assert got[1].endswith("— the read’s side, where our number agrees."), got[1]
    assert "our number disagrees with this read: his likeliest over" in got[2], got[2]
    assert "under the 60% the board needs" in got[3], got[3]


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
