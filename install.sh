#!/bin/bash
# =============================================================================
# Kiosk Setup Panel - Installer Script
# =============================================================================
# Bu script Ubuntu Server üzerine Kiosk Setup Panel kurar.
# Kullanım: sudo bash install.sh
# =============================================================================

set -e

# =============================================================================
# RENKLER VE LOG FONKSİYONLARI
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

LOG_FILE="/var/log/kiosk-setup-install.log"

log() {
    local msg="$1"
    echo -e "${GREEN}[✓]${NC} $msg"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $msg" >> "$LOG_FILE"
}

error() {
    local msg="$1"
    echo -e "${RED}[✗]${NC} $msg"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $msg" >> "$LOG_FILE"
}

warn() {
    local msg="$1"
    echo -e "${YELLOW}[!]${NC} $msg"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $msg" >> "$LOG_FILE"
}

info() {
    local msg="$1"
    echo -e "${CYAN}[i]${NC} $msg"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $msg" >> "$LOG_FILE"
}

# =============================================================================
# DEĞİŞKENLER
# =============================================================================

KIOSK_USER="kiosk"
INSTALL_DIR="/opt/kiosk-setup-panel"
CONFIG_DIR="/etc/kiosk-setup"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# =============================================================================
# ROOT KONTROLÜ
# =============================================================================

if [[ $EUID -ne 0 ]]; then
    error "Bu script root olarak çalıştırılmalıdır!"
    echo "Kullanım: sudo bash install.sh"
    exit 1
fi

# =============================================================================
# BANNER
# =============================================================================

clear
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                                                                      ║"
echo "║               KIOSK SETUP PANEL - INSTALLER                          ║"
echo "║                                                                      ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# =============================================================================
# 1. SİSTEM GÜNCELLEMESİ
# =============================================================================

info "Sistem güncelleniyor..."
apt-get update -qq
apt-get upgrade -y -qq
log "Sistem güncellendi"

# =============================================================================
# 2. TEMEL PAKETLER
# =============================================================================

info "Temel paketler kuruluyor..."

PACKAGES=(
    # X11 ve Display
    xorg
    xserver-xorg
    xinit
    x11-xserver-utils
    xinput
    
    # Window Manager
    openbox
    
    # Browser
    chromium-browser
    
    # Python
    python3
    python3-pip
    python3-venv
    python3-dev
    
    # Sistem araçları
    dbus-x11
    mesa-utils
    fonts-dejavu-core
    curl
    wget
    nano
    git
    
    # Network araçları
    net-tools
    iputils-ping
)

for pkg in "${PACKAGES[@]}"; do
    if ! dpkg -l | grep -q "^ii  $pkg "; then
        apt-get install -y -qq "$pkg" 2>/dev/null || warn "Paket kurulamadı: $pkg"
    fi
done

log "Temel paketler kuruldu"

# =============================================================================
# 3. KIOSK KULLANICI OLUŞTURMA
# =============================================================================

info "Kiosk kullanıcısı oluşturuluyor..."

if ! id "$KIOSK_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$KIOSK_USER"
    # video ve audio gruplarına ekle
    usermod -aG video,audio,input,tty "$KIOSK_USER"
    log "Kullanıcı oluşturuldu: $KIOSK_USER"
else
    log "Kullanıcı zaten mevcut: $KIOSK_USER"
fi

# =============================================================================
# 4. DİZİN YAPISI
# =============================================================================

info "Dizin yapısı oluşturuluyor..."

# Config dizini
mkdir -p "$CONFIG_DIR"

# Install dizini
mkdir -p "$INSTALL_DIR"

# Installer log dosyası
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

# Modül logları dizini
KIOSK_LOG_DIR="/var/log/kiosk-setup"
mkdir -p "$KIOSK_LOG_DIR"
chmod 755 "$KIOSK_LOG_DIR"

log "Dizinler oluşturuldu"

# =============================================================================
# 5. UYGULAMA DOSYALARINI KOPYALA
# =============================================================================

info "Uygulama dosyaları kopyalanıyor..."

