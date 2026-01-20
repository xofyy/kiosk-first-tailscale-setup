#!/bin/bash
# =============================================================================
# ACO Maintenance Panel - Toggle Panel/Kiosk
# Toggle between Panel <-> Kiosk with F10
# =============================================================================

SETUP_COMPLETE="/etc/aco-panel/.setup-complete"
CURRENT_MODE_FILE="/tmp/kiosk-current-mode"

# Don't toggle if setup is not complete
if [ ! -f "$SETUP_COMPLETE" ]; then
    exit 0
fi

# Current mode (default: kiosk)
CURRENT_MODE=$(cat "$CURRENT_MODE_FILE" 2>/dev/null || echo "kiosk")

# First kill ALL watchdog scripts and chromium instances
# This prevents multiple instance issues
pkill -f "chromium-kiosk.sh" 2>/dev/null
pkill -f "chromium-panel.sh" 2>/dev/null
pkill -f "chromium-browser" 2>/dev/null
sleep 1

if [ "$CURRENT_MODE" = "kiosk" ]; then
    # Switch to Panel
    echo "panel" > "$CURRENT_MODE_FILE"
    /usr/local/bin/chromium-panel.sh &
else
    # Switch to Kiosk
    echo "kiosk" > "$CURRENT_MODE_FILE"
    /usr/local/bin/chromium-kiosk.sh &
fi
