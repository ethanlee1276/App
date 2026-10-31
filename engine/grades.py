"""Our grades: each player's season so far, scored 0-100 against the men at his position, from free data.

    python3 -m engine.grades                    # this season's top grades, every kind
    python3 -m engine.grades --player "Luther Burden III"

Ethan, 2026-10-24: "yes build all of D" — PFF grades among them. PFF's
grades cannot be shown here: its terms (pff.com/terms) limit its data to
personal, non-commercial use and bar distributing it, and a page members
pay for is neither. What a PFF grade summarises, play by play, is how well
a man did his job; the free numbers the site already pulls say most of
that for the skill positions and the coverage, and this puts them in one
number with the parts beside it.

A GRADE is the average of a man's percentiles on a few measured parts,
against the men at his position with the volume to be ranked this season
(before the week being read), times 100: 50 is the middle of the position,
90 the top tenth.

    receiving (WR, TE)   yards a target; separation at the catch; yards after
                         the catch over expected (Next Gen Stats); drops a
                         target (PFR's charting)
    rushing (RB)         rushing yards over expected a carry (NGS); yards
                         after contact a carry; broken tackles a carry (PFR)
    passing (QB)         completion rate over expected; yards an attempt
                         (NGS); bad throws an attempt (PFR); interceptions
                         an attempt (NGS)
    coverage (anyone     yards a target allowed; completion rate allowed;
    targeted)            passer rating allowed (PFR)

WHAT IT IS NOT. ngsfit.py measured the tracking numbers on held-out
seasons: none of them improves a projection the box score already makes
(separation the best, inside one standard error). So a grade is a reading,
like the research docs' PFF grade it stands in for, and moves no number;
the report says so beside it.

Standard library only.
"""
from __future__ import annotations

from collections import defaultdict

#: (part, the words for it, +1 when more is better). The value is
#: computed in `_values` below.
PARTS = {
    "receiving": (("yds_per_tgt", "yards a target", +1),
                  ("avg_separation", "yards of separation", +1),
                  ("avg_yac_above_expectation", "yards after the catch over expected", +1),
                  ("drop_rate", "drops a target", -1)),
    "rushing": (("rush_yards_over_expected_per_att", "yards over expected a carry", +1),
                ("contact_avg", "yards after contact a carry", +1),
                ("broken_rate", "broken tackles a carry", +1)),
    "passing": (("completion_percentage_above_expectation", "completion rate over expected", +1),
                ("yds_per_att", "yards an attempt", +1),
                ("bad_rate", "bad throws an attempt", -1),
                ("int_rate", "interceptions an attempt", -1)),
    "coverage": (("yds_per_tgt", "yards a target allowed", -1),
                 ("cmp_rate", "completion rate allowed", -1),
                 ("rating", "passer rating allowed", -1)),
}
#: The season's volume a man needs to be graded: targets, carries,
#: attempts, targets against. About three games of a starter.
MIN_VOLUME = {"receiving": 12, "rushing": 30, "passing": 80, "coverage": 15}
#: Who is graded on what, by position.
POSITIONS = {"receiving": ("WR", "TE"), "rushing": ("RB",), "passing": ("QB",)}
#: The kind a position's grade is read as on the report.
KIND_OF = {"WR": "receiving", "TE": "receiving", "RB": "rushing", "FB": "rushing", "QB": "passing"}
POS_WORDS = {"WR": "wide receivers", "TE": "tight ends", "RB": "running backs", "QB": "quarterbacks",
             "coverage": "defenders"}
NOTE = "Our grade from free tracking and charting numbers, not PFF's; a reading, not part of any number."


def _f(v):
    try:
        if v in (None, "", "NA"):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _key(team, name) -> tuple:
    from .sources.nflscheme import name_key
    from .sources.ngs import _team
    return (_team(team), name_key(name))


def _in_window(r: dict, season: int, before_week) -> bool:
    try:
        s, w = int(float(r.get("season") or 0)), int(float(r.get("week") or 0))
    except (TypeError, ValueError):
        return False
    return (s == int(season) and w > 0 and (before_week is None or w < int(before_week))
            and str(r.get("season_type") or r.get("game_type") or "REG") == "REG")


def _sums(rows, season, before_week, name_col, fields, pos_col=None) -> dict:
    out: dict = {}
    for r in rows or []:
        if not _in_window(r, season, before_week):
            continue
        k = _key(r.get("team_abbr") or r.get("team"), r.get(name_col) or "")
        a = out.setdefault(k, {"name": r.get(name_col) or "", "pos": "", **{f: 0.0 for f in fields},
                               **{f"_{f}": 0.0 for f in fields}})
        if pos_col and r.get(pos_col):
            a["pos"] = str(r[pos_col]).upper()
        for f in fields:
            v = _f(r.get(f))
            if v is not None:
                a[f] += v
        a["games"] = a.get("games", 0) + 1
    return out


