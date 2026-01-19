# Kiosk Setup Panel

Ubuntu Server üzerine kurulacak, grafik tabanlı kiosk kurulum paneli.

## Özellikler

- Dokunmatik ekran desteği (90° rotasyon)
- Web tabanlı arayüz (Flask + Chromium)
- MongoDB tabanlı yapılandırma sistemi
- Otomatik kurulum (install.sh ile tüm temel bileşenler)
- Web panelden NVIDIA ve Tailscale kurulumu
- Nginx reverse proxy ile servis yönetimi

## Kurulum Akışı

```
Ubuntu Server → install.sh → Reboot → Panel (4444) → NVIDIA/Tailscale → Tamamla → Kiosk
```

## Sistem Gereksinimleri

- Ubuntu Server 22.04 LTS veya üzeri
- NVIDIA GPU (opsiyonel, driver kurulumu için)
- İnternet bağlantısı
- Root yetkileri

## Kurulum

### Git ile Kurulum

```bash
git clone https://github.com/xofyy/kiosk-first-tailscale-setup.git
cd kiosk-first-tailscale-setup
sudo bash install.sh
```

### Tek Satır Kurulum

```bash
curl -sSL https://raw.githubusercontent.com/xofyy/kiosk-first-tailscale-setup/main/install.sh | sudo bash
```

## install.sh ile Otomatik Kurulan Bileşenler

| Bileşen | Açıklama |
|---------|----------|
| X11 / Openbox | Grafik arayüz |
| Chromium | Kiosk tarayıcı |
| NetworkManager | Ağ yönetimi |
| Nginx | Reverse proxy (port 4444) |
| Cockpit | Web yönetim paneli |
| VNC (x11vnc) | Uzak masaüstü |
| Docker + MongoDB | Container ve veritabanı |
| Netmon | Ağ izleme servisi |
| Collector | Metrik toplama (Prometheus) |
| UFW + Fail2ban | Güvenlik |
| Tailscale (paket) | VPN kurulumu |

## Web Panel Modülleri

Panel üzerinden kurulacak modüller:

| Modül | Açıklama |
|-------|----------|
| NVIDIA | GPU driver + Secure Boot MOK yönetimi |
| Tailscale | VPN enrollment + Headscale bağlantısı |

## Panel Yapısı

| Sekme | İçerik |
|-------|--------|
| Anasayfa | Kiosk ID, bağlantı durumu, IP yapılandırma, sistem kontrol |
| Kurulum | NVIDIA ve Tailscale modül kurulumları |
| Loglar | Kurulum ve sistem logları |
| Servisler | Cockpit, Mechatronic Controller erişimi |

## Servisler

Nginx üzerinden erişilebilir servisler:

| Servis | Port | Path | Açıklama |
|--------|------|------|----------|
| Panel | 5000 | / | Kiosk Setup Panel |
| Cockpit | 9090 | /cockpit/ | Sistem yönetimi |
| Mechatronic | 1234 | /mechatronic_controller/ | Mechatronic Controller |

## Panel Erişimi

- **Yerel**: http://localhost:4444
- **Tailscale**: http://TAILSCALE-IP:4444

> Not: UFW kuralları gereği panel sadece Tailscale üzerinden erişilebilir.

## Proje Yapısı

```
kiosk-first-tailscale-setup/
├── app/                        # Flask uygulaması
│   ├── modules/                # Aktif: nvidia.py, tailscale.py
│   │   └── base.py             # MongoDB config client
│   ├── routes/                 # API ve sayfa routes
│   ├── services/               # System, Hardware, Enrollment
│   ├── templates/              # HTML templates
│   │   ├── base.html           # Ana şablon
│   │   ├── home.html           # Anasayfa
│   │   ├── install.html        # Kurulum
│   │   ├── logs.html           # Loglar
│   │   └── services.html       # Servisler
│   └── static/                 # CSS + JavaScript
├── scripts/                    # Shell scriptleri
│   ├── chromium-panel.sh       # Panel Chromium
│   ├── chromium-kiosk.sh       # Kiosk Chromium
│   ├── switch-to-*.sh          # Geçiş scriptleri
│   └── display-init.sh         # Ekran ayarları
├── install.sh                  # Ana kurulum scripti
├── requirements.txt            # Python bağımlılıkları
└── README.md
```

## Yapılandırma (MongoDB)

Tüm ayarlar MongoDB'de `kiosk.settings` collection'ında saklanır:

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

## Kurulum Sonrası Dizinler

```
/opt/kiosk-setup-panel/        # Uygulama dosyaları
  ├── app/
  └── venv/                    # Python virtual environment
/srv/docker/                   # Docker Compose
  └── docker-compose.yml       # MongoDB container
/etc/nginx/
  ├── kiosk-services.json      # Servis registry
  └── sites-available/kiosk-panel
/var/log/kiosk-setup/          # Log dosyaları
```

## Klavye Kısayolu

| Kısayol | İşlem |
|---------|-------|
| F10 | Panel ↔ Kiosk toggle |

> Not: Kurulum tamamlanmadan (setup_complete=false) F10 çalışmaz.

## Güvenlik

- UFW firewall (Tailscale-only erişim)
- SSH sadece Tailscale üzerinden
- Fail2ban brute-force koruması
- MongoDB sadece localhost

## Lisans

MIT License

## Geliştirici

xofyy - https://github.com/xofyy
