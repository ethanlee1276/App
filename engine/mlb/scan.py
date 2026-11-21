"""The MLB matchup scan: every game broken down, every hitter and starter read.

Ethan, 2026-09-26: "move on to MLB. We need to get the who's going to
struggle and who's going to do good and best candidates ... the breakout
candidates and good matchups for all the players and pitchers ... which
batters do good against what pitchers and left hand and right hand ... all
the work we did for NFL and college football, we need to figure out how we
can move that to MLB."

The pieces were already in the MLB engine, each pricing a sliver and
telling nobody: every hitter's own platoon split, each starter's slugging
allowed to lefties and righties, the hitter's career line against tonight's
starter, Statcast's expected-stats gap and barrels, the lineup slot's plate
appearances, each opponent's strikeout rate, bullpen workload, the park by
the batter's hand, the wind, the plate umpire. This module reads them the
way the football scan reads a defence — into a TALE OF THE TAPE per game
and a READ per player (could shine / could struggle / breakout) in the
football reads' own shape, so everything downstream (Most Likely's leans,
the one board's matchup check, the game page, the reads shelf) takes MLB
without a second code path.

WHAT IT NEVER DOES: move a probability. The model already priced every
input above (engine/mlb/matchup.py); the read picks a SIDE, the number is
the model's — the same rule as the football scan.

Standard library only.
"""
from __future__ import annotations

from .matchup import LEAGUE_K_RATE, LEAGUE_SLG

#: Reads' labels and sides — the football scan's own (gamescan.READS), so
#: the page and Most Likely treat them identically.
LABELS = {"breakout": "Breakout candidate", "good": "Good matchup", "neutral": "Neutral",
          "tough": "Tough matchup", "avoid": "Avoid"}

#: A hitter's markets and a starter's.
HITTER_LEANS = ["hits", "total_bases"]
POWER_LEANS = ["home_runs"]
PITCHER_LEANS = ["strikeouts", "outs"]

#: Thresholds, each a plain reading of a number the engine already has.
PLATOON_EDGE = 1.05            # his own split vs tonight's hand
SLG_SOFT, SLG_STINGY = 0.460, 0.360
XSLG_GAP = 0.040               # xSLG over SLG: hitting better than his results
BARREL_POWER = 0.12
K_RATE_HIGH, K_RATE_LOW = 0.245, 0.205
SP_K_ELITE = 0.27
CSW_ELITE, CSW_LOW = 0.30, 0.26
XERA_GOOD, XERA_BAD = 3.40, 4.80
WIND_OUT_MPH = 8.0


#: A hitter's whiff rate against tonight's mix this far from his usual
#: reads as a real difference (arsenal.matchup; coverage gates it first).
WHIFF_DELTA = 0.03
#: The share of the lineup's own platoon factors that says it hits this
#: hand better or worse than its average.
LINEUP_HAND_EDGE = 0.03

PITCH_WORDS = {"FF": "four-seamers", "SI": "sinkers", "FC": "cutters", "SL": "sliders", "ST": "sweepers",
               "CU": "curveballs", "KC": "knuckle-curves", "CH": "changeups", "FS": "splitters",
               "SV": "slurves", "KN": "knuckleballs", "FO": "forkballs", "SC": "screwballs"}


def pitch_mix(person_id: int, season: int) -> dict:
    """{pitch_type: share} over his last starts, pooled by pitches thrown —
    the same cached playByPlay the build already warmed for velocity."""
    from .arsenal import history
    tot: dict = {}
    n = 0
    for st in history(int(person_id), int(season)) or []:
        for t, sh in (st.get("shares") or {}).items():
            tot[t] = tot.get(t, 0.0) + sh * st["n"]
        n += st["n"]
    return {t: round(v / n, 4) for t, v in tot.items()} if n else {}