def _weighted(rows, season, before_week, vol: str, metrics) -> dict:
    """{key: {metric: volume-weighted mean}} over NGS weekly rows."""
    acc: dict = defaultdict(lambda: {"n": 0.0, **{m: 0.0 for m in metrics}, **{f"{m}_n": 0.0 for m in metrics}})
    for r in rows or []:
        if not _in_window(r, season, before_week):
            continue
        n = _f(r.get(vol)) or 0.0
        if n <= 0:
            continue
        a = acc[_key(r.get("team_abbr"), r.get("player_display_name") or "")]
        a["n"] += n
        for m in metrics:
            v = _f(r.get(m))
            if v is not None:
                a[m] += v * n
                a[f"{m}_n"] += n
    return {k: {m: (a[m] / a[f"{m}_n"]) if a[f"{m}_n"] else None for m in metrics} for k, a in acc.items()}


def _values(ngs: dict, pfr: dict, season: int, before_week) -> dict:
    """{kind: {key: {"name", "pos", "volume", part: value}}}."""
    from .sources.nflscheme import defenders
    out = {k: {} for k in PARTS}
    rec = _sums(ngs.get("receiving"), season, before_week, "player_display_name",
                ("targets", "yards", "receptions"), "player_position")
    rec_w = _weighted(ngs.get("receiving"), season, before_week, "targets",
                      ("avg_separation", "avg_yac_above_expectation"))
    drops = _sums(pfr.get("rec"), season, before_week, "pfr_player_name", ("receiving_drop",))
    for k, a in rec.items():
        t = a["targets"]
        if t <= 0:
            continue
        d = drops.get(k)
        out["receiving"][k] = {"name": a["name"], "pos": a["pos"], "volume": t,
                               "yds_per_tgt": a["yards"] / t, **rec_w.get(k, {}),
                               "drop_rate": (d["receiving_drop"] / t) if d else None}
    rush = _sums(ngs.get("rushing"), season, before_week, "player_display_name", ("rush_attempts",),
                 "player_position")
    rush_w = _weighted(ngs.get("rushing"), season, before_week, "rush_attempts",
                       ("rush_yards_over_expected_per_att",))
    contact = _sums(pfr.get("rush"), season, before_week, "pfr_player_name",
                    ("carries", "rushing_yards_after_contact", "rushing_broken_tackles"))
    for k, a in rush.items():
        c = contact.get(k) or {}
        car = c.get("carries") or 0.0
        out["rushing"][k] = {"name": a["name"], "pos": a["pos"], "volume": a["rush_attempts"],
                             **rush_w.get(k, {}),
                             "contact_avg": (c["rushing_yards_after_contact"] / car) if car else None,
                             "broken_rate": (c["rushing_broken_tackles"] / car) if car else None}
    pas = _sums(ngs.get("passing"), season, before_week, "player_display_name",
                ("attempts", "pass_yards", "interceptions"), "player_position")
    pas_w = _weighted(ngs.get("passing"), season, before_week, "attempts",
                      ("completion_percentage_above_expectation",))
    bad = _sums(pfr.get("pass"), season, before_week, "pfr_player_name", ("passing_bad_throws",))
    for k, a in pas.items():
        att = a["attempts"]
        if att <= 0:
            continue
        b = bad.get(k)
        out["passing"][k] = {"name": a["name"], "pos": a["pos"] or "QB", "volume": att,
                             "yds_per_att": a["pass_yards"] / att, "int_rate": a["interceptions"] / att,
                             **pas_w.get(k, {}),
                             "bad_rate": (b["passing_bad_throws"] / att) if b else None}
    window = [r for r in pfr.get("def") or [] if _in_window(r, season, before_week)]
    for (team, nk), d in defenders(window).items():
        t = d.get("targets") or 0.0
        if t <= 0:
            continue
        out["coverage"][_key(team, d.get("name") or nk)] = {
            "name": d.get("name") or nk, "pos": "coverage", "volume": t, "yds_per_tgt": d.get("yds_per_tgt"),
            "cmp_rate": d["cmp"] / t, "rating": d.get("rating")}
    return out


