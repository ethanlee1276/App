"""Tests for the ESPN MMA dossier adapter. Fixtures mirror the payload
shapes probed live in July 2026, so the suite runs offline."""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import espnmma

TODAY = dt.date(2026, 7, 26)

STATS_JSON = {
    "categories": [
        {"displayName": "striking",
         "labels": ["SDBL/A", "SDHL/A", "SDLL/A", "TSL", "TSA", "SSL", "SSA",
                    "TSL-TSA", "KD", "%BODY", "%HEAD", "%LEG"],
         "statistics": [
             {"eventId": "600056375",
              "stats": ["11/17", "46/98", "17/20", "100", "173", "84", "149",
                        "57.80%", "1", "65%", "50%", "85%"]},
             {"eventId": "600011111",
              "stats": ["1/2", "10/20", "2/3", "40", "80", "30", "70",
                        "42%", "0", "50%", "40%", "60%"]},
         ]},
        {"displayName": "Clinch",
         "labels": ["SCBL\t", "SCBA", "SCHL", "SCHA", "SCLL", "SCLA", "RV",
                    "SR", "TDL", "TDA", "TDS", "TK ACC"],
         "statistics": [
             {"eventId": "600056375",
              "stats": ["0", "0", "2", "3", "0", "0", "0", "0.000", "2", "5",
                        "0", "40%"]},
             {"eventId": "600011111",
              "stats": ["0", "0", "0", "0", "0", "0", "0", "0.000", "1", "2",
                        "0", "50%"]},
         ]},
        {"displayName": "Ground",
         "labels": ["SGBL", "SGBA\t", "SGHL", "SGHA", "SGLL", "SGLA", "AD",
                    "ADTB", "ADHG", "ADTM", "ADTS", "SM"],
         "statistics": [
             {"eventId": "600056375",
              "stats": ["0", "0", "8", "11", "0", "0", "0", "0", "0", "0",
                        "0", "1"]},
         ]},
    ]
}

SEARCH_JSON = {
    "results": [
        {"type": "article", "contents": [{"displayName": "Some story"}]},
        {"type": "player", "contents": [
            {"displayName": "Jan Blachowicz", "description": "MMA",
             "link": {"web": "https://www.espn.com/mma/fighter/_/id/2506250/jan-blachowicz"}},
            {"displayName": "Janet Todd", "description": "MMA",
             "link": {"web": "https://www.espn.com/mma/fighter/_/id/999/janet-todd"}},
        ]},
    ]
}

COMP_JSON = {
    "id": "401892191",
    "date": "2026-03-01T04:00Z",
    "type": {"id": "990", "text": "Light Heavyweight",
             "abbreviation": "Light Heavyweight"},
    "competitors": [
        {"id": "2506250", "type": "athlete", "order": 1, "winner": False},
        {"id": "3155814", "type": "athlete", "order": 2, "winner": True},
    ],
    "format": {"regulation": {"periods": 3, "displayName": "Round",
                              "clock": 300.0}},
}


def test_parse_stat_rows_by_label_with_stray_tabs():
    rows = espnmma.parse_stat_rows(STATS_JSON)
    r = rows["600056375"]
    assert r["ssl"] == 84 and r["ssa"] == 149 and r["kd"] == 1
    assert r["tdl"] == 2 and r["tda"] == 5      # Clinch labels carry \t
    assert r["sm"] == 1
    # Second fight has no Ground row — missing keys, not crashes.
    assert rows["600011111"]["ssl"] == 30
    assert "sm" not in rows["600011111"]


def test_find_athlete_id_matches_player_results(monkeypatch=None):
    calls = {}

    def fake_get(url, cache, ttl=0):
        calls["url"] = url
        return SEARCH_JSON
    orig = espnmma._get_json
    espnmma._get_json = fake_get
    try:
        assert espnmma.find_athlete_id("Jan Blachowicz") == "2506250"
        assert espnmma.find_athlete_id("Jan Błachowicz") == "2506250"  # accents
        assert espnmma.find_athlete_id("Nobody Real") is None
    finally:
        espnmma._get_json = orig


def test_parse_competition_winner_opponent_division():
    c = espnmma.parse_competition(COMP_JSON, "2506250")
    assert c["winner"] is False and c["opp_id"] == "3155814"
    assert c["date"] == dt.date(2026, 3, 1)
    assert c["division_text"] == "Light Heavyweight" and c["rounds"] == 3
    # From the other corner it reads as a win.
    assert espnmma.parse_competition(COMP_JSON, "3155814")["winner"] is True


def test_method_and_duration():
    ko = {"period": 3, "displayClock": "1:34",
          "type": {"name": "STATUS_FINAL", "description": "Final"},
          "result": {"name": "ko/tko", "displayName": "KO/TKO"}}
    assert espnmma.method_from_status(ko) == "KO/TKO"
    assert espnmma.fight_duration_s(ko, "KO/TKO", 3) == 2 * 300 + 94
    dec = {"period": 3, "displayClock": "5:00",
           "result": {"displayName": "S Dec"}}
    assert espnmma.method_from_status(dec) == "DEC"
    assert espnmma.fight_duration_s(dec, "DEC", 5) == 5 * 300
    sub = {"result": {"description": "Submission (Rear Naked Choke)"}}
    assert espnmma.method_from_status(sub) == "SUB"
    assert espnmma.method_from_status({"type": {"name": "STATUS_FINAL"}}) is None
    # Unknown clock → assume the distance, never crash.
    assert espnmma.fight_duration_s({}, None, 3) == 900


