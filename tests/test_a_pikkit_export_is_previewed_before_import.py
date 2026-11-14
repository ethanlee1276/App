"""A Pikkit export is read, and can be looked at before it is written.

Ethan, 2026-09-26: Juice Reel's API approval is pending and its CSV would
not upload, so his record comes from Pikkit's export. Pikkit publishes no
column list, and a column read wrongly (profit as payout, a date as the
stake) would put a false number on a public record. So:

  * the header names Pikkit is likely to use are aliases, and they only
    apply when a column with that name exists;
  * `python3 -m engine.zeno preview FILE`, and the owner upload with
    `X-Zeno-Preview: 1`, show every column and what it was read as, and
    write nothing.
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import zeno as Z                                          # noqa: E402

CSV = ("﻿bet_id,sportsbook,type,status,odds,amount,profit,time_placed,time_settled,bet_info,"
       "sports,closing_line\n"
       "1,DraftKings,straight,won,-110,22,20,2026-09-20 13:00,2026-09-20 16:20,"
       "Josh Allen Over 1.5 Pass TD,Football,-125\n"
       "2,FanDuel,parlay,lost,+450,10,-10,2026-09-21,2026-09-21,Bills ML / Chiefs ML,Football,\n"
       "3,theScore Bet,straight,pending,1.91,15,,2026-09-26,,Judge o1.5 TB,Baseball,\n")


def test_every_column_says_what_it_was_read_as():
    got = Z.preview(CSV)
    cols = got["columns"]
    assert cols["bet_id"] == "external_id" and cols["amount"] == "stake" and cols["profit"] == "profit"
    assert cols["time_placed"] == "placed_at" and cols["bet_info"] == "selection"
    assert cols["closing_line"] == "NOT READ" and got["unknown_headers"] == ["closing_line"]
    assert "﻿bet_id" not in cols, "the byte-order mark is not part of a name"


def test_the_money_is_read_right():
    first = {t["selection"]: t for t in Z.preview(CSV)["first"]}
    win = first["Josh Allen Over 1.5 Pass TD"]
    assert (win["stake"], win["payout"], win["result"], win["odds"]) == (22.0, 42.0, "won", -110)
    assert first["Bills ML / Chiefs ML"]["payout"] == 0.0
    assert first["Judge o1.5 TB"]["odds"] == -110 and first["Judge o1.5 TB"]["result"] == "open"
    assert Z.preview(CSV)["results"] == {"won": 1, "lost": 1, "open": 1}


def test_a_preview_writes_nothing():
    path = os.path.join(tempfile.mkdtemp(), "zeno.db")
    before = os.path.exists(path)
    Z.preview(CSV)
    assert os.path.exists(path) == before
    conn = Z.connect(path)
    try:
        assert Z.import_rows(conn, Z.parse_text(CSV)[0], source="pikkit")["added"] == 3
    finally:
        conn.close()
    assert sqlite3.connect(path).execute("SELECT COUNT(*) FROM zeno_bets").fetchone()[0] == 3


def test_the_upload_can_ask_for_a_preview():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _zeno_import(")
    body = src[i:src.index("\n    def ", i + 10)]
    assert 'self.headers.get("X-Zeno-Preview")' in body
    assert body.index("Z.preview(text)") < body.index("Z.import_rows("), "the look comes before any write"
    assert body.index("owner_token_ok") < body.index("Z.preview(text)"), "owner only, even to look"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
