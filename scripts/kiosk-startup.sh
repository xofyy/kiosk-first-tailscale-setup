#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Startup Script
# Openbox autostart tarafından çağrılır
# =============================================================================

# Ekran ayarlarını uygula
/usr/local/bin/display-init.sh 2>/dev/null || true

# Ekran koruyucu devre dışı
xset s off
xset -dpms
xset s noblank

# Setup tamamlanmış mı kontrol et
if [ -f /etc/kiosk-setup/.setup-complete ]; then
    # Kiosk modunda başlat
    /usr/local/bin/chromium-kiosk.sh &
else
    # Panel modunda başlat
    /usr/local/bin/chromium-panel.sh &
fi
