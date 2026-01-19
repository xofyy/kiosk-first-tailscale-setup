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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Non-interactive apt kurulumu için
export DEBIAN_FRONTEND=noninteractive
export APT_LISTCHANGES_FRONTEND=none

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
    isc-dhcp-client
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

# Install dizini
mkdir -p "$INSTALL_DIR"

# Setup marker dizini (setup_complete flag dosyası için)
# NOT: Config artık MongoDB'de, bu dizin sadece .setup-complete marker için
mkdir -p /etc/kiosk-setup

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
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
    log "Dosyalar kopyalandı: $SCRIPT_DIR -> $INSTALL_DIR"
fi

# NOT: Config artık MongoDB'de tutuluyor (Docker bölümünde oluşturuluyor)

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

# Hardcoded touch ayarları (90 derece saat yönünde rotasyon)
TOUCH_VENDOR_ID="222a:0001"
TOUCH_MATRIX="0 1 0 -1 0 1 0 0 1"

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
  },
  "mechcontroller": {
    "display_name": "Mechatronic Controller",
    "port": 1234,
    "path": "/mechatronic_controller/",
    "websocket": true,
    "check_type": "port",
    "check_value": 1234
  },
  "cockpit": {
    "display_name": "Cockpit",
    "port": 9090,
    "path": "/cockpit/",
    "websocket": true,
    "check_type": "systemd",
    "check_value": "cockpit.socket"
  }
}
EOF

