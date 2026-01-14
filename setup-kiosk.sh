#!/bin/bash
#
# Kiosk Tailscale Setup Script
# Bu script açılışta çalışır ve tailscale kurulumunu zorunlu kılar
# Merkezi enrollment sistemi ile güvenli cihaz kaydı sağlar
# NVIDIA sürücü kurulumu ve MOK yönetimi dahil
#

set -e

# ============================================================================
# TTY İZOLASYONU VE LOG YÖNETİMİ
# ============================================================================

# Log dosyası
LOG_FILE="/var/log/kiosk-setup.log"

# Kernel mesajlarını sustur (sadece KERN_EMERG göster)
# Script sonunda geri açılacak
ORIGINAL_DMESG_LEVEL=$(cat /proc/sys/kernel/printk 2>/dev/null | awk '{print $1}' || echo "4")
echo 1 > /proc/sys/kernel/printk 2>/dev/null || true

# TTY'yi tamamen kontrol altına al
exec < /dev/tty
exec > /dev/tty 2>&1

# Cleanup fonksiyonu (script sonunda veya hata durumunda)
cleanup() {
    # Kernel mesajlarını geri aç
    echo "$ORIGINAL_DMESG_LEVEL" > /proc/sys/kernel/printk 2>/dev/null || true
}
trap cleanup EXIT

# Ekranı tamamen temizle (scrollback dahil)
clear_screen() {
    clear
    printf '\033[2J\033[H\033[3J'  # Clear + home + clear scrollback
    stty sane 2>/dev/null || true
}

# ============================================================================
# RENKLER VE LOG FONKSİYONLARI
# ============================================================================

# Renkler
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Konfigürasyon
CONFIG_DIR="/etc/kiosk-setup"
ID_FILE="${CONFIG_DIR}/kiosk-id"
HARDWARE_ID_FILE="${CONFIG_DIR}/hardware-id"
SETUP_COMPLETE_FLAG="${CONFIG_DIR}/.setup-complete"
NVIDIA_INSTALLED_FLAG="${CONFIG_DIR}/.nvidia-installed"
NVIDIA_MOK_PENDING_FLAG="${CONFIG_DIR}/.nvidia-mok-pending"
HEADSCALE_SERVER="https://headscale.xofyy.com"
ENROLLMENT_SERVER="https://enrollment.xofyy.com"
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# NVIDIA Konfigürasyonu
NVIDIA_DRIVER_VERSION="580"
MOK_PASSWORD="12345678"  # Basit şifre - US klavye uyumlu

# Dosyaya loglama (internal)
_log_to_file() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE" 2>/dev/null || true
}

# Log fonksiyonları (hem ekrana hem dosyaya)
log() {
    echo -e "${GREEN}[✓]${NC} $1"
    _log_to_file "[INFO] $1"
}

error() {
    echo -e "${RED}[✗]${NC} $1"
    _log_to_file "[ERROR] $1"
}

warn() {
    echo -e "${YELLOW}[!]${NC} $1"
    _log_to_file "[WARN] $1"
}

info() {
    echo -e "${CYAN}[i]${NC} $1"
    _log_to_file "[INFO] $1"
}

# JSON'dan değer çıkar (Python3 ile güvenli parsing)
json_get() {
    local json="$1"
    local key="$2"
    echo "$json" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    keys = '${key}'.split('.')
    val = d
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            val = None
            break
    print('' if val is None else val)
except:
    print('')
" 2>/dev/null
}

