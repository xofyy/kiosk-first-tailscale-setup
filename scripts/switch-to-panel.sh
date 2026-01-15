#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Switch to Panel
# Kurulum paneline geçiş scripti
# Keybinding: Ctrl+Alt+P
# =============================================================================

# Mevcut tüm Chromium'ları kapat
pkill -f chromium-browser

# Biraz bekle
sleep 0.3

# Panel Chromium'unu başlat
exec /usr/local/bin/chromium-panel.sh
