#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Chromium Kiosk Mode
# Ana kiosk uygulaması için Chromium başlatma scripti (Watchdog ile)
# =============================================================================

# Lock dosyası ile çoklu instance önleme
LOCK_FILE="/tmp/chromium-kiosk.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "chromium-kiosk.sh zaten çalışıyor, çıkılıyor..."
    exit 1
fi

# Config'den URL al veya varsayılan kullan
CONFIG_FILE="/etc/kiosk-setup/config.yaml"
URL="http://localhost:3000"

if [ -f "$CONFIG_FILE" ]; then
    CONFIGURED_URL=$(grep -E "^\s*url:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
    if [ -n "$CONFIGURED_URL" ]; then
        URL="$CONFIGURED_URL"
    fi
fi

DATA_DIR="/tmp/chromium-kiosk"

# Crash temizliği
rm -rf "$DATA_DIR/SingletonLock" 2>/dev/null

if [ -f "$DATA_DIR/Default/Preferences" ]; then
    sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' \
        "$DATA_DIR/Default/Preferences" 2>/dev/null
fi

# Mevcut Chromium'u kapat (varsa)
pkill -f "chromium.*--user-data-dir=$DATA_DIR" 2>/dev/null
sleep 0.5

# Watchdog - crash olursa yeniden başlat
while true; do
    # Data dizinini oluştur
    mkdir -p "$DATA_DIR"
    
    # Chromium başlat
    chromium-browser \
        --user-data-dir="$DATA_DIR" \
        --kiosk \
        --incognito \
        --noerrdialogs \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-restore-session-state \
        --disable-dev-tools \
        --disable-sync \
        --disable-default-apps \
        --disable-component-update \
        --disable-features=TranslateUI,Translate,OverscrollHistoryNavigation,TouchpadOverscrollHistoryNavigation,InfiniteSessionRestore,PasswordManager,Autofill,MediaRouter,GlobalMediaControls,ExtensionsToolbarMenu \
        --disable-translate \
        --lang=tr \
        --check-for-update-interval=31536000 \
        --no-first-run \
        --start-fullscreen \
        --window-size=1920,1080 \
        --window-position=0,0 \
        --disable-pinch \
        --overscroll-history-navigation=0 \
        --autoplay-policy=no-user-gesture-required \
        "$URL"
    
    # Chromium kapanırsa 3 saniye bekle ve yeniden başlat
    sleep 3
done &