banner() {
    clear_screen
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                                                            ║"
    echo "║              KIOSK BAŞLANGIÇ KURULUMU                      ║"
    echo "║                                                            ║"
    echo "║   Bu sistem henüz yapılandırılmamış.                       ║"
    echo "║   Kurulum tamamlanmadan sisteme erişim sağlanamaz.         ║"
    echo "║                                                            ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# NVIDIA SÜRÜCÜ FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════════════════════

# Secure Boot durumunu kontrol et
check_secure_boot() {
    if command -v mokutil &>/dev/null; then
        local sb_state=$(mokutil --sb-state 2>/dev/null | head -1)
        if [[ "$sb_state" == *"enabled"* ]]; then
            return 0  # Secure Boot açık
        fi
    fi
    return 1  # Secure Boot kapalı veya kontrol edilemedi
}

# NVIDIA durumunu kontrol et
# Return: 0=çalışıyor, 1=kurulu değil, 2=MOK onayı bekliyor
check_nvidia_status() {
    log "NVIDIA durumu kontrol ediliyor..."
    
    # NVIDIA paketi kurulu mu?
    if ! dpkg -l | grep -q "nvidia-driver-${NVIDIA_DRIVER_VERSION}"; then
        info "NVIDIA sürücüsü kurulu değil"
        return 1
    fi
    
    # NVIDIA modülü yüklü mü?
    if lsmod | grep -q "^nvidia "; then
        log "NVIDIA sürücüsü çalışıyor ✓"
        # nvidia-smi ile doğrula
        if nvidia-smi &>/dev/null; then
            return 0
        fi
    fi
    
    # Modül yüklenmemişse, Secure Boot ve MOK durumunu kontrol et
    if check_secure_boot; then
        # Secure Boot açık ve modül yüklenememiş = MOK onayı gerekli
        if [[ -f "$NVIDIA_MOK_PENDING_FLAG" ]]; then
            warn "NVIDIA kurulu ama MOK onayı bekleniyor"
            return 2
        fi
    fi
    
    # Diğer durumlar (modül yüklenememiş ama sebep belirsiz)
    warn "NVIDIA kurulu ama modül yüklenememiş"
    return 2
}

# NVIDIA sürücüsünü kur
install_nvidia_driver() {
    log "NVIDIA sürücüsü kuruluyor..."
    
    # Sistemi güncelle
    log "Paket listesi güncelleniyor..."
    apt update
    
    # NVIDIA sürücüsünü kur (non-interactive)
    log "NVIDIA driver ${NVIDIA_DRIVER_VERSION} kuruluyor..."
    DEBIAN_FRONTEND=noninteractive apt install -y "nvidia-driver-${NVIDIA_DRIVER_VERSION}"
    
    if [[ $? -ne 0 ]]; then
        error "NVIDIA sürücü kurulumu başarısız!"
        return 1
    fi
    
    # Kurulum flag'ini oluştur
    touch "$NVIDIA_INSTALLED_FLAG"
    
    log "NVIDIA sürücüsü kuruldu ✓"
    return 0
}

# MOK anahtarını kaydet
setup_nvidia_mok() {
    log "MOK anahtarı ayarlanıyor..."
    
    # MOK anahtar dosyasını bul
    local mok_der=""
    if [[ -f "/var/lib/shim-signed/mok/MOK.der" ]]; then
        mok_der="/var/lib/shim-signed/mok/MOK.der"
    elif [[ -f "/var/lib/dkms/mok.pub" ]]; then
        mok_der="/var/lib/dkms/mok.pub"
    else
        # DKMS ile MOK oluşturmayı dene
        log "MOK anahtarı oluşturuluyor..."
        update-secureboot-policy --new-key 2>/dev/null || true
        
        if [[ -f "/var/lib/shim-signed/mok/MOK.der" ]]; then
            mok_der="/var/lib/shim-signed/mok/MOK.der"
        fi
    fi
    
    if [[ -z "$mok_der" ]] || [[ ! -f "$mok_der" ]]; then
        error "MOK anahtar dosyası bulunamadı!"
        return 1
    fi
    
    # MOK'u kaydet
    log "MOK anahtarı UEFI'ye kaydediliyor..."
    echo -e "${MOK_PASSWORD}\n${MOK_PASSWORD}" | mokutil --import "$mok_der"
    
    if [[ $? -ne 0 ]]; then
        error "MOK kaydı başarısız!"
        return 1
    fi
    
    # MOK pending flag'ini oluştur
    touch "$NVIDIA_MOK_PENDING_FLAG"
    
    log "MOK anahtarı kaydedildi ✓"
    return 0
}

# MOK onay ekranı bilgisi göster
show_mok_instructions() {
    echo ""
    echo -e "${YELLOW}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}║              MOK ONAYI GEREKLİ (NVIDIA)                    ║${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}║   Sistem şimdi yeniden başlatılacak.                       ║${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}║   MAVİ EKRANDA ŞUNLARI YAPIN:                              ║${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}║   1. 'Enroll MOK' seçin        → Enter                     ║${NC}"
    echo -e "${YELLOW}║   2. 'Continue' seçin          → Enter                     ║${NC}"
    echo -e "${YELLOW}║   3. 'Yes' seçin               → Enter                     ║${NC}"
    echo -e "${YELLOW}║   4. Şifre girin: ${GREEN}${MOK_PASSWORD}${YELLOW}                              ║${NC}"
    echo -e "${YELLOW}║   5. 'Reboot' seçin            → Enter                     ║${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}║   NOT: Şifre girerken ekranda karakter görünmez!           ║${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# MOK onayı bekleme ekranı
wait_for_mok_approval() {
    echo ""
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                                                            ║${NC}"
    echo -e "${RED}║              MOK ONAYI TAMAMLANMADI!                       ║${NC}"
    echo -e "${RED}║                                                            ║${NC}"
    echo -e "${RED}║   NVIDIA sürücüsü Secure Boot nedeniyle çalışamıyor.       ║${NC}"
    echo -e "${RED}║                                                            ║${NC}"
    echo -e "${RED}║   Lütfen sistemi yeniden başlatın ve MOK ekranında         ║${NC}"
    echo -e "${RED}║   'Enroll MOK' seçerek onay verin.                         ║${NC}"
    echo -e "${RED}║                                                            ║${NC}"
    echo -e "${RED}║   Şifre: ${GREEN}${MOK_PASSWORD}${RED}                                          ║${NC}"
    echo -e "${RED}║                                                            ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    echo -ne "${YELLOW}Yeniden başlatmak için Enter'a basın...${NC}"
    read -r
    reboot
}

# NVIDIA kurulum ana fonksiyonu
setup_nvidia() {
    # GPU var mı kontrol et (opsiyonel - GPU yoksa atla)
    if ! lspci | grep -qi nvidia; then
        log "NVIDIA GPU tespit edilmedi, sürücü kurulumu atlanıyor"
        return 0
    fi
    
    log "NVIDIA GPU tespit edildi"
    
    # Secure Boot kontrolü
    if ! check_secure_boot; then
        log "Secure Boot kapalı, MOK gerekmeyecek"
    else
        log "Secure Boot açık, MOK gerekecek"
    fi
    
    # NVIDIA durumunu kontrol et
    local nvidia_status=0
    check_nvidia_status || nvidia_status=$?
    
    case $nvidia_status in
        0)
            # NVIDIA çalışıyor
            log "NVIDIA sürücüsü hazır ✓"
            # MOK pending flag'ini temizle
            rm -f "$NVIDIA_MOK_PENDING_FLAG"
            return 0
            ;;
        1)
            # NVIDIA kurulu değil - kur
            if ! install_nvidia_driver; then
                error "NVIDIA kurulumu başarısız!"
                return 1
            fi
            
            # Secure Boot açıksa MOK ayarla
            if check_secure_boot; then
                if ! setup_nvidia_mok; then
                    error "MOK ayarlanamadı!"
                    return 1
                fi
                
                show_mok_instructions
                
                log "Sistem 10 saniye içinde yeniden başlatılacak..."
                sleep 10
                reboot
            else
                # Secure Boot kapalı, sadece reboot yeterli
                log "Sistem yeniden başlatılıyor..."
                sleep 3
                reboot
            fi
            ;;
        2)
            # MOK onayı bekliyor
            wait_for_mok_approval
            ;;
    esac
}