def test_division_mapping_incl_women_and_weight_fallback():
    assert espnmma.division_from_text("Light Heavyweight") == "light_heavyweight"
    assert espnmma.division_from_text("Heavyweight") == "heavyweight"
    assert espnmma.division_from_text("Women's Strawweight") == "w_strawweight"
    assert espnmma.division_from_text("Flyweight", gender="FEMALE") == "w_flyweight"
    assert espnmma.division_from_text("", weight_lbs=206.0) == "light_heavyweight"
    assert espnmma.division_from_text("Catchweight") == ""


def _fight(eid, date, winner, method, dur=900, div="Lightweight", opp=None):
    return {"event_id": eid, "date": date, "winner": winner, "method": method,
            "duration_s": dur, "rounds": 3, "division_text": div,
            "opp_row": opp}


def test_build_dossier_measures_rates_and_flags():
    own_rows = {
        "e1": {"ssl": 90, "ssa": 150, "kd": 2, "tdl": 2, "tda": 4, "sm": 1},
        "e2": {"ssl": 60, "ssa": 100, "kd": 1, "tdl": 1, "tda": 3, "sm": 0},
        "e3": {"ssl": 50, "ssa": 90, "kd": 0, "tdl": 0, "tda": 1, "sm": 0},
    }
    fights = [
        _fight("e1", dt.date(2026, 6, 1), False, "KO/TKO", dur=600,
               opp={"ssl": 40, "ssa": 100, "tdl": 1, "tda": 4}),
        _fight("e2", dt.date(2026, 1, 1), False, "KO/TKO", dur=900,
               opp={"ssl": 50, "ssa": 120, "tdl": 0, "tda": 3}),
        _fight("e3", dt.date(2025, 8, 1), True, "DEC", dur=900,
               opp={"ssl": 30, "ssa": 80, "tdl": 1, "tda": 2}),
    ]
    d = espnmma.build_dossier(
        "Test Fighter", bio={"age": 30, "weight_lbs": 155, "gender": "MALE"},
        record=(20, 5, 0), own_rows=own_rows, fights=fights,
        total_ufc_fights=12, today=TODAY)
    # 200 landed over 40 minutes → 5.0 SLpM, measured.
    assert d["slpm"] == 5.0
    # Opponents landed 120 over the same 40 min → SApM 3.0;
    # 120/300 attempts landed → 60% striking defense.
    assert d["sapm"] == 3.0 and d["str_def"] == 0.6
    # Opponents 2/9 takedowns → TDD ≈ 0.778.
    assert abs(d["tdd"] - 0.778) < 1e-3
    assert d["td_acc"] == 0.375                  # 3/8 career
    assert d["kd_per100"] == 1.5                 # 3 KD / 200 SSL
    assert d["ko_losses"] == 2 and d["ko_losses_last3"] == 2
    assert d["times_finished"] == 2
    assert any("chin damage" in f for f in d["red_flags"])
    assert not any("layoff" in f for f in d["red_flags"])
    assert d["division"] == "lightweight"
    assert d["record"] == "20-5-0" and d["ufc_fights"] == 12
    # Windowed counts are disclosed to the reviewer.
    assert any("last 3 fights" in n for n in d["review"])


def test_build_dossier_thin_data_defaults_are_flagged():
    fights = [_fight("e1", dt.date(2024, 6, 1), True, "DEC", opp=None)]
    d = espnmma.build_dossier(
        "Thin Data", bio={"age": 38, "weight_lbs": 135, "gender": "MALE"},
        record=(10, 2, 0), own_rows={"e1": {"ssl": 40, "ssa": 90}},
        fights=fights, total_ufc_fights=1, today=TODAY)
    assert d["tdd"] is None and d["sapm"] is None
    assert any("takedown defense unmeasured" in n for n in d["review"])
    assert any("layoff" in f for f in d["red_flags"])       # 25 months ago
    assert any("age 38" in f for f in d["red_flags"])
    assert d["kd_per100"] == 1.0                # <100 strikes → default


def test_archetype_style_hint_beats_stats():
    arch, why = espnmma.archetype_from_stats(5.0, 0.5, 0.3, 0.2, 0.8,
                                             style_hint="Freestyle Wrestler")
    assert arch == "wrestler" and "Wrestler" in why
    arch, _ = espnmma.archetype_from_stats(3.5, 1.0, 0.3, 0.2, 0.8,
                                           style_hint="Brazilian Jiu-Jitsu")
    assert arch == "submission"
    # Without a hint the stats decide.
    assert espnmma.archetype_from_stats(5.6, 0.5, 0.3, 0.1, 0.6, None)[0] == "pressure"


def test_select_card_groups_nearest_event():
    from ufc_build import select_card
    now = dt.datetime(2026, 7, 26, 12, tzinfo=dt.timezone.utc)
    events = [
        {"id": "1", "commence_time": "2026-08-01T22:00:00Z",
         "home_team": "A One", "away_team": "B One"},
        {"id": "2", "commence_time": "2026-08-02T01:00:00Z",
         "home_team": "C Two", "away_team": "D Two"},
        {"id": "3", "commence_time": "2026-08-15T22:00:00Z",
         "home_team": "E Three", "away_team": "F Three"},
        {"id": "4", "commence_time": "2026-07-01T22:00:00Z",
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
