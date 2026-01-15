#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Startup Script
# Openbox autostart tarafından çağrılır
# =============================================================================

# Ekran ayarları
/usr/local/bin/display-init.sh 2>/dev/null || true

# Ekran koruyucu devre dışı
xset s off
xset -dpms
xset s noblank

# Setup tamamlanmış mı kontrol et
SETUP_COMPLETE_FLAG="/etc/kiosk-setup/.setup-complete"

if [[ -f "$SETUP_COMPLETE_FLAG" ]]; then
    echo "Setup tamamlanmış, kiosk modunda başlatılıyor..."
    /usr/local/bin/chromium-kiosk.sh &
else
    echo "Setup tamamlanmamış, panel modunda başlatılıyor..."
    /usr/local/bin/chromium-panel.sh &
fi