# ═══════════════════════════════════════════════════════════════════════════════
# MEVCUT FONKSİYONLAR (DEĞİŞMEDİ)
# ═══════════════════════════════════════════════════════════════════════════════

# Kurulum zaten tamamlandı mı kontrol et
check_setup_complete() {
    if [[ -f "$SETUP_COMPLETE_FLAG" ]]; then
        log "Kurulum zaten tamamlanmış. Çıkılıyor..."
        exit 0
    fi
}

# Tailscale zaten Headscale'e bağlı mı kontrol et
check_tailscale_connected() {
    if ! command -v tailscale &>/dev/null; then
        return 1
    fi
    
    log "Mevcut Tailscale durumu kontrol ediliyor..."
    
    local status_json=$(tailscale status --json 2>/dev/null)
    if [[ -z "$status_json" ]]; then
        return 1
    fi
    
    local result=$(echo "$status_json" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    state = d.get('BackendState', '')
    url = d.get('CurrentControlURL', '') or d.get('CurrentTailnet', {}).get('Name', '')
    hostname = d.get('Self', {}).get('HostName', '')
    
    if state == 'Running' and 'headscale.xofyy.com' in url:
        print(f'CONNECTED:{hostname}')
    else:
        print('NOT_CONNECTED')
except:
    print('ERROR')
" 2>/dev/null)
    
    if [[ "$result" == CONNECTED:* ]]; then
        local current_hostname="${result#CONNECTED:}"
        log "Tailscale zaten Headscale'e bağlı ✓"
        info "Mevcut hostname: $current_hostname"
        return 0
    fi
    
    return 1
}

# İnternet bağlantısı kontrolü
check_internet() {
    log "İnternet bağlantısı kontrol ediliyor..."
    
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if ping -c 1 -W 3 8.8.8.8 &>/dev/null || ping -c 1 -W 3 1.1.1.1 &>/dev/null; then
            log "İnternet bağlantısı mevcut ✓"
            return 0
        fi
        
        warn "İnternet bağlantısı yok. Deneme $attempt/$max_attempts..."
        sleep 5
        ((attempt++))
    done
    
    error "İnternet bağlantısı kurulamadı!"
    return 1
}

# DNS kontrolü
check_dns() {
    log "DNS çözümlemesi kontrol ediliyor..."
    
    if host google.com &>/dev/null || nslookup google.com &>/dev/null 2>&1; then
        log "DNS çalışıyor ✓"
        return 0
    fi
    
    warn "DNS çözümleme sorunu tespit edildi!"
    return 0
}

# Hardware ID üret
get_hardware_id() {
    if [[ -f "$HARDWARE_ID_FILE" ]]; then
        HARDWARE_ID=$(cat "$HARDWARE_ID_FILE")
        log "Mevcut Hardware ID: $HARDWARE_ID"
        return 0
    fi
    
    log "Hardware ID üretiliyor..."
    
    local hw_script="/usr/local/lib/kiosk/hardware-unique-id.sh"
    if [[ -f "$hw_script" ]]; then
        HARDWARE_ID=$(bash "$hw_script" --short 2>/dev/null)
    elif [[ -f "${SCRIPT_DIR}/hardware-unique-id.sh" ]]; then
        HARDWARE_ID=$(bash "${SCRIPT_DIR}/hardware-unique-id.sh" --short 2>/dev/null)
    else
        local uuid=$(cat /sys/class/dmi/id/product_uuid 2>/dev/null || echo "")
        local mac=$(ip link show | grep -m1 ether | awk '{print $2}' | tr -d ':')
        HARDWARE_ID=$(echo -n "${uuid}${mac}" | sha256sum | cut -c1-16)
    fi
    
    if [[ -z "$HARDWARE_ID" ]]; then
        error "Hardware ID üretilemedi!"
        return 1
    fi
    
    mkdir -p "$CONFIG_DIR"
    echo "$HARDWARE_ID" > "$HARDWARE_ID_FILE"
    chmod 644 "$HARDWARE_ID_FILE"
    
    log "Hardware ID üretildi: $HARDWARE_ID"
    return 0
}

# Kiosk ID al
get_kiosk_id() {
    if [[ -f "$ID_FILE" ]]; then
        KIOSK_ID=$(cat "$ID_FILE")
        log "Mevcut Kiosk ID: $KIOSK_ID"
        return 0
    fi
    
    echo ""
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}                    KIOSK ID GİRİŞİ                         ${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    
    while true; do
        echo -ne "${BLUE}Kiosk ID giriniz (örn: 001, store-ankara, lobby-1): ${NC}"
        read -r input_id
        
        if [[ -z "$input_id" ]]; then
            error "ID boş olamaz!"
            continue
        fi
        
        if [[ ! "$input_id" =~ ^[A-Z0-9_-]+$ ]]; then
            error "ID sadece BÜYÜK harf, rakam, tire (-) ve alt çizgi (_) içerebilir!"
            continue
        fi
        
        if [[ ${#input_id} -gt 50 ]]; then
            error "ID 50 karakterden uzun olamaz!"
            continue
        fi
        
        echo ""
        echo -e "Girilen ID: ${GREEN}$input_id${NC}"
        echo -ne "Bu ID doğru mu? (e/h): "
        read -r confirm
        
        if [[ "$confirm" =~ ^[eEyY]$ ]]; then
            KIOSK_ID="$input_id"
            mkdir -p "$CONFIG_DIR"
            echo "$KIOSK_ID" > "$ID_FILE"
            chmod 644 "$ID_FILE"
            log "Kiosk ID kaydedildi: $KIOSK_ID"
            return 0
        fi
    done
}

# Enrollment API'ye kayıt isteği gönder
enroll_device() {
    log "Enrollment sunucusuna kayıt isteği gönderiliyor..."
    info "Hardware ID: $HARDWARE_ID"
    info "Hostname: $KIOSK_ID"
    
    local motherboard_uuid=$(cat /sys/class/dmi/id/product_uuid 2>/dev/null || echo "")
    local mac_addresses=$(ip link show | grep ether | awk '{print $2}' | tr '\n' ',' | sed 's/,$//')
    
    local response=$(curl -s -X POST "${ENROLLMENT_SERVER}/api/enroll" \
        -H "Content-Type: application/json" \
        -d "{
            \"hardware_id\": \"$HARDWARE_ID\",
            \"hostname\": \"$KIOSK_ID\",
            \"motherboard_uuid\": \"$motherboard_uuid\",
            \"mac_addresses\": \"$mac_addresses\"
        }" 2>/dev/null)
    
    if [[ -z "$response" ]]; then
        error "Enrollment sunucusuna bağlanılamadı!"
        return 1
    fi
    
    local status=$(json_get "$response" "data.status")
    
    if [[ "$status" == "approved" ]]; then
        AUTH_KEY=$(json_get "$response" "data.auth_key")
        if [[ -n "$AUTH_KEY" ]]; then
            log "Kayıt zaten onaylı, auth key alındı ✓"
            return 0
        fi
    elif [[ "$status" == "pending" ]]; then
        log "Kayıt isteği gönderildi, onay bekleniyor..."
        return 0
    elif [[ "$status" == "rejected" ]]; then
        local reason=$(json_get "$response" "data.reason")
        error "Kayıt reddedildi: $reason"
        return 1
    else
        error "Beklenmeyen yanıt: $response"
        return 1
    fi
}

# Onay bekle (polling)
wait_for_approval() {
    echo ""
    echo -e "${YELLOW}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}║   YÖNETİCİ ONAYI BEKLENİYOR                                ║${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}║   Hardware ID: ${HARDWARE_ID}                    ║${NC}"
    echo -e "${YELLOW}║   Hostname:    ${KIOSK_ID}$(printf '%*s' $((41 - ${#KIOSK_ID})) '')║${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}║   Onay geldiğinde kurulum otomatik devam edecek...         ║${NC}"
    echo -e "${YELLOW}║                                                            ║${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    local attempt=0
    local poll_interval=30
    
    while true; do
        ((attempt++))
        
        local response=$(curl -s "${ENROLLMENT_SERVER}/api/enroll/${HARDWARE_ID}/status" 2>/dev/null)
        
        if [[ -z "$response" ]]; then
            warn "Sunucuya bağlanılamadı, yeniden deneniyor..."
            sleep $poll_interval
            continue
        fi
        
        local status=$(json_get "$response" "data.status")
        
        case "$status" in
            "approved")
                AUTH_KEY=$(json_get "$response" "data.auth_key")
                if [[ -n "$AUTH_KEY" ]]; then
                    echo ""
                    log "Onay alındı! ✓"
                    return 0
                else
                    warn "Auth key alınamadı, yeniden deneniyor..."
                fi
                ;;
            "rejected")
                local reason=$(json_get "$response" "data.reason")
                echo ""
                error "Kayıt reddedildi: $reason"
                return 1
                ;;
            "pending")
                printf "\r  Bekleniyor... (Deneme: %d, Süre: %d dk)   " "$attempt" "$((attempt * poll_interval / 60))"
                ;;
            "expired")
                warn "Auth key süresi dolmuş, yeni onay bekleniyor..."
                ;;
            *)
                warn "Beklenmeyen durum: $status"
                ;;
        esac
        
        sleep $poll_interval
    done
}

