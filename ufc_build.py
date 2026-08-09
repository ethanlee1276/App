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


def _lookup(dossiers: dict, name: str):
    """(dossier, closest-name-we-hold) for a fighter on the card.

    THE TWO CAUSES OF `no_dossier` LOOK IDENTICAL TODAY.
    `dossiers.get(normalize_name(a))` is an exact hit or nothing, so "we
    have never written a dossier for this fighter" and "we have one,
    spelled differently from the odds feed" both come out as the same pass
    line — and only the second is fixed by editing one line of JSON. Two
    of the twelve bouts on 2026-08-08 passed for want of a dossier with no
    way to tell which kind they were without opening the file.

    So a miss also reports the CLOSEST name we hold. It does NOT match on
    it. A fighter is not a name similarity, and pricing a bout against the
    wrong man's record is worse than not pricing it at all — the whole
    point of `no dossier, no bet`. The pass line gains "closest we hold is
    X", and a person decides in one glance whether that is a spelling fix
    or a genuinely absent fighter.
    """
    # Imported here, like `load_dossiers` does: this module is also run
    # as a script and the engine import is not free at import time.
    from engine.sources.oddsapi import normalize_name
    key = normalize_name(name)
    d = dossiers.get(key)
    if d is not None:
        return d, None
    return None, _closest(key, dossiers)


