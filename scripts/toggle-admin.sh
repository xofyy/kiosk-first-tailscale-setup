#!/bin/bash
# =============================================================================
# ACO Maintenance Panel - Toggle Admin Browser
# F11 to open/close admin browser
# =============================================================================

CURRENT_MODE_FILE="/tmp/kiosk-current-mode"
ADMIN_ACTIVE_FILE="/tmp/admin-browser-active"

# Is admin already open?
if [ -f "$ADMIN_ACTIVE_FILE" ]; then
    # Close admin, return to previous mode
    rm -f "$ADMIN_ACTIVE_FILE"
    pkill -f "chromium.*chromium-admin" 2>/dev/null
    sleep 0.5

    # Return to previous mode
    PREVIOUS_MODE=$(cat "$CURRENT_MODE_FILE" 2>/dev/null || echo "kiosk")
    if [ "$PREVIOUS_MODE" = "panel" ]; then
        /usr/local/bin/chromium-panel.sh &
    else
        /usr/local/bin/chromium-kiosk.sh &
    fi
    exit 0
fi

# Open admin browser
# Kill current browsers first
pkill -f "chromium-kiosk.sh" 2>/dev/null
pkill -f "chromium-panel.sh" 2>/dev/null
pkill -f "chromium-browser" 2>/dev/null
sleep 0.5

# Mark admin as active
touch "$ADMIN_ACTIVE_FILE"

# Start admin browser
/usr/local/bin/chromium-admin.sh &
