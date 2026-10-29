"""The members' split and the members against the close (engine/consensus,
GET /api/split, the Edge Report's pooled line, Settings' switch).

Ethan's second research paper (2026-10-29): "Qellys consensus. The share of
tracked bets on each side of a game" and "Users vs. the market", with its
guardrails: "Only show a split once it covers 50+ bets so no one can be
picked out. Let users opt out of being counted. Never sell user-level
data." What these hold:

  * nothing at all until both locks open — QB_SPLIT=1 and the Privacy
    Policy's own section (id="members-split"), whose wording waits for Ethan
    in docs/RETENTION.md — and the live policy has no such section yet;
  * counted: the game-line legs of open saved parlays from the last three
    days (a team on a moneyline or spread, over or under on a total), never
    a player prop, never a settled or an old ticket, never a member who said
    no; a market is shown only with MIN_BETS legs; counts and shares only;
  * the members against the close is pooled over counted members' noted
    legs, once MIN_BETS are in;
  * a member's yes or no goes in the consent log; the switch is drawn only
    while the site counts anybody.

Run directly: `python3 tests/test_the_members_split_is_pooled_and_locked.py`
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("QB_SPLIT", None)

from engine import consensus as CN                               # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
NOW = 1_793_304_000.0                                             # 2026-10-29 16:00 Eastern


class _Locks:
    def __init__(self, switch=True, section=True):
        self.switch, self.section = switch, section

    def __enter__(self):
        self.old = (os.environ.get(CN.ENV), CN.POLICY)
        if self.switch:
            os.environ[CN.ENV] = "1"
        else:
            os.environ.pop(CN.ENV, None)
        p = Path(tempfile.mkdtemp()) / "privacy.html"
        p.write_text(f'<h3 id="{CN.POLICY_ID}">The members\' split</h3>' if self.section else "<h3>No</h3>")
        CN.POLICY = p
        CN._cache.update(at=0.0, key=None)
        return self

    def __exit__(self, *exc):
        env, CN.POLICY = self.old
        CN._cache.update(at=0.0, key=None)
        if env is None:
            os.environ.pop(CN.ENV, None)
        else:
            os.environ[CN.ENV] = env


def _db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE user_data (user_id INTEGER, section TEXT, ts INTEGER, payload TEXT, "
              "PRIMARY KEY (user_id, section))")
    return c


def _member(c, uid, legs, settings=None, date="2026-10-29", result="pending"):
    c.execute("INSERT INTO user_data VALUES (?, 'mybets', 1, ?)", (uid, json.dumps(
        {"rows": [{"id": f"t{uid}", "src": "slip", "date": date, "result": result, "legs": legs}], "deleted": []})))
    if settings is not None:
        c.execute("INSERT INTO user_data VALUES (?, 'settings', 1, ?)", (uid, json.dumps(settings)))


ML_BOS = {"sport": "nba", "game": "BOS @ LAL", "market": "moneyline", "team": "BOS"}
ML_LAL = {"sport": "nba", "game": "BOS @ LAL", "market": "spread", "team": "LAL"}
OVER = {"sport": "nba", "game": "BOS @ LAL", "market": "total", "side": "over"}
PROP = {"sport": "nba", "game": "BOS @ LAL", "market": "pts", "player": "LeBron James", "side": "over"}


def test_nothing_until_both_locks_open():
    assert not CN.enabled() and "QB_SPLIT" in CN.why_off()
    with _Locks(switch=True, section=False):
        assert not CN.enabled() and "Privacy Policy" in CN.why_off()
    with _Locks(switch=False, section=True):
        assert not CN.enabled()
    with _Locks():
        assert CN.enabled() and CN.why_off() == ""
    c = _db()
    for uid in range(1, 61):
        _member(c, uid, [ML_BOS])
    assert CN.for_game(c, "nba", "BOS", "LAL", NOW) is None, "locks shut: nothing"
    assert CN.against_the_close(c, NOW) is None
    assert 'id="members-split"' not in READ("web", "privacy.html"), "the wording waits for Ethan"
    assert 'id="members-split"' in READ("docs", "RETENTION.md")


def test_what_is_counted_and_what_never_is():
    c = _db()
    for uid in range(1, 41):
        _member(c, uid, [ML_BOS, OVER, PROP])
    for uid in range(41, 56):
        _member(c, uid, [ML_LAL])
    _member(c, 90, [ML_LAL] * 20, settings={"split": "off"})          # said no
    _member(c, 91, [ML_LAL] * 20, result="win")                        # settled
    _member(c, 92, [ML_LAL] * 20, date="2026-10-20")                   # old
    _member(c, 93, [{"sport": "nba", "game": "nonsense", "market": "moneyline", "team": "LAL"}] * 20)
    got = CN.build(c, NOW)["nba:BOS@LAL"]
    assert got == {"sides": {"BOS": 40, "LAL": 15}, "totals": {"over": 40}}, got
    with _Locks():
        split = CN.for_game(c, "nba", "bos", "lal", NOW)
    assert split == {"sides": {"n": 55, "share": {"BOS": round(40 / 55, 3), "LAL": round(15 / 55, 3)}}}, \
        "a market with fewer than MIN_BETS legs is not shown"
    assert "LeBron" not in json.dumps(CN.build(c, NOW)), "never a player prop"


def test_members_against_the_close_is_pooled():
    from engine import betclv as BC
    c = _db()
    BC.ensure_tables(c)
    for uid in range(1, 4):
        _member(c, uid, [ML_BOS])
    _member(c, 9, [ML_BOS], settings={"split": "off"})
    rows = [(1 + i % 3, f"b{i}", 0, -110, -120, 0.55 if i % 2 else 0.45, NOW - 3600) for i in range(60)]
    rows += [(9, f"x{i}", 0, -110, -120, 0.9, NOW - 3600) for i in range(40)]
    c.executemany("INSERT INTO bet_clv (user_id, bet_id, leg, entry, best, fair, at) VALUES (?,?,?,?,?,?,?)", rows)
    got = CN.members_clv(c, NOW)
    assert got["n"] == 60 and got["beat"] == 30, "the member who said no is not in it"
    want = (30 * (1.909090909 * 0.55 - 1) + 30 * (1.909090909 * 0.45 - 1)) / 60
    assert abs(got["avg"] - round(want, 4)) < 1e-3, (got, want)
    c.execute("DELETE FROM bet_clv WHERE bet_id LIKE 'b1%'")
    assert CN.members_clv(c, NOW) is None, "under MIN_BETS legs: nothing"


def test_a_change_of_mind_is_written_down_and_the_page_asks_only_when_on():
    assert CN.changed({}, {"split": "off"}) == "not counted in the members' split"
    assert CN.changed({"split": "off"}, {"split": "on"}) == "counted in the members' split"
    assert CN.changed(None, {"split": "on"}) is None and CN.changed({"odds": "decimal"}, {}) is None
    srv = READ("server.py")
    assert 'if said and CS.record(conn, who["id"], "split", said):' in srv
    assert 'out["split_switch"] = CN.enabled()' in srv
    assert 'if parsed.path in ("/api/split", "/api/split/"):' in srv and '"members": CN.against_the_close(conn)' in srv
    acct = READ("web", "js", "account.js")
    at = acct.index("Count my bets in the members’ split")
    assert "_pwStatus && _pwStatus.split_switch" in acct[at - 300:at] and 'data-set-switch="split"' in acct[at:at + 300]
    assert "Members against the close" in acct
    assert '  split: "on",' in READ("web", "js", "app.js")
    det = READ("web", "js", "detail.js")
    assert "pbpSplitFill(league);" in det and "Not our pick." in det
    assert 'id="pbp-split"' in det


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
