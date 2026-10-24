"""What the iPhone widget shows: the record, last night, and tonight's boards.

    python3 -m engine.widgetfeed         # the widget's JSON, as the box would serve it

Ethan, 2026-10-24: "build everything ... including all the ideas" — docs/
IDEAS.md 11, Apple Sports' best thing: a Home Screen widget. The widget
(deploy/ios/native/QellysWidget.swift) asks GET /api/widget every half hour
and draws what this returns.

PUBLIC BY DESIGN. A widget cannot sign in (it runs outside the app, on a
schedule iOS picks), so it shows only what the site gives everybody: the
record (free, engine/ledger), last night's line (the same one the email and
the alerts read, engine/digest.last_night), and how many picks each league
has up today — a count, as the "picks are up" alert says it, never a pick.

Standard library only; reads the boards where the box writes them.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _load(path: Path) -> dict:
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8"))
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def build(web: Path = WEB, today: _dt.date | None = None) -> dict:
    from engine import digest, gate, pushalerts as PA
    web = Path(web)
    today = today or _dt.date.today()
    rec = _load(web / "data" / "record_head.json") or _load(web / "data" / "record.json")
    ov = rec.get("overall") or {}
    record = None
    if ov.get("settled"):
        record = {"w": int(ov.get("wins") or 0), "l": int(ov.get("losses") or 0), "p": int(ov.get("pushes") or 0),
                  "units": round(float(ov.get("net_units") or 0), 1), "roi": round(float(ov.get("roi") or 0) * 100, 1)}
    night = digest.last_night(web)
    tonight = []
    for sport, file, label in PA.LEAGUES:
        board = PA._load(gate.board_source(web / "data" / file))
        n, date = PA._picks(board), str(board.get("date") or "")
        if n and date and not (len(date) == 10 and date < today.isoformat()):
            tonight.append({"league": label, "sport": sport, "picks": n, "url": f"/?sport={sport}#recommended"})
    return {"record": record,
            "last_night": ({"date": night["date"], "w": night["w"], "l": night["l"], "p": night["p"],
                            "units": night["net_u"]} if night and (night["w"] or night["l"]) else None),
            "tonight": tonight,
            "updated": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "url": "/#recommended"}


def main(argv=None) -> int:
    print(json.dumps(build(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