# Panel için proxy config
cat > /etc/nginx/sites-available/kiosk-panel << 'NGINX_EOF'
server {
    listen 4444;
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

    # Mechatronic Controller
    location /mechatronic_controller/ {
        proxy_pass http://127.0.0.1:1234/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket desteği
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;

        # HTML path rewrite
        sub_filter 'src="/' 'src="/mechatronic_controller/';
        sub_filter 'href="/' 'href="/mechatronic_controller/';
        sub_filter "src='/" "src='/mechatronic_controller/";
        sub_filter "href='/" "href='/mechatronic_controller/";
        sub_filter_once off;
        sub_filter_types text/html;
        proxy_set_header Accept-Encoding "";
    }

    # Mechatronic socket.io (root path erişimi için)
    location /socket.io/ {
        proxy_pass http://127.0.0.1:1234/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Mechatronic API endpoint
    location = /ip-config {
        proxy_pass http://127.0.0.1:1234/ip-config;
        proxy_set_header Host $host;
    }

    # Cockpit static dosyaları
    location /cockpit/static/ {
        proxy_pass http://127.0.0.1:9090/cockpit/cockpit/static/;
        proxy_set_header Host $host:$server_port;
    }

    # Cockpit ana
    location /cockpit/ {
        proxy_pass http://127.0.0.1:9090;
        proxy_set_header Host $host:$server_port;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Origin http://localhost:4444;

        # WebSocket
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;

        # iframe için
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;
    }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/kiosk-panel /etc/nginx/sites-enabled/
systemctl enable nginx
systemctl restart nginx

# Doğrulama
if systemctl is-active --quiet nginx; then
    log "Nginx reverse proxy hazır (port: 4444)"
else
    warn "Nginx başlatılamadı"
fi

# =============================================================================
# 11. SYSTEMD SERVİSLERİ
# =============================================================================

info "Systemd servisleri oluşturuluyor..."

SERVICE_FILE="/etc/systemd/system/kiosk-panel.service"

# Flask Panel Service (her zaman güncelle - upgrade desteği için)
cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=Kiosk Setup Panel Web Server
After=network.target docker.service
Wants=docker.service

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

# Ekran rotasyonunu uygula (NVIDIA/MOK durumundan bağımsız)
# display-init.sh kendi içinde bekleme ve retry mantığına sahip
/usr/local/bin/display-init.sh &

# Setup tamamlanmış mı kontrol et
# NOT: Bu dosya panel tarafından MongoDB'deki setup_complete değerine göre oluşturulur
if [ -f /etc/kiosk-setup/.setup-complete ]; then
    # Kiosk modunda başlat (kurulum tamamlandı)
    /usr/local/bin/chromium-kiosk.sh &
else
    # Panel modunda başlat (kurulum devam ediyor)
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
# 14. SERVİS ENABLE (Docker/MongoDB sonrası başlatılacak)
# =============================================================================

info "Panel servisi etkinleştiriliyor..."
# NOT: Panel MongoDB'ye bağımlı, Docker kurulumundan sonra başlatılacak
log "Panel servisi etkinleştirildi (MongoDB hazır olduktan sonra başlatılacak)"

# =============================================================================
# 15. NETWORK YAPILANDIRMASI
# =============================================================================

info "Network yapılandırılıyor..."

# NetworkManager kurulumu
if ! dpkg -l | grep -q "^ii  network-manager "; then
    apt-get install -y -qq network-manager
fi

# cloud-init network devre dışı
CLOUD_INIT_FILE="/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg"
if [[ ! -f "$CLOUD_INIT_FILE" ]]; then
    mkdir -p /etc/cloud/cloud.cfg.d
    echo "network: {config: disabled}" > "$CLOUD_INIT_FILE"
    log "cloud-init network devre dışı bırakıldı"
fi

# Varsayılan interface'i bul
DEFAULT_IFACE=$(ip route | grep default | awk '{print $5}' | head -1)
[[ -z "$DEFAULT_IFACE" ]] && DEFAULT_IFACE="eth0"

# Netplan yedekle ve yapılandır
mkdir -p /etc/netplan/backup
for f in /etc/netplan/*.yaml; do
    [[ "$f" == *"01-network-manager"* ]] && continue
    [[ -f "$f" ]] && mv "$f" /etc/netplan/backup/ 2>/dev/null || true
done

cat > /etc/netplan/01-network-manager.yaml << EOF
# Network configuration managed by NetworkManager
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    $DEFAULT_IFACE:
      dhcp4: true
      dhcp4-overrides:
        use-dns: false
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4
EOF

# Netplan uygula
netplan apply 2>/dev/null || true

# systemd-networkd-wait-online mask (boot hızı için)
systemctl mask systemd-networkd-wait-online.service 2>/dev/null || true
systemctl stop systemd-networkd-wait-online.service 2>/dev/null || true
systemctl disable systemd-networkd 2>/dev/null || true
systemctl stop systemd-networkd 2>/dev/null || true

# DNS yapılandırması
cat > /etc/systemd/resolved.conf << 'EOF'
[Resolve]
DNS=8.8.8.8 8.8.4.4
FallbackDNS=1.1.1.1 9.9.9.9
Domains=~.
DNSStubListener=yes
EOF

systemctl restart systemd-resolved 2>/dev/null || true

# NetworkManager servisleri
systemctl enable NetworkManager 2>/dev/null || true
systemctl start NetworkManager 2>/dev/null || true
systemctl enable NetworkManager-wait-online 2>/dev/null || true

# DNS doğrulaması (Tailscale vb. için gerekli)
info "DNS bağlantısı doğrulanıyor..."
for i in $(seq 1 15); do
    if ping -c 1 -W 2 8.8.8.8 &>/dev/null && ping -c 1 -W 2 google.com &>/dev/null; then
        log "DNS çalışıyor"
        break
    fi
    sleep 2
done

# Doğrulama
if systemctl is-active --quiet NetworkManager; then
    log "Network yapılandırması tamamlandı"
else
    warn "NetworkManager başlatılamadı"
fi

# =============================================================================
# 16. TAILSCALE KURULUMU (sadece paket)
# =============================================================================

info "Tailscale kuruluyor..."

if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
    log "Tailscale kuruldu"
else
    log "Tailscale zaten kurulu"
fi

# Servisi etkinleştir ve başlat
systemctl enable tailscaled 2>/dev/null || true
systemctl start tailscaled 2>/dev/null || true

# Doğrulama
if systemctl is-active --quiet tailscaled; then
    log "Tailscale hazır (enrollment panelden yapılacak)"
else
    warn "Tailscaled başlatılamadı"
fi

# =============================================================================
# 17. COCKPIT KURULUMU
# =============================================================================

info "Cockpit kuruluyor..."

COCKPIT_PACKAGES=(
    cockpit
    cockpit-system
    cockpit-networkmanager
    cockpit-storaged
    cockpit-packagekit
)

apt-get install -y -qq "${COCKPIT_PACKAGES[@]}"

# Cockpit yapılandırması
mkdir -p /etc/cockpit
cat > /etc/cockpit/cockpit.conf << 'EOF'
[WebService]
UrlRoot=/cockpit
Origins = http://localhost:4444 ws://localhost:4444
AllowUnencrypted = true
AllowEmbedding = true

[Session]
IdleTimeout = 0
EOF

# Cockpit servisi
systemctl enable cockpit.socket 2>/dev/null || true
systemctl start cockpit.socket 2>/dev/null || true

# Polkit kuralları
mkdir -p /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/50-kiosk-network.rules << 'EOF'
// NetworkManager izinleri
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager") == 0 &&
        subject.user == "kiosk") {
        return polkit.Result.YES;
    }
});

// PackageKit izinleri (sınırlı)
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.packagekit") == 0 &&
        subject.user == "kiosk") {
        if (action.id == "org.freedesktop.packagekit.system-sources-refresh" ||
            action.id == "org.freedesktop.packagekit.package-info") {
            return polkit.Result.YES;
        }
    }
});
EOF

# NOT: Nginx config ve services.json Section 10'da oluşturuldu (Panel + Mechatronic + Cockpit)

# Doğrulama
if systemctl is-active --quiet cockpit.socket; then
    log "Cockpit kuruldu"
else
    warn "Cockpit socket başlatılamadı"
fi

# =============================================================================
# 18. VNC KURULUMU
# =============================================================================

info "VNC kuruluyor..."

apt-get install -y -qq x11vnc

# VNC dizini
VNC_DIR="/home/$KIOSK_USER/.vnc"
mkdir -p "$VNC_DIR"

# VNC şifresi (varsayılan: aco)
VNC_PASSWORD="aco"
x11vnc -storepasswd "$VNC_PASSWORD" "$VNC_DIR/passwd" 2>/dev/null || true
chown -R "$KIOSK_USER:$KIOSK_USER" "$VNC_DIR"

# x11vnc systemd service
cat > /etc/systemd/system/x11vnc.service << EOF
[Unit]
Description=x11vnc VNC Server
After=display-manager.service network.target

[Service]
Type=simple
User=$KIOSK_USER
Environment=DISPLAY=:0
ExecStart=/usr/bin/x11vnc -display :0 -forever -shared -localhost -rfbport 5900 -rfbauth $VNC_DIR/passwd -noxdamage
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable x11vnc 2>/dev/null || true
# Start edilmiyor - X11 başladıktan sonra otomatik başlayacak

log "VNC kuruldu (X11 başladıktan sonra aktif olacak)"

# =============================================================================
# 18.5. NVIDIA FALLBACK SERVICE (nouveau etkinleştirme)
# =============================================================================

info "NVIDIA fallback service kuruluyor..."

# nvidia modülü yüklenemezse nouveau'yu etkinleştiren script
cat > /usr/local/bin/nvidia-fallback.sh << 'EOF'
#!/bin/bash
# NVIDIA Fallback Script
# nvidia modülü yüklenemezse nouveau'yu etkinleştirir
# Bu sayede MOK skip edilse bile ekran rotation çalışır

LOG="/var/log/kiosk-setup/nvidia-fallback.log"
mkdir -p "$(dirname "$LOG")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG"
}

log "NVIDIA fallback kontrolü başlıyor..."

# nvidia modülü zaten yüklü mü?
if lsmod | grep -q "^nvidia "; then
    log "NVIDIA modülü yüklü, fallback gerekmiyor"
    exit 0
fi

# nvidia yüklenebilir mi dene
modprobe nvidia 2>/dev/null
if lsmod | grep -q "^nvidia "; then
    log "NVIDIA modülü başarıyla yüklendi"
    exit 0
fi

# nvidia yüklenemedi, nouveau'yu etkinleştir
log "NVIDIA yüklenemedi, nouveau etkinleştiriliyor..."

# Blacklist'i bypass ederek nouveau yükle
modprobe --ignore-blacklist nouveau 2>/dev/null

if lsmod | grep -q "^nouveau "; then
    log "nouveau başarıyla yüklendi (NVIDIA fallback)"
    # DRM device oluşması için bekle
    sleep 2
    if [ -e /dev/dri/card0 ]; then
        log "/dev/dri/card0 mevcut, GPU hazır"
    else
        log "UYARI: /dev/dri/card0 oluşmadı"
    fi
else
    log "HATA: nouveau da yüklenemedi!"
fi

log "NVIDIA fallback kontrolü tamamlandı"
EOF

chmod +x /usr/local/bin/nvidia-fallback.sh

# Systemd service - X başlamadan önce çalışır
cat > /etc/systemd/system/nvidia-fallback.service << 'EOF'
[Unit]
Description=NVIDIA Fallback to Nouveau
DefaultDependencies=no
Before=display-manager.service
After=systemd-modules-load.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/nvidia-fallback.sh
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=sysinit.target
EOF

systemctl daemon-reload
systemctl enable nvidia-fallback.service

log "NVIDIA fallback service kuruldu"

# =============================================================================
# 19. KIOSK YAPILANDIRMASI
# =============================================================================

info "Kiosk yapılandırılıyor..."

# Kiosk kullanıcı şifresi
KIOSK_PASSWORD="aco"
echo "kiosk:$KIOSK_PASSWORD" | chpasswd 2>/dev/null || true

# GRUB rotation (fbcon=rotate:1 for right rotation)
GRUB_FILE="/etc/default/grub"
if [[ -f "$GRUB_FILE" ]]; then
    # Mevcut GRUB_CMDLINE_LINUX_DEFAULT'u al
    CURRENT_CMDLINE=$(grep "^GRUB_CMDLINE_LINUX_DEFAULT" "$GRUB_FILE" | cut -d'"' -f2)

    # fbcon ve nvidia parametreleri ekle (yoksa)
    NEW_CMDLINE="$CURRENT_CMDLINE"
    [[ "$NEW_CMDLINE" != *"fbcon=rotate:1"* ]] && NEW_CMDLINE="$NEW_CMDLINE fbcon=rotate:1"
    [[ "$NEW_CMDLINE" != *"nvidia-drm.modeset=1"* ]] && NEW_CMDLINE="$NEW_CMDLINE nvidia-drm.modeset=1"
    [[ "$NEW_CMDLINE" != *"quiet"* ]] && NEW_CMDLINE="quiet $NEW_CMDLINE"
    [[ "$NEW_CMDLINE" != *"splash"* ]] && NEW_CMDLINE="$NEW_CMDLINE splash"

    # Güncelle
    sed -i "s|^GRUB_CMDLINE_LINUX_DEFAULT=.*|GRUB_CMDLINE_LINUX_DEFAULT=\"$NEW_CMDLINE\"|" "$GRUB_FILE"
    update-grub 2>/dev/null || true
    log "GRUB rotation ayarlandı"
fi

log "Kiosk yapılandırması tamamlandı"

# =============================================================================
# 20. NETMON KURULUMU
# =============================================================================

info "Netmon kuruluyor..."

apt-get install -y -qq git nethogs python3-pip

NETMON_DIR="/opt/netmon"

# Mevcut varsa kaldır
[[ -d "$NETMON_DIR" ]] && rm -rf "$NETMON_DIR"

# Klonla
git clone https://github.com/xofyy/netmon.git "$NETMON_DIR" 2>/dev/null || {
    warn "netmon repo klonlanamadı"
}

if [[ -d "$NETMON_DIR" ]]; then
    # pip güncellemeleri
    /usr/bin/pip3 install --upgrade pip setuptools wheel 2>/dev/null || true
    /usr/bin/pip3 uninstall -y UNKNOWN 2>/dev/null || true
    rm -rf "$NETMON_DIR/build" "$NETMON_DIR"/*.egg-info 2>/dev/null || true

    # Kur
    cd "$NETMON_DIR" && /usr/bin/pip3 install --no-cache-dir --force-reinstall . 2>/dev/null || true

    # Config
    mkdir -p /etc/netmon
    cat > /etc/netmon/config.yaml << 'EOF'
# netmon Configuration
db_write_interval: 30
data_retention_days: 90
log_level: INFO
database_path: /var/lib/netmon/data.db
EOF

    mkdir -p /var/lib/netmon

    # Systemd service
    [[ -f "$NETMON_DIR/systemd/netmon.service" ]] && cp "$NETMON_DIR/systemd/netmon.service" /etc/systemd/system/

    systemctl daemon-reload
    systemctl enable netmon 2>/dev/null || true
    systemctl start netmon 2>/dev/null || true

    # Doğrulama
    if systemctl is-active --quiet netmon; then
        log "Netmon kuruldu ve çalışıyor"
    else
        warn "Netmon kuruldu ama başlatılamadı"
    fi
else
    warn "Netmon kurulumu atlandı"
fi

# =============================================================================
# 21. COLLECTOR KURULUMU
# =============================================================================

info "Collector kuruluyor..."

apt-get install -y -qq git python3-pip prometheus-node-exporter

# prometheus-node-exporter
systemctl enable prometheus-node-exporter 2>/dev/null || true
systemctl start prometheus-node-exporter 2>/dev/null || true

COLLECTOR_DIR="/opt/collector-agent"

# Mevcut varsa kaldır
[[ -d "$COLLECTOR_DIR" ]] && rm -rf "$COLLECTOR_DIR"

# Klonla
git clone https://github.com/xofyy/collector-agent.git "$COLLECTOR_DIR" 2>/dev/null || {
    warn "collector-agent repo klonlanamadı"
}

if [[ -d "$COLLECTOR_DIR" ]]; then
    # pip güncellemeleri
    /usr/bin/pip3 install --upgrade pip setuptools wheel 2>/dev/null || true
    /usr/bin/pip3 uninstall -y UNKNOWN 2>/dev/null || true
    rm -rf "$COLLECTOR_DIR/build" "$COLLECTOR_DIR"/*.egg-info 2>/dev/null || true

    # Kur
    cd "$COLLECTOR_DIR" && /usr/bin/pip3 install --no-cache-dir --force-reinstall . 2>/dev/null || true

    # Config
    mkdir -p /etc/collector-agent
    cat > /etc/collector-agent/config.yaml << 'EOF'
# collector-agent Configuration
interval: 30

node_exporter:
  enabled: true
  url: "http://localhost:9100/metrics"
  timeout: 5

nvidia_smi:
  enabled: true

logging:
  level: INFO
  file: /var/log/collector-agent.log
EOF

    # Systemd service
    [[ -f "$COLLECTOR_DIR/systemd/collector-agent.service" ]] && cp "$COLLECTOR_DIR/systemd/collector-agent.service" /etc/systemd/system/

    systemctl daemon-reload
    systemctl enable collector-agent 2>/dev/null || true
    systemctl start collector-agent 2>/dev/null || true

    # Doğrulama
    sleep 2
    if systemctl is-active --quiet collector-agent; then
        log "Collector kuruldu ve çalışıyor"
    else
        warn "Collector kuruldu ama başlatılamadı"
    fi

    if systemctl is-active --quiet prometheus-node-exporter; then
        log "Prometheus Node Exporter çalışıyor"
    else
        warn "Prometheus Node Exporter başlatılamadı"
    fi
else
    warn "Collector kurulumu atlandı"
fi

# =============================================================================
# 22. DOCKER KURULUMU
# =============================================================================

info "Docker kuruluyor..."

# Eski paketleri kaldır
OLD_DOCKER_PKGS="docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc"
for pkg in $OLD_DOCKER_PKGS; do
    apt-get remove -y "$pkg" 2>/dev/null || true
done

# Gerekli paketler
apt-get install -y -qq ca-certificates curl gnupg python3-pip python3-docker python3-pymongo

# Docker GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
chmod a+r /etc/apt/keyrings/docker.gpg

# Docker repo
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -qq

# Docker paketleri
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin

# Docker daemon.json (NVIDIA runtime NVIDIA modülünde eklenir)
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2"
}
EOF

# Docker servisi
systemctl enable docker 2>/dev/null || true
systemctl restart docker 2>/dev/null || true

# Docker doğrulaması
sleep 2
docker --version && log "Docker kuruldu: $(docker --version)"
docker compose version && log "Docker Compose: $(docker compose version)"

# Registry login (hardcoded)
REGISTRY_URL="acolinux.azurecr.io"
REGISTRY_USER="acolinux"
REGISTRY_PASS="YOUR_REGISTRY_PASSWORD_HERE"

if [[ -n "$REGISTRY_USER" && -n "$REGISTRY_PASS" && "$REGISTRY_PASS" != "YOUR_REGISTRY_PASSWORD_HERE" ]]; then
    echo "$REGISTRY_PASS" | docker login "$REGISTRY_URL" -u "$REGISTRY_USER" --password-stdin 2>/dev/null || true
fi

# MongoDB docker-compose
COMPOSE_PATH="/srv/docker"
MONGODB_DATA_PATH="/home/aco/mongo-data"

mkdir -p "$COMPOSE_PATH"
mkdir -p "$MONGODB_DATA_PATH"

# MongoDB image - private registry varsa kullan, yoksa official
MONGO_IMAGE="${REGISTRY_URL}/mongodb:latest"
if [[ "$REGISTRY_PASS" == "YOUR_REGISTRY_PASSWORD_HERE" ]] || [[ -z "$REGISTRY_PASS" ]]; then
    MONGO_IMAGE="mongo:7"
    info "Private registry erişimi yok, official MongoDB image kullanılacak"
fi

cat > "$COMPOSE_PATH/docker-compose.yml" << EOF
# Docker Compose Configuration
# Generated by Kiosk Setup Panel

services:
  local_database:
    image: ${MONGO_IMAGE}
    container_name: local_database
    network_mode: host
    restart: always
    volumes:
      - ${MONGODB_DATA_PATH}:/data/db
EOF

# MongoDB başlat
cd "$COMPOSE_PATH" && docker compose up -d 2>/dev/null || {
    warn "MongoDB başlatılamadı"
}

# MongoDB hazır olana kadar bekle
info "MongoDB hazır olması bekleniyor..."
MONGO_READY=false
for i in $(seq 1 60); do
    if docker exec local_database mongosh --eval "db.runCommand({ping:1})" &>/dev/null; then
        MONGO_READY=true
        break
    fi
    sleep 1
done

if [[ "$MONGO_READY" == "true" ]]; then
    log "MongoDB hazır"

    # Varsayılan settings oluştur
    docker exec local_database mongosh --eval '
        db = db.getSiblingDB("kiosk");
        db.settings.updateOne(
            {},
            {
                $setOnInsert: {
                    kiosk_id: null,
                    hardware_id: null,
                    mok_password: null,
                    nvidia_driver: "535",
                    modules: {
                        nvidia: "pending",
                        tailscale: "pending"
                    },
                    setup_complete: false
                }
            },
            {upsert: true}
        );
    ' 2>/dev/null || true
    log "MongoDB varsayılan ayarları oluşturuldu"

    # Panel servisini başlat (artık MongoDB hazır)
    info "Panel servisi başlatılıyor..."
    systemctl start kiosk-panel.service || warn "Panel servisi başlatılamadı"

    # Panel doğrulaması
    sleep 2
    if systemctl is-active --quiet kiosk-panel; then
        log "Panel servisi çalışıyor"
    else
        warn "Panel servisi başlatılamadı"
    fi
else
    warn "MongoDB başlatılamadı (60 saniye timeout)"
    # Yine de paneli başlatmayı dene
    systemctl start kiosk-panel.service 2>/dev/null || true
fi

# Docker ve MongoDB doğrulaması
if systemctl is-active --quiet docker; then
    log "Docker servisi çalışıyor"
else
    warn "Docker servisi çalışmıyor"
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "local_database"; then
    log "MongoDB container çalışıyor"
else
    warn "MongoDB container çalışmıyor"
fi

log "Docker kurulumu tamamlandı"

# =============================================================================
# 23. SECURITY PAKETLERİ KURULUMU
# =============================================================================

info "Güvenlik paketleri kuruluyor..."

# UFW ve fail2ban paketlerini kur (yapılandırma tailscale modülünde)
apt-get install -y -qq ufw fail2ban

# NOT: UFW yapılandırması ve etkinleştirme tailscale modülünde yapılacak
# Çünkü tailscale0 interface'i enrollment sonrası oluşuyor
# SSH ve Panel erişimi kurulum sırasında açık kalmalı

log "Güvenlik paketleri kuruldu (yapılandırma tailscale modülünde)"

# =============================================================================
# 24. KURULUM DOĞRULAMASI (ÖZET)
# =============================================================================

info "Kurulum doğrulaması yapılıyor..."
echo ""

# Sayaçlar
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

check_service() {
    local service_name="$1"
    local display_name="$2"
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    if systemctl is-active --quiet "$service_name" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $display_name"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "  ${RED}✗${NC} $display_name"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

check_command() {
    local command="$1"
    local display_name="$2"
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    if eval "$command" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $display_name"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "  ${RED}✗${NC} $display_name"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

echo -e "${CYAN}Temel Servisler:${NC}"
check_service "nginx" "Nginx (Reverse Proxy)"
check_service "NetworkManager" "NetworkManager"
check_service "docker" "Docker"
check_service "kiosk-panel" "Kiosk Panel"

echo ""
echo -e "${CYAN}Ağ Servisleri:${NC}"
check_service "tailscaled" "Tailscaled"
check_service "cockpit.socket" "Cockpit"

echo ""
echo -e "${CYAN}Uygulama Servisleri:${NC}"
check_service "x11vnc" "VNC Server"
check_service "netmon" "Netmon"
check_service "collector-agent" "Collector Agent"
check_service "prometheus-node-exporter" "Node Exporter"

echo ""
echo -e "${CYAN}Konteynerler:${NC}"
check_command "docker ps --format '{{.Names}}' | grep -q local_database" "MongoDB Container"

echo ""
echo -e "${CYAN}Güvenlik:${NC}"
check_command "which ufw" "UFW (kurulu, tailscale sonrası etkinleşecek)"
check_command "which fail2ban-client" "Fail2ban (kurulu, tailscale sonrası yapılandırılacak)"
echo -e "  ${YELLOW}ℹ${NC} UFW ve SSH config tailscale modülünde yapılandırılacak"

echo ""
echo -e "${CYAN}Sonuç:${NC}"
echo -e "  Toplam: $TOTAL_CHECKS | ${GREEN}Başarılı: $PASSED_CHECKS${NC} | ${RED}Başarısız: $FAILED_CHECKS${NC}"

if [[ $FAILED_CHECKS -gt 0 ]]; then
    echo ""
    warn "Bazı bileşenler başlatılamadı. Reboot sonrası tekrar kontrol edin."
fi

# =============================================================================
# TAMAMLANDI
# =============================================================================

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                     KURULUM TAMAMLANDI!                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Panel Erişimi:${NC}"
echo "  - Yerel: http://localhost:4444"
echo "  - Ağdan: http://$(hostname -I | awk '{print $1}'):4444"
echo ""
echo -e "${CYAN}Sonraki Adımlar:${NC}"
echo -e "  1. Sistemi yeniden başlatın: ${YELLOW}sudo reboot${NC}"
echo "  2. Panel otomatik olarak açılacak"
echo "  3. Modülleri sırasıyla kurun"
echo ""
echo -e "${CYAN}Log Dosyası:${NC} $LOG_FILE"
echo ""

log "Kurulum tamamlandı"