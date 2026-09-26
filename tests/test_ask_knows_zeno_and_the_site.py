"""Ask knows Zeno and the site it lives in.

Ethan, 2026-09-26, a screenshot of Ask: "hows zenos record" answered "I
couldn't find anyone named Zeno in our data". Then: "we need to be able to
answer any question about sports and any questions about the actual site."
Ask read every board and nothing about the product around them.

  * a Zeno question brings his record (the FREE half — totals, Pikkit
    windows, how many bets are open, latest results) and the zeno_record
    tool reads the same; his tickets are the members' board and never
    reach Ask;
  * the site guide rides the system prompt: the boards, the Record, Zeno
    and Pikkit, the plans, the pages, the words;
  * the plans it quotes are the page's PLANS.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import askbot as A                                      # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")

RECORD = {
    "overall": {"settled": 10, "wins": 6, "losses": 4},
    "zeno": {
        "overall": {"settled": 1389, "wins": 221, "losses": 1141, "pushes": 27, "profit": 8001.64,
                    "staked": 30692.9, "roi": 0.2607},
        "snapshot": {"as_of": "2026-09-26T14:23:03", "windows": [
            {"key": "all", "label": "All time", "profit": 8001.64, "roi": 0.2607, "wins": 221, "losses": 1141, "pushes": 27},
            {"key": "2026-09", "label": "September 2026", "profit": 571.53, "roi": 0.3494, "wins": 30, "losses": 150, "pushes": 1},
            {"key": "2026-09-21..2026-09-27", "label": "This week · Sep 21–27", "profit": 134.22, "roi": 0.6286,
             "wins": 9, "losses": 19, "pushes": 0}]},
        "recent": [{"result": "won", "sport": "nfl"}, {"result": "lost", "sport": "mlb"}],
        # A stray ticket in the wrong half must still never reach Ask.
        "open": [{"description": "SECRET PARLAY LEG", "odds": 450}],
        "open_n": 3,
        "unit_dollars": 10,
    },
    "combined": {"settled": 1399, "wins": 227, "losses": 1145, "pushes": 27, "net_units": 812.3, "roi": 0.26,
                 "split": {"model": {"settled": 10}, "zeno": {"settled": 1389}}},
}


def _dir():
    d = Path(tempfile.mkdtemp())
    (d / "record.json").write_text(json.dumps(RECORD), encoding="utf-8")
    return d


def test_a_zeno_question_is_a_zeno_question():
    for q in ("hows zenos record", "How is Zeno doing this week?", "is the owner's record verified on pikkit"):
        assert "zeno" in A.intents(q), q
    assert "zeno" not in A.intents("how are the Bills doing")


def test_the_lookup_is_his_public_record_in_dollars_and_units():
    got = A.zeno_record(data_dir=_dir())
    assert got["all_time"]["wins"] == 221 and got["all_time"]["losses"] == 1141
    assert got["all_time"]["profit_dollars"] == 8001.64 and got["all_time"]["net_units"] == 800.16, "$10 a unit"
    assert got["verified_on"] == "https://links.pikkit.com/user/QellysBook"
    assert got["open_bets"] == 3 and got["latest_results"] == ["won", "lost"]
    assert [w["label"] for w in got["windows"]] == ["September 2026", "This week · Sep 21–27"]
    assert got["combined_with_the_site"]["net_units"] == 812.3
    assert "SECRET PARLAY LEG" not in json.dumps(got), "his tickets are the members' board"
    week = A.zeno_record("week", data_dir=_dir())
    assert [w["label"] for w in week["windows"]] == ["This week · Sep 21–27"]
    assert A.zeno_record(data_dir=Path(tempfile.mkdtemp())).get("error"), "no record file, a sentence not a crash"


def test_the_question_carries_his_record_and_the_guide():
    req = A.build_request({"sport": "nfl", "recommendations": [], "games": []}, "hows zenos record",
                          data_dir=_dir(), boards={})
    facts = json.loads(req["messages"][-1]["content"].split("Facts for this question:\n", 1)[1])
    assert facts["zeno"]["all_time"]["wins"] == 221
    assert any(s["label"] == "Zeno’s record" for s in req["sources"])
    system = req["system"][0]["text"]
    assert A.SITE_GUIDE in system and "Zeno" in system and A.PIKKIT_URL in system
    assert "SECRET PARLAY LEG" not in json.dumps(req["messages"])


def test_the_tool_is_offered_and_answers():
    assert any(t["name"] == "zeno_record" for t in A.TOOLS)
    got = A.run_tool("zeno_record", {"window": "2026-09"}, {}, data_dir=_dir())
    assert [w["label"] for w in got["windows"]] == ["September 2026"]
    assert A.tool_source("zeno_record", {}, got)["label"] == "Zeno’s record"


def test_the_guide_quotes_the_pages_own_plans():
    plans = re.findall(r'\{ id: "(\w+)", name: "[^"]+", price: (\d+), per: "([^"]+)"', APP)
    assert len(plans) == 3, plans
    for _id, price, per in plans:
        assert f"${price} " in A.SITE_GUIDE, (price, per)
    for page in ("Top Picks", "Edge Picks", "Long Shots", "Live Now", "My Bets", "Record", "Zeno's Picks",
                 "Line Shopping", "Futures", "Predict", "Fantasy", "Bankroll"):
        assert page in A.SITE_GUIDE, page
    assert "The model's picks are not on Pikkit" in A.SITE_GUIDE, "the Pikkit claim is Zeno's alone"


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    for f in fns:
        f(); print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
