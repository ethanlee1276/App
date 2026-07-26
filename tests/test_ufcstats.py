"""Tests for the UFCStats dossier adapter — parsing is fixture-driven so
the suite runs offline; the fixtures mirror ufcstats.com's real markup."""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import ufcstats

TODAY = dt.date(2026, 7, 26)

SEARCH_HTML = """
<table class="b-statistics__table">
<tr><td><a href="http://www.ufcstats.com/fighter-details/abc123">Max</a></td>
<td><a href="http://www.ufcstats.com/fighter-details/abc123">Holloway</a></td>
<td><a href="http://www.ufcstats.com/fighter-details/abc123">Blessed</a></td></tr>
<tr><td><a href="http://www.ufcstats.com/fighter-details/def456">Jack</a></td>
<td><a href="http://www.ufcstats.com/fighter-details/def456">Holloway</a></td></tr>
</table>
"""

FIGHTER_HTML = """
<span class="b-content__title-highlight"> Max Holloway </span>
<span class="b-content__title-record"> Record: 26-7-0 </span>
<ul>
<li><i>Height:</i> 5' 11" </li>
<li><i>Weight:</i> 155 lbs. </li>
<li><i>Reach:</i> 69" </li>
<li><i>STANCE:</i> Orthodox </li>
<li><i>DOB:</i> Dec 4, 1991 </li>
</ul>
<ul>
<li><i>SLpM:</i> 7.24 </li>
<li><i>Str. Acc.:</i> 48% </li>
<li><i>SApM:</i> 4.83 </li>
<li><i>Str. Def:</i> 59% </li>
<li><i>TD Avg.:</i> 0.42 </li>
<li><i>TD Acc.:</i> 53% </li>
<li><i>TD Def.:</i> 83% </li>
<li><i>Sub. Avg.:</i> 0.2 </li>
</ul>
<table>
<tr><th>W/L</th><th>Fighter</th></tr>
<tr><td><i class="b-flag__text">next</i></td>
  <td><a href="/fighter-details/abc123">Max Holloway</a>
      <a href="/fighter-details/zzz">Future Guy</a></td></tr>
<tr><td><i class="b-flag__text">loss</i></td>
  <td><a href="/fighter-details/abc123">Max Holloway</a>
      <a href="/fighter-details/x1">Ilia Topuria</a></td>
  <td><p>0</p><p>1</p></td><td><p>44</p><p>62</p></td>
  <td><p>0</p><p>0</p></td><td><p>0</p><p>0</p></td>
  <td><a>UFC 308</a><p>Oct. 26, 2024</p></td>
  <td><p>KO/TKO</p><p>Punch</p></td><td><p>3</p></td><td><p>1:34</p></td></tr>
<tr><td><i class="b-flag__text">win</i></td>
  <td><a href="/fighter-details/abc123">Max Holloway</a>
      <a href="/fighter-details/x2">Justin Gaethje</a></td>
  <td><p>2</p><p>0</p></td><td><p>89</p><p>72</p></td>
  <td><p>0</p><p>1</p></td><td><p>0</p><p>0</p></td>
  <td><a>UFC 300</a><p>Apr. 13, 2024</p></td>
  <td><p>KO/TKO</p><p>Punch</p></td><td><p>5</p></td><td><p>4:59</p></td></tr>
<tr><td><i class="b-flag__text">win</i></td>
  <td><a href="/fighter-details/abc123">Max Holloway</a>
      <a href="/fighter-details/x3">Somebody Else</a></td>
  <td><p>0</p><p>0</p></td><td><p>120</p><p>80</p></td>
  <td><p>1</p><p>0</p></td><td><p>0</p><p>0</p></td>
  <td><a>UFC 276</a><p>Jul. 2, 2022</p></td>
  <td><p>U-DEC</p></td><td><p>3</p></td><td><p>5:00</p></td></tr>
</table>
"""


def test_parse_search_pairs_first_and_last_names():
    rows = ufcstats.parse_search(SEARCH_HTML)
    names = {r["name"]: r["url"] for r in rows}
    assert names["Max Holloway"].endswith("abc123")
    assert names["Jack Holloway"].endswith("def456")
    # The nickname link (3rd for the same URL) never pollutes the name.
    assert all("Blessed" not in n for n in names)


def test_parse_fighter_reads_labels_record_and_history():
    raw = ufcstats.parse_fighter(FIGHTER_HTML)
    assert (raw["wins"], raw["losses"], raw["draws"]) == (26, 7, 0)
    assert raw["slpm"] == 7.24 and raw["sapm"] == 4.83
    assert raw["str_def"] == 0.59 and raw["td_def"] == 0.83   # % → fraction
    assert raw["td_avg"] == 0.42 and raw["sub_avg"] == 0.2
    assert raw["weight_lbs"] == 155.0
    assert raw["dob"] == dt.date(1991, 12, 4)
    # Upcoming bout (flag "next") is skipped; three completed rows remain.
    hist = raw["history"]
    assert len(hist) == 3
    assert hist[0]["result"] == "loss" and hist[0]["method"] == "KO/TKO"
    assert hist[0]["date"] == dt.date(2024, 10, 26)
    assert hist[1]["kd"] == 2 and hist[1]["sig_str"] == 89
    assert hist[2]["method"] == "U-DEC"


