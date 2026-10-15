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
#   BK           Tuesday, once week 6 has settled
#   N, S (second lines)  from the NBA's opening night, the 20th
#   AX's second, AY      the morning after / the day of a UFC card
#   C, D's Stripe settings, F, AE, AJ and the phone halves of the rest:
#                your hands, not the box
set -u

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
journalctl -u qellys --since "2 hours ago" --no-pager | grep -iE "refresh|cycle|took|build|slip watch" | tail -15
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
cd /srv/qellys && for f in recommendations cfb mlb_recommendations nba wnba nhl; do python3 -c "import json,sys; f=sys.argv[1]; d=json.load(open('web/data/'+f+'.json')); ml=d.get('most_likely') or []; print(f, len(ml), 'picks |', sum(1 for r in ml if r.get('matchup_card')), 'matchup |', sum(1 for r in ml if r.get('mate_card')), 'teammate |', d.get('likely_board',{}).get('matchup_source'))" $f 2>/dev/null || echo "$f: no board"; done
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
echo "===== done in $((SECONDS / 60)) min"
