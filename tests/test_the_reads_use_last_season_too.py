"""Who could shine, who could struggle: this season leads, last season
stays in — for the units on both sides of the ball and for the usage
behind each player's read.

Ethan, 2026-09-25: "make sure we are using fresh 2026 data along side
2025 data for both offense and defense bc just bc players are not doing
good right now doesn't mean they are bad and could have done great last
season ... 2026 data should outweigh 2025 data by just a tiny bit but 2025
data should def be used."

`gamescan.season_share` is the one rule: CURRENT_SHARE (0.55) this season
from CURRENT_LEADS_GAMES on, last season the rest. `ratings_from_rows`
(NFL) and `cfb_ratings` use it for the units; `blend_usage` uses it for a
player's targets, carries, shares and snaps, and the read says the split
with last season's own rate beside it.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                                 # noqa: E402


def _wk(team, name, wk, targets, share, carries=0, pos="WR", season_type="REG"):
    return {"team": team, "player_display_name": name, "week": wk, "position": pos,
            "season_type": season_type, "targets": targets, "target_share": share,
            "carries": carries, "receptions": targets * 0.6, "receiving_yards": targets * 8,
            "rushing_yards": carries * 4, "attempts": 0}


def test_a_quiet_start_reads_beside_last_season():
    now = G.usage_table([_wk("CHI", "DJ Moore", 1, 3, 0.10), _wk("CHI", "DJ Moore", 2, 4, 0.12)])
    last = G.usage_table([_wk("CHI", "DJ Moore", w, 9, 0.26) for w in range(1, 18)])
    u = G.blend_usage(now, last)[("CHI", G._key("DJ Moore"))]
    assert u["blend"] == 0.55 and u["games"] == 2, "his games are this season's"
    assert abs(u["tgt_share"] - (0.55 * 0.11 + 0.45 * 0.26)) < 1e-3, u["tgt_share"]
    assert abs(u["targets_pg"] - (0.55 * 3.5 + 0.45 * 9.0)) < 0.06, u["targets_pg"]
    assert u["last_season"]["games"] == 17 and abs(u["last_season"]["tgt_share"] - 0.26) < 1e-6
    # One game: last season fills in more (season_share ramps).
    one = G.blend_usage(G.usage_table([_wk("CHI", "DJ Moore", 1, 3, 0.10)]), last)
    assert one[("CHI", G._key("DJ Moore"))]["blend"] == 0.2


def test_a_mover_keeps_his_record_and_a_rookie_keeps_his_own():
    now = G.usage_table([_wk("HOU", "David Montgomery", 1, 2, 0.05, carries=13, pos="RB"),
                         _wk("HOU", "David Montgomery", 2, 2, 0.05, carries=13, pos="RB"),
                         _wk("CLE", "Quinshon Judkins", 1, 2, 0.05, carries=12, pos="RB"),
                         _wk("CLE", "Quinshon Judkins", 2, 2, 0.05, carries=12, pos="RB")])
    last = G.usage_table([_wk("DET", "David Montgomery", w, 2, 0.05, carries=15, pos="RB") for w in range(1, 18)])
    b = G.blend_usage(now, last)
    dm, qj = b[("HOU", G._key("David Montgomery"))], b[("CLE", G._key("Quinshon Judkins"))]
    assert dm["blend"] == 0.55 and abs(dm["carries_pg"] - (0.55 * 13 + 0.45 * 15)) < 0.06
    assert "last_season" not in qj and qj["carries_pg"] == 12.0, "no last season: his own numbers, unblended"


def test_the_read_says_the_split_and_last_seasons_rate():
    usage = {("CHI", G._key("DJ Moore")): {"name": "DJ Moore", "position": "WR", "games": 2,
                                          "tgt_share": 0.178, "targets_pg": 6.0, "blend": 0.55,
                                          "last_season": {"tgt_share": 0.26, "targets_pg": 9.0, "games": 17}}}
    x = G.player_read("DJ Moore", "CHI", "LV", "WR", usage=usage[("CHI", G._key("DJ Moore"))],
                      ratings={}, room={}, scheme={}, split={}, tackling={}, line_out=[],
                      mates_out=[])
    assert ("Usage is 55% this season, 45% last season — last season he had 26% of the "
            "targets over 17 games") in x["notes"], x["notes"]


def test_the_build_hands_the_scan_both_seasons():
    src = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()
    body = src[src.index("def attach_nfl("):src.index("# ═══ COLLEGE")]
    assert "usage = blend_usage(" in body
    assert "_safe(load_weekly_stats, season - 1), _safe(load_snap_counts, season - 1)" in body
    assert G.CURRENT_SHARE == 0.55 and G.CURRENT_LEADS_GAMES == 2
    assert G.season_share(2) == 0.55 and G.season_share(9) == 0.55, "a tiny bit ahead, all season"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
