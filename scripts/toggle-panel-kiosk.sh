#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Toggle Panel/Kiosk
# F10 ile Panel <-> Kiosk geçişi
# =============================================================================

SETUP_COMPLETE="/etc/kiosk-setup/.setup-complete"
CURRENT_MODE_FILE="/tmp/kiosk-current-mode"

# Setup tamamlanmadıysa geçiş yapma
if [[ ! -f "$SETUP_COMPLETE" ]]; then
    exit 0
fi

# Mevcut mod (varsayılan: kiosk)
CURRENT_MODE=$(cat "$CURRENT_MODE_FILE" 2>/dev/null || echo "kiosk")

if [[ "$CURRENT_MODE" == "kiosk" ]]; then
    # Panel'e geç
    pkill -f "chromium.*chromium-kiosk" 2>/dev/null
    pkill -f "chromium.*chromium-panel" 2>/dev/null
    sleep 0.5
    echo "panel" > "$CURRENT_MODE_FILE"
    /usr/local/bin/chromium-panel.sh &
else
    # Kiosk'a geç
    pkill -f "chromium.*chromium-panel" 2>/dev/null
    pkill -f "chromium.*chromium-kiosk" 2>/dev/null
    sleep 0.5
    echo "kiosk" > "$CURRENT_MODE_FILE"
    /usr/local/bin/chromium-kiosk.sh &
fi
