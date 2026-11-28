#!/usr/bin/env python3
"""Quarterback-receiver chemistry, measured (engine/chemfit.py; what engine/qblean ships).

    python3 chemfit.py                  # 2017 to this season, settings chosen on 2021-2023
    python3 chemfit.py --first 2019

Reads nflverse's play-by-play and rosters through the box's loaders (each season's file, cached a day) and prints
each test's held-out seasons, its interval and whether it passes the bar written in engine/chemfit.
"""
import sys

from engine.chemfit import main

if __name__ == "__main__":
    sys.exit(main())