# Eğer script bir clone dizininde çalışıyorsa
if [[ -d "$SCRIPT_DIR/app" ]]; then
    cp -r "$SCRIPT_DIR/app" "$INSTALL_DIR/"
    cp -r "$SCRIPT_DIR/templates" "$INSTALL_DIR/" 2>/dev/null || true
    cp -r "$SCRIPT_DIR/config" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
    log "Dosyalar kopyalandı: $SCRIPT_DIR -> $INSTALL_DIR"
fi

# Default config
if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
    if [[ -f "$INSTALL_DIR/config/default.yaml" ]]; then
        cp "$INSTALL_DIR/config/default.yaml" "$CONFIG_DIR/config.yaml"
    elif [[ -f "$SCRIPT_DIR/config/default.yaml" ]]; then
        cp "$SCRIPT_DIR/config/default.yaml" "$CONFIG_DIR/config.yaml"
    fi
    log "Varsayılan yapılandırma oluşturuldu"
fi

# =============================================================================
# 6. PYTHON VIRTUAL ENVIRONMENT
# =============================================================================

info "Python virtual environment oluşturuluyor..."

if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    python3 -m venv "$INSTALL_DIR/venv"
    log "Yeni venv oluşturuldu"
else
    log "Venv zaten mevcut: $INSTALL_DIR/venv"
fi

source "$INSTALL_DIR/venv/bin/activate"

pip install --upgrade pip -q
pip install -r "$INSTALL_DIR/requirements.txt" -q

deactivate
log "Python ortamı hazır"

# =============================================================================
# 7. SCRIPTLERİ KOPYALA
# =============================================================================

info "Scriptler kopyalanıyor..."

# Scripts dizini kontrolü - sadece değişmişse kopyala
if [[ -d "$SCRIPT_DIR/scripts" ]]; then
    SCRIPTS_UPDATED=0
    for script in "$SCRIPT_DIR/scripts/"*.sh; do
        script_name=$(basename "$script")
        dest="/usr/local/bin/$script_name"
        
        if [[ ! -f "$dest" ]] || ! cmp -s "$script" "$dest"; then
            cp "$script" "$dest"
            chmod +x "$dest"
            SCRIPTS_UPDATED=$((SCRIPTS_UPDATED + 1))
        fi
    done
    
    if [[ $SCRIPTS_UPDATED -gt 0 ]]; then
        log "$SCRIPTS_UPDATED script güncellendi"
    else
        log "Scriptler zaten güncel"
    fi
fi

# =============================================================================
# 8. XORG TOUCH ROTATION CONFIG
# =============================================================================

info "Dokunmatik ekran yapılandırması..."

XORG_CONF_DIR="/etc/X11/xorg.conf.d"
TOUCH_CONF="$XORG_CONF_DIR/99-touch-rotation.conf"

mkdir -p "$XORG_CONF_DIR"

# Config'den touch ayarlarını al
TOUCH_VENDOR_ID="222a:0001"
TOUCH_MATRIX="0 1 0 -1 0 1 0 0 1"

if [[ -f "$CONFIG_DIR/config.yaml" ]]; then
    CONFIGURED_VENDOR=$(grep -E "^\s*touch_vendor_id:" "$CONFIG_DIR/config.yaml" | head -1 | sed 's/.*touch_vendor_id:\s*//' | tr -d '"' | xargs)
    CONFIGURED_MATRIX=$(grep -E "^\s*touch_matrix:" "$CONFIG_DIR/config.yaml" | head -1 | sed 's/.*touch_matrix:\s*//' | tr -d '"' | xargs)
    
    [[ -n "$CONFIGURED_VENDOR" ]] && TOUCH_VENDOR_ID="$CONFIGURED_VENDOR"
    [[ -n "$CONFIGURED_MATRIX" ]] && TOUCH_MATRIX="$CONFIGURED_MATRIX"
fi

# Xorg config oluştur (sadece yoksa veya farklıysa)
TOUCH_CONF_CONTENT="# Touchscreen Rotation Configuration
# Generated by Kiosk Setup Panel

