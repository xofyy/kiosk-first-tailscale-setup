# ACO Maintenance Panel

A graphical kiosk installation panel to be installed on Ubuntu Server.

## Features

- Touch screen support (90° rotation)
- Web-based interface (Flask + Chromium)
- MongoDB-based configuration system
- Automatic installation (all base components via install.sh)
- NVIDIA and Tailscale installation from web panel
- Docker container management with web UI access
- NVR reverse proxy via Nginx

## Installation Flow

```
Ubuntu Server → install.sh → Reboot → Panel (4444) → NVIDIA/Tailscale → Complete → Kiosk
```

## System Requirements

- Ubuntu Server 22.04 LTS or higher
- NVIDIA GPU (optional, for driver installation)
- Internet connection
- Root privileges

## Installation

```bash
git clone https://github.com/xofyy/kiosk-first-tailscale-setup.git
cd kiosk-first-tailscale-setup
sudo bash install.sh
```

## Upgrade

To upgrade an existing installation to the latest version:

```bash
# Check for updates
sudo bash upgrade.sh --check

# Interactive upgrade
sudo bash upgrade.sh

# Force upgrade without confirmation
sudo bash upgrade.sh --force

# Rollback to previous version
sudo bash upgrade.sh --rollback
```

The upgrade script:
- Creates automatic backups before upgrading
- Updates app files, scripts, configs, and dependencies
- Preserves MongoDB data, UFW rules, and system configuration
- Keeps the last 5 backups for rollback

## Components Installed Automatically via install.sh

| Component | Description |
|-----------|-------------|
| X11 / Openbox | Graphical interface |
| Chromium | Kiosk browser |
| NetworkManager | Network management |
| Nginx | NVR reverse proxy |
| Cockpit | Web management panel |
| VNC (x11vnc) | Remote desktop |
| Docker | Container runtime |
| MongoDB | Database (Docker container) |
| Mongo Express | MongoDB web admin (Docker container, port 8081) |
| Netmon | Network monitoring service |
| Collector | Metric collection (Prometheus) |
| UFW + Fail2ban | Security |
| Tailscale (package) | VPN installation |

## Web Panel Modules

Modules to be installed via panel:

| Module | Description |
|--------|-------------|
| NVIDIA | GPU driver + Secure Boot MOK management |
| Tailscale | VPN enrollment + Headscale connection |

## Panel Structure

| Tab | Visibility | Content |
|-----|------------|---------|
| Home | Always | RVM ID, connection status, IP configuration, system control |
| Install | Setup only | NVIDIA and Tailscale module installations |
| Logs | Setup only | Installation and system logs |
| Services | Always | Docker container management, web UI access |

## Panel Access

- **Local**: http://localhost:4444
- **Tailscale**: http://TAILSCALE-IP:4444

> Note: Due to UFW rules, the panel is only accessible via Tailscale.

## Project Structure

```
kiosk-first-tailscale-setup/
├── app/                        # Flask application
│   ├── modules/                # Active: nvidia.py, tailscale.py
│   │   └── base.py             # MongoDB config client
│   ├── routes/                 # API and page routes
│   ├── services/               # System, Hardware, Enrollment, Docker
│   ├── templates/              # HTML templates
│   │   ├── base.html           # Main template
│   │   ├── home.html           # Home page
│   │   ├── install.html        # Installation
│   │   ├── logs.html           # Logs
│   │   └── services.html       # Services
│   └── static/                 # CSS + JavaScript
├── configs/                    # Configuration files
│   ├── chromium/               # Browser policies
│   ├── cockpit/                # Cockpit config + polkit rules
│   ├── collector/              # Prometheus collector config
│   ├── docker/                 # Docker daemon configs
│   ├── kiosk/                  # User profile, xinit, openbox
│   ├── netmon/                 # Network monitor config
│   ├── network/                # NetworkManager, DNS, resolved
│   ├── nginx/                  # Nginx config + NVR proxy
│   └── systemd/                # Service unit files
├── scripts/                    # Shell scripts
│   ├── chromium-admin.sh       # Admin browser
│   ├── chromium-kiosk.sh       # Kiosk browser
│   ├── chromium-panel.sh       # Panel browser
│   ├── display-init.sh         # Display settings
│   ├── kiosk-startup.sh        # Kiosk session startup
│   ├── network-init.sh         # Network initialization
│   ├── nvidia-fallback.sh      # NVIDIA/nouveau/fbdev fallback
│   ├── toggle-admin.sh         # F11 admin browser toggle
│   └── toggle-panel-kiosk.sh   # F10 panel/kiosk toggle
├── install.sh                  # Main installation script
├── upgrade.sh                  # Upgrade script
├── VERSION                     # Version file
├── requirements.txt            # Python dependencies
└── README.md
```

## Configuration (MongoDB)

All settings are stored in the `aco.settings` collection in MongoDB:

```json
{
  "rvm_id": "RVM-001",
  "hardware_id": "auto-generated",
  "mok_password": "12345678",
  "nvidia_driver": "580",
  "modules": {
    "nvidia": "completed",
    "tailscale": "completed"
  },
  "setup_complete": true
}
```

## Post-Installation Directories

```
/opt/aco-panel/                # Application files
  ├── app/                     # Flask application
  ├── configs/                 # Configuration files
  ├── scripts/                 # Shell scripts (also in /usr/local/bin/)
  └── venv/                    # Python virtual environment
/srv/docker/                   # Docker Compose
  └── docker-compose.yml       # MongoDB + Mongo Express
/etc/nginx/
  ├── nginx.conf               # Main Nginx config
  └── sites-available/nvr-proxy # NVR reverse proxy
/var/log/aco-panel/            # Log files
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| F10 | Panel <-> Kiosk toggle |
| F11 | Admin browser toggle |

> Note: F10 does not work until setup is complete (setup_complete=false).

## Security

- UFW firewall (Tailscale-only access)
- SSH only via Tailscale
- Fail2ban brute-force protection
- MongoDB localhost only

## License

MIT License

## Developer

xofyy - https://github.com/xofyy
