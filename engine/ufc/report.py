"""A written report for every fight on the UFC card (2026-11-16).

Ethan, asked whether UFC should get a written fight report like every other
sport's game report: "Yes". Every row the card writes (engine/ufc/model
.evaluate_fight: the picks and the pass list) becomes a report in the game
reports' own shape, {"fight", "title", "sections": [{"key", "title",
"blocks"}]}, so the site draws it with the same renderer (web/js/report.js)
inside each fight's card on the UFC tab. It says only what the card already
measured:

  * WHO WE THINK WINS: the call follows the price (the books' moneyline with
    their cut taken out), as every game report's does, with our fight
    model's own chance beside it and the chance the bet is priced at, which
    the humility clamp holds near the price; then the case for each corner
    from the model's own inputs (the style matchup from its STYLE_MATRIX,
    the measured striking and grappling rates, age past the sport's peak,
    red flags and short notice), and an upset flagged when more of it
    points at the underdog;
  * THE FIGHTERS: both corners' measured rates side by side;
  * HOW IT ENDS: the model's joint method distribution in words;
  * WEIGH-INS AND THE VENUE: who made weight, and what the room changes;
  * OUR BET: the pick with its price and grade, or why there is none;
  * WHAT KILLS THE BET: the card's own kill rule and each red flag.

A fight the card could not read (no dossier, no price, the clamp) still gets
the corners it has and the reason, said once.
"""
from __future__ import annotations

KEY = "fight_reports"

#: The call's word for how sure, as every game report says it (gamereport.VERDICT_WORDS).
CALL_WORDS = ((0.75, "A clear favorite"), (0.62, "Favored"), (0.55, "A lean"), (0.0, "A coin flip"))
#: A striking edge worth saying: net strikes a minute (landed less absorbed) this far apart.
STRIKE_GAP = 1.0
#: A wrestling edge: this many takedowns per 15 minutes against a defense this leaky.
TD_RATE, TD_LEAKY = 1.5, 0.65
#: A submission threat: this many attempts per 15 minutes against a defense this leaky.
SUB_RATE, SUB_LEAKY = 1.0, 0.70
#: The sport's peak years (engine/ufc/model.age_mult) and the age it falls off after.
PEAK_TOP, PAST_PEAK = 32, 35
#: The most reasons said for the pick, and for the other corner.
WHY_N, CASE_N = 4, 3
#: Each archetype the dossiers write, in words.
STYLE_WORDS = {
    "wrestler": "a wrestler", "striker_poor_tdd": "a striker with weak takedown defense",
    "striker_elite_tdd": "a striker with elite takedown defense", "pressure": "a pressure fighter",
    "counter": "a counter striker", "wild_aggressor": "an aggressive striker, loose on defense",
    "submission": "a submission grappler", "cardio_machine": "a cardio machine",
    "front_runner": "a front-runner",
}
MARKET_WORDS = {"moneyline": "to win", "method": "by method", "distance": "on distance",
                "fighter_finish": "to finish", "round": "by round", "exact_round": "in the exact round"}


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _pct(x) -> str:
    return f"{round(float(x) * 100)}%"


def _odds(v) -> str:
    x = _f(v)
    if x is None:
        return ""
    return f"+{int(x)}" if x > 0 else str(int(x))


def _style(code) -> str:
    c = str(code or "")
    return STYLE_WORDS.get(c, c.replace("_", " "))


def _sec(key: str, title: str, blocks: list) -> dict | None:
    blocks = [b for b in blocks if b]
    return {"key": key, "title": title, "blocks": blocks} if blocks else None


def _sentence(t) -> str:
    """A list item closed as a sentence, as every game report's are."""
    t = str(t or "").strip()
    return t if not t or t[-1] in ".!?" else t + "."


def _list(items) -> dict | None:
    items = [_sentence(i) for i in items if i]
    return {"type": "list", "items": items} if items else None


def _corners(row: dict) -> tuple:
    """(brief a, brief b, name a, name b): the card's two corners in its own
    order ("A vs B")."""
    fighters = [f for f in row.get("fighters") or [] if isinstance(f, dict)]
    a = fighters[0] if fighters else {}
    b = fighters[1] if len(fighters) > 1 else {}
    na, _, nb = str(row.get("fight") or "").partition(" vs ")
    return a, b, (a.get("name") or na or "A"), (b.get("name") or nb or "B")


