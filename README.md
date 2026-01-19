# Kiosk Setup Panel

A graphical kiosk installation panel to be installed on Ubuntu Server.

## Features

- Touch screen support (90° rotation)
- Web-based interface (Flask + Chromium)
- MongoDB-based configuration system
- Automatic installation (all base components via install.sh)
- NVIDIA and Tailscale installation from web panel
- Service management with Nginx reverse proxy

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

### Installation with Git

```bash
git clone https://github.com/xofyy/kiosk-first-tailscale-setup.git
cd kiosk-first-tailscale-setup
sudo bash install.sh
```

### One-Line Installation

```bash
curl -sSL https://raw.githubusercontent.com/xofyy/kiosk-first-tailscale-setup/main/install.sh | sudo bash
```

## Components Installed Automatically via install.sh

| Component | Description |
|-----------|-------------|
| X11 / Openbox | Graphical interface |
| Chromium | Kiosk browser |
| NetworkManager | Network management |
| Nginx | Reverse proxy (port 4444) |
| Cockpit | Web management panel |
| VNC (x11vnc) | Remote desktop |
| Docker + MongoDB | Container and database |
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

| Tab | Content |
|-----|---------|
| Home | Kiosk ID, connection status, IP configuration, system control |
| Install | NVIDIA and Tailscale module installations |
| Logs | Installation and system logs |
| Services | Cockpit, Mechatronic Controller access |

## Services

Services accessible via Nginx:

| Service | Port | Path | Description |
|---------|------|------|-------------|
| Panel | 5000 | / | Kiosk Setup Panel |
| Cockpit | 9090 | /cockpit/ | System management |
| Mechatronic | 1234 | /mechatronic_controller/ | Mechatronic Controller |

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
│   ├── services/               # System, Hardware, Enrollment
│   ├── templates/              # HTML templates
│   │   ├── base.html           # Main template
│   │   ├── home.html           # Home page
│   │   ├── install.html        # Installation
│   │   ├── logs.html           # Logs
│   │   └── services.html       # Services
│   └── static/                 # CSS + JavaScript
├── scripts/                    # Shell scripts
│   ├── chromium-panel.sh       # Panel Chromium
│   ├── chromium-kiosk.sh       # Kiosk Chromium
│   ├── switch-to-*.sh          # Switch scripts
│   └── display-init.sh         # Display settings
├── install.sh                  # Main installation script
├── requirements.txt            # Python dependencies
└── README.md
```

## Configuration (MongoDB)

All settings are stored in the `kiosk.settings` collection in MongoDB:

```json
{
  "kiosk_id": "KIOSK-001",
  "hardware_id": "auto-generated",
  "mok_password": "12345678",
  "nvidia_driver": "535",
  "modules": {
    "nvidia": "completed",
    "tailscale": "completed"
  },
  "setup_complete": true
}
```

## Post-Installation Directories

```
/opt/kiosk-setup-panel/        # Application files
  ├── app/
  └── venv/                    # Python virtual environment
/srv/docker/                   # Docker Compose
  └── docker-compose.yml       # MongoDB container
/etc/nginx/
  ├── kiosk-services.json      # Service registry
  └── sites-available/kiosk-panel
/var/log/kiosk-setup/          # Log files
```

## Keyboard Shortcut

| Shortcut | Action |
|----------|--------|
| F10 | Panel <-> Kiosk toggle |

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
