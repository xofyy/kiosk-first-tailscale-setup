#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Chromium Panel Mode
# Panel arayüzü için Chromium başlatma scripti (Watchdog ile)
# =============================================================================

# Lock dosyası ile çoklu instance önleme
LOCK_FILE="/tmp/chromium-panel.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "chromium-panel.sh zaten çalışıyor, çıkılıyor..."
    exit 1
fi

URL="http://localhost:8080"
DATA_DIR="/tmp/chromium-panel"

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
        "$URL"
    
    # Chromium kapanırsa 3 saniye bekle ve yeniden başlat
    sleep 3
done &
