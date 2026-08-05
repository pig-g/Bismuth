#!/bin/bash
# Observer-node ban analysis: run net ban-analyze on the live node log and
# record a timestamped summary. Read-only. Persistent copy (survives /tmp wipes).
LOG="$1"
OUT="$2"
PY="${3:-python3}"
CLI="${4:-labs/mainnet-interaction/mainnet_cli.py}"
if [ -z "$LOG" ] || [ -z "$OUT" ]; then
  echo "usage: ban_check.sh <node.log> <out_dir> [python] [cli]"
  exit 2
fi
mkdir -p "$OUT"
RESULT=$("$PY" "$CLI" net ban-analyze "$LOG" 2>/dev/null)
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# count actual ban IPs from the live banlist line
BANLIST=$(grep 'Status: Banlist:' "$LOG" | tail -1 | sed -E 's/.*Banlist: //')
BANS=$(echo "$BANLIST" | grep -oE "'[0-9][0-9.]*'" 2>/dev/null | wc -l)
BANS=${BANS:-0}
printf '==== %s ====\nBans=%s\nBanlist=%s\n%s\n' "$TS" "$BANS" "$BANLIST" "$RESULT" >> "$OUT/ban_check.log"
echo "recorded at $TS (bans=$BANS)"
