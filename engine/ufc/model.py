"""Scalpy MMA — the UFC model. Distributions of outcomes, never predictions.

MMA is not basketball: one event, no law of large numbers, four-ounce
gloves. The doctrine, as enforced code:

* **weighted scorecard** — style matchup is the highest-weight input (25%),
  then grappling and striking differentials, durability, cardio,
  situational. The differential maps to a win probability HARD-CAPPED at
  88%: nobody is safer than that in four-ounce gloves, and any model
  output above it is a model error;
* **method of victory is a JOINT distribution** — P(A by KO) = P(A wins) ×
  P(KO | A wins); the six outcomes must sum to 1.00 or the model is
  broken (validated in code and tests). Conditionals start from divisional
  base rates and shift on knockdown rates, chin damage, and sub threat;
* **durability beats finishing** — being finishable is a stable trait;
  finishing ability is noisy. The opponent's durability history weighs
  ~1.5× the fighter's finishing history in the distance model;
* **the humility clamp** — w by information quality (0.60 unpriced news →
  0.25 standard → 0.12 thin samples → NO BET for debutants), kill rule at
  a 15-point disagreement;
* **the approval gate** — edge ≥4 pts over break-even (6 on props), EV
  ≥5%, price never worse than −300 (MMA favorites above that are traps),
  camp red flags block, max 3 bets a card, 1 per fight;
* **the pass list** — every fight NOT bet gets one line on why. A 13-fight
  card with zero bets is a completely valid output.

Staking is one-fifth Kelly (model error runs higher than NBA), capped at
2.5% per bet.
"""

from __future__ import annotations

WIN_CAP = 0.88
CLAMP_KILL_DIFF = 0.15
GATE_EDGE_ML = 0.04
GATE_EDGE_PROP = 0.06
GATE_MIN_EV = 0.05
GATE_WORST_PRICE = -300
MAX_BETS_PER_CARD = 3
KELLY_FRACTION = 0.20
STAKE_CAP = 0.025

# §6.1 weights — style is the single highest-weight input.
WEIGHTS = {"style": 0.25, "grappling": 0.20, "striking": 0.20,
           "durability": 0.10, "cardio": 0.10, "situational": 0.10,
           "fight_iq": 0.05}

# §6.1 differential → P(win) anchors (interpolated between).
DIFF_TO_P = ((0.0, 0.50), (0.5, 0.56), (1.0, 0.62), (1.5, 0.68),
             (2.0, 0.73), (2.5, 0.78), (3.0, 0.82), (4.0, 0.88))

# §7.2 divisional outcome rates (KO, SUB, DEC) — anchors, recompute yearly.
DIVISION_RATES = {
    "heavyweight": (0.52, 0.11, 0.37), "light_heavyweight": (0.43, 0.17, 0.37),
    "middleweight": (0.40, 0.15, 0.40), "welterweight": (0.37, 0.15, 0.43),
    "lightweight": (0.35, 0.13, 0.47), "featherweight": (0.30, 0.14, 0.52),
    "bantamweight": (0.28, 0.15, 0.55), "flyweight": (0.25, 0.18, 0.53),
    "w_bantamweight": (0.22, 0.20, 0.57), "w_flyweight": (0.18, 0.20, 0.60),
    "w_strawweight": (0.13, 0.20, 0.66),
}
DEFAULT_RATES = (0.33, 0.19, 0.47)

# §5.2 style interaction: (a_archetype, b_archetype) → (diff shift toward A,
# method lean for the favored side, note). Mirrored automatically.
STYLE_MATRIX = {
    ("wrestler", "striker_poor_tdd"): (0.8, "dec",
        "wrestler vs poor TDD — control decision or GnP TKO"),
    ("striker_elite_tdd", "wrestler"): (0.6, "ko",
        "elite TDD vs one-dimensional wrestler — wrestlers get hurt failing shots"),
    ("pressure", "counter"): (0.4, "dec",
        "pressure denies the counter striker space"),
    ("counter", "wild_aggressor"): (0.7, "ko",
        "counter striker vs defensively loose aggressor — the highest "
        "KO-probability matchup in the sport"),
    ("submission", "wrestler"): (-0.4, "dec",
        "wrestlers stay on top and avoid subs"),
    ("submission", "striker_poor_tdd"): (0.7, "sub",
        "grappler vs poor TDD — submission path"),
    ("cardio_machine", "front_runner"): (0.5, "dec",
        "cardio machine drowns the front-runner late"),
}


