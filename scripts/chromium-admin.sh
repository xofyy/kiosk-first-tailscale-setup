#!/bin/bash
# =============================================================================
# ACO Maintenance Panel - Chromium Admin Mode
# Normal browser - no kiosk restrictions, no watchdog
# =============================================================================

URL="about:blank"
DATA_DIR="/tmp/chromium-admin"

# Cleanup
rm -rf "$DATA_DIR/SingletonLock" 2>/dev/null
pkill -f "chromium.*--user-data-dir=$DATA_DIR" 2>/dev/null
sleep 0.3

mkdir -p "$DATA_DIR"

# Normal mode (NOT kiosk)
# - No --kiosk flag: address bar visible
# - No --disable-dev-tools: F12 works
# - --incognito: no history saved
# - No watchdog: exits when browser closes
chromium-browser \
    --user-data-dir="$DATA_DIR" \
    --incognito \
    --start-maximized \
    --no-first-run \
    --disable-sync \
    --disable-default-apps \
    --disable-component-update \
    --check-for-update-interval=31536000 \
    --lang=en \
    "$URL"
