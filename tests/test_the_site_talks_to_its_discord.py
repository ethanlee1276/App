"""The community feed (engine/discordfeed): last night's record once it has
settled, the Pick of the Day, the board, a long shot that cashed, the week
— each once, to the right channel. Fixtures only; no webhook is called.

Ethan, 2026-10-06: "every single night when bets settle, it'll
automatically post that day's record to the Discord."

Run directly: `python3 tests/test_the_site_talks_to_its_discord.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import discordfeed as D                            # noqa: E402
from engine import ledger                                      # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
#: Tuesday 2026-10-13, 15:00 UTC = 11:00 ET.
NOW = dt.datetime(2026, 10, 13, 15, 0, tzinfo=dt.timezone.utc)
ENV = {"QB_DISCORD_RECORD_WEBHOOK": "https://discord.test/record",
       "QB_DISCORD_PICKS_WEBHOOK": "https://discord.test/picks", "QB_DISCORD_SPORTS": "nfl"}


def _ledger():
    d = Path(tempfile.mkdtemp())
    conn = ledger.connect(d / "ledger.db")
    return conn, d


def _bet(conn, day, category, status, pnl, player="Josh Allen", market="pass_yds", side="OVER", line=249.5,
         odds=-110, hp=0.62, sport="nfl"):
    conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, hit_prob, status, "
                 "pnl_units, category, game_day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (f"{day}T12:00:00", sport, day, player, market, side, line, "DraftKings", odds, hp, status, pnl,
                  category, day))
    conn.commit()


class Posts(list):
    def __call__(self, url, text):
        self.append((url.rsplit("/", 1)[-1], text))
        return True


def test_nothing_happens_without_a_webhook():
    conn, d = _ledger()
    posts = Posts()
    out = D.run(conn, NOW, env={}, boards={}, post_fn=posts, state_path=d / "s.json")
    assert out["note"] == "no Discord webhook set" and posts == []


def test_last_nights_record_posts_once_after_every_pick_has_graded():
    conn, d = _ledger()
    _bet(conn, "2026-10-12", "likely_live", "won", 0.91)
    _bet(conn, "2026-10-12", "likely_live", "lost", -1.0, player="Khalil Shakir", market="receptions", line=3.5,
         odds=-150, hp=0.59)
    _bet(conn, "2026-10-12", "main", "won", 1.4, player="James Cook", market="rush_yds", line=70.5, odds=140, hp=0.55)
    posts = Posts()
    out = D.run(conn, NOW, env=ENV, boards={}, post_fn=posts, state_path=d / "s.json")
    assert "record:2026-10-12" in out["posted"]
    text = next(t for u, t in posts if "— the record" in t)
    assert "Mon Oct 12 — the record" in text and "Most Likely: **1-1**" in text and "Edge picks: **1-0**" in text
    assert "Best hit: James Cook over 70.5 rushing yards (+140)" in text
    assert "Toughest miss: Khalil Shakir over 3.5 receptions (−150) — we said 59%" in text
    assert "still grading" not in text and "#record" in text
    # Never twice.
    again = D.run(conn, NOW + dt.timedelta(hours=1), env=ENV, boards={}, post_fn=posts, state_path=d / "s.json")
    assert "record:2026-10-12" not in again["posted"] and len([p for p in posts if p[0] == "record"]) == 2, \
        "the second record post is the weekly (Tuesday), not a repeat"


def test_a_night_still_grading_waits_until_late_morning_then_says_so():
    conn, d = _ledger()
    _bet(conn, "2026-10-12", "likely_live", "won", 0.91)
    _bet(conn, "2026-10-12", "likely_live", "open", None, player="Late Game")
    posts = Posts()
    early = dt.datetime(2026, 10, 13, 9, 0, tzinfo=dt.timezone.utc)          # 05:00 ET
    out = D.run(conn, early, env=ENV, boards={}, post_fn=posts, state_path=d / "s.json")
    assert "record:2026-10-12" not in out["posted"]
    out = D.run(conn, NOW, env=ENV, boards={}, post_fn=posts, state_path=d / "s.json")      # 11:00 ET
    assert "record:2026-10-12" in out["posted"]
    assert "(1 still grading)" in next(t for u, t in posts if "— the record" in t)


def test_the_week_posts_on_tuesday_once():
    conn, d = _ledger()
    for day in ("2026-10-08", "2026-10-11", "2026-10-12"):
        _bet(conn, day, "board", "won", 0.9, player=f"P{day}")
    posts = Posts()
    D.run(conn, NOW, env=ENV, boards={}, post_fn=posts, state_path=d / "s.json")
    weekly = [t for u, t in posts if t.startswith("**The week")]
    assert len(weekly) == 1 and "The one board: **3-0**" in weekly[0]
    D.run(conn, NOW + dt.timedelta(hours=3), env=ENV, boards={}, post_fn=posts, state_path=d / "s.json")
    assert len([t for u, t in posts if t.startswith("**The week")]) == 1
    wed = dt.datetime(2026, 10, 14, 15, 0, tzinfo=dt.timezone.utc)
    out = D.run(conn, wed, env=ENV, boards={}, post_fn=posts, state_path=d / "s.json")
    assert not any(k.startswith("weekly") for k in out["posted"])


def _board(today="2026-10-13"):
    pick = {"player": "Josh Allen", "market": "pass_yds", "side": "OVER", "line": 249.5, "odds": -110,
            "book": "DraftKings", "hit_prob": 0.61}
    return {"games": [{"home": "BUF", "away": "LAC", "date": today}],
            "likely_board": {"rows": [dict(pick, tier="top"), dict(pick, player="James Cook", market="rush_yds",
                                                                   line=70.5, tier="strong"),
                                      dict(pick, player="K. Shakir", market="receptions", line=3.5, tier="look")]},
            "recommendations": [dict(pick, recommended=True), dict(pick, recommended=False)],
            "game_bets": [{"kind": "game", "pick_label": "BUF −6.5", "market": "spread", "odds": -110, "recommended": True}],
            "pick_of_the_day": {"date": today, "pick": pick, "verdict": {"bet": True, "say": "Allen at home, soft pass defence."}}}


def test_the_board_and_the_pick_of_the_day_post_once_a_day_with_the_detail_the_channel_allows():
    conn, d = _ledger()
    posts = Posts()
    out = D.run(conn, NOW, env=ENV, boards={"nfl": _board()}, post_fn=posts, state_path=d / "s.json")
    assert "board:nfl:2026-10-13" in out["posted"] and "potd:nfl:2026-10-13" in out["posted"]
    by = {t.split("\n")[0][:14]: t for u, t in posts}
    board = next(t for u, t in posts if t.startswith("**NFL board"))
    assert "1 game today: 3 Most Likely picks (1 Top, 1 Strong, 1 Worth a look) · 2 Edge picks." in board
    assert "Top: Josh Allen over 249.5 passing yards (−110)" in board
    potd = next(t for u, t in posts if t.startswith("**Pick of the Day"))
    assert "Josh Allen over 249.5 passing yards (−110) at DraftKings — we say 61%" in potd
    assert "Allen at home, soft pass defence." in potd
    again = D.run(conn, NOW + dt.timedelta(minutes=15), env=ENV, boards={"nfl": _board()}, post_fn=posts,
                  state_path=d / "s.json")
    assert again["posted"] == []
    # A public channel: counts only.
    posts2 = Posts()
    D.run(conn, NOW, env=dict(ENV, QB_DISCORD_PICKS_DETAIL="0"), boards={"nfl": _board()}, post_fn=posts2,
          state_path=d / "s2.json")
    texts = "\n".join(t for u, t in posts2)
    assert "Josh Allen" not in texts and "is locked — members see it" in texts and "3 Most Likely picks" in texts
    # No games today: no board post, and a Pick of the Day dated another day stays quiet.
    posts3 = Posts()
    out = D.run(conn, NOW, env=ENV, boards={"nfl": _board(today="2026-10-19")}, post_fn=posts3,
                state_path=d / "s3.json")
    assert not any(k.startswith(("board", "potd")) for k in out["posted"])


def test_a_long_shot_that_cashed_posts_once():
    conn, d = _ledger()
    _bet(conn, "2026-10-12", "longshot", "won", 4.5, player="Keon Coleman", market="anytime_td", side="YES",
         line=0.5, odds=450, hp=0.2)
    _bet(conn, "2026-10-12", "main", "won", 0.9, player="Not A Longshot", odds=-110)
    _bet(conn, "2026-10-12", "longshot", "lost", -1.0, player="Missed", odds=600)
    posts = Posts()
    out = D.run(conn, NOW, env=ENV, boards={}, post_fn=posts, state_path=d / "s.json")
    shots = [t for u, t in posts if "Long shot cashed" in t]
    assert len(shots) == 1 and "Keon Coleman anytime TD (+450)" in shots[0]
    assert any(k.startswith("longshot:") for k in out["posted"])
    D.run(conn, NOW + dt.timedelta(hours=2), env=ENV, boards={}, post_fn=posts, state_path=d / "s.json")
    assert len([t for u, t in posts if "Long shot cashed" in t]) == 1


def test_a_webhook_that_fails_is_retried_next_cycle():
    conn, d = _ledger()
    _bet(conn, "2026-10-12", "likely_live", "won", 0.91)

    def flaky(url, text):
        raise OSError("discord down")
    out = D.run(conn, NOW, env=ENV, boards={}, post_fn=flaky, state_path=d / "s.json")
    assert out["posted"] == [] and out["failed"] and not (d / "s.json").exists()
    posts = Posts()
    out = D.run(conn, NOW, env=ENV, boards={}, post_fn=posts, state_path=d / "s.json")
    assert "record:2026-10-12" in out["posted"]


def test_the_words_read_like_a_person_wrote_them():
    assert D.pick_text({"player": "Josh Allen", "market": "pass_yds", "side": "OVER", "line": 249.5, "odds": -110}) \
        == "Josh Allen over 249.5 passing yards (−110)"
    assert D.pick_text({"player": "Keon Coleman", "market": "anytime_td", "side": "YES", "line": 0.5, "odds": 450}) \
        == "Keon Coleman anytime TD (+450)"
    assert D.pick_text({"kind": "game", "pick_label": "BUF −6.5", "market": "spread", "odds": -108}) == "BUF −6.5 (−108)"
    assert D.record_text({"books": []}, "2026-10-12") is None


def test_the_seal_step_runs_the_feed_after_the_witness():
    src = (ROOT / "launch.py").read_text()
    assert src.index("_wit.run(conn)") < src.index("_dc.run(conn)") < src.index("forecast log   : +")


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
