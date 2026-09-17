#!/usr/bin/env bash
# Health check 1 edge box: heartbeat + evidence mới nhất (dùng cho Makefile health).
set -e
found=0
for hb in data/heartbeat_*; do
  [ -e "$hb" ] || continue
  found=1
  age=$(( $(date +%s) - $(stat -c %Y "$hb" 2>/dev/null || stat -f %m "$hb" 2>/dev/null || date +%s) ))
  if [ "$age" -le 30 ]; then echo "[LIVE] $hb: ${age}s"; else echo "[STALE] $hb: ${age}s"; fi
done
[ "$found" -eq 0 ] && echo "(no heartbeat yet — run pipeline first)"
ls -t evidence/*/*/ 2>/dev/null | head -n 5 || true
