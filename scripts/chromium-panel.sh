#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Chromium Panel Mode
# Chromium launch script for panel interface (with Watchdog)
# =============================================================================

# Prevent multiple instances with lock file
LOCK_FILE="/tmp/chromium-panel.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "chromium-panel.sh is already running, exiting..."
    exit 1
fi

URL="http://localhost:4444"
DATA_DIR="/tmp/chromium-panel"

# Crash cleanup
rm -rf "$DATA_DIR/SingletonLock" 2>/dev/null

if [ -f "$DATA_DIR/Default/Preferences" ]; then
    sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' \
        "$DATA_DIR/Default/Preferences" 2>/dev/null
fi

# Close existing Chromium (if any)
pkill -f "chromium.*--user-data-dir=$DATA_DIR" 2>/dev/null
sleep 0.5

# Watchdog - restart if crashed
while true; do
    # Create data directory
    mkdir -p "$DATA_DIR"

    # Start Chromium
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
        --lang=en \
        --check-for-update-interval=31536000 \
        --no-first-run \
        --start-fullscreen \
        --window-size=1920,1080 \
        --window-position=0,0 \
        --disable-pinch \
        --overscroll-history-navigation=0 \
        "$URL"

    # If Chromium closes, wait 3 seconds and restart
    sleep 3
done &
