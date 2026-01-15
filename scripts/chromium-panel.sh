#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Chromium Panel Mode
# Panel arayüzü için Chromium başlatma scripti
# =============================================================================

URL="http://localhost:8080"

# Chromium data dizini
DATA_DIR="/home/kiosk/.config/chromium-panel"
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
    "$URL"