def reasons(row: dict) -> dict:
    """{fighter name: [reason, ...]}: the case for each corner from the
    model's own inputs, each counted for the corner it helps."""
    a, b, na, nb = _corners(row)
    out = {na: [], nb: []}
    other = {na: nb, nb: na}
    brief = {na: a, nb: b}
    # The style matchup, read the model's way (engine/ufc/model.style_read).
    try:
        from .model import style_read
        shift, _lean, note = style_read(a.get("archetype", ""), b.get("archetype", ""))
    except Exception:                                        # noqa: BLE001
        shift, note = 0.0, ""
    if shift and note:
        who = na if shift > 0 else nb
        out[who].append(f"The style matchup: {_style(brief[who].get('archetype'))} against "
                        f"{_style(brief[other[who]].get('archetype'))}, {note}")
    # Striking: strikes landed less absorbed, a minute.
    net = {}
    for n in (na, nb):
        sl, sa = _f(brief[n].get("slpm")), _f(brief[n].get("sapm"))
        if sl is not None and sa is not None:
            net[n] = (sl, sa, sl - sa)
    if len(net) == 2 and abs(net[na][2] - net[nb][2]) >= STRIKE_GAP:
        best = na if net[na][2] > net[nb][2] else nb
        o = other[best]
        out[best].append(f"{best} lands {net[best][0]:.1f} significant strikes a minute and absorbs "
                         f"{net[best][1]:.1f}; {o} lands {net[o][0]:.1f} and absorbs {net[o][1]:.1f}")
    for n in (na, nb):
        o = other[n]
        td, tdd = _f(brief[n].get("td_per15")), _f(brief[o].get("tdd"))
        if td is not None and tdd is not None and td >= TD_RATE and tdd <= TD_LEAKY:
            out[n].append(f"{n} averages {td:.1f} takedowns per 15 minutes; {o} stops {_pct(tdd)} of them")
        sub, tdd2 = _f(brief[n].get("sub_att_per15")), _f(brief[o].get("tdd"))
        if sub is not None and sub >= SUB_RATE and (tdd2 is None or tdd2 <= SUB_LEAKY):
            out[n].append(f"{n} tries {sub:.1f} submissions per 15 minutes"
                          + (f", against {o}'s {_pct(tdd2)} takedown defense" if tdd2 is not None else ""))
    # Age past the sport's peak, against a corner inside it.
    ages = {n: _f(brief[n].get("age")) for n in (na, nb)}
    for n in (na, nb):
        o = other[n]
        if ages[n] is not None and ages[o] is not None and ages[n] >= PAST_PEAK and ages[o] <= PEAK_TOP:
            out[o].append(f"{n} is {int(ages[n])}, past the sport's peak years (27 to 32); {o} is {int(ages[o])}")
    # Red flags, and a short-notice corner, count for the other.
    for n in (na, nb):
        flags = [str(x) for x in brief[n].get("red_flags") or [] if x]
        if flags:
            out[other[n]].append(f"{n}'s red flags: {'; '.join(flags[:2])}")
    for note in row.get("style_notes") or []:
        for n in (na, nb):
            if str(note).startswith(f"{n} on short notice"):
                out[other[n]].append(f"{n} took the fight on short notice: no full camp")
    return out