def _interp(diff: float) -> float:
    d = abs(diff)
    pts = DIFF_TO_P
    if d >= pts[-1][0]:
        p = pts[-1][1]
    else:
        p = pts[0][1]
        for (d0, p0), (d1, p1) in zip(pts, pts[1:]):
            if d0 <= d <= d1:
                p = p0 + (p1 - p0) * (d - d0) / (d1 - d0)
                break
    p = min(p, WIN_CAP)
    return p if diff >= 0 else round(1.0 - p, 4)


def age_mult(age: int | None) -> float:
    """Peak 27-32; decline from 33, sharp after 35."""
    if age is None or 27 <= age <= 32:
        return 1.00
    if age < 27:
        return 0.99
    return {33: 0.97, 34: 0.94, 35: 0.90}.get(age, 0.85)


def style_read(a_arch: str, b_arch: str) -> tuple[float, str | None, str]:
    key = (a_arch, b_arch)
    if key in STYLE_MATRIX:
        return STYLE_MATRIX[key]
    rev = (b_arch, a_arch)
    if rev in STYLE_MATRIX:
        shift, lean, note = STYLE_MATRIX[rev]
        return -shift, lean, note
    return 0.0, None, "no strong style read"


def _clamp3(x: float) -> float:
    return max(-3.0, min(3.0, x))


def scorecard(a: dict, b: dict) -> tuple[float, list[str]]:
    """Weighted differential (A positive) from both dossiers."""
    notes = []
    style_shift, _lean, style_note = style_read(a.get("archetype", ""),
                                                b.get("archetype", ""))
    notes.append(f"Style: {style_note}")

    def sdiff(fa, fb, scale):
        return _clamp3((fa - fb) / scale)

    striking = sdiff((a.get("slpm", 3.5) - a.get("sapm", 3.5)),
                     (b.get("slpm", 3.5) - b.get("sapm", 3.5)), 1.5)
    grappling = _clamp3(
        sdiff(a.get("td_per15", 1.0) * a.get("td_acc", 0.4),
              b.get("td_per15", 1.0) * b.get("td_acc", 0.4), 1.0)
        + sdiff(a.get("tdd", 0.6), b.get("tdd", 0.6), 0.25)
        + sdiff(a.get("ctrl_per15", 2.0), b.get("ctrl_per15", 2.0), 3.0))
    durability = _clamp3(sdiff(b.get("ko_losses", 0) + 2 * b.get("ko_losses_last3", 0),
                               a.get("ko_losses", 0) + 2 * a.get("ko_losses_last3", 0),
                               1.5))
    cardio = _clamp3(sdiff(b.get("r3_decay", 0.15), a.get("r3_decay", 0.15), 0.15))
    situational = _clamp3(3.0 * (age_mult(a.get("age")) - age_mult(b.get("age")))
                          - 0.5 * (len(a.get("red_flags", []))
                                   - len(b.get("red_flags", []))))

    diff = (WEIGHTS["style"] * 4 * style_shift
            + WEIGHTS["striking"] * striking
            + WEIGHTS["grappling"] * grappling
            + WEIGHTS["durability"] * durability
            + WEIGHTS["cardio"] * cardio
            + WEIGHTS["situational"] * situational)
    return round(diff, 3), notes


def win_probability(a: dict, b: dict) -> tuple[float, list[str]]:
    """P(A wins), scorecard-driven, hard-capped at 88%."""
    diff, notes = scorecard(a, b)
    p = _interp(diff)
    p = min(max(p, 1.0 - WIN_CAP), WIN_CAP)
    return round(p, 4), notes