def arsenal_context(slate, season: int) -> dict:
    """{"batters": Savant's pitch-arsenal batter board, "season": year used,
    "mix": {team: {"pitcher", "shares"}}} for tonight's starters with a
    person id. Either half missing leaves the other; nothing raises."""
    from .models import STRIKEOUTS, OUTS
    out = {"batters": {}, "season": None, "mix": {}, "error": ""}
    try:
        from .sources.savant import load_arsenal
        board = load_arsenal(int(season), "batter")
        out["season"] = board.pop("_season", None) if board else None
        out["batters"] = board or {}
        if not board:
            out["error"] = "Savant's arsenal board came back empty for this season and last"
    except Exception as exc:                                 # noqa: BLE001
        # SAID, not swallowed: the box's first run printed "arsenal board:
        # 0 hitter(s)" with no reason (2026-09-26).
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
    for p in getattr(slate, "props", None) or []:
        if p.market not in (STRIKEOUTS, OUTS) or not getattr(p, "person_id", 0) or p.team in out["mix"]:
            continue
        try:
            shares = pitch_mix(p.person_id, season)
        except Exception:                                    # noqa: BLE001
            shares = {}
        if shares:
            out["mix"][p.team] = {"pitcher": p.player, "shares": shares}
    return out


def _mix_words(shares: dict, k: int = 3) -> str:
    top = sorted(shares.items(), key=lambda kv: -kv[1])[:k]
    return ", ".join(f"{PITCH_WORDS.get(t, t)} {sh:.0%}" for t, sh in top)


