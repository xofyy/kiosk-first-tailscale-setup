#!/bin/bash
# =============================================================================
# ACO Maintenance Panel - Installer Script
# =============================================================================
# This script installs ACO Maintenance Panel on Ubuntu Server.
# Usage: sudo bash install.sh
# =============================================================================

set -e

# =============================================================================
# COLORS AND LOG FUNCTIONS
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

LOG_FILE="/var/log/aco-panel-install.log"

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
# VARIABLES
# =============================================================================

KIOSK_USER="kiosk"
INSTALL_DIR="/opt/aco-panel"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# For non-interactive apt installation
export DEBIAN_FRONTEND=noninteractive
export APT_LISTCHANGES_FRONTEND=none

# =============================================================================
# ROOT CHECK
# =============================================================================

if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root!"
    echo "Usage: sudo bash install.sh"
    exit 1
fi

# =============================================================================
# BANNER
# =============================================================================

clear
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                                                                      ║"
echo "║               ACO Maintenance Panel - INSTALLER                      ║"
echo "║                                                                      ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# =============================================================================
# 1. SYSTEM UPDATE
# =============================================================================

info "Updating system..."
apt-get update -qq
apt-get upgrade -y -qq
log "System updated"

# =============================================================================
# 2. BASE PACKAGES
# =============================================================================

info "Installing base packages..."

PACKAGES=(
    # X11 and Display
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
    
    # System tools
    dbus-x11
    mesa-utils
    fonts-dejavu-core
    curl
    wget
    nano
    git
    
    # Network tools
    net-tools
    isc-dhcp-client
    iputils-ping
)

for pkg in "${PACKAGES[@]}"; do
    if ! dpkg -l | grep -q "^ii  $pkg "; then
        apt-get install -y -qq "$pkg" 2>/dev/null || warn "Package could not be installed: $pkg"
    fi
done

log "Base packages installed"

# =============================================================================
# 3. CREATE KIOSK USER
# =============================================================================

info "Creating kiosk user..."

if ! id "$KIOSK_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$KIOSK_USER"
    # Add to video and audio groups
    usermod -aG video,audio,input,tty "$KIOSK_USER"
    log "User created: $KIOSK_USER"
else
    log "User already exists: $KIOSK_USER"
fi

# =============================================================================
# 4. DIRECTORY STRUCTURE
# =============================================================================

info "Creating directory structure..."

# Install directory
mkdir -p "$INSTALL_DIR"

# Setup marker directory (for setup_complete flag file)
# NOTE: Config is now in MongoDB, this directory is only for .setup-complete marker
mkdir -p /etc/aco-panel

# Installer log file
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

# Module logs directory
KIOSK_LOG_DIR="/var/log/aco-panel"
mkdir -p "$KIOSK_LOG_DIR"
chmod 755 "$KIOSK_LOG_DIR"

log "Directories created"

# =============================================================================
# 5. COPY APPLICATION FILES
# =============================================================================

info "Copying application files..."

# If script is running in a clone directory
if [[ -d "$SCRIPT_DIR/app" ]]; then
    cp -r "$SCRIPT_DIR/app" "$INSTALL_DIR/"
    cp -r "$SCRIPT_DIR/templates" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
    log "Files copied: $SCRIPT_DIR -> $INSTALL_DIR"
fi

# NOTE: Config is now stored in MongoDB (created in Docker section)

# =============================================================================
# 6. PYTHON VIRTUAL ENVIRONMENT
# =============================================================================

info "Creating Python virtual environment..."

if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    python3 -m venv "$INSTALL_DIR/venv"
    log "New venv created"
else
    log "Venv already exists: $INSTALL_DIR/venv"
fi

source "$INSTALL_DIR/venv/bin/activate"

pip install --upgrade pip -q
pip install -r "$INSTALL_DIR/requirements.txt" -q

deactivate
log "Python environment ready"

# =============================================================================
# 7. COPY SCRIPTS
# =============================================================================

info "Copying scripts..."

# Check scripts directory - only copy if changed
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
        log "$SCRIPTS_UPDATED scripts updated"
    else
        log "Scripts already up to date"
    fi
fi

# =============================================================================
# 8. XORG TOUCH ROTATION CONFIG
# =============================================================================

info "Configuring touchscreen..."

XORG_CONF_DIR="/etc/X11/xorg.conf.d"
TOUCH_CONF="$XORG_CONF_DIR/99-touch-rotation.conf"

mkdir -p "$XORG_CONF_DIR"