# Tailscale kurulumu
install_tailscale() {
    log "Tailscale durumu kontrol ediliyor..."
    
    if command -v tailscale &>/dev/null; then
        log "Tailscale zaten kurulu ✓"
        return 0
    fi
    
    log "Tailscale kuruluyor..."
    
    curl -fsSL https://tailscale.com/install.sh | sh
    
    if [[ $? -ne 0 ]]; then
        error "Tailscale kurulumu başarısız!"
        return 1
    fi
    
    systemctl enable --now tailscaled
    sleep 3
    
    log "Tailscale başarıyla kuruldu ✓"
    return 0
}

# Tailscale bağlantısı
connect_tailscale() {
    log "Tailscale sunucusuna bağlanılıyor..."
    
    local hostname="${KIOSK_ID}"
    
    if tailscale status &>/dev/null 2>&1; then
        local ts_info=$(tailscale status --json 2>/dev/null | python3 -c "
import sys,json
try:
    d = json.load(sys.stdin)
    print(d.get('BackendState', ''))
    print(d.get('Self', {}).get('HostName', ''))
except:
    print('')
    print('')
" 2>/dev/null)
        
        local current_status=$(echo "$ts_info" | head -1)
        local current_hostname=$(echo "$ts_info" | tail -1)
        
        if [[ "$current_status" == "Running" ]]; then
            if [[ "${current_hostname,,}" == "${hostname,,}" ]]; then
                log "Tailscale zaten doğru ID ile bağlı: $hostname ✓"
                return 0
            else
                warn "Tailscale farklı hostname ile bağlı: $current_hostname"
                log "Hostname değiştiriliyor: $hostname"
                tailscale set --hostname="$hostname"
                if [[ $? -eq 0 ]]; then
                    log "Hostname başarıyla değiştirildi: $hostname ✓"
                    return 0
                fi
            fi
        fi
    fi
    
    if [[ -z "$AUTH_KEY" ]]; then
        error "Auth key bulunamadı!"
        return 1
    fi
    
    tailscale up \
        --login-server "$HEADSCALE_SERVER" \
        --authkey "$AUTH_KEY" \
        --hostname="$hostname" \
        --advertise-tags=tag:kiosk \
        --ssh \
        --accept-dns=true \
        --accept-routes=false \
        --reset
    
    if [[ $? -ne 0 ]]; then
        error "Tailscale bağlantısı başarısız!"
        return 1
    fi
    
    sleep 3
    
    if tailscale status &>/dev/null; then
        log "Tailscale başarıyla bağlandı ✓"
        echo ""
        echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
        tailscale status
        echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
        return 0
    else
        error "Tailscale bağlantı durumu doğrulanamadı!"
        return 1
    fi
}

# Kurulum tamamlandı işareti
mark_setup_complete() {
    mkdir -p "$CONFIG_DIR"
    date '+%Y-%m-%d %H:%M:%S' > "$SETUP_COMPLETE_FLAG"
    chmod 644 "$SETUP_COMPLETE_FLAG"
    log "Kurulum tamamlandı olarak işaretlendi ✓"
}

# ═══════════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════════

main() {
    # TTY'yi temizle ve boot loglarını gizle
    clear_screen
    
    # Root kontrolü
    if [[ $EUID -ne 0 ]]; then
        error "Bu script root olarak çalıştırılmalıdır!"
        exit 1
    fi
    
    # Kurulum zaten tamamlandı mı?
    check_setup_complete
    
    # Tailscale zaten bağlı mı?
    if check_tailscale_connected; then
        # NVIDIA kontrolü yap (bağlı olsa bile)
        setup_nvidia
        mark_setup_complete
        log "Sistem zaten yapılandırılmış. Kurulum atlanıyor."
        exit 0
    fi
    
    banner
    log "Kurulum başlatılıyor..."
    echo ""
    
    # Adım 1: İnternet kontrolü
    if ! check_internet; then
        error "İnternet bağlantısı olmadan devam edilemez!"
        echo ""
        echo "Lütfen ağ bağlantınızı kontrol edin ve sistemi yeniden başlatın."
        echo "Tekrar denemek için bir tuşa basın..."
        read -n 1
        exec "$0"
    fi
    
    # Adım 2: DNS kontrolü
    check_dns
    
    # Adım 3: NVIDIA Kurulumu (Tailscale'den önce)
    setup_nvidia
    # Not: setup_nvidia içinde reboot olabilir, bu satırdan sonrası çalışmayabilir
    
    # Adım 4: Hardware ID üret
    if ! get_hardware_id; then
        error "Hardware ID üretilemedi! Yeniden deneniyor..."
        sleep 5
        exec "$0"
    fi
    
    # Adım 5: Kiosk ID al
    get_kiosk_id
    
    # Adım 6: Enrollment API'ye kayıt
    if ! enroll_device; then
        error "Enrollment başarısız! Yeniden deneniyor..."
        sleep 5
        exec "$0"
    fi
    
    # Adım 7: Auth key yoksa onay bekle
    if [[ -z "$AUTH_KEY" ]]; then
        if ! wait_for_approval; then
            error "Onay alınamadı!"
            sleep 10
            exec "$0"
        fi
    fi
    
    # Adım 8: Tailscale kurulumu
    if ! install_tailscale; then
        error "Tailscale kurulumu başarısız! Yeniden deneniyor..."
        sleep 5
        exec "$0"
    fi
    
    # Adım 9: Tailscale bağlantısı
    if ! connect_tailscale; then
        error "Tailscale bağlantısı başarısız! Yeniden deneniyor..."
        sleep 5
        exec "$0"
    fi
    
    # Kurulum tamamlandı
    mark_setup_complete
    
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}║              KURULUM BAŞARIYLA TAMAMLANDI!                 ║${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}║   Hostname: ${KIOSK_ID}$(printf '%*s' $((41 - ${#KIOSK_ID})) '')║${NC}"
    echo -e "${GREEN}║   Hardware: ${HARDWARE_ID}                    ║${NC}"
    echo -e "${GREEN}║   NVIDIA:   $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo "N/A")$(printf '%*s' $((41 - ${#gpu_name})) '')║${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}║   Sistem 10 saniye içinde yeniden başlatılacak...          ║${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    sleep 10
    reboot
}

# Scripti çalıştır
main "$@"