def sec_call(row: dict) -> dict | None:
    """Who we think wins: the price's call, our model's chance beside it, and
    the case for each corner."""
    _a, _b, na, nb = _corners(row)
    side, pm, pmod, pf = row.get("pick"), _f(row.get("p_market")), _f(row.get("p_model")), _f(row.get("p_final"))
    if side not in (na, nb) or pm is None:
        return None
    other = nb if side == na else na
    fav, p = (side, pm) if pm >= 0.5 else (other, 1.0 - pm)
    dog = nb if fav == na else na
    word = next(w for bar, w in CALL_WORDS if p >= bar)
    blocks: list = [{"type": "winner", "team": fav, "other": dog, "name": fav, "other_name": dog,
                     "chance": round(p, 3), "word": word, "source": "market"}]
    nums = [f"{fav} to win, a {_pct(p)} chance by the books' moneyline with their cut taken out — the sharpest "
            f"number on the board"]
    if pmod is not None:
        mfav, mp = (side, pmod) if pmod >= 0.5 else (other, 1.0 - pmod)
        nums.append(f"Our fight model: {mfav} {_pct(mp)}" + ("" if mfav == fav else ", the other corner from the price"))
    if pf is not None:
        nums.append(f"The chance our bet is priced at, held near the price: {side} {_pct(pf)}")
    blocks.append(_list(nums))
    ev = reasons(row)
    why, case = ev[fav][:WHY_N], ev[dog][:CASE_N]
    if why:
        blocks += [{"type": "h", "text": f"Why {fav}"}, _list(why)]
    if case:
        blocks += [{"type": "h", "text": f"The case for {dog}"}, _list(case)]
    if len(ev[dog]) > len(ev[fav]):
        blocks.append({"type": "p", "text": f"More of this report points to {dog} than to {fav} "
                                            f"({len(ev[dog])} reasons to {len(ev[fav])}): the case for an upset, "
                                            f"against the price."})
    blocks.append({"type": "note", "text": "The call follows the price, the sharpest number on the board for who "
                                           "wins. Our fight model's chance sits beside it; a bet is priced at a "
                                           "blend the humility clamp holds near the price. The reasons are the "
                                           "card's own measured numbers, for each corner."})
    return _sec("verdict", "Who we think wins", blocks)


def sec_fighters(row: dict) -> dict | None:
    """Both corners' measured rates side by side."""
    a, b, na, nb = _corners(row)
    if not (a.get("has_dossier") or b.get("has_dossier")):
        return None

    def cell(br, key, how):
        v = br.get(key)
        if v is None or v == "":
            return "—"
        x = _f(v)
        if how == "pct" and x is not None:
            return _pct(x)
        if how == "num" and x is not None:
            return f"{x:.1f}"
        if how == "int" and x is not None:
            return str(int(x))
        return str(v)
    spec = (("Record", "record", ""), ("Age", "age", "int"), ("Strikes landed a minute", "slpm", "num"),
            ("Strikes absorbed a minute", "sapm", "num"), ("Takedowns per 15 minutes", "td_per15", "num"),
            ("Takedown defense", "tdd", "pct"), ("Submission tries per 15 minutes", "sub_att_per15", "num"),
            ("UFC fights on file", "covered", "int"))
    rows = [[label, cell(a, k, how), cell(b, k, how)] for label, k, how in spec]
    rows.insert(2, ["Style", _style(a.get("archetype")) or "—", _style(b.get("archetype")) or "—"])
    rows = [r for r in rows if r[1] != "—" or r[2] != "—"]
    return _sec("fighters", "The fighters", [{"type": "table", "title": f"{na} and {nb}", "head": ["", na, nb],
                                              "rows": rows}])


def sec_ends(row: dict) -> dict | None:
    """How it ends: the model's joint method distribution."""
    _a, _b, na, nb = _corners(row)
    m = row.get("method") if isinstance(row.get("method"), dict) else {}
    if not m or _f(m.get("distance")) is None:
        return None
    items = []
    for who, n in (("a", na), ("b", nb)):
        ko, sub, dec = (_f(m.get(f"{who}_{k}")) for k in ("ko", "sub", "dec"))
        if None not in (ko, sub, dec):
            items.append(f"{n}: by knockout or TKO {_pct(ko)}, by submission {_pct(sub)}, on the judges' cards "
                         f"{_pct(dec)}")
    rounds = int(_f(row.get("scheduled_rounds")) or 3)
    e_min = _f(row.get("e_minutes"))
    items.append(f"It goes the distance {_pct(m['distance'])}"
                 + (f"; about {e_min:.1f} of its {rounds * 5} minutes expected" if e_min is not None else ""))
    return _sec("ends", "How it ends", [_list(items)])


