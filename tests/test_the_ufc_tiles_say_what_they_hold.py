"""The UFC tab's tiles say what they hold (USEREYES1, 18 November 2026).

Walk 7 read the UFC tab as a visitor: the card's tile said "2026-11-20", a
date as the database keeps it, and the record's said "Flat ROI +22.2%" over
"+2.35u return on investment". The stakes are not flat (10.59 units staked
across 43 fights), the 22.2% is the return on those, and the 2.35 units are
the profit, not a return on investment. What these hold:

  * the card's date reads as every other date on the site ("Fri, Nov 20");
  * the record's tile is "ROI", with the units won on the units staked
    under it, a loss with a true minus.

    python3 tests/test_the_ufc_tiles_say_what_they_hold.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")


def test_the_cards_date_reads_as_a_date():
    assert 'statCardHTML("calendar", "Card", escapeHtml(formatGameDate(d.event_date) || d.event_date || "—"),' in MORE
    assert 'escapeHtml(d.event_date || "—")' not in MORE


def test_the_record_tile_is_the_return_on_what_was_staked():
    assert 'statCardHTML("chart", "Flat ROI"' not in MORE and "toFixed(2)}u return on investment`" not in MORE
    i = MORE.index('statCardHTML("chart", "ROI",')
    tile = MORE[i:i + 400]
    assert "fmtRoi(u.roi)" in tile and "u.units_staked" in tile and "u staked`" in tile, tile
    assert "trueMinus(" in tile, tile
    # The number it reads is net over staked (engine/ledger.performance).
    led = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    assert '"units_staked": round(staked_u, 2), "net_units": round(net_u, 2),' in led
    assert '"roi": (net_u / staked_u) if staked_u else 0.0,' in led


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