def method_conditionals(f: dict, opp: dict, division: str) -> dict:
    """P(method | this fighter wins) — divisional prior, shifted by traits,
    normalized so ko+sub+dec = 1."""
    ko, sub, dec = DIVISION_RATES.get(division, DEFAULT_RATES)
    # Knockdown rate & the opponent's chin push KO; the chin doesn't heal.
    ko *= 1.0 + 0.8 * min(1.5, f.get("kd_per100", 1.0) / 2.0)
    ko *= 1.0 + 0.35 * min(3, opp.get("ko_losses_last3", 0))
    # Sub threat needs BOTH an active hunter and a takedown-vulnerable
    # opponent; a wrestler on top produces decisions, not submissions.
    if f.get("archetype") == "wrestler":
        dec *= 1.4
    else:
        sub *= 1.0 + 0.6 * min(2.0, f.get("sub_att_per15", 0.5)) \
            * (1.0 + max(0.0, 0.6 - opp.get("tdd", 0.6)))
    # Durable opponents drag fights to the cards — durability is stable
    # (weighted 1.5×); finishing ability is noisy.
    finished_rate = opp.get("times_finished", 0) / max(1, opp.get("fights", 10))
    dec *= 1.0 + 1.5 * (0.35 - min(0.7, finished_rate))
    total = ko + sub + dec
    return {"ko": round(ko / total, 4), "sub": round(sub / total, 4),
            "dec": round(dec / total, 4)}


def joint_method(p_a: float, cond_a: dict, cond_b: dict) -> dict:
    """The six-outcome joint. Sums to 1.00 or the model is broken."""
    p_b = 1.0 - p_a
    out = {
        "a_ko": round(p_a * cond_a["ko"], 4),
        "a_sub": round(p_a * cond_a["sub"], 4),
        "a_dec": round(p_a * cond_a["dec"], 4),
        "b_ko": round(p_b * cond_b["ko"], 4),
        "b_sub": round(p_b * cond_b["sub"], 4),
        "b_dec": round(p_b * cond_b["dec"], 4),
    }
    assert abs(sum(out.values()) - 1.0) < 0.005, "joint must sum to 1"
    out["distance"] = round(out["a_dec"] + out["b_dec"], 4)
    return out


# --- clamp, gate, staking ---------------------------------------------------
def clamp_weight(a: dict, b: dict, unpriced_info: bool = False) -> float | None:
    """w for the humility clamp — or None, meaning NO BET (debutants,
    regional records, catchweight chaos)."""
    fa, fb = a.get("ufc_fights", 0), b.get("ufc_fights", 0)
    if min(fa, fb) < 1:
        return None
    if unpriced_info:
        return 0.60
    if min(fa, fb) < 3 or a.get("short_notice") or b.get("short_notice"):
        return 0.12
    if min(fa, fb) >= 5:
        return 0.35
    return 0.25


def humility_clamp(p_model: float, p_market: float, w: float) -> tuple:
    diff = abs(p_model - p_market)
    if diff > CLAMP_KILL_DIFF:
        return None, (f"model and market disagree by {diff:.0%} — MMA lines "
                      f"are soft but not that soft. Re-audit, no bet.")
    return round(w * p_model + (1 - w) * p_market, 4), f"w={w:g}"


def _dec_odds(odds: int) -> float:
    return 1.0 + (100.0 / abs(odds) if odds < 0 else odds / 100.0)


def approval_gate(p_final: float, odds: int, market: str,
                  red_flags: list[str], bets_on_card: int) -> list[str]:
    fails = []
    be = 1.0 / _dec_odds(odds)
    need = GATE_EDGE_PROP if market != "moneyline" else GATE_EDGE_ML
    if p_final - be < need:
        fails.append(f"edge {p_final - be:+.1%} < {need:.0%} over "
                     f"break-even {be:.1%}")
    ev = p_final * (_dec_odds(odds) - 1.0) - (1.0 - p_final)
    if ev < GATE_MIN_EV:
        fails.append(f"EV {ev:+.1%} < +5%")
    if odds < GATE_WORST_PRICE:
        fails.append(f"price {odds} worse than −300 — MMA favorites there are traps")
    if red_flags:
        fails.append("unresolved red flag(s): " + ", ".join(red_flags[:3]))
    if bets_on_card >= MAX_BETS_PER_CARD:
        fails.append("card cap — max 3 bets per card")
    return fails


