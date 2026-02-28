#!/bin/bash
# =============================================================
# Hydraulic Filter Expert — Daily Backup Script
# =============================================================
# Backs up the two most critical data stores:
#   1. SQLite database (questions, votes, comments, invention sessions)
#   2. Training data JSONL files (the fine-tuning exhaust — irreplaceable)
#
# Uses SQLite's online backup API (safe while the app is running).
#
# Setup:
#   chmod +x backup.sh
#   crontab -e
#   # Add: 0 3 * * * /opt/sprayoracle/backup.sh >> /opt/sprayoracle/backups/backup.log 2>&1
#
# Retention: 30 days of daily backups
# =============================================================

set -euo pipefail

# Configuration
APP_DIR="/opt/sprayoracle"
BACKUP_ROOT="${APP_DIR}/backups"
DATE=$(date +%Y-%m-%d)
BACKUP_DIR="${BACKUP_ROOT}/${DATE}"
RETENTION_DAYS=30

echo "=== Backup started: $(date) ==="

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# --- 1. SQLite Database (online backup — safe while app is running) ---
DB_PATH="${APP_DIR}/data/community.db"
if [ -f "${DB_PATH}" ]; then
    echo "Backing up SQLite database..."
    sqlite3 "${DB_PATH}" ".backup '${BACKUP_DIR}/community.db'"
    echo "  -> $(du -h "${BACKUP_DIR}/community.db" | cut -f1)"
else
    echo "Warning: Database not found at ${DB_PATH}"
fi

# --- 2. Training Data (JSONL files — the gold) ---
TRAINING_DIR="${APP_DIR}/08-training-data"
if [ -d "${TRAINING_DIR}" ]; then
    echo "Backing up training data..."
    mkdir -p "${BACKUP_DIR}/training-data"
    cp -a "${TRAINING_DIR}"/*.jsonl "${BACKUP_DIR}/training-data/" 2>/dev/null || true
    echo "  -> $(du -sh "${BACKUP_DIR}/training-data" | cut -f1)"
else
    echo "Warning: Training data directory not found at ${TRAINING_DIR}"
fi

# --- 3. Gap Tracker (useful for knowledge base improvements) ---
GAP_FILE="${APP_DIR}/02-knowledge-base/gap-tracker.jsonl"
if [ -f "${GAP_FILE}" ]; then
    echo "Backing up gap tracker..."
    cp "${GAP_FILE}" "${BACKUP_DIR}/gap-tracker.jsonl"
fi

# --- Compress ---
echo "Compressing backup..."
ARCHIVE="${BACKUP_ROOT}/backup-${DATE}.tar.gz"
tar -czf "${ARCHIVE}" -C "${BACKUP_ROOT}" "${DATE}"
rm -rf "${BACKUP_DIR}"
echo "  -> ${ARCHIVE} ($(du -h "${ARCHIVE}" | cut -f1))"

# --- Cleanup old backups ---
echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_ROOT}" -name "backup-*.tar.gz" -mtime +${RETENTION_DAYS} -delete
REMAINING=$(find "${BACKUP_ROOT}" -name "backup-*.tar.gz" | wc -l)
echo "  -> ${REMAINING} backups retained"

echo "=== Backup complete: $(date) ==="
