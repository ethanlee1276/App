#!/usr/bin/env bash
# Every read-only check in docs/WHEN_YOU_ARE_HOME.md that can run on any
# day, in one go, each under its block's letter.
#
# Ethan, 2026-10-15: "I want you to check the runbook and make sure that
# there's no code at all that I still need to run". Forty-odd lettered
# blocks had never been pasted back. Most only confirm that a feature the
# box already runs does what it should, so they are here as one command:
#
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh 2>&1 | tee /tmp/catchup.txt
#
# Letters after it run those blocks only, in this file's order (2026-10-24,
# the runbook's DH: every check from CT on, the night Ethan got home):
#
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh CT CU CV CW CX CY CZ DA DB DC DD DE DG DH BK 2>&1 | tee /tmp/tonight.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh CY DA DE DB2 DI 2>&1 | tee /tmp/di.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DE DJ 2>&1 | tee /tmp/dj.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DK 2>&1 | tee /tmp/dk.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DL 2>&1 | tee /tmp/dl.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DM 2>&1 | tee /tmp/dm.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DN 2>&1 | tee /tmp/dn.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DK DL DM DN 2>&1 | tee /tmp/dn.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DO 2>&1 | tee /tmp/do.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DK DL DM DN DO 2>&1 | tee /tmp/do.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DP 2>&1 | tee /tmp/dp.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DK DL DM DN DO DP 2>&1 | tee /tmp/dp.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DQ 2>&1 | tee /tmp/dq.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DK DL DM DN DO DP DQ 2>&1 | tee /tmp/dq.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DR 2>&1 | tee /tmp/dr.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DK DL DM DN DO DP DQ DR 2>&1 | tee /tmp/dr.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DS 2>&1 | tee /tmp/ds.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DK DL DM DN DO DP DQ DR DS 2>&1 | tee /tmp/ds.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DT 2>&1 | tee /tmp/dt.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DU 2>&1 | tee /tmp/du.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DV 2>&1 | tee /tmp/dv.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DW 2>&1 | tee /tmp/dw.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DX 2>&1 | tee /tmp/dx.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DY 2>&1 | tee /tmp/dy.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh DZ 2>&1 | tee /tmp/dz.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EA 2>&1 | tee /tmp/ea.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EB 2>&1 | tee /tmp/eb.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EC 2>&1 | tee /tmp/ec.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh ED 2>&1 | tee /tmp/ed.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EE 2>&1 | tee /tmp/ee.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EF 2>&1 | tee /tmp/ef.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EG 2>&1 | tee /tmp/eg.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EH 2>&1 | tee /tmp/eh.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EI 2>&1 | tee /tmp/ei.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EJ 2>&1 | tee /tmp/ej.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EK 2>&1 | tee /tmp/ek.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EL 2>&1 | tee /tmp/el.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EM 2>&1 | tee /tmp/em.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EN 2>&1 | tee /tmp/en.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EO 2>&1 | tee /tmp/eo.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EP 2>&1 | tee /tmp/ep.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EQ 2>&1 | tee /tmp/eq.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh ER 2>&1 | tee /tmp/er.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh ES 2>&1 | tee /tmp/es.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh ET 2>&1 | tee /tmp/et.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EU 2>&1 | tee /tmp/eu.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EV 2>&1 | tee /tmp/ev.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EX 2>&1 | tee /tmp/ex.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EY 2>&1 | tee /tmp/ey.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh EZ 2>&1 | tee /tmp/ez.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh FA 2>&1 | tee /tmp/fa.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh FB 2>&1 | tee /tmp/fb.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh FC 2>&1 | tee /tmp/fc.txt
#   cd /srv/qellys && nice -n 19 bash tools/catchup.sh FD 2>&1 | tee /tmp/fd.txt
#
# Quick checks first and the slow measurements last (AT, BE, M2, P2, O, AD,
# E: about half an hour together), so a stop part-way still has the quick
# ones on screen. Each block has its own time limit; one that stops or fails
# says so, and the next one runs anyway.
#
# READ-ONLY. Every command is the runbook's own line, word for word (a test
# holds this file to the runbook), with the writing ones left out:
#   * M's and K's --fill, Q's photo fill, AD's fit-and-save, AP's chart fill,
#     AZ's cap change, BB's --apply: each writes, and the chores do them anyway;
#   * AR re-downloads Savant's files, as the next MLB build would.
# Two lines differ from the runbook, both to print less or write nothing:
#   * AD's test runs with --dry-run (the runbook says to add it to print
#     without saving);
#   * K reads the last 20 lines of the weekly chart-fill log, not all of it.
# A's merge-base line moves with every push, so only its first line is here.
#
# NOT HERE, because they need a moment that is not now:
#   BH, BI, BJ   during games (NBA, NHL, football and baseball live pages)
#   BG           Friday and Monday, after Thursday night's game settles
#   N, S (second lines)  from the NBA's opening night, the 20th
#   AX's second, AY      the morning after / the day of a UFC card
#   C, D's Stripe settings, F, AE, AJ and the phone halves of the rest:
#                your hands, not the box
#   DF           the iPhone Duo, on the phone
# BK waited for week 6 to settle (the third held-out week its bar needs); it
# has, and it runs with the quick ones now.
# AND NOT HERE BECAUSE THEY WRITE: CT's NBA rebuilds (one buys odds), CV's
# reset-day setting, CW's fantasy fit (--save), DA's inventions run (it saves
# their verdicts, and runs itself every Thursday), CZ's linemen study (it
# fetches any old season's files it lacks; already run, nothing applied),
# DM's pushalerts --send (it records and sends what is owed), DN's and DO's
# Caddyfile install (it reloads the web server).
set -u

ONLY=""
[ "$#" -gt 0 ] && ONLY=" $* "
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1
if [ "$(id -u)" != 0 ]; then
  echo "Run it as root: the checks read the service log and act as the qellys user."
  exit 1
fi

# One block: its commands from the heredoc, run with nothing on stdin (so no
# command can swallow the next block's lines), under a time limit.
run() {
  local letter="$1" title="$2" limit="$3" cmds start rc
  cmds="$(cat)"
  # Letters on the command line run those blocks only (DB also runs DB2).
  if [ -n "${ONLY:-}" ] && [[ "$ONLY" != *" $letter "* && "$ONLY" != *" ${letter%%[0-9]*} "* ]]; then
    return
  fi
  start=$SECONDS
  echo
  echo "===== $letter. $title"
  timeout "$limit" bash -c "$cmds" < /dev/null 2>&1
  rc=$?
  [ "$rc" = 124 ] && echo "  (stopped after ${limit}s)"
  echo "  ($((SECONDS - start))s)"
}

echo "catch-up $(date -Iseconds) on $(git -C "$REPO" log --oneline -1 2>/dev/null)"

