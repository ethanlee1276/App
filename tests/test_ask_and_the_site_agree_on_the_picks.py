"""Ask names the same picks the site shows.

Ethan, 2026-09-24, with two screenshots side by side: the Most Likely
board showing GB ML (69%, Top) and Bijan Robinson over 3.5 receptions
(66%, Strong) for Falcons at Packers, and Ask, asked "What are some good
picks for the Green Bay vs falcons game tonight", answering that GB was
"an info-only lean, not a staked bet" and that "we don't have any staked
picks or props specifically for this game". "Why are we showing 2 bets
for the game tonight but then when I ask the ai is says something
different from what we offer. Fix that."

Three causes, each pinned here:

1. "Green Bay" and "falcons" matched nothing — only a team code typed in
   capitals did — so neither pick was attached to the question.
2. The rule "a row with recommended false or no stake is not one of our
   bets: say so" is true of the Edge board and false of the Most Likely
   board, whose rows carry recommended false and no Edge stake — so Ask
   called a published 69% Top pick not recommended.
3. The Most Likely row carried the Edge board's warning on the other
   side's price, ending "info only", which Ask repeated.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import askbot as A                                    # noqa: E402

GB_ML = {"kind": "game", "player": "GB ML", "team": "GB", "opponent": "ATL", "home": "GB", "away": "ATL",
         "matchup": "ATL @ GB", "pick_label": "GB ML", "bet_type": "moneyline", "market": "moneyline",
         "odds": -228, "book": "Novig", "model_prob": 0.69, "implied_prob": 0.69, "win_prob": 0.659,
         "edge": 0.0, "grade": "Likely", "stake_units": 0.0, "recommended": False, "ranked": True,
         "reasons": ["The likely side. The edge board backed ATL ML at +223 on price; this is the side "
                     "the same numbers say lands more often (69%).",
                     "Model win probability 31% vs book's 31% — a +0.0% edge on ATL after the market haircut",
                     "Power rating: GB +0.5 vs ATL -3.4 net pts/game (incl. home field)"],
         "warnings": ["No sharp-anchor value at current prices, and the model's own number has never "
                      "beaten the NFL close — info only"]}
BIJAN = {"player": "Bijan Robinson", "team": "ATL", "opponent": "GB", "market": "receptions",
         "side": "OVER", "line": 3.5, "odds": -238, "book": "DraftKings", "model_prob": 0.66,
         "implied_prob": 0.66, "recommended": False, "stake_units": 0.0, "ranked": True}
PASSED = {"player": "ATL ML", "team": "ATL", "opponent": "GB", "home": "GB", "away": "ATL",
          "matchup": "ATL @ GB", "pick_label": "ATL ML", "bet_type": "moneyline", "market": "moneyline",
          "odds": 223, "win_prob": 0.31, "fair_prob": 0.31, "edge": 0.0, "recommended": False}
BOARD = {"sport": "nfl", "date": "2026-09-24",
         "games": [{"home": "GB", "away": "ATL", "total": 43, "spread": 4.5, "favorite": "GB"}],
         "game_bets": [PASSED], "most_likely": [GB_ML, BIJAN], "recommendations": []}
Q = "What are some good picks for the Green Bay vs falcons game tonight"


def test_a_team_named_in_words_finds_its_game():
    assert A.named_teams(Q, "nfl") == {"GB", "ATL"}
    assert A.named_teams("new york tonight", "nfl") == set(), "a city two teams share names neither"
    assert [A._game_label(g) for g in A.named_games(BOARD, Q, [])] == ["ATL @ GB"]
    facts = A.game_facts(BOARD, BOARD["games"][0])
    assert facts["home_team"] == "GB" and facts["away_team"] == "ATL"


def test_both_picks_come_first_labelled_as_the_site_labels_them():
    rows = A.matched_rows(BOARD, Q)
    assert [r.get("pick_label") or r.get("player") for r in rows[:2]] == ["GB ML", "Bijan Robinson"], rows
    gb, bijan, passed = rows[0], rows[1], rows[2]
    assert gb["board"] == "most_likely" and gb["our_pick"] is True and gb["tier"] == "Top"
    assert bijan["our_pick"] is True and bijan["tier"] == "Strong"
    for k in ("recommended", "stake_units", "edge", "grade"):
        assert k not in gb, f"the Edge board's {k} does not ride on a Most Likely pick"
    assert "warnings" not in gb, "no 'info only' on a published pick"
    assert not any("edge on ATL" in x for x in gb["reasons"]), "the other side's price verdict stays off"
    assert passed["board"] == "edge" and passed["our_pick"] is False, "a price we passed on says so"


def test_the_rule_names_both_boards():
    assert "recommended false or no stake is not one of our bets" not in A.SYSTEM
    for words in ("every row on it is one of our picks", "never call one not recommended or info only",
                  "give every our_pick row for it from both boards"):
        assert words in " ".join(A.SYSTEM.split()), words


def test_the_lookups_hand_the_same_labels():
    tb = A.tonight_board({"nfl": BOARD}, "Packers")
    rows = tb["boards"][0]["rows"]
    assert [r["board"] for r in rows][:2] == ["most_likely", "most_likely"], rows
    picks = A.our_picks({"nfl": BOARD}, kind="most_likely")["rows"]
    assert all(r["board"] == "most_likely" and r["our_pick"] for r in picks)
    s = A.board_summary(BOARD)
    assert s["most_likely_total"] == 2 and s["most_likely"][0]["tier"] == "Top"


def test_an_old_answer_is_not_served_under_the_new_rule():
    key = A.answer_key("recommendations.json", BOARD, "", Q)
    assert "|p:" + A._prompt_tag() in key


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
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
