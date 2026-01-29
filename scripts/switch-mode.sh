#!/bin/bash
# =============================================================================
# ACO Maintenance Panel - Switch Browser Mode
# Usage: switch-mode.sh <kiosk|panel|admin>
# =============================================================================

TARGET_MODE="$1"
CURRENT_MODE_FILE="/tmp/kiosk-current-mode"
SETUP_COMPLETE="/etc/aco-panel/.setup-complete"

# Validate argument
if [ -z "$TARGET_MODE" ]; then
    exit 1
fi

# Kiosk mode requires setup complete
if [ "$TARGET_MODE" = "kiosk" ] && [ ! -f "$SETUP_COMPLETE" ]; then
    exit 0
fi

# Already in target mode? Do nothing
CURRENT_MODE=$(cat "$CURRENT_MODE_FILE" 2>/dev/null || echo "unknown")
if [ "$CURRENT_MODE" = "$TARGET_MODE" ]; then
    exit 0
fi

# Kill all chromium processes
pkill -f "chromium-kiosk.sh" 2>/dev/null
pkill -f "chromium-panel.sh" 2>/dev/null
pkill -f "chromium.*chromium-admin" 2>/dev/null
pkill -f "chromium-browser" 2>/dev/null
sleep 0.5

# Update mode and start target
echo "$TARGET_MODE" > "$CURRENT_MODE_FILE"

case "$TARGET_MODE" in
    kiosk)
        /opt/aco-panel/scripts/chromium-kiosk.sh &
        ;;
    panel)
        /opt/aco-panel/scripts/chromium-panel.sh &
        ;;
    admin)
        /opt/aco-panel/scripts/chromium-admin.sh &
        ;;
esac
