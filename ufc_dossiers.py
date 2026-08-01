#!/usr/bin/env python3
"""Draft fighter dossiers for the next UFC card — automatically.

    python3 ufc_dossiers.py              # draft everyone on the next card
    python3 ufc_dossiers.py --refresh    # re-fetch auto entries too
    python3 ufc_dossiers.py "Jon Jones"  # draft specific fighters by name

Reads the upcoming card from the odds feed (the events list is free),
looks each fighter up on ESPN's public MMA API, and writes drafted
dossiers into ``data/ufc_dossiers.json`` — keyed by the odds feed's
spelling so the model matches them automatically. Rates are measured
from per-fight data (strikes over real fight minutes, opponents' rows
for the defensive numbers), not copied from a stats label.

What it will NOT do: overwrite anything a human wrote. Hand-made entries
and previously drafted entries are left alone unless ``--refresh`` is
passed (and even then, only auto-drafted entries are re-fetched).

The two-minute review this leaves you: each drafted entry carries a
``review`` list of every estimated number, and auto red flags (chin
damage, layoffs, age) BLOCK bets until you confirm or delete them.
"no dossier, no bet" becomes "no review, no bet" — as it should be.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.secrets import load_local_secrets
from engine.sources.fetch import DataUnavailable

DOSSIERS = Path("data/ufc_dossiers.json")
README = ("Drafted by ufc_dossiers.py from UFCStats.com + your own edits. "
          "Review each entry's 'review' notes; red_flags block bets until "
          "confirmed or deleted. Hand edits are never overwritten.")


def card_fighters() -> tuple[str, list[str]]:
    """(event_date, fighter names) for the next card.

    Cached events first; on a cold cache, a LIVE events pull — that
    endpoint is free on The Odds API (event lists don't count against
    the credit quota), so drafting dossiers never waits on the budget."""
    from engine.sources import oddsapi
    from ufc_build import select_card
    key = oddsapi.get_api_key()
    try:
        events = oddsapi.list_events(key, sport="ufc", cache_only=True)
    except oddsapi.OddsAPIError:
        events = oddsapi.list_events(key, sport="ufc")
    label, card = select_card(events)
    names: list[str] = []
    for ev in card:
        for n in (ev.get("home_team", ""), ev.get("away_team", "")):
            if n and n not in names:
                names.append(n)
    return label, names


def load_book() -> dict:
    book = json.loads(DOSSIERS.read_text()) if DOSSIERS.exists() else {}
    book.setdefault("_readme", README)
    return book


def needs_draft(book: dict, name: str, refresh: bool = False) -> bool:
    """Is this fighter missing, or an auto entry worth re-fetching?

    Never true for a hand-written entry. The one thing this tool must not
    do is overwrite something a human decided.
    """
    existing = book.get(name)
    if not isinstance(existing, dict):
        return True
    auto = str(existing.get("source", "")).endswith("-auto")
    # Auto drafts from an older schema (no career_fights marker) are
    # re-drafted automatically — their rates predate the coverage fix.
    stale = auto and "career_fights" not in existing
    return stale or (refresh and auto)


def draft(names: list[str], refresh: bool = False, limit: int | None = None,
          verbose: bool = False) -> tuple[dict, list, list, list]:
    """Draft dossiers for ``names``. Returns (book, drafted, kept, missing).

    ``limit`` caps how many fighters are FETCHED in one call. A fighter is
    ~50 small cached requests and takes about half a minute cold, so the
    launcher's 60-second refresh drafts a few per tick and lets a 34-bout
    card fill itself in over several minutes rather than stalling one
    refresh for half an hour. Progress is written to disk as it goes, so
    every tick keeps what it earned.
    """
    book = load_book()
    from engine.sources.espnmma import fetch_dossier, octagon_styles, _norm
    styles = octagon_styles()      # one request; style hints for ranked names
    drafted, kept, missing = [], [], []
    for name in names:
        if not needs_draft(book, name, refresh):
            kept.append(name)
            continue
        if limit is not None and len(drafted) + len(missing) >= limit:
            continue                     # next tick picks this one up
        if verbose:
            print(f"  fetching {name} … (a fighter takes ~30s the first time)")
        try:
            d = fetch_dossier(name, style_hint=styles.get(_norm(name)))
        except DataUnavailable as exc:
            if verbose:
                print(f"  ⚠️  {name}: {exc}")
            missing.append(name)
            continue
        if d is None:
            missing.append(name)
            continue
        book[name] = d
        # Record the gym on every draft. A camp CHANGE is only visible
        # because we remember where he was last time — the same
        # diff-our-own-history trick that finds NFL trades without a news
        # feed. It needs two drafts to see one, which is why it is worth
        # writing down now rather than when we want it.
        if d.get("gym"):
            from engine.ufc import camp as _camp
            moved = _camp.record_gym(name, d["gym"])
            if verbose and moved["changed"]:
                print(f"  📍 {name} changed camps: "
                      f"{moved['changed_from']} → {moved['gym']}")
        drafted.append(name)
        DOSSIERS.write_text(json.dumps(book, indent=2))   # save as we go

    DOSSIERS.write_text(json.dumps(book, indent=2))
    return book, drafted, kept, missing


def _fighters(book: dict):
    return [(k, v) for k, v in book.items()
            if isinstance(v, dict) and not k.startswith("_")]


def _review(args) -> None:
    """The two-minute job the drafting tool leaves behind.

    Red flags exist to BLOCK bets until a human confirms them, so they
    have to be reviewable without hand-editing JSON — one fat-fingered
    comma silently unbets a whole card."""
    if not DOSSIERS.exists():
        print("No dossiers yet — run python3 ufc_dossiers.py first.")
        return
    book = json.loads(DOSSIERS.read_text())

    if args.clear:
        target = args.clear.strip().lower()
        hit = [k for k, _ in _fighters(book) if k.strip().lower() == target]
        if not hit:
            close = [k for k, _ in _fighters(book) if target in k.lower()]
            print(f"No dossier named {args.clear!r}."
                  + (f" Did you mean: {', '.join(close)}?" if close else ""))
            return
        name = hit[0]
        had = book[name].get("red_flags") or []
        if not had:
            print(f"{name} has no red flags — nothing to clear.")
            return
        book[name]["red_flags"] = []
        book[name]["flags_cleared_by_hand"] = True
        DOSSIERS.write_text(json.dumps(book, indent=2))
        print(f"Cleared {len(had)} red flag(s) on {name}:")
        for f in had:
            print(f"    - {f}")
        print("\nThat fight is now bettable if it also clears the model's "
              "clamp and gate.\nThe tool will not re-add these unless you "
              "re-draft with --refresh.")
        return

    flagged = [(k, v) for k, v in _fighters(book) if v.get("red_flags")]
    total = len(_fighters(book))
    if not flagged:
        print(f"{total} dossier(s), no red flags. Nothing blocking a bet.")
        return
    print(f"{len(flagged)} of {total} fighter(s) carry a red flag. Each one "
          f"BLOCKS\nevery bet on that fight until you clear it.\n")
    for name, d in flagged:
        print(f"  {name}  ({d.get('division') or '?'}, age {d.get('age') or '?'}, "
              f"record {d.get('record', '?')})")
        for f in d.get("red_flags") or []:
            print(f"      ⚑ {f}")
        print(f"      clear with:  python3 ufc_dossiers.py --clear \"{name}\"")
        print()
    print("Leaving a flag in place is a decision, not a delay — it means the "
          "model\npasses that fight. Clear one only when you have actually "
          "checked it.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*",
                    help="specific fighters (default: everyone on the next card)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch entries previously drafted by this tool")
    ap.add_argument("--review", action="store_true",
                    help="list every red flag blocking a bet, with context")
    ap.add_argument("--clear", metavar="FIGHTER",
                    help="clear the red flags on one fighter — say you have "
                         "checked them and accept the risk")
    args = ap.parse_args()
    load_local_secrets()

    if args.review or args.clear:
        _review(args)
        return

    if args.names:
        label, names = "requested", list(args.names)
    else:
        try:
            label, names = card_fighters()
        except Exception as exc:  # noqa: BLE001
            print(f"Could not read the upcoming card from the odds cache ({exc}).\n"
                  f"Run the launcher once so the UFC odds cache fills, or pass "
                  f"fighter names directly: python3 ufc_dossiers.py \"Name\" …")
            return
        if not names:
            print("No UFC card inside the 8-day odds window — nothing to draft.")
            return

    book, drafted, kept, missing = draft(names, refresh=args.refresh,
                                         verbose=True)

    print(f"\nUFC dossiers · card {label}: {len(drafted)} drafted, "
          f"{len(kept)} kept (hand-made or already drafted), "
          f"{len(missing)} not found → {DOSSIERS}")
    if missing:
        print("  Not found on ESPN (debutants/spelling): " + ", ".join(missing)
              + "\n  Those fights stay on the pass list — which is correct.")
    def num(v):
        return "—" if v is None else v

    def pct(v):
        return "—" if v is None else f"{int(v * 100)}%"

    for name in drafted:
        d = book[name]
        flags = " · ".join(d.get("red_flags") or []) or "none"
        print(f"\n  {name}  ({d.get('division') or '?'}, age {d.get('age') or '?'}, "
              f"record {d.get('record', '?')}, stats for {d.get('ufc_fights', 0)} "
              f"of {d.get('career_fights', '?')} fights)")
        print(f"    striking {num(d.get('slpm'))}/{num(d.get('sapm'))} SLpM/SApM · "
              f"TD {num(d.get('td_per15'))}/15 at {pct(d.get('td_acc'))} · "
              f"TDD {pct(d.get('tdd'))} · subs {num(d.get('sub_att_per15'))}/15")
        print(f"    archetype {d.get('archetype')} · red flags: {flags}")
        if d.get("ufc_fights", 0) == 0:
            print("    ⚠️  no stat coverage — the model treats this fighter "
                  "as unmodelable (correct for regional records)")
    if drafted:
        print("\nReview: open data/ufc_dossiers.json — check each 'review' "
              "note, fix archetypes you know better, and delete red flags "
              "you've verified. Red flags block bets until you do.")


if __name__ == "__main__":
    main()