def _closest(key: str, dossiers: dict) -> str | None:
    """The nearest dossier key, when one is near enough to be worth naming.

    TWO TESTS, because string distance alone misses the commonest case.
    `jose aldo junior` against `jose aldo` scores 0.72 — under any cutoff
    loose enough to be safe — and yet it is obviously the same man with a
    suffix the folder does not know (`Jr.` is in `normalize_name`'s suffix
    list, the spelled-out `Junior` is not). An extra middle name does the
    same thing.

    So: every token of one name contained in the other, with at least two
    tokens to match on, OR a high string similarity. The token test
    catches added words, the distance test catches altered letters, and
    neither is allowed to pick a fighter — see `_lookup`.

    Cutoffs are deliberately tight. Anything looser starts proposing a
    different fighter in the same division, which is exactly the
    suggestion someone would act on by mistake.
    """
    import difflib
    if not key or not dossiers:
        return None
    want = set(key.split())
    if len(want) >= 2:
        # Longest containment wins: between `jon jones` and `jon`, the
        # fuller name is the better guess at who was meant.
        subs = [k for k in dossiers
                if len(k.split()) >= 2
                and (set(k.split()) <= want or want <= set(k.split()))]
        if subs:
            return max(subs, key=lambda k: len(k.split()))
    hit = difflib.get_close_matches(key, list(dossiers), n=1, cutoff=0.82)
    return hit[0] if hit else None


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
    ap.add_argument("--why", action="store_true",
                    help="group the passes by reason — missing data, no "
                         "posted price, or the model refusing")
    ap.add_argument("--cached-odds", action="store_true")
    ap.add_argument("--out", default="web/data/ufc.json")
    args = ap.parse_args()
    load_local_secrets()

    out: dict = {"generated_at": datetime.datetime.now()
                 .isoformat(timespec="seconds")}
    dossiers = load_dossiers()

    fights, event_label = [], ""
    near: list = []      # (name on the card, closest dossier we hold)
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
                    da, na = _lookup(dossiers, a)
                    db, nb = _lookup(dossiers, b)
                    for who, close in ((a, na), (b, nb)):
                        if close:
                            near.append((who, close))
                    fights.append({"a": da, "b": db, "prices": prices,
                                   "division": (da or db or {}).get("division", "")})
            # §8 — where the card is. One fact per event, recorded by hand
            # because the odds feed carries no venue; it decides cage size
            # and altitude, which reshape every method and distance price.
            from engine.ufc import environment as _env
            venue = _env.card_for(event_label, _env.load_cards())
            out["card_venue"] = venue
            for f in fights:
                f["prices"]["venue"] = venue.get("venue", "")
                f["prices"]["city"] = venue.get("city", "")
        except oddsapi.OddsAPIError as exc:
            out["odds_error"] = str(exc)

    # Weigh-ins, before the model runs: a missed weight is appended to that
    # fighter's red_flags, and approval_gate already refuses to bet through
    # a red flag. The rule every card prints in `kill_if` finally has
    # something enforcing it.
    weigh_store = {}
    if fights:
        from engine.ufc import weighin
        weigh_store = weighin.load_store()
        for f in fights:
            weighin.annotate_fight(f, weigh_store)
        out["weigh_ins"] = weighin.card_summary(fights)

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
        # Carry the per-fight weigh-in state onto the rendered rows so the
        # page can show "not recorded" rather than implying "made weight".
        by_fight = {f"{(f.get('prices') or {}).get('fighter_a', '')} vs "
                    f"{(f.get('prices') or {}).get('fighter_b', '')}":
                    f.get("weigh_in") for f in fights}
        for row in list(out.get("picks", [])) + list(out.get("pass_list", [])):
            wi = by_fight.get(row.get("fight"))
            if wi:
                row["weigh_in"] = wi

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))

    # Learning engine: journal the card's picks at their real prices and
    # settle any open ones whose fights have since happened (ESPN MMA
    # results). Its own probation bucket — never the headline record.
    # Never let the journal break a build.
    if args.odds or args.cached_odds:
        try:
            from engine import ledger
            lconn = ledger.connect()
            logged = ledger.log_ufc_picks(lconn, out)
            open_n = lconn.execute(
                "SELECT COUNT(*) FROM bets WHERE status='open' "
                "AND sport='ufc'").fetchone()[0]
            settled = ledger.settle_ufc(lconn) if open_n else 0
            if logged or settled:
                ledger.export_json(lconn, "web/data/record.json")
                print(f"UFC journal: {logged} pick(s) logged, {settled} "
                      f"settled — see the Record tab")
        except Exception as exc:
            print(f"⚠️  UFC journal skipped: {exc}")

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
        # WHY, grouped, because "12 passes" and "why 12 passes" are
        # different questions and only the second one is actionable. Two
        # cards in a row produced nothing and the counts alone could not
        # say whether that was missing data or a model correctly refusing —
        # which are opposite problems with opposite fixes.
        if args.why:
            from collections import Counter
            # `pass_list`, not `passes` — the latter is a COUNT inside
            # `counts`. The first version of this read the count's key,
            # found nothing iterable, and printed a header with no rows
            # under it, which is a diagnostic that diagnoses nothing.
            codes = Counter((p.get("reason_code") or "other")
                            for p in out.get("pass_list", []))
            print("\n  why each bout passed:")
            if not codes:
                print("    (no pass records in the payload — the model "
                      "returned none, which is itself the finding)")
            for code, n in codes.most_common():
                print(f"    {n:>3}  {code}")
            near = out.get("near_misses") or [
                p for p in out.get("pass_list", []) if p.get("near_miss")]
            if near:
                print(f"\n  {len(near)} near miss(es) — priced, gated, "
                      f"and close:")
                for p in near[:6]:
                    # `fight`, which is what `base` actually carries. The
                    # first version guessed `fighter`/`bout`, neither of
                    # which exists, and printed "?" for every row — the
                    # one part of the line you cannot act on without.
                    print(f"    {p.get('fight', '?')}")
                    print(f"      {p.get('why', '')[:96]}")
            # THE MODEL'S STRONGEST OPINIONS, WHICH WERE THE ONLY PASSES
            # WITH NO NAMES ON THEM. A clamp kill is not a quiet refusal —
            # it is the model claiming a bigger edge than the humility
            # clamp will let it act on, which is either the best read on
            # the card or a dossier that is wrong about somebody. Those
            # are opposite problems and neither is visible from the tally.
            #
            # On the 2026-08-08 card two of seven bouts ended here and the
            # output named neither, so the only actionable thing about
            # them was a number 2.
            killed = [p for p in out.get("pass_list", [])
                      if p.get("reason_code") == "clamp_kill"]
            if killed:
                print(f"\n  {len(killed)} bout(s) the model wanted and the "
                      f"clamp refused:")
                for p in killed:
                    print(f"    {p.get('fight', '?')}")
                    print(f"      {p.get('why', '')[:96]}")
            # WHICH BOUTS AND WHICH FIGHTERS. A count of data gaps is not
            # a to-do list; the names are. These are the ones a dossier or
            # a fight history would turn into a priced bout.
            gaps = [p for p in out.get("pass_list", [])
                    if p.get("reason_code") in ("no_dossier", "no_data")]
            if gaps:
                print(f"\n  {len(gaps)} bout(s) the model could not price "
                      f"for want of data:")
                for p in gaps:
                    print(f"    {p.get('fight', '?')}")
                    print(f"      {p.get('why', '')[:96]}")
                    # Which KIND of gap, in one line. A near name is a
                    # one-line JSON fix; no near name is a fighter we have
                    # never written up.
                    for who, close in near:
                        if who in (p.get("fight") or ""):
                            print(f"      ↳ no dossier under \"{who}\" — the "
                                  f"closest we hold is \"{close}\". If that is "
                                  f"the same man, fix the spelling in "
                                  f"data/ufc_dossiers.json; the lookup is "
                                  f"exact and never guesses.")
            print("\n  READ IT LIKE THIS")
            print("    mostly no_data   -> dossiers are missing, not the "
                  "model's doing. Check `python3 launch.py` drafted them.")
            print("    mostly no_price  -> books had not posted h2h yet; "
                  "rebuild closer to the card.")
            print("    mostly gated     -> the model priced every bout and "
                  "refused. That is the system working, and the near")
            print("                        misses above say by how much.")
    else:
        print(f"UFC: {out['status']}. Wrote {args.out}")


if __name__ == "__main__":
    main()
