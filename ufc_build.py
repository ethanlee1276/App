#!/usr/bin/env python3
"""Build the UFC (Scalpy MMA) card: dossiers → model → clamp → gate.

    python3 ufc_build.py --cached-odds --out web/data/ufc.json

Upcoming bouts and moneylines come from The Odds API (each bout is one
event; budgeted like every other sport). Fighter dossiers are OURS:
``data/ufc_dossiers.json``, keyed by normalized fighter name, following
the spec's §3 fields — no dossier, no bet, and the pass list says so.
Copy ``data/ufc_dossiers.sample.json`` to get started.
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from engine.secrets import load_local_secrets
from engine.ufc.model import run_card

DOSSIERS = Path("data/ufc_dossiers.json")


def load_dossiers() -> dict:
    from engine.sources.oddsapi import normalize_name
    if not DOSSIERS.exists():
        return {}
    raw = json.loads(DOSSIERS.read_text())
    # Skip the _readme note and anything that isn't a dossier dict.
    return {normalize_name(k): v for k, v in raw.items()
            if isinstance(v, dict) and not k.startswith("_")}


def select_card(events: list[dict],
                now: datetime.datetime | None = None) -> tuple[str, list[dict]]:
    """The nearest card from an events list: bouts within 8 days, grouped
    to the earliest event date (+1 day for late-night main cards).
    Returns (event_date_iso, bouts) — ("", []) when nothing is upcoming."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    upcoming = []
    for ev in events:
        try:
            t = datetime.datetime.fromisoformat(
                (ev.get("commence_time") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if now - datetime.timedelta(hours=12) <= t <= now + datetime.timedelta(days=8):
            upcoming.append((t, ev))
    upcoming.sort(key=lambda x: x[0])
    if not upcoming:
        return "", []
    first_day = upcoming[0][0].date()
    card = [ev for t, ev in upcoming if (t.date() - first_day).days <= 1]
    return first_day.isoformat(), card


def best_h2h(payload: dict, name_a: str, name_b: str) -> dict:
    """Best price per fighter across books from an event-odds payload."""
    best: dict = {}
    for bm in payload.get("bookmakers", []) or []:
        for mkt in bm.get("markets", []) or []:
            if mkt.get("key") != "h2h":
                continue
            for o in mkt.get("outcomes", []) or []:
                nm, price = o.get("name", ""), o.get("price")
                if price is None:
                    continue
                if nm not in best or price > best[nm][0]:
                    best[nm] = (int(price), bm.get("title", bm.get("key", "")))
    out = {"fighter_a": name_a, "fighter_b": name_b}
    if name_a in best:
        out["a_odds"], out["book"] = best[name_a]
    if name_b in best:
        out["b_odds"] = best[name_b][0]
        out.setdefault("book", best[name_b][1])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--odds", action="store_true")
    ap.add_argument("--cached-odds", action="store_true")
    ap.add_argument("--out", default="web/data/ufc.json")
    args = ap.parse_args()
    load_local_secrets()

    out: dict = {"generated_at": datetime.datetime.now()
                 .isoformat(timespec="seconds")}
    dossiers = load_dossiers()

    fights, event_label = [], ""
    if args.odds or args.cached_odds:
        from engine.sources import oddsapi
        from engine.sources.oddsapi import normalize_name
        try:
            key = oddsapi.get_api_key()
            events = oddsapi.list_events(key, sport="ufc",
                                         cache_only=args.cached_odds and not args.odds)
            event_label, card = select_card(events)
            if card:
                for ev in card:
                    a, b = ev.get("home_team", ""), ev.get("away_team", "")
                    try:
                        payload, _q = oddsapi.fetch_event_odds(
                            ev["id"], key, markets=["h2h"], sport="ufc",
                            cache_only=args.cached_odds and not args.odds)
                        prices = best_h2h(payload, a, b)
                    except oddsapi.OddsAPIError:
                        prices = {"fighter_a": a, "fighter_b": b}
                    da = dossiers.get(normalize_name(a))
                    db = dossiers.get(normalize_name(b))
                    fights.append({"a": da, "b": db, "prices": prices,
                                   "division": (da or db or {}).get("division", "")})
        except oddsapi.OddsAPIError as exc:
            out["odds_error"] = str(exc)

    if not fights:
        out.update(status="no_card",
                   note=out.get("odds_error",
                                "No UFC bouts inside the 8-day window (or no "
                                "odds requested). The engine — scorecard, "
                                "joint method model, clamp, gate — is built "
                                "and tested; it runs when a card is."))
    else:
        result = run_card(fights)
        out.update(status="card", event_date=event_label,
                   dossiers_loaded=len(dossiers), **result)

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    if out.get("status") == "card":
        c = out["counts"]
        print(f"UFC {event_label}: {c['fights']} bouts, {len(dossiers)} "
              f"dossiers → {c['picks']} pick(s), {c['passes']} pass(es). "
              f"Wrote {args.out}")
        if out.get("no_qualifying"):
            print("No qualifying plays on this card — a valid output.")
        if not dossiers:
            print("0 dossiers loaded — copy data/ufc_dossiers.sample.json to "
                  "data/ufc_dossiers.json and fill in fighters. No dossier, "
                  "no bet.")
    else:
        print(f"UFC: {out['status']}. Wrote {args.out}")


if __name__ == "__main__":
    main()
