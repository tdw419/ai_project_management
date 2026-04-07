#!/bin/bash
# GeoForge SQLite Backup
# Usage: ./scripts/backup.sh [backup_dir]
# Add to crontab: 0 */6 * * * /home/jericho/zion/projects/geo-forge/scripts/backup.sh

set -euo pipefail

DB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="${DB_DIR}/geo_forge.db"
BACKUP_DIR="${1:-${DB_DIR}/backups}"
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: Database not found at $DB_PATH" >&2
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/geo_forge_${TIMESTAMP}.db"

# WAL checkpoint (flush WAL into main DB) then copy
sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null || true
cp "$DB_PATH" "$BACKUP_FILE"

# Also backup WAL and SHM if they exist
[ -f "${DB_PATH}-wal" ] && cp "${DB_PATH}-wal" "${BACKUP_FILE}-wal"
[ -f "${DB_PATH}-shm" ] && cp "${DB_PATH}-shm" "${BACKUP_FILE}-shm"

# Verify backup is readable
if sqlite3 "$BACKUP_FILE" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "OK: $BACKUP_FILE ($SIZE)"
else
    echo "ERROR: Backup integrity check failed" >&2
    rm -f "$BACKUP_FILE" "${BACKUP_FILE}-wal" "${BACKUP_FILE}-shm"
    exit 1
fi

# Prune old backups
find "$BACKUP_DIR" -name "geo_forge_*.db" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true

echo "Done. Kept backups from last ${RETENTION_DAYS} days."
