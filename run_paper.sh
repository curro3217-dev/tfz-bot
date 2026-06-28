#!/usr/bin/env bash
# TFZ paper-trading cycle runner for a Linux VPS (called by cron every 5 min).
# No INSECURE_SSL here: a clean server has normal working TLS.
cd "$(dirname "$0")" || exit 1
# Telegram creds: export them in the environment or a .env sourced here.
[ -f .env ] && set -a && . ./.env && set +a
{
  echo "##### cycle $(date '+%Y-%m-%d %H:%M:%S') #####"
  python3 -u main.py paper --timeframe 5m,15m --fresh 2 --ml-cutoff 0.50
} >> paper_log.txt 2>&1
