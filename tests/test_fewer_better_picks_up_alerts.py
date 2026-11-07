"""Fewer, better picks-are-up alerts (engine/pushalerts POSTED_GAP_S and
merge_posted; docs/RETENTION.md: how often alerts come is what turns them
off — 37% of people say they would turn an app's alerts off at 2-5 a week).

What these hold:

  * a phone gets at most one picks-are-up alert in POSTED_GAP_S; a board
    that comes due sooner is held for the next one, and every other kind
    still goes;
  * when several boards are up, the phone hears one line naming them all
    (the knocked phone's own line, and the iPhone app's one push), newest
    first, with each board's count;
  * a phone that never had one is not held; the privacy policy says what
    is kept for it.

Run directly: `python3 tests/test_fewer_better_picks_up_alerts.py`
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import pushalerts as PA                                   # noqa: E402

FCM = "https://fcm.googleapis.com/fcm/send/abc123:APA91bHxyz"
NOW = 1_760_000_000.0


def _posted(lg, label, n):
    return {"id": f"posted:{lg}:d", "kind": "posted", "league": lg, "label": label, "n": n,
            "title": f"Tonight’s {label} picks are up", "body": "b", "url": f"/?sport={lg}#recommended"}


def _conn():
    c = sqlite3.connect(":memory:")
    PA.ensure_tables(c)
    return c


def test_several_boards_are_one_line():
    m = PA.merge_posted([_posted("nba", "NBA", 6), _posted("nhl", "NHL", 4), _posted("nfl", "NFL", 8)])
    assert m["title"] == "Picks are up: NBA, NHL and NFL", m
    assert m["body"].startswith("NBA 6 · NHL 4 · NFL 8 on the board"), m
    assert m["url"] == "/?sport=nba#recommended" and m["kind"] == "posted"
    one = _posted("nba", "NBA", 6)
    assert PA.merge_posted([one]) is one and PA.merge_posted([]) == {}


def test_a_phone_hears_one_picks_up_alert_in_three_hours():
    c = _conn()
    PA.subscribe(c, FCM)
    PA.subscribe(c, "cd" * 32, kind="apns")
    knocked, pushed = [], []
    knock = lambda e, k, topic="": knocked.append(topic) or 201        # noqa: E731
    apns = lambda e, m, cfg: pushed.append(m) or 200                    # noqa: E731
    two = [_posted("nba", "NBA", 6), _posted("nhl", "NHL", 4)]
    st = PA.send(c, two, knock=knock, apns=apns, vapid={"x": 1}, apns_cfg={"x": 1}, now_s=NOW)
    assert st["sent"] == 2 and "capped" not in st, st
    assert len(knocked) == 1 and len(pushed) == 1, "one knock, one push — not one a board"
    assert pushed[0]["title"] == "Picks are up: NBA and NHL", pushed[0]
    # An hour later another board: held, both phones.
    st = PA.send(c, [_posted("nfl", "NFL", 8)], knock=knock, apns=apns, vapid={"x": 1}, apns_cfg={"x": 1},
                 now_s=NOW + 3600)
    assert st.get("capped") == 2 and len(knocked) == 1 and len(pushed) == 1, st
    # Every other kind still goes inside the gap.
    st = PA.send(c, [{"id": "settled:d", "kind": "settled", "league": "", "title": "Last night", "body": "b",
                      "url": "/#record"}, _posted("nfl", "NFL", 8)], knock=knock, apns=apns, vapid={"x": 1},
                 apns_cfg={"x": 1}, now_s=NOW + 3700)
    assert st["sent"] == 2 and pushed[-1]["kind"] == "settled" and len(pushed) == 2, (st, pushed)
    # Past the gap, the next board goes.
    st = PA.send(c, [_posted("cfb", "CFB", 5)], knock=knock, apns=apns, vapid={"x": 1}, apns_cfg={"x": 1},
                 now_s=NOW + PA.POSTED_GAP_S + 1)
    assert st["sent"] == 2 and "capped" not in st, st


def test_the_knocked_phone_reads_every_board_up_in_one_line():
    path = os.path.join(tempfile.mkdtemp(), "latest.json")
    now = time.time()
    json.dump({"messages": [dict(_posted("nfl", "NFL", 8), at=now - 7200),
                            dict(_posted("nhl", "NHL", 4), at=now - 600),
                            dict(_posted("nba", "NBA", 6), at=now - 60)]}, open(path, "w"))
    got = PA.latest_for({"topics": ["posted"], "leagues": []}, path, now)
    assert got["title"] == "Picks are up: NBA, NHL and NFL" and got["kind"] == "posted", got
    nba_only = PA.latest_for({"topics": ["posted"], "leagues": ["nba"]}, path, now)
    assert nba_only["title"] == "Tonight’s NBA picks are up", "a phone hears only the boards it asked for"


def test_the_policy_names_what_is_kept():
    priv = (ROOT / "web" / "privacy.html").read_text(encoding="utf-8")
    assert "when it was last sent a picks-are-up alert" in priv
    c = _conn()
    assert "posted_at" in {r[1] for r in c.execute("PRAGMA table_info(push_subs)")}
    PA.ensure_tables(c)                                                  # twice is harmless


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
