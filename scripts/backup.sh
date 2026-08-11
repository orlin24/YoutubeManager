#!/usr/bin/env bash
# PostgreSQL backup: pg_dump to backups/ with timestamp, keeps last 14.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
mkdir -p "$BACKUP_DIR"

DB_URL="${DATABASE_URL:-}"
if [ -z "$DB_URL" ] && [ -f "$APP_DIR/backend/.env" ]; then
  DB_URL="$(grep '^DATABASE_URL=' "$APP_DIR/backend/.env" | cut -d= -f2- | tr -d '"')"
fi

if [ -z "$DB_URL" ]; then
  echo "ERROR: DATABASE_URL not set." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/ai_youtube_manager_${STAMP}.dump"
echo "==> Backing up to $OUT"
pg_dump "$DB_URL" -Fc -f "$OUT"
echo "==> Pruning backups older than 14 days"
find "$BACKUP_DIR" -name '*.dump' -mtime +14 -delete
echo "Done. Latest backup: $OUT"
echo
echo "Restore with:  pg_restore -d <db_url> --clean $OUT"
echo "For offsite backups, sync backups/ with rclone/S3, e.g.:"
echo "  rclone copy $OUT mybucket:aym-backups/"
