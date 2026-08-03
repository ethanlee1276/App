"""Per-player memory: learn WHO the blend misreads, gently.

Rung three of the self-tuning ladder. The recency dial (formfit.py) fits
how the blend weighs time for everyone at once; this learns the players
it still misses — the declining veteran it keeps projecting off last
year's bat, the role-changed starter whose innings moved, anyone whose
trajectory the window blend structurally lags. Per player and market, a
single multiplicative correction on the projected mean:

    mult = 1 + (Σactual/Σprojected − 1) · n/(n + N0)      clamped

Three restraints keep this from becoming a memory of noise:

  * **Shrinkage.** The correction is pulled toward 1.0 in proportion to
    how little evidence there is (:data:`N0` games of prior strength) —
    fifteen games of bad luck barely moves it, a season of persistent
    bias moves it most of the way. Sum-over-sum, not mean-of-ratios: a
    single 0-hit game cannot blow up a ratio.
  * **The clamp.** ±:data:`CLAMP_PCT` at most, enforced at fit AND at
    read — a store row outside it is rejected, not obeyed, so a
    hand-edited file cannot smuggle in a 2x correction.
  * **Causal validation, market by market.** The mechanism is only
    ADOPTED for a market when applying it — with each game's correction
    computed strictly from earlier games — beat the uncorrected model's
    walk-forward Brier by :data:`MIN_GAIN` on :data:`MIN_SAMPLES`
    settled predictions. Out-of-sample at every single row; a memory
    that doesn't help predict stays off.

Home runs are excluded as ever: the rare-event path's empirical-Bayes
rate already IS a per-player learner.

Run order: formfit.py → playerfit.py → calibrate.py. Each fitter shapes
the model the next one measures, and the temperature comes last because
it corrects the model that will actually run.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
from pathlib import Path

DEFAULT_PATH = Path("data/models/playerfit.json")

#: Prior strength of "this player is ordinary", in games.
N0 = 40.0
#: Maximum correction either way. A blend wrong by more than this is a
#: modeling bug to fix, not a dial to turn.
CLAMP_PCT = 0.15
#: Market-level adoption: causal corrected Brier must beat baseline by
#: this margin on at least MIN_SAMPLES rows (same bars as the other fits).
MIN_GAIN = 0.0005
MIN_SAMPLES = 200
#: Players below this many games are never stored — their correction is
#: all prior anyway.
MIN_GAMES_STORE = 20
#: Corrections this close to 1.0 are not worth a store row.
MIN_DELTA_STORE = 0.02


def _norm(name: str) -> str:
    return " ".join(str(name).lower().split())


def shrunk_mult(sum_actual: float, sum_projected: float, games: int) -> float:
    """The correction from a player's accumulated record. 1.0 on no or
    degenerate evidence."""
    if games <= 0 or sum_projected <= 0:
        return 1.0
    raw = sum_actual / sum_projected
    m = 1.0 + (raw - 1.0) * (games / (games + N0))
    return max(1.0 - CLAMP_PCT, min(1.0 + CLAMP_PCT, m))


@dataclasses.dataclass
class PlayerFit:
    sport: str
    market: str
    samples: int
    brier_baseline: float
    brier_corrected: float
    adopted: bool
    players: dict            # norm name -> {"mult", "games"}

    @property
    def verdict(self) -> str:
        if not self.adopted:
            return ("memory off — remembering these players did not "
                    "predict better than forgetting them")
        return (f"memory on — {len(self.players)} player(s) the blend "
                f"persistently misreads, corrected up to ±{CLAMP_PCT:.0%}")

    def to_dict(self) -> dict:
        return {"sport": self.sport, "market": self.market,
                "samples": self.samples,
                "brier_baseline": round(self.brier_baseline, 5),
                "brier_corrected": round(self.brier_corrected, 5),
                "adopted": self.adopted, "players": self.players,
                "n0": N0, "clamp_pct": CLAMP_PCT,
                "fitted": _dt.datetime.now().isoformat(timespec="seconds")}


def _brier(pairs) -> float:
    return sum((p - won) ** 2 for p, won in pairs) / len(pairs)


def fit(entries: list[dict], market: str, min_history: int | None = None,
        sport: str = "mlb") -> PlayerFit | None:
    """Two walk-forwards: uncorrected, and corrected with each game's
    multiplier computed strictly from that player's EARLIER games. The
    difference is the honest value of remembering players.

    The projection inside the corrected pass accumulates (projected,
    actual) sums as the walk advances — the same causal bookkeeping the
    live store is built from at the end.
    """
    from . import calibrate as cal
    from .logwalk import walk

    ledger: dict[str, dict] = {}      # per player: running sums, causal

    def causal_mult(name: str) -> float:
        s = ledger.get(_norm(name))
        if not s:
            return 1.0
        return shrunk_mult(s["a"], s["p"], s["n"])

    def record(name: str, projected: float, actual: float) -> None:
        s = ledger.setdefault(_norm(name), {"a": 0.0, "p": 0.0, "n": 0})
        s["a"] += actual
        s["p"] += projected
        s["n"] += 1

    with cal.disabled():
        base = walk(sport, entries, market, min_history=min_history,
                    player_adjust=lambda name: 1.0)
        if not base.pairs:
            return None
        corrected = walk(sport, entries, market, min_history=min_history,
                         player_adjust=causal_mult, player_record=record)

    brier_base = _brier(base.pairs)
    brier_corr = _brier(corrected.pairs)
    samples = len(base.pairs)
    adopted = (samples >= MIN_SAMPLES
               and brier_base - brier_corr >= MIN_GAIN)

    players = {}
    if adopted:
        for name, s in ledger.items():
            if s["n"] < MIN_GAMES_STORE:
                continue
            m = shrunk_mult(s["a"], s["p"], s["n"])
            if abs(m - 1.0) < MIN_DELTA_STORE:
                continue
            players[name] = {"mult": round(m, 4), "games": s["n"]}

    return PlayerFit(sport=sport, market=market, samples=samples,
                     brier_baseline=brier_base, brier_corrected=brier_corr,
                     adopted=adopted, players=players)


# --- persistence and the projection-time lookup ------------------------------
def save(fits: dict[str, PlayerFit], path=None) -> Path:
    """Merge these fits into the store. Merge, not replace: the store is
    shared by every sport (deep fitters AND the journal fitter), and one
    sport's run must not erase keys it never looked at."""
    p = Path(path if path is not None else DEFAULT_PATH)
    try:
        stored = json.loads(p.read_text()) if p.is_file() else {}
        if not isinstance(stored, dict):
            stored = {}
    except (ValueError, OSError):
        stored = {}
    stored.update({k: f.to_dict() for k, f in fits.items()})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(stored, indent=1))
    return p


