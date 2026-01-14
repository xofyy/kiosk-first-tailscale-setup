#!/bin/bash
#
# Kiosk Setup Installer
# Bu script kiosk setup sistemini kurar
# - Gerekli paketleri yükler
# - Scriptleri kopyalar
# - Systemd service ve getty override'ları oluşturur
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         KIOSK SETUP SİSTEMİ KURULUMU                       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Root kontrolü
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}Bu script root olarak çalıştırılmalıdır!${NC}"
    echo "Kullanım: sudo $0"
    exit 1
fi

# Script dizinini güvenilir şekilde bul
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

echo -e "${CYAN}Script dizini: ${SCRIPT_DIR}${NC}"
echo ""

# ============================================================================
# ADIM 1: Gerekli dosyaları kontrol et
# ============================================================================
echo -e "${YELLOW}[1/7]${NC} Gerekli dosyalar kontrol ediliyor..."

REQUIRED_FILES=("setup-kiosk.sh" "hardware-unique-id.sh")
for file in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "${SCRIPT_DIR}/${file}" ]]; then
        echo -e "${RED}HATA: ${file} bulunamadı!${NC}"
        echo "Lütfen ${file} dosyasının ${SCRIPT_DIR} dizininde olduğundan emin olun."
        exit 1
    fi
    echo -e "  ✓ ${file}"
done
echo ""

# ============================================================================
# ADIM 2: Gerekli paketleri kur
# ============================================================================
echo -e "${YELLOW}[2/7]${NC} Gerekli paketler kontrol ediliyor ve kuruluyor..."

# Önce apt güncelle
apt-get update -qq

# Zorunlu paketler (script çalışması için gerekli)
PACKAGES=(
    "curl"           # HTTP istekleri (enrollment API, Tailscale kurulumu)
    "dmidecode"      # Donanım bilgisi (hardware ID üretimi)
    "iputils-ping"   # ping komutu (internet kontrolü)
)

for pkg in "${PACKAGES[@]}"; do
    if dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
        echo -e "  ✓ ${pkg} (zaten kurulu)"
    else
        echo -e "  → ${pkg} kuruluyor..."
        apt-get install -y -qq "$pkg" >/dev/null 2>&1
        echo -e "  ✓ ${pkg}"
    fi
done
echo ""

# ============================================================================
# ADIM 3: Gerekli dizinleri oluştur
# ============================================================================
echo -e "${YELLOW}[3/7]${NC} Gerekli dizinler oluşturuluyor..."

mkdir -p /etc/kiosk-setup
mkdir -p /usr/local/lib/kiosk
mkdir -p /etc/systemd/system/getty@tty1.service.d
mkdir -p /etc/systemd/system/getty@tty2.service.d
mkdir -p /etc/systemd/system/getty@tty3.service.d

echo -e "  ✓ /etc/kiosk-setup"
echo -e "  ✓ /usr/local/lib/kiosk"
echo -e "  ✓ /etc/systemd/system/getty@ttyX.service.d"
echo ""

# ============================================================================
# ADIM 4: Scriptleri kopyala
# ============================================================================
echo -e "${YELLOW}[4/7]${NC} Scriptler kopyalanıyor..."

cp "${SCRIPT_DIR}/setup-kiosk.sh" /usr/local/bin/setup-kiosk.sh
cp "${SCRIPT_DIR}/hardware-unique-id.sh" /usr/local/lib/kiosk/hardware-unique-id.sh

chmod +x /usr/local/bin/setup-kiosk.sh
chmod +x /usr/local/lib/kiosk/hardware-unique-id.sh

echo -e "  ✓ /usr/local/bin/setup-kiosk.sh"
echo -e "  ✓ /usr/local/lib/kiosk/hardware-unique-id.sh"
echo ""

# ============================================================================
# ADIM 5: Systemd service dosyasını oluştur
# ============================================================================
echo -e "${YELLOW}[5/7]${NC} Systemd service oluşturuluyor..."