def sec_camp(row: dict) -> dict | None:
    """Weigh-ins, and what the venue changes."""
    _a, _b, na, nb = _corners(row)
    items = []
    wi = row.get("weigh_in") if isinstance(row.get("weigh_in"), dict) else {}
    said = {"made": "made weight", "missed": "missed weight", "unrecorded": "not weighed in on our record yet"}
    for who, n in (("a", na), ("b", nb)):
        st = (wi.get(who) or {}).get("state")
        if st:
            items.append(f"{n}: {said.get(st, st)}")
    env = row.get("environment") if isinstance(row.get("environment"), dict) else {}
    where = ", ".join(x for x in (env.get("venue"), env.get("city")) if x)
    if where:
        items.append(f"The fight is at {where}")
    for w in env.get("why") or []:
        if w:
            items.append(str(w))
    return _sec("camp", "Weigh-ins and the venue", [_list(items)])


def sec_bet(row: dict) -> dict | None:
    """Our bet on the fight, or why there is none."""
    if row.get("kind") == "pick":
        sel, market = row.get("selection") or row.get("pick"), row.get("market") or "moneyline"
        best = row.get("best_market") if isinstance(row.get("best_market"), dict) else {}
        odds = best.get("odds") if best.get("odds") is not None else row.get("odds")
        edge = _f(best.get("edge")) if best.get("edge") is not None else _f(row.get("edge"))
        bits = [f"{sel} {MARKET_WORDS.get(market, market)}" + (f" at {_odds(odds)}" if _odds(odds) else "")
                + (f" ({row.get('book')})" if row.get("book") and market == "moneyline" else "")]
        if edge is not None:
            bits.append(f"an edge of {edge * 100:.1f} points over the price")
        if row.get("grade_score") is not None:
            bits.append(f"grade {row['grade_score']}" + (f" ({row['grade_label']})" if row.get("grade_label") else ""))
        if _f(row.get("stake_units")):
            bits.append(f"{_f(row['stake_units']):g} unit(s)")
        return _sec("bet", "Our bet", [{"type": "p", "text": ": ".join([bits[0], ", ".join(bits[1:])]) + "."
                                        if len(bits) > 1 else bits[0] + "."}])
    why = str(row.get("why") or "").strip()
    return _sec("bet", "Our bet", [{"type": "p", "text": f"No bet on this fight: {why}." if why else "No bet on this fight."}])


def sec_kill(row: dict) -> dict | None:
    """What kills the bet: the card's own rule and each corner's red flags."""
    a, b, na, nb = _corners(row)
    items = []
    if row.get("kill_if"):
        items.append(f"Voids it: {row['kill_if']}")
    for br, n in ((a, na), (b, nb)):
        flags = [str(x) for x in br.get("red_flags") or [] if x]
        if flags:
            items.append(f"{n}'s red flags: {'; '.join(flags)}")
    return _sec("kill", "What kills the bet", [_list(items)])


def build(row: dict) -> dict | None:
    """One fight's report, or None for a row with no fight."""
    if not isinstance(row, dict) or " vs " not in str(row.get("fight") or ""):
        return None
    _a, _b, na, nb = _corners(row)
    sections = [s for s in (sec_call(row), sec_fighters(row), sec_ends(row), sec_camp(row), sec_bet(row),
                            sec_kill(row)) if s]
    words = sum(len(str(t).split()) for s in sections for blk in s["blocks"]
                for t in ([blk.get("text")] + list(blk.get("items") or [])) if t)
    return {"fight": str(row["fight"]), "game": str(row["fight"]), "title": f"{na} vs {nb}",
            "division": row.get("division") or "", "sport": "ufc", "minutes": max(1, round(words / 230)),
            "sections": sections}


def attach(out: dict) -> str:
    """``out["fight_reports"]``: a report for every fight the card wrote
    (its picks and its pass list). One line for the build log; never raises."""
    try:
        rows = [r for r in list(out.get("picks") or []) + list(out.get("pass_list") or []) if isinstance(r, dict)]
        reports = [r for r in (build(x) for x in rows) if r]
        out[KEY] = reports
        return f"Fight reports: {len(reports)} fight(s)"
    except Exception as exc:                                 # noqa: BLE001
        out.pop(KEY, None)
        return f"⚠️  Fight reports skipped ({type(exc).__name__}: {exc})"
