#!/bin/bash
# Backup script for ProManager database

BACKUP_DIR="/app/backups"
DB_FILE="/app/data/proManager.db"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/proManager_backup_$TIMESTAMP.db.gz"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Backup database
if [ -f "$DB_FILE" ]; then
    gzip -c "$DB_FILE" > "$BACKUP_FILE"
    echo "Backup created: $BACKUP_FILE"

    # Keep only last 7 days of backups
    find "$BACKUP_DIR" -name "proManager_backup_*.db.gz" -mtime +7 -delete
    echo "Old backups cleaned up"
else
    echo "Error: Database file not found at $DB_FILE"
    exit 1
fi
