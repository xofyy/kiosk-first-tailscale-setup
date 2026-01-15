#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Switch to Cockpit
# Cockpit yönetim paneline geçiş scripti
# Keybinding: Ctrl+Alt+C
# =============================================================================

# Config'den Cockpit portunu al
CONFIG_FILE="/etc/kiosk-setup/config.yaml"
COCKPIT_PORT=9090

if [[ -f "$CONFIG_FILE" ]]; then
    CONFIGURED_PORT=$(grep -E "^\s*port:" "$CONFIG_FILE" -A5 | grep -A5 "cockpit:" | grep "port:" | head -1 | awk '{print $2}')
    if [[ -n "$CONFIGURED_PORT" ]]; then
        COCKPIT_PORT="$CONFIGURED_PORT"
    fi
fi

URL="http://localhost:${COCKPIT_PORT}"

# Chromium data dizini
DATA_DIR="/home/kiosk/.config/chromium-cockpit"
mkdir -p "$DATA_DIR"

# Mevcut tüm Chromium'ları kapat
pkill -f chromium-browser

# Biraz bekle
sleep 0.3

# Cockpit Chromium'unu başlat
exec chromium-browser \
    --user-data-dir="$DATA_DIR" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --start-fullscreen \
    "$URL"
