#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Display Initialization
# Ekran ayarları başlatma scripti
# =============================================================================

# Varsayılan rotation
ROTATION="right"

# MongoDB'den rotation değerini almayı dene
if command -v mongosh &>/dev/null; then
    MONGO_ROTATION=$(mongosh --quiet --eval 'db.getSiblingDB("kiosk").settings.findOne({}, {kiosk_rotation: 1})?.kiosk_rotation' 2>/dev/null)
    if [[ -n "$MONGO_ROTATION" && "$MONGO_ROTATION" != "null" ]]; then
        ROTATION="$MONGO_ROTATION"
    fi
fi

# Ekran koruyucu devre dışı
xset s off 2>/dev/null
xset -dpms 2>/dev/null
xset s noblank 2>/dev/null

# DISPLAY değişkeni kontrolü
if [ -z "$DISPLAY" ]; then
    export DISPLAY=:0
fi

# X/NVIDIA hazır olana kadar bekle (max 10 saniye)
echo "X server hazır olması bekleniyor..."
for i in $(seq 1 10); do
    CONNECTED_OUTPUT=$(xrandr 2>/dev/null | grep ' connected' | head -1 | cut -d' ' -f1)
    if [ -n "$CONNECTED_OUTPUT" ]; then
        break
    fi
    sleep 1
done

if [ -n "$CONNECTED_OUTPUT" ]; then
    echo "Ekran bulundu: $CONNECTED_OUTPUT"
    echo "Rotation: $ROTATION"

    # Ekran rotasyonunu uygula (retry ile)
    for attempt in 1 2 3; do
        xrandr --output "$CONNECTED_OUTPUT" --rotate "$ROTATION" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "Ekran rotasyonu uygulandı (attempt $attempt)"
            break
        fi
        sleep 1
    done
else
    echo "Bağlı ekran bulunamadı (10 saniye beklendi)"
fi

echo "Display initialization completed"