# Hardcoded touch settings (90 degree clockwise rotation)
TOUCH_VENDOR_ID="222a:0001"
TOUCH_MATRIX="0 1 0 -1 0 1 0 0 1"

# Create Xorg config (only if missing or different)
TOUCH_CONF_CONTENT="# Touchscreen Rotation Configuration
# Generated by ACO Maintenance Panel

Section \"InputClass\"
    Identifier \"Touchscreen Rotation\"
    MatchUSBID \"$TOUCH_VENDOR_ID\"
    MatchIsTouchscreen \"on\"
    Option \"TransformationMatrix\" \"$TOUCH_MATRIX\"
EndSection"

if [[ ! -f "$TOUCH_CONF" ]] || [[ "$(cat "$TOUCH_CONF")" != "$TOUCH_CONF_CONTENT" ]]; then
    echo "$TOUCH_CONF_CONTENT" > "$TOUCH_CONF"
    log "Xorg touch rotation config created"
else
    log "Xorg touch rotation config already up to date"
fi

# =============================================================================
# 9. CHROMIUM POLICY
# =============================================================================

info "Configuring Chromium policy..."

CHROME_POLICY_DIR="/etc/chromium-browser/policies/managed"
mkdir -p "$CHROME_POLICY_DIR"

cat > "$CHROME_POLICY_DIR/aco-policy.json" << 'EOF'
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

log "Chromium policy created"

# =============================================================================
# 10. NGINX REVERSE PROXY
# =============================================================================

info "Installing Nginx reverse proxy..."

apt-get install -y nginx

# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Services registry (start empty - modules add)
mkdir -p /etc/nginx
cat > /etc/nginx/aco-services.json << 'EOF'
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
  "scanners": {
    "display_name": "Scanners Dashboard",
    "port": 504,
    "path": "/scanners/",
    "websocket": true,
    "check_type": "port",
    "check_value": 504
  },
  "printer": {
    "display_name": "Printer Panel",
    "port": 5200,
    "path": "/printer/",
    "websocket": true,
    "check_type": "port",
    "check_value": 5200
  },
  "camera": {
    "display_name": "Camera Controller",
    "port": 5100,
    "path": "/camera/",
    "websocket": true,
    "check_type": "port",
    "check_value": 5100
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

# Proxy config for panel
cat > /etc/nginx/sites-available/aco-panel << 'NGINX_EOF'
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

        # WebSocket support
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

    # Mechatronic socket.io (for root path access)
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

    # Cockpit static files
    location /cockpit/static/ {
        proxy_pass http://127.0.0.1:9090/cockpit/cockpit/static/;
        proxy_set_header Host $host:$server_port;
    }

    # Cockpit main
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

        # For iframe
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;
    }

    # Scanners Dashboard
    location /scanners/ {
        proxy_pass http://127.0.0.1:504/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;

        # For iframe
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;

        # HTML/JS path rewrite
        sub_filter 'src="/' 'src="/scanners/';
        sub_filter 'href="/' 'href="/scanners/';
        sub_filter "src='/" "src='/scanners/";
        sub_filter "href='/" "href='/scanners/";
        # API/fetch calls
        sub_filter '"/api/' '"/scanners/api/';
        sub_filter "'/api/" "'/scanners/api/";
        sub_filter 'fetch("/' 'fetch("/scanners/';
        sub_filter "fetch('/" "fetch('/scanners/";
        # Hardcoded WebSocket/HTTP URLs
        sub_filter 'localhost:504' "' + window.location.host + '/scanners";
        sub_filter '127.0.0.1:504' "' + window.location.host + '/scanners";
        sub_filter_once off;
        sub_filter_types text/html text/css text/javascript application/javascript application/x-javascript;
        proxy_set_header Accept-Encoding "";
    }

    # Scanners socket.io
    location /scanners/socket.io/ {
        proxy_pass http://127.0.0.1:504/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Printer Panel
    location /printer/ {
        proxy_pass http://127.0.0.1:5200/printer/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;

        # For iframe
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;

        # HTML/JS path rewrite
        sub_filter 'src="/' 'src="/printer/';
        sub_filter 'href="/' 'href="/printer/';
        sub_filter "src='/" "src='/printer/";
        sub_filter "href='/" "href='/printer/";
        # API/fetch calls
        sub_filter '"/api/' '"/printer/api/';
        sub_filter "'/api/" "'/printer/api/";
        sub_filter 'fetch("/' 'fetch("/printer/';
        sub_filter "fetch('/" "fetch('/printer/";
        # Hardcoded socket.io URLs
        sub_filter 'http://0.0.0.0:5200/socket.io' '/printer/socket.io';
        sub_filter '0.0.0.0:5200/socket.io' '/printer/socket.io';
        sub_filter 'http://0.0.0.0:5200' '/printer';
        sub_filter '0.0.0.0:5200' '/printer';
        sub_filter_once off;
        sub_filter_types text/html text/css text/javascript application/javascript application/x-javascript;
        proxy_set_header Accept-Encoding "";
    }

    # Printer socket.io
    location /printer/socket.io/ {
        proxy_pass http://127.0.0.1:5200/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Camera Controller
    location /camera/ {
        proxy_pass http://127.0.0.1:5100/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # For iframe
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;

        # HTML/JS path rewrite
        sub_filter 'src="/' 'src="/camera/';
        sub_filter 'href="/' 'href="/camera/';
        sub_filter "src='/" "src='/camera/";
        sub_filter "href='/" "href='/camera/";
        # API/fetch calls
        sub_filter '"/api/' '"/camera/api/';
        sub_filter "'/api/" "'/camera/api/";
        sub_filter '"/static/' '"/camera/static/';
        sub_filter "'/static/" "'/camera/static/";
        sub_filter 'fetch("/' 'fetch("/camera/';
        sub_filter "fetch('/" "fetch('/camera/";
        # Hardcoded URLs
        sub_filter 'localhost:5100' "' + window.location.host + '/camera";
        sub_filter '127.0.0.1:5100' "' + window.location.host + '/camera";
        sub_filter_once off;
        sub_filter_types text/html text/css text/javascript application/javascript application/x-javascript;
        proxy_set_header Accept-Encoding "";
    }

    # Camera Controller - Socket.IO
    location /camera/socket.io/ {
        proxy_pass http://127.0.0.1:5100/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/aco-panel /etc/nginx/sites-enabled/
systemctl enable nginx
systemctl restart nginx

# Verification
if systemctl is-active --quiet nginx; then
    log "Nginx reverse proxy ready (port: 4444)"
else
    warn "Nginx could not be started"
fi

# =============================================================================
# 11. SYSTEMD SERVICES
# =============================================================================

info "Creating systemd services..."

SERVICE_FILE="/etc/systemd/system/aco-panel.service"

# Flask Panel Service (always update - for upgrade support)
cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=ACO Maintenance Panel Web Server
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aco-panel
Environment="PATH=/opt/aco-panel/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/opt/aco-panel/venv/bin/python -m gunicorn -b 127.0.0.1:5000 -w 2 --timeout 120 app.main:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
log "aco-panel.service created/updated"

# Enable service
systemctl enable aco-panel.service 2>/dev/null || true

log "Systemd services ready"

# =============================================================================
# 12. TTY1 AUTOLOGIN
# =============================================================================

info "Configuring TTY1 autologin..."

mkdir -p /etc/systemd/system/getty@tty1.service.d/

cat > /etc/systemd/system/getty@tty1.service.d/override.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $KIOSK_USER --noclear %I \$TERM
EOF

log "TTY1 autologin configured"

# =============================================================================
# 13. KIOSK USER CONFIGURATION
# =============================================================================

info "Configuring kiosk user..."

KIOSK_HOME="/home/$KIOSK_USER"

# .bash_profile - X startup (only create if missing)
if [[ ! -f "$KIOSK_HOME/.bash_profile" ]]; then
    cat > "$KIOSK_HOME/.bash_profile" << 'EOF'
# ACO Maintenance Panel - Bash Profile

# Automatically start X on TTY1 (with watchdog)
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    while true; do
        startx -- -nocursor
        sleep 2
    done
fi
EOF
    log ".bash_profile created"
else
    log ".bash_profile already exists, skipping"
fi

# .xinitrc (only create if missing)
if [[ ! -f "$KIOSK_HOME/.xinitrc" ]]; then
    cat > "$KIOSK_HOME/.xinitrc" << 'EOF'
#!/bin/bash
# ACO Maintenance Panel - X Init

# Screen settings
/usr/local/bin/display-init.sh 2>/dev/null || true

# Start Openbox
exec openbox-session
EOF
    chmod +x "$KIOSK_HOME/.xinitrc"
    log ".xinitrc created"
else
    log ".xinitrc already exists, skipping"
fi

# Openbox config directory
mkdir -p "$KIOSK_HOME/.config/openbox"

# Openbox autostart (only create if missing)
if [[ ! -f "$KIOSK_HOME/.config/openbox/autostart" ]]; then
    cat > "$KIOSK_HOME/.config/openbox/autostart" << 'EOF'
#!/bin/bash
# ACO Maintenance Panel - Openbox Autostart

# Disable screensaver
xset s off
xset -dpms
xset s noblank

# Apply screen rotation (independent of NVIDIA/MOK status)
# display-init.sh has its own wait and retry logic
/usr/local/bin/display-init.sh &

# Check if setup is complete
# NOTE: This file is created by panel based on setup_complete value in MongoDB
if [ -f /etc/aco-panel/.setup-complete ]; then
    # Start in kiosk mode (installation complete)
    /usr/local/bin/chromium-kiosk.sh &
else
    # Start in panel mode (installation in progress)
    /usr/local/bin/chromium-panel.sh &
fi
EOF
    chmod +x "$KIOSK_HOME/.config/openbox/autostart"
    log "openbox/autostart created"
else
    log "openbox/autostart already exists, skipping"
fi

# Openbox rc.xml - keybindings (only create if missing)
if [[ ! -f "$KIOSK_HOME/.config/openbox/rc.xml" ]]; then
    cat > "$KIOSK_HOME/.config/openbox/rc.xml" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <keyboard>
    <!-- ========== Kiosk Shortcuts ========== -->

    <!-- Panel/Kiosk Toggle: F10 -->
    <keybind key="F10">
      <action name="Execute">
        <command>/usr/local/bin/toggle-panel-kiosk.sh</command>
      </action>
    </keybind>

    <!-- ========== Block Browser Shortcuts ========== -->

    <!-- Block F1-F9, F11-F12 (F10 is toggle) -->
    <keybind key="F1"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="F2"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="F3"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="F4"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="F5"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="F6"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="F7"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="F8"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="F9"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="F11"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="F12"><action name="Execute"><command>/bin/true</command></action></keybind>

    <!-- Block Ctrl combinations -->
    <keybind key="C-t"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-n"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-w"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-h"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-j"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-p"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-s"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-u"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-o"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-g"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-f"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-d"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-r"><action name="Execute"><command>/bin/true</command></action></keybind>

    <!-- Block Ctrl+Shift combinations -->
    <keybind key="C-S-t"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-S-n"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-S-j"><action name="Execute"><command>/bin/true</command></action></keybind>
    <keybind key="C-S-i"><action name="Execute"><command>/bin/true</command></action></keybind>
  </keyboard>

  <applications>
    <application class="*">
      <decor>no</decor>
      <fullscreen>yes</fullscreen>
    </application>
  </applications>
</openbox_config>
EOF
    log "openbox/rc.xml created"
else
    log "openbox/rc.xml already exists, skipping"
fi

# Set ownership
chown -R "$KIOSK_USER:$KIOSK_USER" "$KIOSK_HOME"

log "Kiosk user configuration completed"

# =============================================================================
# 14. SERVICE ENABLE (will start after Docker/MongoDB)
# =============================================================================

info "Enabling panel service..."
# NOTE: Panel depends on MongoDB, will start after Docker installation
log "Panel service enabled (will start after MongoDB is ready)"

# =============================================================================
# 15. NETWORK CONFIGURATION
# =============================================================================

info "Configuring network..."

# NetworkManager installation
if ! dpkg -l | grep -q "^ii  network-manager "; then
    apt-get install -y -qq network-manager
fi

# Disable cloud-init network
CLOUD_INIT_FILE="/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg"
if [[ ! -f "$CLOUD_INIT_FILE" ]]; then
    mkdir -p /etc/cloud/cloud.cfg.d
    echo "network: {config: disabled}" > "$CLOUD_INIT_FILE"
    log "cloud-init network disabled"
fi

# -----------------------------------------------------------------------------
# Netplan Configuration (NetworkManager handles all interfaces dynamically)
# -----------------------------------------------------------------------------

# Backup existing netplan configs
mkdir -p /etc/netplan/backup
for f in /etc/netplan/*.yaml; do
    [[ "$f" == *"01-network-manager"* ]] && continue
    [[ -f "$f" ]] && mv "$f" /etc/netplan/backup/ 2>/dev/null || true
done

# Simple netplan config - let NetworkManager handle everything
# Interface names are detected dynamically at runtime by the panel
cat > /etc/netplan/01-network-manager.yaml << 'EOF'
# Network configuration managed by NetworkManager
# Generated by ACO Maintenance Panel installer
# All ethernet interfaces managed dynamically - no hardcoded names
network:
  version: 2
  renderer: NetworkManager
EOF

log "Netplan configured with NetworkManager renderer"

# Apply netplan
netplan apply 2>/dev/null || true

# Mask systemd-networkd-wait-online (for boot speed)
systemctl mask systemd-networkd-wait-online.service 2>/dev/null || true
systemctl stop systemd-networkd-wait-online.service 2>/dev/null || true
systemctl disable systemd-networkd 2>/dev/null || true
systemctl stop systemd-networkd 2>/dev/null || true

# DNS configuration - systemd-resolved
cat > /etc/systemd/resolved.conf << 'EOF'
[Resolve]
DNS=8.8.8.8 8.8.4.4
FallbackDNS=1.1.1.1 9.9.9.9
Domains=~.
DNSStubListener=yes
EOF

systemctl restart systemd-resolved 2>/dev/null || true

# NetworkManager global DNS configuration
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/dns.conf << 'EOF'
[main]
dns=systemd-resolved

[global-dns-domain-*]
servers=8.8.8.8,8.8.4.4
EOF

# NetworkManager services
systemctl enable NetworkManager 2>/dev/null || true
systemctl start NetworkManager 2>/dev/null || true
# Reload config if NM was already running
nmcli general reload conf 2>/dev/null || true
systemctl enable NetworkManager-wait-online 2>/dev/null || true

# DNS validation (required for Tailscale etc.)
info "Validating DNS connection..."
for i in $(seq 1 15); do
    if ping -c 1 -W 2 8.8.8.8 &>/dev/null && ping -c 1 -W 2 google.com &>/dev/null; then
        log "DNS working"
        break
    fi
    sleep 2
done

# Verification
if systemctl is-active --quiet NetworkManager; then
    log "Network configuration completed"
else
    warn "NetworkManager could not be started"
fi

# =============================================================================
# 16. TAILSCALE INSTALLATION (package only)
# =============================================================================

info "Installing Tailscale..."

if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
    log "Tailscale installed"
else
    log "Tailscale already installed"
fi

# Enable and start service
systemctl enable tailscaled 2>/dev/null || true
systemctl start tailscaled 2>/dev/null || true

# Verification
if systemctl is-active --quiet tailscaled; then
    log "Tailscale ready (enrollment will be done from panel)"
else
    warn "Tailscaled could not be started"
fi

# =============================================================================
# 17. COCKPIT INSTALLATION
# =============================================================================

info "Installing Cockpit..."

COCKPIT_PACKAGES=(
    cockpit
    cockpit-system
    cockpit-networkmanager
    cockpit-storaged
    cockpit-packagekit
)

apt-get install -y -qq "${COCKPIT_PACKAGES[@]}"

# Cockpit configuration
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

# Cockpit service
systemctl enable cockpit.socket 2>/dev/null || true
systemctl start cockpit.socket 2>/dev/null || true

# Polkit rules
mkdir -p /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/50-aco-network.rules << 'EOF'
// NetworkManager permissions
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager") == 0 &&
        subject.user == "kiosk") {
        return polkit.Result.YES;
    }
});

// PackageKit permissions (limited)
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

# NOTE: Nginx config and services.json created in Section 10 (Panel + Mechatronic + Cockpit)

# Verification
if systemctl is-active --quiet cockpit.socket; then
    log "Cockpit installed"
else
    warn "Cockpit socket could not be started"
fi

# =============================================================================
# 18. VNC INSTALLATION
# =============================================================================

info "Installing VNC..."

apt-get install -y -qq x11vnc

# VNC directory
VNC_DIR="/home/$KIOSK_USER/.vnc"
mkdir -p "$VNC_DIR"

# VNC password (default: aco)
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
ExecStart=/usr/bin/x11vnc -display :0 -forever -shared -rfbport 5900 -rfbauth $VNC_DIR/passwd -noxdamage
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable x11vnc 2>/dev/null || true
# Not started - will auto-start after X11 starts

log "VNC installed (will be active after X11 starts)"

# =============================================================================
# 18.5. NVIDIA FALLBACK SERVICE (enable nouveau)
# =============================================================================

info "Installing NVIDIA fallback service..."

# Script that enables nouveau if nvidia module cannot be loaded
cat > /usr/local/bin/nvidia-fallback.sh << 'EOF'
#!/bin/bash
# NVIDIA Fallback Script
# Enables nouveau if nvidia module cannot be loaded
# Creates FBDEV rotation config in Secure Boot lockdown state

LOG="/var/log/aco-panel/nvidia-fallback.log"
FBDEV_CONF="/etc/X11/xorg.conf.d/10-fbdev-rotation.conf"

mkdir -p "$(dirname "$LOG")"
mkdir -p "$(dirname "$FBDEV_CONF")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG"
}

# Create FBDEV rotation config (Secure Boot lockdown fallback)
create_fbdev_config() {
    log "Creating FBDEV rotation config..."
    cat > "$FBDEV_CONF" << 'FBDEV_EOF'
# FBDEV Rotation Configuration (Auto-generated by nvidia-fallback)
# Activates if GPU driver cannot be loaded in Secure Boot lockdown state
Section "Device"
    Identifier "FBDEV"
    Driver "fbdev"
    Option "fbdev" "/dev/fb0"
    Option "Rotate" "CW"
    Option "ShadowFB" "true"
EndSection
FBDEV_EOF
    log "FBDEV rotation config created"
}

# Delete FBDEV config (not needed if nvidia/nouveau is working)
remove_fbdev_config() {
    if [ -f "$FBDEV_CONF" ]; then
        rm -f "$FBDEV_CONF"
        log "FBDEV rotation config deleted (GPU driver active)"
    fi
}

log "Starting NVIDIA fallback check..."

# Is nvidia module already loaded?
if lsmod | grep -q "^nvidia "; then
    log "NVIDIA module loaded, fallback not needed"
    remove_fbdev_config
    exit 0
fi

# Try if nvidia can be loaded
modprobe nvidia 2>/dev/null
if lsmod | grep -q "^nvidia "; then
    log "NVIDIA module loaded successfully"
    remove_fbdev_config
    exit 0
fi

# nvidia failed to load, enable nouveau
log "NVIDIA failed to load, trying nouveau..."

# Load nouveau (won't work in kernel lockdown even if blacklisted)
modprobe nouveau 2>/dev/null

if lsmod | grep -q "^nouveau "; then
    log "nouveau loaded successfully (NVIDIA fallback)"
    remove_fbdev_config
    # Wait for DRM device to be created
    sleep 2
    if [ -e /dev/dri/card0 ]; then
        log "/dev/dri/card0 exists, GPU ready"
    else
        log "WARNING: /dev/dri/card0 not created"
    fi
    exit 0
fi

# nouveau also failed to load - probably Secure Boot lockdown
log "ERROR: nouveau also failed to load (Secure Boot lockdown?)"
log "FBDEV fallback will be used, rotation provided by Xorg config"

# Create FBDEV rotation config
create_fbdev_config

log "NVIDIA fallback check completed"
EOF

chmod +x /usr/local/bin/nvidia-fallback.sh

# Systemd service - runs before X starts
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

log "NVIDIA fallback service installed"

# =============================================================================
# 19. KIOSK CONFIGURATION
# =============================================================================

info "Configuring kiosk..."

# Kiosk user password
KIOSK_PASSWORD="aco"
echo "kiosk:$KIOSK_PASSWORD" | chpasswd 2>/dev/null || true

# GRUB rotation (fbcon=rotate:1 for right rotation)
GRUB_FILE="/etc/default/grub"
if [[ -f "$GRUB_FILE" ]]; then
    # Get current GRUB_CMDLINE_LINUX_DEFAULT
    CURRENT_CMDLINE=$(grep "^GRUB_CMDLINE_LINUX_DEFAULT" "$GRUB_FILE" | cut -d'"' -f2)

    # Add fbcon and nvidia parameters (if missing)
    NEW_CMDLINE="$CURRENT_CMDLINE"
    [[ "$NEW_CMDLINE" != *"fbcon=rotate:1"* ]] && NEW_CMDLINE="$NEW_CMDLINE fbcon=rotate:1"
    [[ "$NEW_CMDLINE" != *"nvidia-drm.modeset=1"* ]] && NEW_CMDLINE="$NEW_CMDLINE nvidia-drm.modeset=1"
    [[ "$NEW_CMDLINE" != *"quiet"* ]] && NEW_CMDLINE="quiet $NEW_CMDLINE"
    [[ "$NEW_CMDLINE" != *"splash"* ]] && NEW_CMDLINE="$NEW_CMDLINE splash"

    # Update
    sed -i "s|^GRUB_CMDLINE_LINUX_DEFAULT=.*|GRUB_CMDLINE_LINUX_DEFAULT=\"$NEW_CMDLINE\"|" "$GRUB_FILE"
    update-grub 2>/dev/null || true
    log "GRUB rotation configured"
fi

log "Kiosk configuration completed"

# =============================================================================
# 20. NETMON INSTALLATION
# =============================================================================

info "Installing Netmon..."

apt-get install -y -qq git nethogs python3-pip

NETMON_DIR="/opt/netmon"

# Remove if exists
[[ -d "$NETMON_DIR" ]] && rm -rf "$NETMON_DIR"

# Clone
git clone https://github.com/xofyy/netmon.git "$NETMON_DIR" 2>/dev/null || {
    warn "netmon repo could not be cloned"
}

if [[ -d "$NETMON_DIR" ]]; then
    # pip updates
    /usr/bin/pip3 install --upgrade pip setuptools wheel 2>/dev/null || true
    /usr/bin/pip3 uninstall -y UNKNOWN 2>/dev/null || true
    rm -rf "$NETMON_DIR/build" "$NETMON_DIR"/*.egg-info 2>/dev/null || true

    # Install
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

    # Verification
    if systemctl is-active --quiet netmon; then
        log "Netmon installed and running"
    else
        warn "Netmon installed but could not be started"
    fi
else
    warn "Netmon installation skipped"
fi

# =============================================================================
# 21. COLLECTOR INSTALLATION
# =============================================================================

info "Installing Collector..."

apt-get install -y -qq git python3-pip prometheus-node-exporter

# prometheus-node-exporter
systemctl enable prometheus-node-exporter 2>/dev/null || true
systemctl start prometheus-node-exporter 2>/dev/null || true

COLLECTOR_DIR="/opt/collector-agent"

# Remove if exists
[[ -d "$COLLECTOR_DIR" ]] && rm -rf "$COLLECTOR_DIR"

# Clone
git clone https://github.com/xofyy/collector-agent.git "$COLLECTOR_DIR" 2>/dev/null || {
    warn "collector-agent repo could not be cloned"
}

if [[ -d "$COLLECTOR_DIR" ]]; then
    # pip updates
    /usr/bin/pip3 install --upgrade pip setuptools wheel 2>/dev/null || true
    /usr/bin/pip3 uninstall -y UNKNOWN 2>/dev/null || true
    rm -rf "$COLLECTOR_DIR/build" "$COLLECTOR_DIR"/*.egg-info 2>/dev/null || true

    # Install
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

    # Verification
    sleep 2
    if systemctl is-active --quiet collector-agent; then
        log "Collector installed and running"
    else
        warn "Collector installed but could not be started"
    fi

    if systemctl is-active --quiet prometheus-node-exporter; then
        log "Prometheus Node Exporter running"
    else
        warn "Prometheus Node Exporter could not be started"
    fi
else
    warn "Collector installation skipped"
fi

# =============================================================================
# 22. DOCKER INSTALLATION
# =============================================================================

info "Installing Docker..."

# Remove old packages
OLD_DOCKER_PKGS="docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc"
for pkg in $OLD_DOCKER_PKGS; do
    apt-get remove -y "$pkg" 2>/dev/null || true
done

# Required packages
apt-get install -y -qq ca-certificates curl gnupg python3-pip python3-docker python3-pymongo

# Docker GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
chmod a+r /etc/apt/keyrings/docker.gpg

# Docker repo
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -qq

# Docker packages
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin

# Docker daemon.json (NVIDIA runtime added in NVIDIA module)
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

# Docker service
systemctl enable docker 2>/dev/null || true
systemctl restart docker 2>/dev/null || true

# Docker validation
sleep 2
docker --version && log "Docker installed: $(docker --version)"
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
MONGODB_DATA_PATH="/data/mongo-data"

mkdir -p "$COMPOSE_PATH"
mkdir -p "$MONGODB_DATA_PATH"

# MongoDB image - use private registry if available, otherwise official
MONGO_IMAGE="${REGISTRY_URL}/mongodb:latest"
if [[ "$REGISTRY_PASS" == "YOUR_REGISTRY_PASSWORD_HERE" ]] || [[ -z "$REGISTRY_PASS" ]]; then
    MONGO_IMAGE="mongo:7"
    info "No private registry access, will use official MongoDB image"
fi

cat > "$COMPOSE_PATH/docker-compose.yml" << EOF
# Docker Compose Configuration
# Generated by ACO Maintenance Panel

services:
  local_database:
    image: ${MONGO_IMAGE}
    container_name: local_database
    network_mode: host
    restart: always
    volumes:
      - ${MONGODB_DATA_PATH}:/data/db
EOF

# Start MongoDB
cd "$COMPOSE_PATH" && docker compose up -d 2>/dev/null || {
    warn "MongoDB could not be started"
}

# Wait until MongoDB is ready
info "Waiting for MongoDB to be ready..."
MONGO_READY=false
for i in $(seq 1 60); do
    if docker exec local_database mongosh --eval "db.runCommand({ping:1})" &>/dev/null; then
        MONGO_READY=true
        break
    fi
    sleep 1
done

if [[ "$MONGO_READY" == "true" ]]; then
    log "MongoDB ready"

    # Create default settings
    docker exec local_database mongosh --eval '
        db = db.getSiblingDB("aco");
        db.settings.updateOne(
            {},
            {
                $setOnInsert: {
                    rvm_id: null,
                    hardware_id: null,
                    mok_password: null,
                    nvidia_driver: "580",
                    modules: {
                        "remote-connection": "pending",
                        nvidia: "pending"
                    },
                    system: {
                        headscale_url: "https://headscale.xofyy.com",
                        enrollment_url: "https://enrollment.xofyy.com"
                    },
                    setup_complete: false
                }
            },
            {upsert: true}
        );
    ' 2>/dev/null || true
    log "MongoDB default settings created"

    # Start panel service (MongoDB is now ready)
    info "Starting panel service..."
    systemctl start aco-panel.service || warn "Panel service could not be started"

    # Panel validation
    sleep 2
    if systemctl is-active --quiet aco-panel; then
        log "Panel service running"
    else
        warn "Panel service could not be started"
    fi
else
    warn "MongoDB failed to start (60 second timeout)"
    # Try to start panel anyway
    systemctl start aco-panel.service 2>/dev/null || true
fi

# Docker and MongoDB validation
if systemctl is-active --quiet docker; then
    log "Docker service running"
else
    warn "Docker service not running"
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "local_database"; then
    log "MongoDB container running"
else
    warn "MongoDB container not running"
fi

log "Docker installation completed"

# =============================================================================
# 23. SECURITY PACKAGES INSTALLATION
# =============================================================================

info "Installing security packages..."

# Install UFW and fail2ban packages (configuration in tailscale module)
apt-get install -y -qq ufw fail2ban

# NOTE: UFW configuration and enabling will be done in tailscale module
# Because tailscale0 interface is created after enrollment
# SSH and Panel access must remain open during installation

log "Security packages installed (configuration in tailscale module)"

# =============================================================================
# 24. INSTALLATION VERIFICATION (SUMMARY)
# =============================================================================

info "Running installation verification..."
echo ""

# Counters
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
    else
        echo -e "  ${RED}✗${NC} $display_name"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
    return 0
}

check_command() {
    local command="$1"
    local display_name="$2"
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    if eval "$command" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $display_name"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        echo -e "  ${RED}✗${NC} $display_name"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
    return 0
}

echo -e "${CYAN}Base Services:${NC}"
check_service "nginx" "Nginx (Reverse Proxy)"
check_service "NetworkManager" "NetworkManager"
check_service "docker" "Docker"
check_service "aco-panel" "ACO Panel"

echo ""
echo -e "${CYAN}Network Services:${NC}"
check_service "tailscaled" "Tailscaled"
check_service "cockpit.socket" "Cockpit"

echo ""
echo -e "${CYAN}Application Services:${NC}"
check_service "x11vnc" "VNC Server"
check_service "netmon" "Netmon"
check_service "collector-agent" "Collector Agent"
check_service "prometheus-node-exporter" "Node Exporter"

echo ""
echo -e "${CYAN}Containers:${NC}"
check_command "docker ps --format '{{.Names}}' | grep -q local_database" "MongoDB Container"

echo ""
echo -e "${CYAN}Security:${NC}"
check_command "which ufw" "UFW (installed, will be enabled after tailscale)"
check_command "which fail2ban-client" "Fail2ban (installed, will be configured after tailscale)"
echo -e "  ${YELLOW}ℹ${NC} UFW and SSH config will be configured in tailscale module"

echo ""
echo -e "${CYAN}Result:${NC}"
echo -e "  Total: $TOTAL_CHECKS | ${GREEN}Passed: $PASSED_CHECKS${NC} | ${RED}Failed: $FAILED_CHECKS${NC}"

if [[ $FAILED_CHECKS -gt 0 ]]; then
    echo ""
    warn "Some components could not be started. Check again after reboot."
fi

# =============================================================================
# COMPLETED
# =============================================================================

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                     INSTALLATION COMPLETE!                           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Panel Access:${NC}"
echo "  - Local: http://localhost:4444"
echo "  - From network: http://$(hostname -I | awk '{print $1}'):4444"
echo ""
echo -e "${CYAN}Next Steps:${NC}"
echo -e "  1. Reboot the system: ${YELLOW}sudo reboot${NC}"
echo "  2. Panel will open automatically"
echo "  3. Install modules in order"
echo ""
echo -e "${CYAN}Log File:${NC} $LOG_FILE"
echo ""

log "Installation completed"