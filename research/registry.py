#!/usr/bin/env python3
"""The research registry and data audit, checked and loaded into tables.

    python3 research/registry.py                 the ledger: every experiment, its status and decisions
    python3 research/registry.py --sources       the data-source matrix
    python3 research/registry.py --db lab.db     load both into SQLite (research/schema.sql)

research/registry.json and research/sources.json are the source of truth,
reviewed in git like code; this checks them (every field the spec's Part 11
asks for, a known novelty class and status, numbers where a result is
claimed) and writes the spec's tables. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REQUIRED = ("id", "sport", "market", "proposed", "question", "equation", "variables", "mechanism",
            "prior_art", "novelty", "data", "dataset_version", "code", "baseline", "protocol",
            "primary_metric", "sample_size", "results", "decision", "multiple_testing",
            "failure_modes", "next", "status")
SOURCE_FIELDS = ("id", "sports", "provider", "dataset", "url", "access", "coverage", "update", "ids",
                 "missing", "quality", "license", "verified", "status")
SOURCE_STATUSES = ("VERIFIED", "PARTIALLY VERIFIED", "UNVERIFIED", "UNAVAILABLE")
#: Statuses that claim a measurement, so they must carry at least one result.
MEASURED = ("BACKTESTED", "HOLDOUT VALIDATED", "PROSPECTIVELY TESTED", "INDEPENDENTLY REPLICATED")


def load(path: Path | None = None) -> dict:
    return json.loads((path or HERE / "registry.json").read_text(encoding="utf-8"))


def load_sources(path: Path | None = None) -> dict:
    return json.loads((path or HERE / "sources.json").read_text(encoding="utf-8"))


def problems(reg: dict, src: dict) -> list[str]:
    """Every way the registry or the audit breaks its own rules; [] when sound."""
    out = []
    source_ids = set()
    for s in src.get("sources", []):
        sid = s.get("id", "?")
        missing = [f for f in SOURCE_FIELDS if f not in s or s[f] in (None, "")]
        if missing:
            out.append(f"{sid}: missing {', '.join(missing)}")
        if s.get("status") not in SOURCE_STATUSES:
            out.append(f"{sid}: status {s.get('status')!r} is not one of {SOURCE_STATUSES}")
        if sid in source_ids:
            out.append(f"{sid}: listed twice")
        source_ids.add(sid)
    seen = set()
    for e in reg.get("experiments", []):
        eid = e.get("id", "?")
        missing = [f for f in REQUIRED if f not in e]
        if missing:
            out.append(f"{eid}: missing {', '.join(missing)}")
            continue
        if eid in seen:
            out.append(f"{eid}: listed twice")
        seen.add(eid)
        if str(e["novelty"]) not in reg.get("novelty_classes", {}):
            out.append(f"{eid}: novelty {e['novelty']!r} is not a known class")
        if e["status"] not in reg.get("statuses", []):
            out.append(f"{eid}: status {e['status']!r} is not a known status")
        if e["status"] in MEASURED and not e["results"]:
            out.append(f"{eid}: status {e['status']} claims a measurement but lists no result")
        for d in e["data"]:
            if d not in source_ids:
                out.append(f"{eid}: data source {d} is not in sources.json")
        for r in e["results"]:
            if not isinstance(r.get("value"), (int, float)):
                out.append(f"{eid}: a result without a number ({r.get('market')})")
            lo, hi = r.get("lo"), r.get("hi")
            if lo is not None and hi is not None and not lo <= r["value"] <= hi:
                out.append(f"{eid}: {r.get('market')} value {r['value']} sits outside its own interval")
        if not (HERE.parent / e["code"].split()[0]).exists():
            out.append(f"{eid}: code {e['code']} does not exist")
    return out


def to_sqlite(conn, reg: dict, src: dict) -> dict:
    conn.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))
    for t in ("experiment_decisions", "experiment_results", "experiments", "data_sources"):
        conn.execute(f"DELETE FROM {t}")
    for s in src["sources"]:
        conn.execute("INSERT INTO data_sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (s["id"], s["provider"], s["dataset"], s["url"], s["access"], ",".join(s["sports"]),
                      s["coverage"], s["update"], s["ids"], s["missing"], s["quality"], s["license"],
                      s["verified"], s["status"]))
    n_res = 0
    for e in reg["experiments"]:
        conn.execute("INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (e["id"], e["question"][:120], e["sport"], e["market"], e["question"], e["equation"],
                      e["variables"], e["mechanism"], e["prior_art"], str(e["novelty"]), ",".join(e["data"]),
                      e["dataset_version"], e["code"], e["baseline"], e["protocol"], e["primary_metric"],
                      e["sample_size"], e["multiple_testing"], e["failure_modes"], e["next"], e["status"],
                      e["proposed"]))
        for r in e["results"]:
            conn.execute("INSERT INTO experiment_results (experiment_id, evaluation_period, subject, metric_name, "
                         "metric_value, uncertainty_lower, uncertainty_upper, notes) VALUES (?,?,?,?,?,?,?,?)",
                         (e["id"], r["period"], r.get("market"), r["metric"], r["value"], r.get("lo"), r.get("hi"),
                          r.get("notes")))
            n_res += 1
        for subject, decision in e["decision"].items():
            conn.execute("INSERT INTO experiment_decisions VALUES (?,?,?)", (e["id"], subject, decision))
    conn.commit()
    return {"sources": len(src["sources"]), "experiments": len(reg["experiments"]), "results": n_res}


def ledger_text(reg: dict) -> str:
    lines = ["Research registry — every candidate, run or refused"]
    for e in reg["experiments"]:
        lines.append(f"\n{e['id']}  [{e['status']}]  {e['sport']} · {e['market']}")
        lines.append(f"  {e['question']}")
        lines.append(f"  novelty: {reg['novelty_classes'][str(e['novelty'])]}")
        for k, v in e["decision"].items():
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def sources_text(src: dict) -> str:
    lines = ["Data sources — status as of each entry's verified date"]
    for s in src["sources"]:
        lines.append(f"\n{s['id']}  [{s['status']}]  {s['provider']} — {s['dataset']}")
        lines.append(f"  sports: {', '.join(s['sports'])}; access: {s['access']}")
        lines.append(f"  coverage: {s['coverage']}")
        lines.append(f"  missing: {s['missing']}; license: {s['license']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sources", action="store_true", help="print the data-source matrix")
    ap.add_argument("--db", help="load the registry and the audit into this SQLite file")
    a = ap.parse_args(argv)
    reg, src = load(), load_sources()
    bad = problems(reg, src)
    if bad:
        print("registry problems:\n  " + "\n  ".join(bad))
        return 1
    if a.db:
        with sqlite3.connect(a.db) as conn:
            print(to_sqlite(conn, reg, src))
        return 0
    print(sources_text(src) if a.sources else ledger_text(reg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