def stake_units(p: float, odds: int) -> float:
    b = _dec_odds(odds) - 1.0
    if b <= 0:
        return 0.0
    kelly = max(0.0, (p * b - (1.0 - p)) / b)
    return round(min(kelly * KELLY_FRACTION, STAKE_CAP) * 20, 2)


# --- card runner ------------------------------------------------------------
def evaluate_fight(a: dict | None, b: dict | None, prices: dict,
                   division: str, bets_so_far: int) -> dict:
    """One fight → a pick, or a pass-list line with the reason."""
    name_a = prices.get("fighter_a", (a or {}).get("name", "A"))
    name_b = prices.get("fighter_b", (b or {}).get("name", "B"))
    base = {"fight": f"{name_a} vs {name_b}", "division": division}
    if not a or not b:
        return {**base, "kind": "pass", "why": "no dossier — no bet (build "
                "both dossiers before any modeling)"}
    w = clamp_weight(a, b)
    if w is None:
        return {**base, "kind": "pass",
                "why": "debutant / regional record — unmodelable, no bet"}
    odds_a, odds_b = prices.get("a_odds"), prices.get("b_odds")
    if not odds_a or not odds_b:
        return {**base, "kind": "pass", "why": "no two-sided price posted yet"}

    from ..nba.prob import devig, market_hold
    p_model, notes = win_probability(a, b)
    mkt_a, mkt_b = devig(int(odds_a), int(odds_b))

    # Bet the side the model likes vs its de-vigged price.
    if p_model - mkt_a >= (1 - p_model) - mkt_b:
        side, p_m, p_mkt, odds, fighter, opp = (name_a, p_model, mkt_a,
                                                int(odds_a), a, b)
    else:
        side, p_m, p_mkt, odds, fighter, opp = (name_b, 1 - p_model, mkt_b,
                                                int(odds_b), b, a)

    p_final, clamp_note = humility_clamp(p_m, p_mkt, w)
    if p_final is None:
        return {**base, "kind": "pass", "why": clamp_note}

    cond_a = method_conditionals(a, b, division)
    cond_b = method_conditionals(b, a, division)
    joint = joint_method(p_model, cond_a, cond_b)

    red = list(fighter.get("red_flags", []))
    fails = approval_gate(p_final, odds, "moneyline", red, bets_so_far)
    card = {
        **base, "pick": side, "odds": odds, "book": prices.get("book", ""),
        "p_model": round(p_m, 4), "p_market": round(p_mkt, 4),
        "p_final": p_final, "w": w,
        "break_even": round(1.0 / _dec_odds(odds), 4),
        "edge": round(p_final - 1.0 / _dec_odds(odds), 4),
        "ev": round(p_final * (_dec_odds(odds) - 1) - (1 - p_final), 4),
        "hold": market_hold(int(odds_a), int(odds_b)),
        "method": joint, "p_distance": joint["distance"],
        "style_notes": notes,
        "kill_if": ("missed weight, late replacement, or visible cut damage "
                    "at weigh-ins → automatic void"),
    }
    if fails:
        return {**card, "kind": "pass",
                "why": "; ".join(fails[:2]), "near_miss": True}
    card["stake_units"] = stake_units(p_final, odds)
    return {**card, "kind": "pick"}


def run_card(fights: list[dict]) -> dict:
    """fights: [{a, b, prices, division}] → picks (≤3) + the pass list."""
    picks, passes = [], []
    for f in fights:
        r = evaluate_fight(f.get("a"), f.get("b"), f.get("prices", {}),
                           f.get("division", ""), len(picks))
        (picks if r["kind"] == "pick" else passes).append(r)
    near = [p for p in passes if p.get("near_miss")][:3]
    return {"sport": "ufc", "picks": picks, "pass_list": passes,
            "near_misses": near, "no_qualifying": not picks,
            "counts": {"fights": len(fights), "picks": len(picks),
                       "passes": len(passes)}}