Section \"InputClass\"
    Identifier \"Touchscreen Rotation\"
    MatchUSBID \"$TOUCH_VENDOR_ID\"
    MatchIsTouchscreen \"on\"
    Option \"TransformationMatrix\" \"$TOUCH_MATRIX\"
EndSection"

if [[ ! -f "$TOUCH_CONF" ]] || [[ "$(cat "$TOUCH_CONF")" != "$TOUCH_CONF_CONTENT" ]]; then
    echo "$TOUCH_CONF_CONTENT" > "$TOUCH_CONF"
    log "Xorg touch rotation config oluşturuldu"
else
    log "Xorg touch rotation config zaten güncel"
fi

# =============================================================================
# 9. CHROMIUM POLICY
# =============================================================================

info "Chromium policy yapılandırılıyor..."

CHROME_POLICY_DIR="/etc/chromium-browser/policies/managed"
mkdir -p "$CHROME_POLICY_DIR"

cat > "$CHROME_POLICY_DIR/kiosk-policy.json" << 'EOF'
{
  "TranslateEnabled": false,
  "AutofillAddressEnabled": false,
  "AutofillCreditCardEnabled": false,
  "PasswordManagerEnabled": false,
  "ImportBookmarks": false,
  "ImportHistory": false,
  "ImportSavedPasswords": false,
  "MetricsReportingEnabled": false,
  "SpellCheckServiceEnabled": false
}
EOF

log "Chromium policy oluşturuldu"

# =============================================================================
# 10. NGINX REVERSE PROXY
# =============================================================================

info "Nginx reverse proxy kuruluyor..."

apt-get install -y nginx

# Default site'i kaldır
rm -f /etc/nginx/sites-enabled/default

# Services registry (boş başlat - modüller ekler)
mkdir -p /etc/nginx
cat > /etc/nginx/kiosk-services.json << 'EOF'
{
  "panel": {
    "display_name": "Panel",
    "port": 5000,
    "path": "/",
    "websocket": false,
    "internal": true
  }
}
EOF

