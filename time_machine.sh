#!/usr/bin/env bash
# /opt/email-intel-bot/time_machine.sh
# Time Machine script for Rey Tran Bot backups and rollbacks.
# Run as root/sudo on the VPS.

set -euo pipefail

APP_DIR="/opt/email-intel-bot"
BACKUP_DIR="$APP_DIR/backups"
MAX_BACKUPS=10

get_env_var() {
    local var_name=$1
    if [ -f "$APP_DIR/.env" ]; then
        grep "^${var_name}=" "$APP_DIR/.env" | cut -d'=' -f2- | tr -d '"' | tr -d "'" | tr -d '\r' || true
    fi
}

send_telegram() {
    local message=$1
    local token
    token=$(get_env_var "TELEGRAM_BOT_TOKEN")
    local chats
    chats=$(get_env_var "TELEGRAM_CHAT_IDS")
    
    if [ -z "$token" ] || [ -z "$chats" ]; then
        echo "Warning: Telegram credentials not configured in .env, cannot send alert."
        return
    fi
    
    # Convert commas to spaces to loop
    IFS=',' read -ra ADDR <<< "$chats"
    for chat in "${ADDR[@]}"; do
        local chat_trimmed
        chat_trimmed=$(echo "$chat" | xargs)
        if [ -n "$chat_trimmed" ]; then
            curl -s -X POST "https://api.telegram.org/bot${token}/sendMessage" \
                -d "chat_id=${chat_trimmed}" \
                -d "text=${message}" \
                -d "parse_mode=Markdown" > /dev/null || true
        fi
    done
}

backup() {
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local dest="$BACKUP_DIR/backup_$timestamp"
    
    echo "Creating backup at $dest..."
    mkdir -p "$BACKUP_DIR"
    
    # Sync active files to backup folder, excluding virtualenv, logs, and backups
    rsync -a --exclude='.venv' \
             --exclude='logs' \
             --exclude='backups' \
             --exclude='__pycache__' \
             --exclude='.git' \
             "$APP_DIR/" "$dest/"
             
    # Create metadata file
    echo "timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "$dest/metadata.txt"
    if [ -d "$APP_DIR/.git" ] && command -v git >/dev/null 2>&1; then
        git -C "$APP_DIR" log -1 --oneline >> "$dest/metadata.txt" || true
    fi
    
    echo "Backup created successfully: backup_$timestamp"
    
    # Prune old backups
    prune
}

restore() {
    local backup_name=${1:-""}
    
    if [ -z "$backup_name" ]; then
        # Find latest backup directory
        if [ -d "$BACKUP_DIR" ]; then
            backup_name=$(ls -td "$BACKUP_DIR"/backup_* 2>/dev/null | head -n 1 | xargs basename || true)
        fi
    fi
    
    if [ -z "$backup_name" ]; then
        echo "Error: No backups found to restore."
        return 1
    fi
    
    local target_dir="$BACKUP_DIR/$backup_name"
    if [ ! -d "$target_dir" ]; then
        echo "Error: Backup folder $target_dir does not exist."
        return 1
    fi
    
    echo "Restoring from backup: $backup_name..."
    
    # Stop the bot service if active
    if systemctl is-active --quiet email-intel-bot; then
        echo "Stopping email-intel-bot service..."
        systemctl stop email-intel-bot || true
    fi
    
    # Restore files: sync from backup_dir to active_dir, deleting obsolete files.
    # Exclude dynamic run directories (.venv, logs, backups, cache)
    rsync -a --delete \
             --exclude='.venv' \
             --exclude='logs' \
             --exclude='backups' \
             --exclude='__pycache__' \
             --exclude='.git' \
             "$target_dir/" "$APP_DIR/"
             
    echo "Restore completed. Restarting service..."
    systemctl reset-failed email-intel-bot
    systemctl start email-intel-bot
}

list_backups() {
    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]; then
        echo "No backups available."
        return 0
    fi
    
    echo "Available Backups:"
    local count=0
    # List backups in reverse chronological order
    for dir in $(ls -d "$BACKUP_DIR"/backup_* 2>/dev/null | sort -r); do
        local name
        name=$(basename "$dir")
        local date_str
        if [[ $name =~ backup_([0-9]{4})([0-9]{2})([0-9]{2})_([0-9]{2})([0-9]{2})([0-9]{2}) ]]; then
            date_str="${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:${BASH_REMATCH[6]}"
        else
            date_str="Unknown date"
        fi
        
        local size
        size=$(du -sh "$dir" | cut -f1)
        
        echo "- \`$name\` ($date_str) [Size: $size]"
        count=$((count+1))
    done
}

prune() {
    echo "Pruning backups (keeping latest $MAX_BACKUPS)..."
    local count
    count=$(ls -d "$BACKUP_DIR"/backup_* 2>/dev/null | wc -l)
    if [ "$count" -le "$MAX_BACKUPS" ]; then
        echo "No pruning needed (current count: $count)."
        return 0
    fi
    
    # Delete oldest backups
    local to_delete
    to_delete=$((count - MAX_BACKUPS))
    echo "Deleting $to_delete old backup(s)..."
    
    ls -td "$BACKUP_DIR"/backup_* 2>/dev/null | tail -n "$to_delete" | xargs rm -rf
    echo "Pruning completed."
}

auto_rollback() {
    echo "=== Auto-Rollback Handler Started ==="
    
    if [ ! -d "$BACKUP_DIR" ]; then
        echo "Error: Backups folder does not exist. Cannot perform auto-rollback."
        send_telegram "❌ *Rey Tran Bot Time Machine Alert*

⚠️ *Systemd Crash-Loop Detected!*
The bot service failed repeatedly, but no backups folder exists to roll back to. Please inspect the VPS manually."
        return 1
    fi
    
    local backups
    backups=$(ls -td "$BACKUP_DIR"/backup_* 2>/dev/null || true)
    if [ -z "$backups" ]; then
        echo "Error: No backups found."
        send_telegram "❌ *Rey Tran Bot Time Machine Alert*

⚠️ *Systemd Crash-Loop Detected!*
The bot service failed repeatedly, but no backup snapshots were found. Please inspect the VPS manually."
        return 1
    fi
    
    # Fetch the latest backup
    local target_backup
    target_backup=$(echo "$backups" | head -n 1 | xargs basename)
    
    echo "Rolling back to: $target_backup"
    
    # Restore the backup (this starts the service at the end)
    restore "$target_backup"
    
    # Send success notification
    send_telegram "🤖 *Rey Tran Bot Time Machine Alert*

⚠️ *Systemd Crash-Loop Detected!*
Rey encountered persistent errors and has been automatically rolled back to the last working snapshot:
📁 \`$target_backup\`

The bot has been restarted with the working code and is back online."
}

# Main routing
CMD=${1:-"help"}
case "$CMD" in
    backup)
        backup
        ;;
    restore)
        restore "${2:-""}"
        ;;
    list)
        list_backups
        ;;
    auto-rollback)
        auto_rollback
        ;;
    *)
        echo "Usage: $0 {backup|restore [backup_name]|list|auto-rollback}"
        exit 1
        ;;
esac