_cache: dict = {}


def _load(path=None) -> dict:
    p = Path(path if path is not None else DEFAULT_PATH)
    try:
        key = (str(p), p.stat().st_mtime)
    except OSError:
        return {}
    if key in _cache:
        return _cache[key]
    try:
        raw = json.loads(p.read_text())
        out = raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        out = {}
    _cache.clear()
    _cache[key] = out
    return out


def mult_for(sport: str, market: str, player: str, path=None) -> float:
    """This player's earned correction, or 1.0. The adoption rules and
    the clamp are re-checked here — a store cannot serve what the fit
    could not have produced."""
    d = _load(path).get(f"{sport}:{market}")
    if not isinstance(d, dict) or not d.get("adopted"):
        return 1.0
    row = (d.get("players") or {}).get(_norm(player))
    if not isinstance(row, dict):
        return 1.0
    try:
        m = float(row.get("mult", 1.0))
        games = int(row.get("games", 0))
    except (TypeError, ValueError):
        return 1.0
    if games < MIN_GAMES_STORE:
        return 1.0
    if not (1.0 - CLAMP_PCT) <= m <= (1.0 + CLAMP_PCT):
        return 1.0
    return m


def report(path=None) -> list[dict]:
    """Per market, for the Record page — including "memory off" rows: a
    memory the record tried and rejected is part of the story."""
    out = []
    for key, d in sorted(_load(path).items()):
        if not isinstance(d, dict):
            continue
        sport, _, market = key.partition(":")
        players = d.get("players") or {}
        worst = sorted(
            ({"player": n, "mult": float(r.get("mult", 1.0)),
              "games": int(r.get("games", 0))}
             for n, r in players.items() if isinstance(r, dict)),
            key=lambda r: -abs(r["mult"] - 1.0))[:4]
        journal = d.get("basis") == "journal-mae"
        out.append({
            "sport": d.get("sport") or sport,
            "market": d.get("market") or market or key,
            "adopted": bool(d.get("adopted")),
            "samples": int(d.get("samples", 0) or 0),
            "brier_baseline": d.get("brier_baseline"),
            "brier_corrected": d.get("brier_corrected"),
            # Journal-fitted entries score by projection MAE, not Brier —
            # the page must label the number it shows, not borrow a name.
            "score_label": "proj error" if journal else "Brier",
            "score_baseline": (d.get("mae_baseline") if journal
                               else d.get("brier_baseline")),
            "score_corrected": (d.get("mae_corrected") if journal
                                else d.get("brier_corrected")),
            "n_players": len(players),
            "top": worst,
            "fitted": d.get("fitted"),
            "reading": (f"{len(players)} player(s) corrected"
                        if d.get("adopted") else "memory off — didn't help"),
        })
    return out
