#!/usr/bin/env python3
"""Is the crowd right? Kalshi and Polymarket against the books and our model.

    python3 crowdfit.py            # read the history DB, print the report

Joins the pregame prices every build records (engine/crowd, table
crowd_snaps) to the final scores and prints three answers: which source
is most accurate, whether the prediction markets know something the
books do not, and whether a late price swing keeps going. See
engine/crowdfit for the maths and the bar a finding must clear.
"""

from __future__ import annotations

import argparse

from engine import crowdfit
from engine.db import DEFAULT_DB, connect


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help="history database")
    ap.add_argument("--no-write", action="store_true", help="print only; leave the state file alone")
    args = ap.parse_args()
    conn = connect(args.db)
    try:
        state = crowdfit.run(conn, write=not args.no_write)
    finally:
        conn.close()
    print(crowdfit.report(state))


if __name__ == "__main__":
    main()
