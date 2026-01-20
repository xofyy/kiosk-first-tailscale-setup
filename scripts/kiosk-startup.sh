#!/bin/bash
# =============================================================================
# ACO Maintenance Panel - Startup Script
# Called by Openbox autostart
# =============================================================================

# Apply display settings
/usr/local/bin/display-init.sh 2>/dev/null || true

# Disable screen saver
xset s off
xset -dpms
xset s noblank

# Check if setup is complete
if [ -f /etc/aco-panel/.setup-complete ]; then
    # Start in kiosk mode
    /usr/local/bin/chromium-kiosk.sh &
else
    # Start in panel mode
    /usr/local/bin/chromium-panel.sh &
fi