cat > /etc/systemd/system/kiosk-setup.service << 'EOF'
[Unit]
Description=Kiosk First Boot Setup
After=network-online.target
Wants=network-online.target
Before=getty@tty1.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/setup-kiosk.sh
StandardInput=tty
StandardOutput=journal+console
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

chmod 644 /etc/systemd/system/kiosk-setup.service
echo -e "  ✓ /etc/systemd/system/kiosk-setup.service"
echo ""

# ============================================================================
# ADIM 6: Getty override'ları oluştur (numaralı dosya adı)
# ============================================================================
echo -e "${YELLOW}[6/7]${NC} Getty override'lar oluşturuluyor..."

# Numaralı dosya adı: 10-kiosk-setup.conf
# Ansible sonradan 20-autologin.conf ekleyebilir, çakışma olmaz
for tty in tty1 tty2 tty3; do
    cat > "/etc/systemd/system/getty@${tty}.service.d/10-kiosk-setup.conf" << 'EOF'
[Unit]
After=kiosk-setup.service
Requires=kiosk-setup.service
EOF
    echo -e "  ✓ getty@${tty} → 10-kiosk-setup.conf"
done
echo ""

# ============================================================================
# ADIM 7: Servisleri etkinleştir
# ============================================================================
echo -e "${YELLOW}[7/7]${NC} Servisler etkinleştiriliyor..."

systemctl daemon-reload
systemctl enable kiosk-setup.service

echo -e "  ✓ systemctl daemon-reload"
echo -e "  ✓ kiosk-setup.service etkinleştirildi"
echo ""

# ============================================================================
# KURULUM ÖZETİ
# ============================================================================
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Kurulum tamamlandı!${NC}"
echo ""

echo -e "${CYAN}Kurulan Paketler:${NC}"
for pkg in "${PACKAGES[@]}"; do
    echo "  • $pkg"
done
echo ""

echo -e "${CYAN}Sistem şu şekilde çalışacak:${NC}"
echo "  1. Her açılışta kiosk-setup.service çalışacak"
echo "  2. İlk açılışta: Kiosk ID girilecek, enrollment onayı beklenecek"
echo "  3. Onay sonrası Tailscale kurulup bağlanacak"
echo "  4. Kurulum tamamlanana kadar login mümkün olmayacak"
echo "  5. Sonraki açılışlarda: Flag varsa hızlıca geçilecek"
echo ""

echo -e "${CYAN}Önemli Dosyalar:${NC}"
echo "  • Setup Script:     /usr/local/bin/setup-kiosk.sh"
echo "  • Hardware ID:      /usr/local/lib/kiosk/hardware-unique-id.sh"
echo "  • Config Dizini:    /etc/kiosk-setup/"
echo "  • Kiosk ID:         /etc/kiosk-setup/kiosk-id"
echo "  • Hardware ID:      /etc/kiosk-setup/hardware-id"
echo "  • Kurulum Flag:     /etc/kiosk-setup/.setup-complete"
echo ""

echo -e "${YELLOW}Getty Override Dosyaları:${NC}"
echo "  • /etc/systemd/system/getty@tty1.service.d/10-kiosk-setup.conf"
echo "  • /etc/systemd/system/getty@tty2.service.d/10-kiosk-setup.conf"
echo "  • /etc/systemd/system/getty@tty3.service.d/10-kiosk-setup.conf"
echo ""
echo -e "${CYAN}Not: Ansible autologin için 20-autologin.conf ekleyebilir.${NC}"
echo ""

echo -e "${YELLOW}Yeniden kurulum için:${NC}"
echo "  sudo rm /etc/kiosk-setup/.setup-complete"
echo "  sudo reboot"
echo ""

echo -e "${GREEN}Şimdi sistemi yeniden başlatabilirsiniz: sudo reboot${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