def test_to_dossier_maps_the_spec_fields():
    raw = ufcstats.parse_fighter(FIGHTER_HTML)
    d = ufcstats.to_dossier("Max Holloway", raw, today=TODAY)
    assert d["age"] == 34                       # b. Dec 1991
    assert d["division"] == "lightweight"       # 155 lbs
    assert d["fights"] == 33 and d["ufc_fights"] == 3
    assert d["ko_losses"] == 1 and d["ko_losses_last3"] == 1
    assert d["times_finished"] == 1
    # KD/100 sig strikes: 2 KD on 253 landed ≈ 0.79.
    assert abs(d["kd_per100"] - 0.79) < 0.01
    # TDD 83% + 7.2 SLpM → elite-TDD striker.
    assert d["archetype"] == "striker_elite_tdd"
    # Last fight Oct 2024, "today" Jul 2026 → layoff red flag; age 34 → none.
    assert any("layoff" in f for f in d["red_flags"])
    assert not any("age" in f for f in d["red_flags"])
    # Estimated fields are called out for the human.
    assert any("archetype" in n for n in d["review"])
    assert any("r3_decay" in n for n in d["review"])
    assert d["source"] == "ufcstats-auto"


def test_archetype_heuristics_cover_the_matrix_styles():
    wrestler = {"td_avg": 4.1, "td_acc": 0.45, "sub_avg": 0.3,
                "td_def": 0.6, "slpm": 3.0}
    assert ufcstats._archetype(wrestler)[0] == "wrestler"
    sub = {"td_avg": 2.0, "td_acc": 0.4, "sub_avg": 1.8,
           "td_def": 0.5, "slpm": 2.5}
    assert ufcstats._archetype(sub)[0] == "submission"
    poor_tdd = {"td_avg": 0.2, "td_acc": 0.2, "sub_avg": 0.1,
                "td_def": 0.38, "slpm": 4.0}
    assert ufcstats._archetype(poor_tdd)[0] == "striker_poor_tdd"
    pressure = {"td_avg": 0.8, "td_acc": 0.3, "sub_avg": 0.2,
                "td_def": 0.6, "slpm": 5.6}
    assert ufcstats._archetype(pressure)[0] == "pressure"


def test_chin_damage_and_age_red_flags():
    hist = [
        {"result": "loss", "method": "KO/TKO", "date": dt.date(2026, 6, 1),
         "kd": 0, "sig_str": 30},
        {"result": "loss", "method": "KO/TKO", "date": dt.date(2026, 2, 1),
         "kd": 0, "sig_str": 40},
        {"result": "win", "method": "U-DEC", "date": dt.date(2025, 9, 1),
         "kd": 1, "sig_str": 80},
    ]
    raw = {"wins": 20, "losses": 8, "draws": 0, "history": hist,
           "weight_lbs": 205.0, "dob": dt.date(1988, 1, 1),
           "slpm": 3.2, "sapm": 4.0, "td_avg": 0.5, "td_acc": 0.3,
           "td_def": 0.5, "sub_avg": 0.2, "str_def": 0.5}
    d = ufcstats.to_dossier("Old Chin", raw, today=TODAY)
    assert d["division"] == "light_heavyweight"
    assert any("chin damage" in f for f in d["red_flags"])
    assert any("age 38" in f for f in d["red_flags"])
    assert d["ko_losses_last3"] == 2
    # Red flags block bets — the review note says so explicitly.
    assert any("BLOCK" in n for n in d["review"])


def test_womens_division_and_thin_strike_data_defaults():
    raw = {"wins": 8, "losses": 2, "draws": 0, "weight_lbs": 115.0,
           "dob": dt.date(1998, 5, 5), "slpm": 4.0, "sapm": 3.0,
           "td_avg": 1.0, "td_acc": 0.4, "td_def": 0.6, "sub_avg": 0.5,
           "str_def": 0.55,
           "history": [{"result": "win", "method": "S-DEC",
                        "date": dt.date(2026, 5, 1), "kd": 0, "sig_str": 40}]}
    d = ufcstats.to_dossier("Straw Weight", raw, today=TODAY)
    assert d["division"] == "w_strawweight"
    assert d["kd_per100"] == 1.0            # < 100 strikes → neutral default
    assert any("kd_per100" in n for n in d["review"])


def test_select_card_groups_nearest_event():
    from ufc_build import select_card
    now = dt.datetime(2026, 7, 26, 12, tzinfo=dt.timezone.utc)
    events = [
        {"id": "1", "commence_time": "2026-08-01T22:00:00Z",
         "home_team": "A One", "away_team": "B One"},
        {"id": "2", "commence_time": "2026-08-02T01:00:00Z",   # same card, late
         "home_team": "C Two", "away_team": "D Two"},
        {"id": "3", "commence_time": "2026-08-15T22:00:00Z",   # next card, out of window
         "home_team": "E Three", "away_team": "F Three"},
        {"id": "4", "commence_time": "2026-07-01T22:00:00Z",   # already fought
         "home_team": "G Four", "away_team": "H Four"},
    ]
    label, card = select_card(events, now=now)
    assert label == "2026-08-01"
    assert [e["id"] for e in card] == ["1", "2"]
    assert select_card([], now=now) == ("", [])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
