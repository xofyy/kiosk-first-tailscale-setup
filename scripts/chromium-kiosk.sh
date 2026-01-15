#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Chromium Kiosk Mode
# Ana kiosk uygulaması için Chromium başlatma scripti
# =============================================================================

# Config'den URL al veya varsayılan kullan
CONFIG_FILE="/etc/kiosk-setup/config.yaml"
URL="http://localhost:3000"

if [[ -f "$CONFIG_FILE" ]]; then
    CONFIGURED_URL=$(grep -E "^\s*url:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
    if [[ -n "$CONFIGURED_URL" ]]; then
        URL="$CONFIGURED_URL"
    fi
fi

# Chromium data dizini (snap uyumlu - /tmp kullan)
DATA_DIR="/tmp/chromium-kiosk"
mkdir -p "$DATA_DIR"

# Mevcut Chromium'u kapat (varsa)
pkill -f "chromium.*--user-data-dir=$DATA_DIR" 2>/dev/null

# Biraz bekle
sleep 0.5

# Chromium başlat
exec chromium-browser \
    --user-data-dir="$DATA_DIR" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --disable-features=TranslateUI \
    --check-for-update-interval=31536000 \
    --no-first-run \
    --start-fullscreen \
    --window-size=1920,1080 \
    --window-position=0,0 \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --autoplay-policy=no-user-gesture-required \
    "$URL"