def _ord(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _hand_word(bats: str) -> str:
    return "lefties" if (bats or "").upper() in ("L", "S") else "righties"


def _label(pro: list, con: list, breakout: bool, fam: dict | None = None,
           featured: bool = False) -> tuple[str, str]:
    """ONE VOTE A FAMILY (engine/readlogic, 2026-11-14): the slugging a
    starter allows a hitter's side, his expected ERA and how his mix plays
    against the hitter's whiffs are one reason — the starter — not three;
    and a bat at the top of the order, or a starting pitcher, is never
    "avoid"."""
    from ..readlogic import ladder, score as _score
    key = ladder(_score(pro, con, fam), featured=featured, breakout_ok=breakout,
                 good_at=2, breakout_at=3)
    return key, LABELS[key]


def read_hitter(prop, game, park, arsenal: dict | None = None) -> dict:
    """One hitter against tonight's starter, park and pen."""
    from .. import readlogic as RL
    pro, con, notes = [], [], []
    fam: dict = {}

    def said(lst, text, family):
        lst.append(text)
        fam[text] = family
    team, opp = prop.team, prop.opponent
    sp = (game.pitchers or {}).get(opp)
    breakout = False
    power = False
    if sp:
        hand = (sp.throws or "R").upper()
        if prop.platoon_factor >= PLATOON_EDGE:
            said(pro, prop.platoon_note or f"Hits {hand}HP better than the hitter's average", RL.PLATOON)
        elif prop.platoon_factor <= 2 - PLATOON_EDGE:
            said(con, prop.platoon_note or f"Struggles against {hand}HP", RL.PLATOON)
        side_slg = sp.slg_allowed_vs_l if (prop.bats or "R").upper() in ("L", "S") else sp.slg_allowed_vs_r
        if side_slg >= SLG_SOFT:
            said(pro, f"{sp.name} allows a .{side_slg * 1000:.0f} SLG to {_hand_word(prop.bats)}", RL.PITCHER)
        elif side_slg <= SLG_STINGY:
            said(con, f"{sp.name} holds {_hand_word(prop.bats)} to a .{side_slg * 1000:.0f} SLG", RL.PITCHER)
        if sp.xera >= XERA_BAD:
            said(pro, f"{sp.name}'s expected ERA is {sp.xera:.2f}", RL.PITCHER)
        elif sp.xera <= XERA_GOOD:
            said(con, f"{sp.name}'s expected ERA is {sp.xera:.2f} — a tough starter", RL.PITCHER)
        # HOW HE HANDLES WHAT THIS STARTER THROWS (arsenal.matchup): his own
        # whiff rate by pitch type (Savant's arsenal board), re-weighted by
        # the starter's mix over his last starts — against his usual. The
        # difference is the read, and only over most of the arsenal.
        mx = ((arsenal or {}).get("mix") or {}).get(opp)
        if mx and (arsenal or {}).get("batters"):
            from .arsenal import matchup as _am
            from .sources.savant import _norm as _sv_norm
            row = arsenal["batters"].get(_sv_norm(prop.player))
            m = _am(mx["shares"], row) if row else None
            if m and m.get("enough") and m.get("whiff_delta") is not None:
                what = (f"against {sp.name}'s mix ({_mix_words(mx['shares'])}): whiffs "
                        f"{m['whiff_vs_mix']:.0%}, usually {m['whiff_baseline']:.0%}")
                if m["whiff_delta"] <= -WHIFF_DELTA:
                    said(pro, "Sees the ball well " + what, RL.PITCHER)
                elif m["whiff_delta"] >= WHIFF_DELTA:
                    said(con, "Swings and misses more " + what, RL.PITCHER)
                else:
                    notes.append("No edge " + what)
        if prop.vs_pitcher_avg is not None:
            notes.append(f"Career against {sp.name}: {prop.vs_pitcher_avg:.2f} a game "
                         f"(too few meetings to count)")
    sc = prop.statcast
    if sc is not None:
        if sc.xslg is not None and sc.slg is not None:
            gap = sc.xslg - sc.slg
            if gap >= XSLG_GAP:
                breakout = True
                said(pro, f"Hitting better than the results — xSLG .{sc.xslg * 1000:.0f} "
                          f"vs SLG .{sc.slg * 1000:.0f}", RL.CONTACT)
            elif gap <= -XSLG_GAP:
                said(con, f"Results ahead of the contact — SLG .{sc.slg * 1000:.0f} "
                          f"vs xSLG .{sc.xslg * 1000:.0f}", RL.CONTACT)
        if sc.barrel_pct is not None and sc.barrel_pct >= BARREL_POWER:
            power = True
            said(pro, f"Barrels {sc.barrel_pct:.0%} of batted balls", RL.CONTACT)
    if prop.lineup_spot and prop.lineup_spot <= 3:
        said(pro, f"Bats {_ord(prop.lineup_spot)} — the most trips to the plate", RL.LINEUP)
    elif prop.lineup_spot >= 8:
        said(con, f"Bats {_ord(prop.lineup_spot)} — the fewest trips to the plate", RL.LINEUP)
    hr = park.hr_factor
    by_hand = park.hr_factor_lhb if (prop.bats or "R").upper() == "L" else park.hr_factor_rhb
    if by_hand is not None:
        hr = by_hand
    if hr >= 1.10:
        said(pro, f"{park.name} boosts home runs for {_hand_word(prop.bats)} ({(hr - 1) * 100:+.0f}%)", RL.PARK)
        power = power or hr >= 1.15
    elif hr <= 0.90:
        said(con, f"{park.name} suppresses home runs for {_hand_word(prop.bats)} ({(hr - 1) * 100:+.0f}%)", RL.PARK)
    w = game.weather
    if w and not w.roof_closed and w.wind_dir_rel == "out" and w.wind_mph >= WIND_OUT_MPH:
        said(pro, f"Wind blowing out at {w.wind_mph:.0f} mph", RL.WEATHER)
    elif w and not w.roof_closed and w.wind_dir_rel == "in" and w.wind_mph >= WIND_OUT_MPH:
        said(con, f"Wind blowing in at {w.wind_mph:.0f} mph", RL.WEATHER)
    fat = (game.bullpen_fatigue or {}).get(opp)
    if fat is not None and fat >= 6.0:
        said(pro, f"{opp}'s bullpen worked {fat:.1f} relief innings the last two days", RL.BULLPEN)
    if prop.streak_note:
        notes.append(prop.streak_note)
    key, label = _label(pro, con, breakout, fam,
                        featured=bool(prop.lineup_spot) and prop.lineup_spot <= 4)
    lean = HITTER_LEANS + (POWER_LEANS if power else [])
    return {"player": prop.player, "team": team, "opp": opp, "pos": prop.position or "",
            "read": key, "label": label, "pro": pro, "con": con, "notes": notes, "lean": lean,
            "headshot": getattr(prop, "headshot", "") or "",
            "usage": {"lineup_spot": prop.lineup_spot or None, "bats": prop.bats},
            "vs": {"pitcher": sp.name if sp else "", "throws": sp.throws if sp else ""}}


def read_starter(prop, game, park) -> dict:
    """One starting pitcher against tonight's lineup, park and umpire."""
    from .. import readlogic as RL
    pro, con, notes = [], [], []
    fam: dict = {}

    def said(lst, text, family):
        lst.append(text)
        fam[text] = family
    team, opp = prop.team, prop.opponent
    me = (game.pitchers or {}).get(team)
    opp_k = (game.team_k_rate or {}).get(opp)
    if opp_k is not None:
        if opp_k >= K_RATE_HIGH:
            said(pro, f"{opp} strikes out {opp_k:.1%} of the time (league {LEAGUE_K_RATE:.0%})", RL.DEFENSE)
        elif opp_k <= K_RATE_LOW:
            said(con, f"{opp} rarely strikes out ({opp_k:.1%})", RL.DEFENSE)
    breakout = False
    if me:
        # His own stuff is one reason, however many numbers say it.
        if me.k_rate >= SP_K_ELITE:
            breakout = True
            said(pro, f"Strikes out {me.k_rate:.0%} of the batters faced", RL.CONTACT)
        if me.xera <= XERA_GOOD:
            said(pro, f"Expected ERA {me.xera:.2f}", RL.CONTACT)
        elif me.xera >= XERA_BAD:
            said(con, f"Expected ERA {me.xera:.2f}", RL.CONTACT)
    sc = prop.statcast
    if sc is not None and sc.csw_pct is not None:
        if sc.csw_pct >= CSW_ELITE:
            breakout = True
            said(pro, f"Called strikes plus whiffs on {sc.csw_pct:.1%} of pitches", RL.CONTACT)
        elif sc.csw_pct <= CSW_LOW:
            said(con, f"Only {sc.csw_pct:.1%} called strikes plus whiffs", RL.CONTACT)
    if game.ump_k_factor >= 1.03 and game.plate_umpire:
        said(pro, f"Plate umpire {game.plate_umpire} calls a big zone ({(game.ump_k_factor - 1) * 100:+.0f}% strikeouts)",
             RL.UMPIRE)
    elif game.ump_k_factor <= 0.97 and game.plate_umpire:
        said(con, f"Plate umpire {game.plate_umpire} calls a tight zone ({(game.ump_k_factor - 1) * 100:+.0f}% strikeouts)",
             RL.UMPIRE)
    if park.k_factor >= 1.04:
        said(pro, f"{park.name} adds strikeouts ({(park.k_factor - 1) * 100:+.0f}%)", RL.PARK)
    elif park.k_factor <= 0.96:
        said(con, f"{park.name} takes strikeouts away ({(park.k_factor - 1) * 100:+.0f}%)", RL.PARK)
    own = (game.bullpen_fatigue or {}).get(team)
    if own is not None and own >= 6.0:
        said(pro, f"The pitcher's own bullpen is tired ({own:.1f} relief innings in two days) — a longer leash", RL.BULLPEN)
    if prop.streak_note:
        notes.append(prop.streak_note)
    key, label = _label(pro, con, breakout, fam, featured=True)
    return {"player": prop.player, "team": team, "opp": opp, "pos": "SP",
            "read": key, "label": label, "pro": pro, "con": con, "notes": notes,
            "lean": list(PITCHER_LEANS), "headshot": getattr(prop, "headshot", "") or "",
            "usage": {"throws": prop.throws}}


def lineup_vs_hand(props, team: str, hand: str) -> dict | None:
    """How tonight's lineup hits this hand, from each hitter's own measured
    platoon factor (engine/mlb/platoon): the average, and how many of the
    lineup it rests on. None with fewer than four measured bats."""
    fs = {}
    for p in props or []:
        if p.team == team and (p.position or "").upper() not in ("SP", "P", "RP") \
                and p.platoon_factor and p.player not in fs:
            fs[p.player] = float(p.platoon_factor)
    measured = [v for v in fs.values() if v != 1.0]
    if len(measured) < 4:
        return None
    avg = sum(measured) / len(measured)
    return {"hand": hand, "factor": round(avg, 3), "hitters": len(measured)}


def tape(game, props=None, arsenal: dict | None = None) -> dict:
    """The tale of the tape: each starter against the other lineup, pens,
    park, weather, umpire."""
    from .parks import get_park
    park = get_park(game.park)
    sides = {}
    for team in (game.away, game.home):
        sp = (game.pitchers or {}).get(team)
        opp_sp = (game.pitchers or {}).get(game.home if team == game.away else game.away)
        mx = ((arsenal or {}).get("mix") or {}).get(team)
        sides[team] = {
            "mix": _mix_words(mx["shares"]) if mx else "",
            "vs_hand": lineup_vs_hand(props, team, (opp_sp.throws or "R").upper()) if opp_sp else None,
            "starter": ({"name": sp.name, "throws": sp.throws, "k_rate": round(sp.k_rate, 3),
                         "xera": round(sp.xera, 2), "slg_vs_l": round(sp.slg_allowed_vs_l, 3),
                         "slg_vs_r": round(sp.slg_allowed_vs_r, 3)} if sp else None),
            "k_rate": (game.team_k_rate or {}).get(team),
            "pen_rank": (game.bullpen_rank or {}).get(team),
            "pen_fatigue": (game.bullpen_fatigue or {}).get(team),
        }
    w = game.weather
    return {"sides": sides, "park": {"name": park.name, "hr": park.hr_factor, "runs": park.run_factor,
                                     "k": park.k_factor},
            "weather": ({"roof_closed": w.roof_closed, "temp_f": w.temp_f, "wind_mph": w.wind_mph,
                         "wind": w.wind_dir_rel} if w else None),
            "umpire": {"name": game.plate_umpire, "k": game.ump_k_factor, "runs": game.ump_run_factor}
            if game.plate_umpire else None,
            "league": {"slg": LEAGUE_SLG, "k_rate": LEAGUE_K_RATE}}


def scan(slate, arsenal: dict | None = None) -> dict:
    """``{"reads": {away@home: {"players": [...]}}, "tapes": {away@home: tape}}``
    — one read per player (his first prop row carries what the read
    needs), hitters and starters."""
    from .parks import get_park
    reads, tapes = {}, {}
    by_game: dict = {}
    for p in getattr(slate, "props", None) or []:
        for g in slate.games:
            if {p.team, p.opponent} == {g.home, g.away}:
                by_game.setdefault(id(g), (g, {}))[1].setdefault(p.player, p)
                break
    for g in slate.games:
        key = f"{g.away}@{g.home}"
        tapes[key] = tape(g, getattr(slate, "props", None), arsenal)
        park = get_park(g.park)
        players = []
        for _name, p in (by_game.get(id(g)) or (g, {}))[1].items():
            if (p.position or "").upper() in ("SP", "P", "RP"):
                players.append(read_starter(p, g, park))
            else:
                players.append(read_hitter(p, g, park, arsenal))
        players.sort(key=lambda x: (["breakout", "good", "neutral", "tough", "avoid"].index(x["read"]),
                                    -len(x["pro"])))
        if players:
            reads[key] = {"players": players}
    return {"reads": reads, "tapes": tapes}