run A "The box has today's code (the commit it runs)" 30 <<'SH'
git -C /srv/qellys log --oneline -1
SH
run B "Health check" 60 <<'SH'
uptime; free -m
ps -eo pid,ni,pcpu,pmem,etime,args --sort=-pcpu | head -8
for p in / /js/app.js /data/recommendations.json /data/record.json; do curl -s -o /dev/null -w "$p %{http_code} %{size_download}B %{time_total}s\n" http://127.0.0.1:8000$p; done
journalctl -u qellys --since "2 hours ago" --no-pager | grep -iE "refresh|cycle|took|build|slip watch" | grep -v "/api/" | tail -15
SH
run C "Is email on? (reset_by_email true means yes)" 30 <<'SH'
curl -s http://127.0.0.1:8000/api/account/me; echo
SH
run D "Stripe: subscriptions read from Stripe (statuses and counts only)" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "import time; from engine import accounts as A, billing as B; c=A.connect(); B.init(c); n=time.time(); print([tuple(r) for r in c.execute('SELECT status, COUNT(*), SUM(checked_at IS NOT NULL), ROUND(MAX(?-checked_at)/3600.0,1) FROM subscriptions GROUP BY status', (n,))])"
cd /srv/qellys && sudo -u qellys python3 -c "import time; from engine import accounts as A, billing as B; c=A.connect(); B.init(c); print(c.execute('SELECT ROUND(?-MAX(checked_at)) FROM subscriptions', (time.time(),)).fetchone()[0])"
SH
run G "Saved-slip alerts, and the hockey box file" 60 <<'SH'
journalctl -u qellys --since "12 hours ago" --no-pager | grep "slip watch"
cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A; c = A.connect(); print([tuple(r) for r in c.execute('SELECT user_id, bet_id, fired_at, mailed FROM slip_alerts')])"
cd /srv/qellys && sudo -u qellys python3 -c "import json; d=json.load(open('web/data/live_nhl_box.json')); print(d['generated_at'], [(g['away']+'@'+g['home'], g['state'], len(g['players'])) for g in d['games']])"
SH
run J "Bets settle minutes after the final" 120 <<'SH'
journalctl -u qellys --since "6 hours ago" --no-pager | grep -E "settle:|settled|box scores|UFC:|desk:" | tail -20
cd /srv/qellys && sudo -u qellys python3 settlecheck.py
SH
run K "The carry and route charts are filled" 300 <<'SH'
journalctl -u qellys --since "today" --no-pager | grep -E "charts:|engine.chartfill" | tail -8; sudo -u qellys tail -20 /srv/qellys/data/cache/weekly_chartfill.log
cd /srv/qellys && sudo -u qellys python3 carryfill.py && sudo -u qellys python3 routefill.py
SH
run M "College receivers thrown at who caught nothing (check only)" 300 <<'SH'
cd /srv/qellys && sudo -u qellys python3 cfbzeros.py
SH
run N "The NBA board's rosters and injury words" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "
import collections, nba_build
t, missed = nba_build.current_teams('nba')
print(len(t), 'players placed by the club rosters; clubs missing:', missed or 'none')
i = nba_build.hoops_injuries('nba')
print(len(i), 'on the injury board:', dict(collections.Counter(v['status'] for v in i.values())))
"
SH
run P1 "UFC line moves on the card" 30 <<'SH'
grep "Line moves" /srv/qellys/data/logs/ufc_build.log
SH
run Q "Every chart shows the player's face (check only)" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 facesfill.py --check
journalctl -u qellys --since "today" --no-pager | grep "faces:"
SH
run R "College grading waits on the play file" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 homecheck.py grading
SH
run S "The NBA's priced markets and credits" 30 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "from engine.sources.oddsapi import SPORT_CONFIG as C; from engine.oddsbudget import EVENT_CREDITS as E; print(sorted(C['nba']['markets'].values())); print(E['nba'], E['wnba'])"
SH
run T "The football charts on the pick page" 60 <<'SH'
curl -s http://127.0.0.1:8000/js/carrychart.js | grep -c "function mount(el)"
curl -s "http://127.0.0.1:8000/api/players/routes?sport=nfl&player=Amon-Ra%20St.%20Brown" | head -c 300; echo
SH
run U "The passing chart" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute('SELECT season, kind, COUNT(*) FROM passes GROUP BY season, kind ORDER BY season DESC').fetchall())"
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db, passes; c=db.connect(); d=passes.chart(c, 'Josh Allen', 2026); g=[x for x in d['games'] if x['week']==5][0]; print(g['opp'], {k: g['line'][k] for k in ('att','cmp','yds','td','int','sk')})"
curl -s "http://127.0.0.1:8000/api/players/chart?kind=passes&sport=nfl&player=Josh%20Allen" | head -c 300; echo
SH
run V "The college target chart" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute(\"SELECT season, COUNT(*), SUM(complete) FROM targets WHERE sport='cfb' GROUP BY season\").fetchall())"
curl -s "http://127.0.0.1:8000/api/players/routes?sport=cfb&player=Jeremiah%20Smith" | head -c 300; echo
SH
run W "The hit tracker and the pitch chart" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute('SELECT season, COUNT(DISTINCT game_pk), COUNT(*) FROM mlb_pa GROUP BY season').fetchall(), c.execute('SELECT season, COUNT(*) FROM mlb_pitches GROUP BY season').fetchall())"
curl -s "http://127.0.0.1:8000/api/players/chart?kind=spray&sport=mlb&player=Aaron%20Judge" | head -c 300; echo
curl -s "http://127.0.0.1:8000/api/players/chart?kind=pitches&sport=mlb&player=Tarik%20Skubal" | head -c 300; echo
sudo -u qellys tail -5 /srv/qellys/data/cache/weekly_chartfill.log
SH
run X "The NBA shot chart (stored shots and the page's ask)" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute('SELECT season, COUNT(DISTINCT game_id), COUNT(*) FROM nba_shots GROUP BY season').fetchall())"
curl -s "http://127.0.0.1:8000/api/players/chart?kind=shots&sport=nba&player=Nikola%20Jokic" | head -c 300; echo
sudo -u qellys tail -5 /srv/qellys/data/cache/weekly_chartfill.log
SH
run Y "The NHL shot map and save map" 60 <<'SH'
curl -s "http://127.0.0.1:8000/api/players/chart?kind=shotmap&sport=nhl&player=Auston%20Matthews" | head -c 300; echo
curl -s "http://127.0.0.1:8000/api/players/chart?kind=saves&sport=nhl&player=Igor%20Shesterkin" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('season_label'), d.get('season_line'), d.get('xg_model'))"
SH
run Z "The role chart in every league" 120 <<'SH'
for q in "nfl&player=Ja%27Marr%20Chase" "cfb&player=Jeremiah%20Smith" "nba&player=Jalen%20Brunson" "wnba&player=Caitlin%20Clark" "mlb&player=Aaron%20Judge" "nhl&player=Auston%20Matthews"; do curl -s "http://127.0.0.1:8000/api/players/chart?kind=role&sport=$q" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sport'), d.get('player'), d.get('lead'), [m['key'] for m in d.get('metrics', [])], (d.get('season_line') or {}).get('n'))"; done
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='index' AND name IN ('nhl_shots_shooter','nhl_shots_goalie','mlb_pa_batter_name','mlb_pa_pitcher_name','nba_shots_name')\")])"
SH
run AA "The kicker chart" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(c.execute('SELECT season, kind, COUNT(*) FROM kicks GROUP BY season, kind').fetchall())"
curl -s "http://127.0.0.1:8000/api/players/chart?kind=kicks&sport=nfl&player=Brandon%20Aubrey" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('player'), d.get('season_line'), [(b['name'], b['fgm'], b['fga'], b['league']) for b in d.get('by_band', [])])"
sudo -u qellys tail -5 /srv/qellys/data/cache/weekly_chartfill.log
SH
run AB "The UFC fight history" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print(tuple(c.execute('SELECT COUNT(DISTINCT fighter), COUNT(*) FROM ufc_fights').fetchone()), tuple(c.execute('SELECT COUNT(*), SUM(fights = 0) FROM ufc_fighters_read').fetchone()))"
journalctl -u qellys --since "6 hours ago" --no-pager | grep "fight history" | tail -5
f=$(cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; r=db.connect().execute('SELECT fighter FROM ufc_fighters_read WHERE fights > 0 ORDER BY fetched DESC LIMIT 1').fetchone(); print(r[0] if r else '')"); echo "$f"; curl -s "http://127.0.0.1:8000/api/players/chart?kind=fights&sport=ufc&player=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$f")" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('player'), d.get('season_line'), [(g['opp'], g['result'], g['method'], g['rnd'], g['clock']) for g in d.get('games', [])[:3]])"
SH
run AC "The matchup view in every league" 300 <<'SH'
for q in "nfl&player=Ja%27Marr%20Chase&opp=PIT" "nfl&player=Derrick%20Henry&opp=CLE" "cfb&player=Jeremiah%20Smith&opp=Penn%20State" "nba&player=Jalen%20Brunson&opp=BOS" "nhl&player=Auston%20Matthews&opp=MTL&fam=shotmap" "nhl&player=Igor%20Shesterkin&opp=TOR&fam=saves" "mlb&player=Aaron%20Judge&opp=TOR&fam=spray"; do curl -s "http://127.0.0.1:8000/api/players/chart?kind=matchup&sport=$q" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sport'), d.get('player'), d.get('family'), d.get('opp'), d.get('season'), d.get('fit'), (d.get('overall') or {}).get('rank'), d.get('starter', ''))"; done
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; c=db.connect(); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='index' AND name IN ('carries_season','targets_season','passes_season','nba_shots_opp','nhl_shots_season','mlb_pa_season')\")])"
SH
run AF "Every league's Most Likely cards" 60 <<'SH'
cd /srv/qellys && for f in recommendations cfb mlb_recommendations nba wnba nhl; do python3 -c "import json,sys; f=sys.argv[1]; import os; p='data/built/'+f+'.json'; d=json.load(open(p if os.path.exists(p) else 'web/data/'+f+'.json')); ml=d.get('most_likely') or []; print(f, len(ml), 'picks |', sum(1 for r in ml if r.get('matchup_card')), 'matchup |', sum(1 for r in ml if r.get('mate_card')), 'teammate |', d.get('likely_board',{}).get('matchup_source'))" $f 2>/dev/null || echo "$f: no board"; done
journalctl -u qellys --since "3 hours ago" --no-pager | grep -E "Matchup cards:" | tail -3
SH
run AH "UFC round prices" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "from engine import db; from engine.ufc import rounds as R; c=db.connect(); print({n: len(R.league(c, n)) for n in (3, 5)}, 'need', R.MIN_LEAGUE)"
journalctl -u qellys --since "6 hours ago" --no-pager | grep -E "Round prices:" | tail -3
SH
run AK "A back's chart reads his newest final" 30 <<'SH'
curl -s "http://127.0.0.1:8000/api/players/carries?sport=nfl&player=James%20Cook" | python3 -c "import json,sys; d=json.load(sys.stdin); g=(d.get('games') or [{}])[0]; print(g.get('week'), g.get('opp'), g.get('score'), g.get('rec'), g.get('orec'))"
SH
run AL "The NBA, MLB and NHL charts read their newest final" 60 <<'SH'
for q in "shots&sport=nba&player=Nikola%20Jokic" "spray&sport=mlb&player=Aaron%20Judge" "shotmap&sport=nhl&player=Auston%20Matthews"; do curl -s "http://127.0.0.1:8000/api/players/chart?kind=$q" | python3 -c "import json,sys; d=json.load(sys.stdin); g=(d.get('games') or [{}])[0]; print(d.get('sport'), d.get('player'), g.get('date'), g.get('opp'), g.get('score'))"; done
SH
run AM "Memory, restarts and every board's age" 120 <<'SH'
git -C /srv/qellys log --oneline -1; cat /srv/qellys/data/autoupdate.json; echo
systemctl show qellys -p ActiveState -p NRestarts -p ExecMainStartTimestamp -p MemoryCurrent
free -m; swapon --show; df -h /srv | tail -1
journalctl -k --since "2 days ago" --no-pager | grep -iE "oom-kill|out of memory|killed process" | tail -12
journalctl -u qellys --since "2 days ago" --no-pager | grep -iE "killed by signal|out of memory|database is locked|build failed|mlb charts|nba shots|charts:|watchdog|auto-update" | tail -30
python3 -c "import json,time; d=json.load(open('/srv/qellys/web/data/heartbeat.json')); print(round((time.time()-d['at_epoch'])/60), 'min since the last cycle;', d.get('swept'), '; cycle', d.get('cycle_s'), 's; running', d.get('commit'), ';', d.get('disk_free_gb'), 'GB free')"
for f in recommendations cfb mlb_recommendations nba wnba nhl ufc; do printf "%-20s %s\n" $f "$(stat -c %y /srv/qellys/web/data/$f.json 2>/dev/null | cut -c1-16)"; done
for u in "/api/players/search?q=allen&sport=nfl&scope=sport" "/api/recommendations" "/api/nba/recommendations"; do curl -s -o /dev/null -w "%{http_code} %{size_download}B %{time_total}s  $u\n" "http://127.0.0.1:8000$u"; done
ps -eo pid,ni,rss,etime,args --sort=-rss | head -6
SH
run AN "The hit page reads" 30 <<'SH'
curl -s "http://127.0.0.1:8000/api/players/chart?kind=spray&sport=mlb&player=Aaron%20Judge" | python3 -c "import json,sys; d=json.load(sys.stdin); g=d.get('games') or []; p=[x for y in g for x in y['pas']]; L=d.get('season_line') or {}; print(d.get('player'), d.get('position'), d.get('jersey'), d.get('team'), d.get('season'), '| charted', len(g), 'of', d.get('logged'), 'games | AVG', L.get('avg'), 'OBP', L.get('obp'), 'OPS', L.get('ops'), '| with pitches', sum(1 for x in p if x.get('ps')), 'of', len(p))"
SH
run AO "The hit tracker answers fast" 120 <<'SH'
B="http://127.0.0.1:8000/api/players/chart?sport=mlb&player=Aaron%20Judge"; for k in "kind=spray" "kind=role" "kind=matchup&opp=DET&fam=spray" "kind=spray" "kind=role" "kind=matchup&opp=DET&fam=spray"; do curl -s -o /dev/null -w "$k %{http_code} %{time_total}s %{size_download}B\n" "$B&$k"; done; curl -s "$B&kind=spray" | python3 -c "import json,sys; print('face:', json.load(sys.stdin).get('face'))"
SH
run AP "The hit page's seven pieces" 300 <<'SH'
cd /srv/qellys && sudo -u qellys python3 hitpagecheck.py
SH
run AQ "Every league's Pick of the Day reaches its record" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 potdcheck.py
SH
run AS "Where each sweep's minutes go" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 launch.py --boards
SH
run AV "Quarterback carries on the NFL board" 30 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "
import json; from engine.gate import board_source
b = json.load(open(board_source('web/data/recommendations.json')))
q = [r for r in b.get('recommendations') or [] if r.get('market') == 'rush_att' and r.get('position') == 'QB']
print(len(q), 'quarterback carries rows')
for r in q[:12]: print(r['player'], r.get('side'), r.get('line'), r.get('odds'), r.get('book'), r.get('projection'))"
SH
run AW "The college read sees each depth order" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "
import json; from engine.gate import board_source; from engine import slipread as SR
from engine.teammates import _norm
b = json.load(open(board_source('web/data/cfb.json'))); c = SR._connect(); s = SR._seasons(c, 'cfb')[0]; n = 0
for g in b.get('games') or []:
    for t, x in SR._cfb_lineup(c, b, g, s, g.get('home'), g.get('away')).items():
        n += any(x['order'].values())
        out = [o[0] for r in x['order'].values() for o in r if _norm(o[0]) in x['out']]
        if out: print(t, 'out on the order:', ', '.join(out))
print(n, 'college team(s) with a depth order, season', s)"
SH
run AX "UFC fights in the parlay checker" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "
from engine import slipgrade as SG, slipfight as SF
b = SG.with_fights({}).get('ufc') or {}
print(b.get('event_date') or 'no card', len(SF.bouts(b)), 'bout(s)')
for r in SF.bouts(b):
    a, c = SF.corners(r)
    p = SG.price_leg({'ufc': b}, {'sport': 'ufc', 'player': '', 'team': a, 'game': r['fight'], 'market': 'moneyline', 'side': 'team', 'line': 0.0, 'odds': 0, 'text': ''})
    print(r['fight'], '|', a, 'wins', 'no number: ' + str(r.get('why'))[:60] if p['prob'] is None else round(p['prob'], 3))"
SH
run AY "The UFC Pick of the Day and its books" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 potdcheck.py | grep -E -A1 "^ufc|^record.json"
cd /srv/qellys && sudo -u qellys python3 ufcbooks.py
SH
run AZ "Fresh prices for uploaded slips" 30 <<'SH'
journalctl -u qellys --since "24 hours ago" --no-pager | grep "slip odds" | tail -10
cd /srv/qellys && sudo -u qellys python3 -c "from engine import slipodds as SO; print(SO.spent_today(), 'of', SO.daily_cap(), 'fresh-price credits spent today;', SO.spare_credits(), 'spare this month')"
SH
run AU "Saved slips settle with the Live tab closed" 30 <<'SH'
journalctl -u qellys --since "24 hours ago" --no-pager | grep "slip watch" | tail -12
SH
run BA "The boards journal while the settle pass runs" 60 <<'SH'
cd /srv/qellys && grep -h "journal skipped" data/logs/*.log | sort | uniq -c
journalctl -u qellys --since "24 hours ago" --no-pager | grep -c "database is locked"
SH
run BF "Every league's card gets its photo" 300 <<'SH'
cd /srv/qellys && sudo -u qellys python3 photocheck.py
SH
run CT "NBA opening night: the build, its odds calls, the board and live" 120 <<'SH'
cd /srv/qellys && git log -1 --format='%h %ci %s' && journalctl -u qellys --since "2026-10-20 12:00" --no-pager | grep -E "nba_build|NBA " | tail -20
cd /srv/qellys && sudo -u qellys python3 -c "import time; from engine.oddsbudget import decisions; [print(r['iso'][11:16], r['lane'], 'BUY' if r['ok'] else 'no ', r['reason'][:120]) for r in decisions(since=time.time()-16*3600) if r['lane'].startswith('nba')][-12:]"
cd /srv/qellys && sudo -u qellys python3 -c "import json; from engine.gate import board_source; b=json.load(open(board_source('web/data/nba.json'))); print(b.get('generated_at'), b.get('status'), len(b.get('recommendations') or []), 'props'); [print(g['away'],'@',g['home'], g.get('spread'), g.get('total'), g.get('away_ml'), g.get('home_ml'), (g.get('live') or {}).get('state')) for g in b.get('games') or []]"
cd /srv/qellys && sudo -u qellys python3 -c "import json; d=json.load(open('web/data/live_nba.json')); print(d.get('generated_at'), d.get('note') or ''); [print(g.get('away'),'@',g.get('home'),(g.get('live') or {}).get('state'),(g.get('live') or {}).get('detail')) for g in d.get('games') or []]"
SH
run CU "The live scoreboard on a phone" 30 <<'SH'
cd /srv/qellys && git log -1 --format='%h %ci %s' && grep -c "hc-watch { grid-column: 1 / -1" web/css/hoopscast.css
SH
run CV "The month's odds plan" 60 <<'SH'
cd /srv/qellys && git log -1 --format='%h %ci %s' && sudo -u qellys python3 -m engine.oddsplan
SH
run CW "Fantasy reads the NFL board: the saved week" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "from engine import fantasyweek as F; d=F.load(); print(F.summary_line(d)); print('week', d.get('week'), '· this week:', F.current(d), '· byes:', d.get('byes'))"
SH
run CX "The short version reads in sentences" 30 <<'SH'
cd /srv/qellys && git log -1 --format='%h %ci %s' && grep -c "Where the matchup tilts" engine/gamereport.py
SH
run CY "The box updates itself" 30 <<'SH'
cd /srv/qellys && cat data/autoupdate.json; echo; journalctl -u qellys-update --since "1 day ago" --no-pager | grep -E "ok: |FAILED: " | tail -3
SH
run CZ "The Patriots-Bears fixes are in" 30 <<'SH'
cd /srv/qellys && git log -1 --format='%h %ci %s' && grep -c "def line_sentence" engine/gamereport.py
SH
run DA "The inventions in the picks" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.ideagate --sport nfl
SH
run DB "Burden on the board and his season" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "
import json, sqlite3
from engine.calibrate import shut_reason
d = json.load(open('data/built/recommendations.json'))
for r in d.get('recommendations') or []:
    if 'Burden' in (r.get('player') or ''):
        bad = [c.get('key') for c in r.get('checks') or [] if not c.get('passed')]
        why = 'market shut' if shut_reason('nfl', r.get('market')) else ', '.join(bad or ['-'])
        print('edge:', r.get('market'), r.get('side'), r.get('line'), r.get('odds'), 'ours', round(100 * (r.get('hit_prob') or 0)), 'pick' if r.get('recommended') else 'no pick: ' + why)
print('most likely:', [(r.get('market'), r.get('side'), r.get('line'), r.get('odds')) for r in d.get('most_likely') or [] if 'Burden' in (r.get('player') or '')] or 'not on it')
c = sqlite3.connect('data/ledger.db')
print('season picks:', c.execute(\"SELECT category, COUNT(*) FROM bets WHERE sport='nfl' AND player LIKE '%Burden%' GROUP BY category\").fetchall())
"
SH
run DC "The past-the-cap list and the box's curve on Burden" 60 <<'SH'
cd /srv/qellys && git log -1 --format='%h %ci %s' && grep -c "def past_cap_rows" engine/likely.py
cd /srv/qellys && sudo -u qellys python3 -c "
import json
d = json.load(open('data/built/recommendations.json'))
rows = d.get('likely_past_cap')
print('built by older code' if rows is None else f'{len(rows)} past the cap')
for r in rows or []:
    print(' ', r.get('player'), r.get('market'), r.get('side'), r.get('line'), r.get('odds'), r.get('book'), str(round(100 * r.get('model_prob', 0))) + '%')
"
cd /srv/qellys && sudo -u qellys python3 -c "
from engine.yardagefit import load_fits, display_prob
f = load_fits()
for m in ('rec_yds', 'receptions'):
    print(m, {k: f.get(m, {}).get(k) for k in ('sigma', 'width_weight', 'typical_cv', 'rows')})
print('40+ yards', round(100 * display_prob('rec_yds', 54.4, 39.5, [95, 47, 63, 61, 32, 63], fits=f)))
print('4+ catches', round(100 * display_prob('receptions', 4.7, 3.5, [8, 4, 4, 7, 3, 5], fits=f)))
"
SH
run DE "The bigger lines on the board" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -c "
import json
d = json.load(open('data/built/recommendations.json'))
rows = [r for r in d.get('most_likely') or [] if r.get('bigger_lines')]
print(len(rows), 'picks with bigger lines,', sum(1 for r in rows for c in r['bigger_lines'] if c.get('better')), 'marked')
for r in rows[:5]:
    print(' ', r.get('player'), r.get('side'), r.get('line'), r.get('odds'), '->', ', '.join(f\"{c['line']} {c['odds']} {round(100 * c['prob'])}%{' *' if c.get('better') else ''}\" for c in r['bigger_lines']))
"
SH
run DH "Every change is on the box" 60 <<'SH'
cd /srv/qellys && git log --oneline -8 && sudo -u qellys python3 -c "import json; print('running:', json.load(open('web/data/heartbeat.json')).get('commit'))"
curl -s http://127.0.0.1:8000/js/app.js | grep -o -E "function likelyPastCapHTML|function likelyBiggerHTML|UNFOLDED_MQ =|function initFoldSeams" | sort -u
curl -s http://127.0.0.1:8000/css/styles.css | grep -o -E "max-width: 720px\) and \(min-height: 700px\)|max-width: 760px\) and \(max-height: 700px\)|max-width: 999px" | sort | uniq -c
cd /srv/qellys && sudo -u qellys python3 -c "import inspect; from engine import likely, backtest, maintenance; print('past cap to', likely.PAST_CAP_HEAVIEST, '· bigger lines', likely.BIGGER_SHOWN, '· replay rows', 'rows_out' in inspect.signature(backtest.backtest_from_stats).parameters, '· Thursday inventions', hasattr(maintenance, '_run_inventions'))"
cd /srv/qellys && sudo -u qellys python3 -c "import json; d=json.load(open('data/built/recommendations.json')); ml=d.get('most_likely') or []; pc=d.get('likely_past_cap'); print(len(ml), 'Most Likely picks,', sum(1 for r in ml if r.get('bigger_lines')), 'with bigger lines; past-cap list:', 'missing (an older build)' if pc is None else len(pc))"
SH
run BK "Trust the price more where our chance runs far above it?" 300 <<'SH'
cd /srv/qellys && sudo -u qellys nice -n 19 python3 pricetrust.py 2>&1 | tail -150
SH
run DI "Past cap on every sport; the referee, the grades, the splits" 300 <<'SH'
cd /srv/qellys && git log --oneline -4 && sudo -u qellys python3 -c "from engine import nflrefs, grades, splits, gate; print('referee', hasattr(nflrefs, 'attach'), '· grades', hasattr(grades, 'table'), '· splits', 'betting_splits' in gate.PAID_KEYS)"
cd /srv/qellys && sudo -u qellys python3 -m engine.nflrefs
cd /srv/qellys && sudo -u qellys python3 -m engine.grades | head -40
cd /srv/qellys && grep -A9 "could not be placed" data/logs/nba_build.log | tail -10
cd /srv/qellys && sudo -u qellys python3 -c "
import json
from engine import gate
for sp, f in (('nfl', 'web/data/recommendations.json'), ('cfb', 'web/data/cfb.json'), ('mlb', 'web/data/mlb_recommendations.json'), ('nba', 'web/data/nba.json'), ('wnba', 'web/data/wnba.json'), ('nhl', 'web/data/nhl.json')):
    try:
        d = json.load(open(gate.board_source(f)))
    except Exception as e:
        print(sp, 'no board', type(e).__name__)
        continue
    pc = d.get('likely_past_cap')
    print(sp, 'past-cap list:', 'missing (an older build)' if pc is None else len(pc), '· Most Likely', len(d.get('most_likely') or []))
games = json.load(open(gate.board_source('web/data/recommendations.json'))).get('games') or []
print(sum(1 for g in games if g.get('officials')), 'of', len(games), 'NFL games have a referee named')
"
SH
run DJ "Why no referee yet, and why the NBA and NHL boards are empty" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.nflrefs --why
cd /srv/qellys && sudo -u qellys python3 -c "
import json
from engine import gate
for sp, f in (('nba', 'web/data/nba.json'), ('nhl', 'web/data/nhl.json')):
    d = json.load(open(gate.board_source(f)))
    print(sp, len(d.get('recommendations') or []), 'props priced;', d.get('likely_census'))
"
SH
run DK "The referees read from the prose post, and the marks on a fresh board" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.nflrefs --why | tail -30
cd /srv/qellys && cat data/autoupdate.json; echo; sudo -u qellys python3 -c "
import json
d = json.load(open('data/built/recommendations.json'))
rows = [r for r in d.get('most_likely') or [] if r.get('bigger_lines')]
print('built', d.get('built_at'), '·', len(rows), 'picks with bigger lines,', sum(1 for r in rows for c in r['bigger_lines'] if c.get('better')), 'marked,', sum(1 for r in rows for c in r['bigger_lines'] if (c.get('odds') or 0) < -1000), 'priced past -1000')
"
SH
run DL "The bug scan" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.bugscan
SH
run DM "Push alerts owed, the served lines, the manifest" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.pushalerts
curl -s https://qellysbook.com/js/app.js | wc -l; wc -l < /srv/qellys/web/js/app.js
curl -s https://qellysbook.com/manifest.webmanifest | python3 -c "import json,sys; m=json.load(sys.stdin); print(m['start_url'], 'share_target' in m)"
SH
run DN "Your own alerts, calendar links, the widget feed, compression, the offline worker" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.pushmine
cd /srv/qellys && sudo -u qellys python3 -m engine.calfeed
curl -s https://qellysbook.com/api/widget | python3 -m json.tool | head -30
curl -s -o /dev/null -D - -H 'Accept-Encoding: zstd, gzip' https://qellysbook.com/js/app.js | grep -i '^content-encoding'
curl -s https://qellysbook.com/sw.js | grep -c 'const LAZY'
curl -s -o /dev/null -w '%{http_code}\n' https://qellysbook.com/js/fantasy.js
SH
run DO "The pages' own files, the trimmed copy, this version live" 120 <<'SH'
for f in js/record.js js/detail.js js/account.js js/more.js css/record.css css/detail.css css/account.css css/more.css; do printf '%s ' $f; curl -s -o /dev/null -w '%{http_code}\n' https://qellysbook.com/$f; done
curl -s https://qellysbook.com/css/more.css | wc -c; wc -c < /srv/qellys/web/css/more.css
curl -s https://qellysbook.com/ | grep -c 'id="likely-board"'
SH
run DP "The new look is live (the settings rows, the dark theme told to the browser)" 120 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'function setItem('
curl -s https://qellysbook.com/css/styles.css | grep -c 'color-scheme: dark'
SH
run DQ "The live score on the park's scoreboard is live" 120 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpBoardSVG('
SH
run DR "The runners on the park's scoreboard are live" 120 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'PBP_BOARD_BASES = '
SH
run DS "The stadiums come alive (the football board, big moments, the wind, the countdown)" 120 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpFieldBoardSVG('
curl -s https://qellysbook.com/css/styles.css | grep -c '@keyframes pbp-boom'
SH
run DT "The arenas come alive (their boards, every sport's moments; zstd on a file with no copy made ahead)" 120 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpArenaSVG('
curl -s -o /dev/null -D - -H 'Accept-Encoding: zstd, gzip' https://qellysbook.com/js/hoopscast.js | grep -i '^content-encoding'
SH
run DU "The boards blend into the photographs (their own screens, colours and lettering; any box shape)" 120 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'PBP_FIELD_FACES = '
curl -s https://qellysbook.com/js/gamecast.js | grep -c 'xMidYMax slice'
SH
run DV "Every page, read like an app (plain play words, said once, the record folded, the NBA false warning)" 120 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'function footballWords('
curl -s https://qellysbook.com/js/detail.js | grep -c 'pbp-has-tabs'
grep -c 'could not be placed on the slate' /srv/qellys/data/logs/nba_build.log
SH
run DW "The live pages, caught up with the game (fresh every pass, a 5-second loop, 5-second pages)" 120 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'const PBP_POLL_MS = 5000;'
grep -c '^SCORES_FAST_S = 5' /srv/qellys/launch.py
python3 -c "import json,time,glob;fs=[f for f in sorted(glob.glob('/srv/qellys/web/data/live_*.json')) if '_box' not in f];g=lambda f:json.load(open(f)).get('generated_at');s={f:{g(f)} for f in fs};[time.sleep(2) or [s[f].add(g(f)) for f in fs] for _ in range(15)];print(' '.join(f.split('live_')[1][:-5]+'='+str(len(v)-1) for f,v in s.items()))"
SH
run DX "A chat on every game, plays like Real, and the site free to look around" 60 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'function chatMount('
curl -s https://qellysbook.com/js/app.js | grep -c '"live", "pbp", "game", "fantasy", "mybets",'
curl -s -o /dev/null -w '%{http_code}\n' 'https://qellysbook.com/api/chat/room?room=nfl_1'
SH
run DY "Real's first screens and play cards (rating, lines, win chance, share)" 60 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'function pcBodyHTML('
curl -s https://qellysbook.com/js/account.js | grep -c 'function introHTML('
python3 -c "import json,glob;rows=[r for f in glob.glob('/srv/qellys/web/data/live_*.json') if '_box' not in f for g in json.load(open(f)).get('games',[]) for r in (g.get('plays') or [])+(g.get('big') or [])];print(len(rows),sum('rating' in r for r in rows),sum('wp' in r for r in rows))"
SH
run DZ "Referral codes: $6.25 off for both sides" 60 <<'SH'
curl -s https://qellysbook.com/js/account.js | grep -c 'async function invFill('
curl -s -o /dev/null -w '%{http_code}\n' https://qellysbook.com/api/account/referral
SH
run EA "Follow your teams and players after sign-up (count-only alerts for free accounts)" 60 <<'SH'
curl -s https://qellysbook.com/js/account.js | grep -c 'function followStep('
curl -s https://qellysbook.com/js/app.js | grep -c 'My teams and players make the board'
SH
run EB "Live injuries and birthdays on the game" 60 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpNewInjuriesHTML('
python3 -c "import json,glob;print(' '.join(f.split('rosters_')[1][:-5]+'='+str(sum(1 for t in json.load(open(f)).get('teams',{}).values() for q in t.get('players',[]) if q.get('born'))) for f in sorted(glob.glob('/srv/qellys/web/data/rosters_*.json'))))"
python3 -c "import json,glob;fs=glob.glob('/srv/qellys/web/data/pbp/*.json');print(len(fs),sum(1 for f in fs if json.load(open(f)).get('injuries_live')))"
SH
run EC "Sign up with a phone number (on once Twilio's three values are set)" 30 <<'SH'
curl -s https://qellysbook.com/api/account/me | grep -o '"phone_signup": [a-z]*'
SH
run ED "The game's win chance, drawn play by play" 30 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpWinChartHTML('
SH
run EE "Your players, live (a strip on the Live tab)" 60 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'async function yourPlayersMount('
curl -s -o /dev/null -w '%{http_code}\n' https://qellysbook.com/api/alerts/live
cd /srv/qellys && sudo -u qellys python3 -c "from engine import yourplayers as YP; print(len(YP.index()), 'players with a line right now')"
SH
run EF "Big moments by push (the clutch switch in Alerts)" 60 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'Big moments in games I follow'
cd /srv/qellys && sudo -u qellys python3 -m engine.pushmine
SH
run EG "Call it on live games" 60 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpCallItHTML('
curl -s https://qellysbook.com/api/callit/soccer/1
cd /srv/qellys && sudo -u qellys python3 -c "import sqlite3; from engine import accounts as A; c=sqlite3.connect(f'file:{A.DB_PATH}?mode=ro', uri=True); t=c.execute(\"SELECT 1 FROM sqlite_master WHERE name='callit_calls'\").fetchone(); print(c.execute('SELECT COUNT(*), COUNT(won), COALESCE(SUM(won), 0) FROM callit_calls').fetchone() if t else 'no calls yet')"
SH
run EH "Your ticket in the game's chat" 60 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'async function chatDrawTix('
curl -s -X POST -H 'Content-Type: application/json' -d '{"room": "soccer_1"}' https://qellysbook.com/api/chat/ticket
SH
run EI "Your players on the iPhone widget" 60 <<'SH'
curl -s 'https://qellysbook.com/api/widget/mine?k=1.notakey'
cd /srv/qellys && sudo -u qellys python3 -c "import sqlite3; from engine import accounts as A; c=sqlite3.connect(f'file:{A.DB_PATH}?mode=ro', uri=True); t=c.execute(\"SELECT 1 FROM sqlite_master WHERE name='widget_links'\").fetchone(); print(c.execute('SELECT COUNT(*) FROM widget_links').fetchone()[0] if t else 0, 'widgets on')"
SH
run EJ "The game chat, out of the corner and rebuilt" 30 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'function chatEntryPaint('
SH
run EK "While you were away, and the game in 30 seconds" 30 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpRecapHTML('
SH
run EL "Watching on TV: no spoilers" 30 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function tvPick('
SH
run EM "An account to use the site, and the paid side on its first screen" 30 <<'SH'
curl -s https://qellysbook.com/api/billing/status | grep -o '"account_wall": [a-z]*'
curl -s https://qellysbook.com/api/firstlook | head -c 400; echo
SH
run EN "The game chat's buttons, and a plans page that shows the free side" 120 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'async function lvmLoad('
curl -s https://qellysbook.com/js/account.js | grep -c 'function pwDoorsHTML('
cd /srv/qellys && sudo -u qellys python3 -m engine.bugscan --hours 48 | head -40
SH
run EO "The free trial's reminder" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.trialnote
SH
run EP "What a lapsed member missed" 30 <<'SH'
curl -s https://qellysbook.com/js/account.js | grep -c 'function pwSinceHTML('
SH
run EQ "How many are here, on the first screen" 30 <<'SH'
curl -s https://qellysbook.com/api/firstlook | grep -oE '"proof":(null|\{[^}]*\})'
SH
run ER "Not today? The plans page keeps the door open" 30 <<'SH'
curl -s https://qellysbook.com/js/account.js | grep -c 'function pwLaterHTML('
SH
run ES "The house posts the big moments in each game's chat" 30 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.housepost
SH
run ET "Call it across every game: ladders, the flame, the share" 30 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function ciLadderHTML('
SH
run EU "Final scores by push" 30 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'Final scores of games I follow'
SH
run EV "The app replaces its old copy on your phone" 30 <<'SH'
curl -s https://qellysbook.com/js/register-sw.js | grep -c 'function reloadNow('
SH
run EX "Every sport's scoreboard is the basketball page's" 30 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpBoardHTML('
SH
run EY "On a live game page the sport buttons hop between games" 30 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'async function pbpHop('
SH
run FA "Start A or B? on the Fantasy page and in Ask" 60 <<'SH'
curl -s https://qellysbook.com/js/fantasyweek.js | grep -c 'function compareHTML('
curl -s https://qellysbook.com/data/fantasy_week.json | python3 -c "import json,sys,urllib.parse,urllib.request; d=json.load(sys.stdin); n=[r['player'] for r in d.get('players', []) if r.get('position') == 'RB'][:2]; a=json.load(urllib.request.urlopen('https://qellysbook.com/api/fantasy/compare?' + urllib.parse.urlencode([('p', x) for x in n]))); print(a.get('call', {}).get('text') or a.get('error') or a.get('note'))"
SH
run FB "Your season and last week in review on a Sleeper league's desk" 60 <<'SH'
curl -s https://qellysbook.com/js/fantasyweek.js | grep -c 'function seasonHTML('
curl -s "https://qellysbook.com/api/leagueseason?league=x"; echo
SH
run FC "Lineup alerts: phones asking and leagues kept" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.pushmine
SH
run FD "Your matchup live and fantasy points on the game pages" 30 <<'SH'
curl -s https://qellysbook.com/js/fantasyweek.js | grep -c 'function liveHTML('
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpFantasyHTML('
SH
run FE "NBA and NHL tonight in fantasy points" 30 <<'SH'
curl -s https://qellysbook.com/js/fantasyweek.js | grep -c 'function nightHTML('
for s in nba nhl; do curl -s "https://qellysbook.com/data/fantasy_$s.json" | python3 -c "import json,sys
try: d=json.load(sys.stdin)
except ValueError: print('not built yet'); raise SystemExit
p=d.get('players') or []; print(d.get('sport'), d.get('date'), len(p), 'players', (p[0]['player'], p[0]['points']) if p else '')"; done
sudo -u qellys grep -h "Fantasy tonight" /srv/qellys/data/logs/nba_build.log /srv/qellys/data/logs/nhl_build.log
SH
run FF "The Fantasy room, redesigned" 30 <<'SH'
curl -s https://qellysbook.com/js/fantasy.js | grep -c 'function ffStripHTML('
SH
run FG "The whole app, pass one" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -c 'data-sub-enhanced'
SH
run FH "Ask Qellys shows its work" 30 <<'SH'
curl -s https://qellysbook.com/js/ask.js | grep -c 'function askReadStream('
SH
run FI "Act on an Ask answer: add to slip, track it, watch" 30 <<'SH'
curl -s https://qellysbook.com/js/ask.js | grep -c 'function askActsHTML('
SH
run FJ "The lights on: every league its colour, glow and motion" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -cF ':root[data-league="nba"] { --league: var(--lg-nba); }'
SH
run FK "Ask reads your open bets; Ask from the player card" 30 <<'SH'
curl -s https://qellysbook.com/js/ask.js | grep -c 'function askOpenBets('
SH
run FL "The board comes alive: hit rates, wins, team colours, ticks" 30 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'function hitChipsHTML('
SH
run FM "Price alerts; your starters on tonight's board" 30 <<'SH'
curl -s https://qellysbook.com/js/ask.js | grep -c 'function askActAlert('
SH
run FN "The blend: one face, a graphite ground, fills not outlines" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -c 'fonts/inter.woff2'
SH
run FO "Sweat it, find it, keep coming back: nine more ideas" 30 <<'SH'
curl -s https://qellysbook.com/js/ask.js | grep -c 'function askFollows('
SH
run FP "No hard lines: every outline a fill, every edge a fade" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -c 'grad-team-spill:'
SH
run FQ "The dashboard's newest draw wins" 30 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'let _deckGen = 0;'
SH
run FR "The last lines: badges, stripes and tabs" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -c '.mbc.open { --tone: var(--warn); }'
SH
run FS "The room against the math" 30 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpRoomLine('
SH
run FT "Spoiler-free later" 30 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'function spoiledG('
SH
run FU "Your fantasy lineup, live" 30 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'function ffLiveLoad('
SH
run HP "Every NBA alternate line meets the market" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 nbalean.py
SH
run HO "NBA minutes at the season's start, and the teammate-out minutes" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 nbalean.py
SH
run HN "NBA Most Likely stops leaning under" 120 <<'SH'
cd /srv/qellys && sudo -u qellys python3 nbalean.py
SH
run HM "The new app icon, fitted to the tile" 30 <<'SH'
curl -s https://qellysbook.com/apple-touch-icon.png | wc -c
SH
run HL "The iPhone app's tab bar sits lower" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -cF 'html.store-ios, html.ios-home { --tb-drop: min(20px, env(safe-area-inset-bottom, 0px)); }'
SH
run HK "The Discord link, the Instagram link, the defenses' turnovers" 30 <<'SH'
curl -s https://qellysbook.com/api/billing/status | python3 -c "import json,sys; print(json.load(sys.stdin).get('instagram'))"
cd /srv/qellys && sudo -u qellys python3 -c "from engine import accounts as A; [print(r[0], r[1], 'accounts, the last on', r[2]) for r in A.connect().execute(\"SELECT code, COUNT(*), date(MAX(created_at), 'unixepoch') FROM code_redemptions GROUP BY code\")]"
SH
run HJ "The yearly offer and Gift a month, switched on" 30 <<'SH'
curl -s https://qellysbook.com/api/billing/status | python3 -c "import json,sys; print(json.load(sys.stdin).get('gifts'))"
SH
run HI "The free side opens the pages that sell the plan, and Alerts" 30 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c '"why", "about", "features", "methodology", "status", "alerts"'
SH
run HH "A game saved for later never shows its chat bar" 30 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'spoiledG(league, { event_id: event'
SH
run HG "Kickoff for your teams, each in its own league" 30 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'box("kickoff"'
SH
run HF "Your pick'em week comes back" 30 <<'SH'
curl -s https://qellysbook.com/js/social.js | grep -c 'fd-prof-30 fd-prof-pk'
curl -s https://qellysbook.com/js/karma.js | grep -c 'pickem: "'
SH
run HE "The pick'em comes to you" 30 <<'SH'
curl -s https://qellysbook.com/js/karma.js | grep -c 'function krPickemHTML(p)'
curl -s https://qellysbook.com/js/social.js | grep -c 'function pickemRemindHTML(P)'
SH
run HD "A held game tile selects nothing" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -c '.seg button, .game-card, .hd-game {'
SH
run HC "A highlight fades out, not into a box" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -c 'games-scroller { padding: 24px 2px 40px 26px;'
SH
run HB "The top of Live, uncluttered" 30 <<'SH'
curl -s https://qellysbook.com/js/karma.js | grep -c 'function krAskHTML(d)'
curl -s https://qellysbook.com/css/styles.css | grep -c '.hd-quiet.lv-rest { margin-bottom: 12px; }'
SH
run HA "The black bar under the menu on the iPhone" 30 <<'SH'
curl -s https://qellysbook.com/js/boot.js | grep -c 'setProperty("--vgap"'
curl -s https://qellysbook.com/css/styles.css | grep -c 'more-sheet { bottom: calc(-1'
SH
run GZ "Find people, round two: Recent and who you know that follows them" 30 <<'SH'
curl -s https://qellysbook.com/js/social.js | grep -c 'function mutualHTML(m)'
SH
run GY "Getting started points new accounts at Find people" 30 <<'SH'
curl -s https://qellysbook.com/js/karma.js | grep -c 'a class="kr-qt" href='
SH
run GX "A friend request reaches the other person" 30 <<'SH'
curl -s https://qellysbook.com/js/social.js | grep -c 'const FRIEND_NOTES'
SH
run GW "Find people, and an @ that reaches anybody" 30 <<'SH'
curl -s https://qellysbook.com/js/social.js | grep -c 'function findPageHTML()'
curl -s https://qellysbook.com/js/chat.js | grep -c 'function chatAtFar(q)'
SH
run GV "Every sport its own budget out of the 100k" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.oddsplan
cd /srv/qellys && sudo -u qellys python3 -c "import launch; print('seasons over:', ', '.join(sorted(launch._seasons_over())) or 'none')"
SH
run GU "NBA picks before college until Nov 1" 60 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.oddsplan | head -16
cd /srv/qellys && sudo -u qellys python3 -c "
import json
d = json.load(open('data/built/nba.json'))
print('built', d.get('built_at') or d.get('generated_at'), '·', len(d.get('recommendations') or []), 'Edge ·', len(d.get('most_likely') or []), 'Most Likely ·', d.get('likely_census'))
"
SH
run GT "A free account's menu wears its locks" 30 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'pill.classList.toggle("nav-locked", src.classList.contains("nav-locked"));'
SH
run GS "The player-of-the-game vote reads the box" 30 <<'SH'
curl -s https://qellysbook.com/css/chat.css | grep -c '.gch-potg .gch-vote i {'
SH
run GR "Remind me" 30 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'function chatBellPaint('
SH
run GQ "The fans' player of the game" 30 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'function chatPotgHTML('
SH
run GP "Today's question" 30 <<'SH'
curl -s https://qellysbook.com/js/karma.js | grep -c 'function krDailyHTML('
SH
run GO "Share my level" 30 <<'SH'
curl -s https://qellysbook.com/js/karma.js | grep -c 'function krShareCanvas('
SH
run GN "The game chat talks back: replies, pushes, names as you type" 30 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'function chatAtWord('
SH
run GM "Friends' karma race, pinned badges, chat @mentions, Monday's line" 30 <<'SH'
curl -s https://qellysbook.com/js/karma.js | grep -c 'data-kr="pin"'
SH
run GL "Friends watching now, getting started, the Season ticket" 30 <<'SH'
curl -s https://qellysbook.com/js/karma.js | grep -c 'function krFriendsHTML('
SH
run GK "Karma alerts, and levels on Social" 60 <<'SH'
curl -s https://qellysbook.com/js/karma.js | grep -c 'const krSwitch = '
cd /srv/qellys && sudo -u qellys python3 -m engine.pushmine
SH
run GJ "Karma: levels and badges for watching and talking" 60 <<'SH'
curl -s https://qellysbook.com/js/karma.js | grep -c 'function karmaStripMount('
cd /srv/qellys && sudo -u qellys python3 -m engine.karma
SH
run GI "Each stadium half in each team's colour" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -c -- 'var(--ta) 40%, var(--tb) 60%'
curl -s https://qellysbook.com/js/app.js | grep -c 'C > .02 ? Math.max(1, .08 / C) : 1'
SH
run GH "No player's face stretched" 30 <<'SH'
curl -s https://qellysbook.com/js/visuals.js | grep -c 'const ESPN_FACE_ASPECT = 1.37;'
SH
run GG "The Under pressure card, one thing to a line" 30 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'gold is what the score is testing'
SH
run GF "Your team's colour through the top bar" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -c -- '--grad-team-ground: linear-gradient'
SH
run GE "Each stadium lit in its two teams' colours" 30 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'function teamLight('
curl -s https://qellysbook.com/css/styles.css | grep -c 'stadium-wrap:has(.venue-photo)::before {'
SH
run GD "The whole pick card opens its pick" 30 <<'SH'
curl -s https://qellysbook.com/js/app.js | grep -c 'card.querySelector("\[data-open\]")'
SH
run GC "Each Most Likely tier in its colour" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -c -- '--tier: var(--brand); }'
SH
run GB "What you circled on the Home: the tile, the pick numbers, the iPhone bar" 30 <<'SH'
curl -s https://qellysbook.com/css/styles.css | grep -c 'html.store-ios body::before, html.ios-home body::before {'
SH
run GA "Passkeys" 30 <<'SH'
curl -s https://qellysbook.com/js/account.js | grep -c 'function pkHTML('
curl -s -X POST -H 'Origin: https://qellysbook.com' -H 'Content-Type: application/json' -d '{}' https://qellysbook.com/api/passkey/login-options | python3 -c "import json,sys; print(json.load(sys.stdin).get('rpId'))"
SH
run FZ "Gift a month (off until a gift price is set)" 30 <<'SH'
curl -s https://qellysbook.com/js/account.js | grep -c 'function giftHTML('
curl -s https://qellysbook.com/api/billing/status | python3 -c "import json,sys; print(json.load(sys.stdin).get('gifts'))"
SH
run FY "Yearly at month two (off until switched on)" 30 <<'SH'
curl -s https://qellysbook.com/js/account.js | grep -c 'function yearlyOfferHTML('
SH
run FX "Crew watch" 30 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpUmpHTML('
SH
run FW "Watch parties" 30 <<'SH'
curl -s https://qellysbook.com/js/chat.js | grep -c 'function chatPartyHTML('
SH
run FV "Trivia in the stoppages" 120 <<'SH'
curl -s https://qellysbook.com/js/detail.js | grep -c 'function pbpTriviaHTML('
cd /srv/qellys && sudo -u qellys python3 -c "from engine import trivia, db; [print(q['text'], '->', q['why']) for q in trivia.bank(db.connect(), 'nfl', 'KC', 'BUF')[:4]]"
SH
run EZ "The Fantasy room, round one: 101, defenses, your week, pickups" 600 <<'SH'
curl -s https://qellysbook.com/js/fantasyweek.js | grep -c 'function todo('
curl -s https://qellysbook.com/data/fantasy_week.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(sum(1 for r in d.get('players', []) if r.get('position') == 'DEF'))"
cd /srv/qellys && sudo -u qellys python3 dstfit.py
SH
run AT "Past UFC voids that look like the midnight bug (asks ESPN)" 600 <<'SH'
cd /srv/qellys && sudo -u qellys python3 ufcvoids.py
SH
run BE "College's usage step, re-run on the box" 600 <<'SH'
cd /srv/qellys && sudo -u qellys python3 cfbbridgefit.py
SH
run M2 "The college thrown-at measurement" 600 <<'SH'
cd /srv/qellys && sudo -u qellys python3 cfbtargetfit.py
SH
run P2 "UFC and every league: does our number know more than the price" 900 <<'SH'
cd /srv/qellys && sudo -u qellys python3 stakecheck.py --info --sport ufc --include-measurement
cd /srv/qellys && sudo -u qellys python3 stakecheck.py --clv --sport ufc --include-measurement
cd /srv/qellys && for s in nfl cfb mlb nba wnba nhl; do echo "== $s"; sudo -u qellys python3 stakecheck.py --info --sport $s; done
SH
run O "When an NBA regular sits, his teammates against the board" 900 <<'SH'
cd /srv/qellys && sudo -u qellys python3 nbavacancy.py
SH
run AD "Our expected stats, and their test (printed, not saved)" 1200 <<'SH'
ls -la /srv/qellys/data/models/mlb_xstats.json
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.mlb.xstatsfit --dry-run
curl -s "http://127.0.0.1:8000/api/players/chart?kind=spray&sport=mlb&player=Aaron%20Judge" | python3 -c "import json,sys; d=json.load(sys.stdin); L=d.get('season_line') or {}; print(d.get('player'), d.get('season'), L.get('avg'), L.get('xba'), L.get('slg'), L.get('xslg'), d.get('x_measured'))"
SH
run E "The parlay checker's measurements" 2400 <<'SH'
cd /srv/qellys && sudo -u qellys python3 -m engine.proplivefit
cd /srv/qellys && sudo -u qellys python3 -m engine.slipread nfl "Josh Allen" rush_att over 5.5 -130
cd /srv/qellys && sudo -u qellys python3 -m engine.slipreadfit --sport nfl --seasons 2023 2024 2025
cd /srv/qellys && sudo -u qellys python3 -m engine.slipreadfit --sport cfb --seasons 2024 2025 --limit 3000
SH

echo
run DB2 "Receiving and rushing yards against this season's closes" 900 <<'SH'
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.yardagefit --real rec_yds rush_yds receptions
SH
run DD "The receiving curve by receiver volume" 900 <<'SH'
cd /srv/qellys && sudo -u qellys nice -n 19 python3 curvecheck.py
SH
run DG "The carry projections, every running back's game" 1500 <<'SH'
cd /srv/qellys && sudo -u qellys nice -n 19 python3 carrycheck.py
SH

echo "===== done in $((SECONDS / 60)) min"
