#!/bin/bash
# Observer-node research snapshot: ban + peers + block/consensus activity.
# Records a timestamped entry to OUT/observer.log. Read-only.
# usage: observer_snapshot.sh <node.log> <out_dir> [python] [cli] [ledger.db]
LOG="$1"
OUT="$2"
PY="${3:-python3}"
CLI="${4:-labs/mainnet-interaction/mainnet_cli.py}"
LEDGER="${5:-}"
if [ -z "$LOG" ] || [ -z "$OUT" ]; then
  echo "usage: observer_snapshot.sh <node.log> <out_dir> [python] [cli] [ledger.db]"
  exit 2
fi
mkdir -p "$OUT"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
B=${B:-20}
{
  echo "######## $TS ########"
  echo "## NODE LIVENESS / UPTIME ##"
  # Is the observer node process alive? Report raw signal (not a dose of the
  # stale-log problem): process presence + how recently node.log was written.
  if pgrep -f '[n]ode.py.*config-custom' >/dev/null 2>&1; then
    echo "NodeProcess=up"
  else
    echo "NodeProcess=down"
  fi
  if [ -f "$LOG" ]; then
    LOG_MTIME=$(stat -c %Y "$LOG" 2>/dev/null)
    if [ -n "$LOG_MTIME" ]; then
      NOW=$(date +%s)
      LOG_AGE=$(( NOW - LOG_MTIME ))
      echo "LogLastWriteUTC=$(date -u -d "@$LOG_MTIME" +%Y-%m-%dT%H:%M:%SZ)"
      echo "LogFreshSec=$LOG_AGE"
      # Log written within the last 10 min => node actively producing data.
      if [ "$LOG_AGE" -le 600 ]; then
        echo "NodeLive=true"
      else
        echo "NodeLive=false  # stale log: metrics below may be a frozen/fake flatline"
      fi
    fi
  else
    echo "NodeLive=unknown  # no log file at $LOG"
  fi

  echo "## BANS ##"
  BANLIST=$(grep 'Status: Banlist:' "$LOG" | tail -1 | sed -E 's/.*Banlist: //')
  echo "Banlist=$BANLIST"
  BANS=$(echo "$BANLIST" | grep -oE "'[0-9][0-9.]*'" | wc -l); BANS=${BANS:-0}
  echo "BanCount=$BANS"
  "$PY" "$CLI" net ban-analyze "$LOG" 2>/dev/null | tail -n +2

  echo "## PEERS ##"
  echo "KnownPeers=$(grep 'Known Peers:' "$LOG" | tail -1 | grep -oE 'Known Peers: [0-9]+' | grep -oE '[0-9]+' | tail -1)"
  echo "OutboundConn=$(grep 'Number of Outbound connections:' "$LOG" | tail -1 | grep -oE 'Outbound connections: [0-9]+' | grep -oE '[0-9]+' | tail -1)"
  echo "ConsensusNodes=$(grep 'Total number of nodes:' "$LOG" | tail -1 | grep -oE 'number of nodes: [0-9]+' | grep -oE '[0-9]+' | tail -1)"
  echo "ConsensusHeight=$(grep 'Consensus height:' "$LOG" | tail -1 | sed -E 's/.*Consensus height: //;s/ =.*//')"
  echo "ConsensusPct=$(grep 'Consensus height:' "$LOG" | tail -1 | grep -oE '= [0-9.]+%' | head -1)"

  echo "## LAST BLOCK OPINION (consensus) ##"
  grep 'Last block opinion:' "$LOG" | tail -1 | sed -E 's/.*Last block opinion: //'

  echo "## BLOCKS RECEIVED (last $B valid blocks: height:hash from ip, mined_by) ##"
  if [ -n "$LEDGER" ]; then
    "$PY" "$CLI" net observe "$LOG" --n "$B" --ledger "$LEDGER" 2>/dev/null | sed -n '/Last .*blocks/,/^Block sources/p' | head -n -1
  else
    grep 'Valid block:' "$LOG" | tail -"$B" | grep -oE 'Valid block: [0-9]+: [0-9a-f]+ .* digestion from [0-9.]+' | tail -"$B"
  fi
  echo "## DIFFICULTY (latest) ##"
  grep 'Current difficulty:' "$LOG" | tail -1
  echo "## BLOCK SOURCE TALLY (last $B blocks by provider IP) ##"
  grep 'Valid block:' "$LOG" | tail -"$B" | grep -oE 'from [0-9.]+' | sort | uniq -c | sort -rn
  echo
} >> "$OUT/observer.log"
echo "recorded $TS -> $OUT/observer.log"
