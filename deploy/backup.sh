#!/usr/bin/env bash
# SimulateE 数据每日备份（.53 上 crontab 每天跑）：
#   SQLite 用在线备份 API（不锁库、一致快照）+ 用户数据目录打包，保留最近 14 份。
#   ROM 不备（体积大且可重放），封面 / 截图备（小、重抓要联网）。
#   恢复：停 simulatee-api → 解包到 ~/simulatee/data → 起服务。
set -euo pipefail
APP="$HOME/simulatee"
DEST="$HOME/simulatee-backups"
KEEP=14
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
"$APP/apps/api/.venv/bin/python" - "$APP/data/retroweb.db" "$tmp/retroweb.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PY
tar -C "$APP/data" -czf "$DEST/simulatee-$STAMP.tar.gz" \
  --exclude='roms' --exclude='cache' \
  -C "$tmp" retroweb.db -C "$APP/data" saves states bios covers screenshots
ls -1t "$DEST"/simulatee-*.tar.gz | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "[ok] $DEST/simulatee-$STAMP.tar.gz ($(du -h "$DEST/simulatee-$STAMP.tar.gz" | cut -f1)), kept $(ls -1 "$DEST"/simulatee-*.tar.gz | wc -l)"
