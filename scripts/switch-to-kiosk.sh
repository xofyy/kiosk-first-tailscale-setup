#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Switch to Kiosk
# Ana kiosk uygulamasına geçiş scripti
# Keybinding: Ctrl+Alt+K
# =============================================================================

# Mevcut tüm Chromium'ları kapat
pkill -f chromium-browser

# Biraz bekle
sleep 0.3

# Kiosk Chromium'unu başlat
exec /usr/local/bin/chromium-kiosk.sh
