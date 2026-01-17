#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Display Initialization
# Ekran ayarları başlatma scripti
# =============================================================================

# Config'den rotation değerini al
CONFIG_FILE="/etc/kiosk-setup/config.yaml"
ROTATION="right"

if [[ -f "$CONFIG_FILE" ]]; then
    CONFIGURED_ROTATION=$(grep -E "^\s*rotation:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
    if [[ -n "$CONFIGURED_ROTATION" ]]; then
        ROTATION="$CONFIGURED_ROTATION"
    fi
fi

# Ekran koruyucu devre dışı
xset s off 2>/dev/null
xset -dpms 2>/dev/null
xset s noblank 2>/dev/null

# DISPLAY değişkeni kontrolü
if [[ -z "$DISPLAY" ]]; then
    export DISPLAY=:0
fi

# Bağlı ekranları bul
CONNECTED_OUTPUT=$(xrandr | grep ' connected' | head -1 | cut -d' ' -f1)

if [[ -n "$CONNECTED_OUTPUT" ]]; then
    echo "Ekran bulundu: $CONNECTED_OUTPUT"
    echo "Rotation: $ROTATION"
    
    # Ekran rotasyonunu uygula
    xrandr --output "$CONNECTED_OUTPUT" --rotate "$ROTATION" 2>/dev/null
    
    if [[ $? -eq 0 ]]; then
        echo "Ekran rotasyonu uygulandı"
    else
        echo "Ekran rotasyonu uygulanamadı"
    fi
else
    echo "Bağlı ekran bulunamadı"
fi

# Fare imleci ayarları
# Cursor'u gizlemek için unclutter kullanılacak (openbox autostart'ta)

echo "Display initialization completed"