# Panel için proxy config
cat > /etc/nginx/sites-available/kiosk-panel << 'NGINX_EOF'
server {
    listen 8080;
    server_name localhost;
    
    add_header X-Content-Type-Options "nosniff" always;
    client_max_body_size 100M;
    
    proxy_connect_timeout 60;
    proxy_send_timeout 60;
    proxy_read_timeout 60;
    
    location / {
        proxy_pass http://127.0.0.1:5000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/kiosk-panel /etc/nginx/sites-enabled/
systemctl enable nginx
systemctl restart nginx

log "Nginx reverse proxy hazır (port: 8080)"

# =============================================================================
# 11. SYSTEMD SERVİSLERİ
# =============================================================================

info "Systemd servisleri oluşturuluyor..."

SERVICE_FILE="/etc/systemd/system/kiosk-panel.service"

# Flask Panel Service (her zaman güncelle - upgrade desteği için)
cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=Kiosk Setup Panel Web Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/kiosk-setup-panel
Environment="PATH=/opt/kiosk-setup-panel/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/opt/kiosk-setup-panel/venv/bin/python -m gunicorn -b 127.0.0.1:5000 -w 2 --timeout 120 app.main:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
log "kiosk-panel.service oluşturuldu/güncellendi"

# Enable service
systemctl enable kiosk-panel.service 2>/dev/null || true

log "Systemd servisleri hazır"

# =============================================================================
# 12. TTY1 AUTOLOGIN
# =============================================================================

info "TTY1 autologin yapılandırılıyor..."

mkdir -p /etc/systemd/system/getty@tty1.service.d/

cat > /etc/systemd/system/getty@tty1.service.d/override.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $KIOSK_USER --noclear %I \$TERM
EOF

log "TTY1 autologin yapılandırıldı"

# =============================================================================
# 13. KIOSK KULLANICI YAPILANDIRMASI
# =============================================================================

info "Kiosk kullanıcı yapılandırması..."

KIOSK_HOME="/home/$KIOSK_USER"

# .bash_profile - X başlatma (sadece yoksa oluştur)
if [[ ! -f "$KIOSK_HOME/.bash_profile" ]]; then
    cat > "$KIOSK_HOME/.bash_profile" << 'EOF'
# Kiosk Setup Panel - Bash Profile

# TTY1'de otomatik olarak X başlat (watchdog ile)
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    while true; do
        startx -- -nocursor
        sleep 2
    done
fi
EOF
    log ".bash_profile oluşturuldu"
else
    log ".bash_profile zaten mevcut, atlanıyor"
fi

# .xinitrc (sadece yoksa oluştur)
if [[ ! -f "$KIOSK_HOME/.xinitrc" ]]; then
    cat > "$KIOSK_HOME/.xinitrc" << 'EOF'
#!/bin/bash
# Kiosk Setup Panel - X Init

# Ekran ayarları
/usr/local/bin/display-init.sh 2>/dev/null || true

# D-Bus
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
    eval $(dbus-launch --sh-syntax --exit-with-session)
fi

# Openbox başlat
exec openbox-session
EOF
    chmod +x "$KIOSK_HOME/.xinitrc"
    log ".xinitrc oluşturuldu"
else
    log ".xinitrc zaten mevcut, atlanıyor"
fi

# Openbox config dizini
mkdir -p "$KIOSK_HOME/.config/openbox"

# Openbox autostart (sadece yoksa oluştur)
if [[ ! -f "$KIOSK_HOME/.config/openbox/autostart" ]]; then
    cat > "$KIOSK_HOME/.config/openbox/autostart" << 'EOF'
#!/bin/bash
# Kiosk Setup Panel - Openbox Autostart

# Ekran koruyucu devre dışı
xset s off
xset -dpms
xset s noblank

# Setup tamamlanmış mı kontrol et
if [[ -f /etc/kiosk-setup/.setup-complete ]]; then
    # Kiosk modunda başlat
    /usr/local/bin/chromium-kiosk.sh &
else
    # Panel modunda başlat
    /usr/local/bin/chromium-panel.sh &
fi
EOF
    chmod +x "$KIOSK_HOME/.config/openbox/autostart"
    log "openbox/autostart oluşturuldu"
else
    log "openbox/autostart zaten mevcut, atlanıyor"
fi

# Openbox rc.xml - keybindings (sadece yoksa oluştur)
if [[ ! -f "$KIOSK_HOME/.config/openbox/rc.xml" ]]; then
    cat > "$KIOSK_HOME/.config/openbox/rc.xml" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <keyboard>
    <!-- Panel/Kiosk Toggle: F10 -->
    <keybind key="F10">
      <action name="Execute">
        <command>/usr/local/bin/toggle-panel-kiosk.sh</command>
      </action>
    </keybind>
  </keyboard>
  
  <applications>
    <application class="*">
      <decor>no</decor>
      <fullscreen>yes</fullscreen>
    </application>
  </applications>
</openbox_config>
EOF
    log "openbox/rc.xml oluşturuldu"
else
    log "openbox/rc.xml zaten mevcut, atlanıyor"
fi

# Sahipliği ayarla
chown -R "$KIOSK_USER:$KIOSK_USER" "$KIOSK_HOME"

log "Kiosk kullanıcı yapılandırması tamamlandı"

# =============================================================================
# 14. SERVİSİ BAŞLAT
# =============================================================================

info "Panel servisi başlatılıyor..."

systemctl start kiosk-panel.service || warn "Panel servisi başlatılamadı (uygulama dosyaları eksik olabilir)"

# =============================================================================
# TAMAMLANDI
# =============================================================================

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                     KURULUM TAMAMLANDI!                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Panel Erişimi:${NC}"
echo "  - Yerel: http://localhost:8080"
echo "  - Ağdan: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo -e "${CYAN}Sonraki Adımlar:${NC}"
echo "  1. Sistemi yeniden başlatın: ${YELLOW}sudo reboot${NC}"
echo "  2. Panel otomatik olarak açılacak"
echo "  3. Modülleri sırasıyla kurun"
echo ""
echo -e "${CYAN}Log Dosyası:${NC} $LOG_FILE"
echo ""

log "Kurulum tamamlandı"