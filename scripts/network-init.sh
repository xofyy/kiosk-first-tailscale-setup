#!/bin/bash
#
# ACO Network Initialization Script
# Boot'ta fiziksel ethernet interface'leri tespit edip connection oluşturur
#

LOG="/var/log/aco-panel/network-init.log"
mkdir -p /var/log/aco-panel

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG"
}

log "Network init started"

# NetworkManager hazır olana kadar bekle
for i in $(seq 1 30); do
    if nmcli general status &>/dev/null; then
        break
    fi
    sleep 1
done

# Fiziksel ethernet interface'leri bul ve connection oluştur
for iface in $(ls /sys/class/net 2>/dev/null); do
    # Virtual interface'leri atla
    [[ "$iface" == "lo" ]] && continue
    [[ "$iface" == docker* ]] && continue
    [[ "$iface" == veth* ]] && continue
    [[ "$iface" == br-* ]] && continue
    [[ "$iface" == virbr* ]] && continue
    [[ "$iface" == tailscale* ]] && continue
    
    # Fiziksel cihaz mı? (device symlink var mı)
    [[ -d "/sys/class/net/$iface/device" ]] || continue
    
    # Wireless mı?
    [[ -d "/sys/class/net/$iface/wireless" ]] && continue
    
    CONN="eth-$iface"
    
    # Connection zaten var mı?
    if nmcli connection show "$CONN" &>/dev/null; then
        log "$CONN exists, skipping"
        # Sadece interface'in managed ve connected olduğundan emin ol
        nmcli device set "$iface" managed yes 2>/dev/null || true
        nmcli connection up "$CONN" 2>/dev/null || true
        continue
    fi
    
    # Yeni connection oluştur (interface'e bağlı)
    log "Creating $CONN for $iface"
    nmcli connection add \
        con-name "$CONN" \
        type ethernet \
        ifname "$iface" \
        autoconnect yes \
        ipv4.method auto \
        ipv6.method disabled 2>/dev/null
    
    # Interface'i managed yap ve bağlan
    nmcli device set "$iface" managed yes 2>/dev/null || true
    nmcli connection up "$CONN" 2>/dev/null || true
done

# Orphan connection temizliği (interface'i olmayan eth-* connection'ları sil)
for conn in $(nmcli -t -f NAME connection show 2>/dev/null | grep "^eth-"); do
    iface="${conn#eth-}"
    if [[ ! -d "/sys/class/net/$iface" ]]; then
        log "Removing orphan connection: $conn"
        nmcli connection delete "$conn" 2>/dev/null || true
    fi
done

log "Network init completed"