def grade(values: dict) -> dict:
    """{kind: {key: {"grade", "n", "pos", "name", "volume", "parts": [...]}}}
    — percentiles within each kind and position, among the men with
    MIN_VOLUME; a part a man has no number for is left out of his mean."""
    out = {}
    for kind, rows in values.items():
        out[kind] = {}
        groups: dict = defaultdict(list)
        for k, v in rows.items():
            if v.get("volume", 0) < MIN_VOLUME[kind]:
                continue
            pos = v.get("pos") or ""
            if kind in POSITIONS and pos not in POSITIONS[kind]:
                continue
            groups[pos if kind != "coverage" else "coverage"].append(k)
        for pos, keys in groups.items():
            ranks: dict = defaultdict(dict)
            for part, _words, sign in PARTS[kind]:
                have = [k for k in keys if rows[k].get(part) is not None]
                if len(have) < 2:
                    continue
                order = sorted(have, key=lambda k: sign * rows[k][part], reverse=True)
                for i, k in enumerate(order):
                    ranks[k][part] = (i + 1, len(have), 1.0 - i / (len(have) - 1))
            for k in keys:
                got = ranks.get(k) or {}
                if len(got) < 2:
                    continue
                v = rows[k]
                parts = [{"part": part, "words": words, "value": round(v[part], 4),
                          "rank": got[part][0], "of": got[part][1]}
                         for part, words, _s in PARTS[kind] if part in got]
                out[kind][k] = {"grade": round(100 * sum(p[2] for p in got.values()) / len(got)),
                                "n": len(keys), "pos": pos, "name": v.get("name"),
                                "volume": int(v.get("volume") or 0), "parts": parts}
    return out


def table(season: int, before_week=None, ngs=None, pfr=None) -> dict:
    """The season's grades before ``before_week``, from the files the scan
    already reads (cached); {} kinds where a file cannot be had."""
    from .sources import ngs as NGS
    from .sources import nflscheme as N
    if ngs is None:
        ngs = {}
        for kind in NGS.KINDS:
            try:
                ngs[kind] = NGS.fetch(kind)
            except Exception:                                # noqa: BLE001
                ngs[kind] = []
    if pfr is None:
        pfr = {}
        for kind, fn in (("rec", N.load_pfr_rec), ("rush", N.load_pfr_rush),
                         ("pass", N.load_pfr_pass), ("def", N.load_pfr_def)):
            try:
                pfr[kind] = fn(season)
            except Exception:                                # noqa: BLE001
                pfr[kind] = []
    return grade(_values(ngs, pfr, season, before_week))


def of(grades: dict, team: str, name: str, pos: str) -> dict | None:
    """A man's grade at his position's kind, or None."""
    kind = KIND_OF.get(str(pos or "").upper())
    return ((grades or {}).get(kind) or {}).get(_key(team, name)) if kind else None


def coverage_of(grades: dict, team: str, name: str) -> dict | None:
    return ((grades or {}).get("coverage") or {}).get(_key(team, name))


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _value_words(p: dict) -> str:
    v, part = p["value"], p["part"]
    if part in ("drop_rate", "bad_rate", "int_rate", "cmp_rate"):
        text = f"{v * 100:.1f}%" if part != "cmp_rate" else f"{v * 100:.0f}%"
    elif part == "completion_percentage_above_expectation":
        text = f"{v:+.1f} points"
    elif part in ("avg_yac_above_expectation", "rush_yards_over_expected_per_att"):
        text = f"{v:+.1f}"
    elif part == "rating":
        text = f"{v:.0f}"
    elif part == "broken_rate":
        text = f"{v:.2f}"
    else:
        text = f"{v:.1f}"
    return f"{text} {p['words']} ({_ord(p['rank'])})"


def words(g: dict | None, kind_words: str | None = None) -> str:
    """"84 of 100 — 7th of 40 wide receivers ... : <parts>" or ""."""
    if not g:
        return ""
    who = POS_WORDS.get(g.get("pos") or "", "players")
    kind = kind_words or {"coverage": "in coverage"}.get(g.get("pos") or "", "")
    return (f"{g['grade']} of 100{(' ' + kind) if kind else ''}, against {g['n']} {who} with the volume to "
            f"rank: " + "; ".join(_value_words(p) for p in g.get("parts") or []))


def main(argv=None) -> int:
    import argparse
    import datetime as _dt
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--season", type=int, default=0)
    ap.add_argument("--week", type=int, default=0, help="grade the weeks before this one (default: all played)")
    ap.add_argument("--player", default="")
    a = ap.parse_args(argv)
    season = a.season or _dt.date.today().year - (1 if _dt.date.today().month < 3 else 0)
    got = table(season, a.week or None)
    for kind, rows in got.items():
        if a.player:
            for k, g in rows.items():
                if g.get("name", "").lower() == a.player.lower():
                    print(f"  {kind}: {g['name']} ({k[0]}) {words(g)}")
            continue
        print(f"  {kind}: {len(rows)} graded")
        for k, g in sorted(rows.items(), key=lambda kv: -kv[1]["grade"])[:8]:
            print(f"    {g['grade']:>3}  {g['name']:<24} {k[0]:<4} {g['pos']:<8} {g['volume']:>4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
