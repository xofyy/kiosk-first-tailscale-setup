# Kiosk Setup Panel

Ubuntu Server üzerine kurulacak, grafik tabanlı kiosk kurulum paneli.

## Özellikler

- Dokunmatik ekran, klavye ve mouse desteği
- Web tabanlı arayüz (Flask + Chromium)
- Modüler kurulum sistemi (10 modül)
- Ansible ile yapılan tüm işlemlerin entegrasyonu
- Merkezi ayar yönetimi (`/etc/kiosk-setup/config.yaml`)
- **Idempotent kurulum** - tekrar çalıştırılabilir, mevcut config'ler korunur

## Kurulum Akışı

```
Ubuntu Server → install.sh → Reboot → Panel (4444) → Kurulumlar → Tamamla → Kiosk (3000)
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

## Kurulum Modülleri

Modüller aşağıdaki sırayla kurulmalıdır:

| # | Modül | Açıklama | Bağımlılık |
|---|-------|----------|------------|
| 1 | NVIDIA | GPU driver kurulumu | İnternet |
| 2 | Tailscale | VPN ve Enrollment | İnternet |
| 3 | Network | NetworkManager, DNS | NVIDIA, Tailscale |
| 4 | Kiosk | Ekran yapılandırması | Network |
| 5 | VNC | Uzak masaüstü (x11vnc) | Kiosk |
| 6 | Cockpit | Web yönetim paneli | Kiosk |
| 7 | netmon | Ağ izleme | VNC, Cockpit |
| 8 | collector | Metrik toplama | VNC, Cockpit |
| 9 | Docker | Container + MongoDB | VNC, Cockpit |
| 10 | Security | UFW + SSH | netmon, collector, Docker |

## Klavye Kısayolları

Kurulum tamamlandıktan sonra:

| Kısayol | İşlem |
|---------|-------|
| Ctrl+Alt+P | Panel'e geç (localhost:4444) |
| Ctrl+Alt+K | Kiosk'a geç (localhost:3000) |
| Ctrl+Alt+C | Cockpit'e geç (localhost:9090) |

## Panel Erişimi

- **Yerel**: http://localhost:4444
- **Ağdan**: http://IP:4444 (sadece Tailscale üzerinden)
- **Tailscale**: http://TAILSCALE-IP:4444

## Proje Yapısı

```
kiosk-first-tailscale-setup/
├── app/                        # Flask uygulaması
│   ├── modules/                # 10 kurulum modülü
│   ├── routes/                 # API ve sayfa routes
│   ├── services/               # System, Hardware, Enrollment
│   ├── templates/              # HTML templates
│   └── static/                 # CSS + JavaScript
├── scripts/                    # Shell scriptleri
│   ├── chromium-panel.sh       # Panel Chromium
│   ├── chromium-kiosk.sh       # Kiosk Chromium
│   ├── switch-to-*.sh          # Geçiş scriptleri
│   └── display-init.sh         # Ekran ayarları
├── systemd/                    # Service dosyaları
├── templates/                  # Jinja2 kurulum şablonları
├── config/                     # Varsayılan config
│   └── default.yaml
├── install.sh                  # Ana kurulum scripti
├── requirements.txt            # Python bağımlılıkları
└── README.md
```

## Yapılandırma

Ayarlar `/etc/kiosk-setup/config.yaml` dosyasında saklanır.

### Örnek Yapılandırma

```yaml
kiosk:
  url: "http://localhost:3000"
  rotation: "right"

network:
  dns_servers: ["8.8.8.8", "8.8.4.4"]

docker:
  compose_path: "/srv/docker"

registry:
  url: "acolinux.azurecr.io"
  username: "user"
  password: "pass"
```

## Kurulum Sonrası Dizinler

```
/etc/kiosk-setup/              # Yapılandırma
  └── config.yaml
/opt/kiosk-setup-panel/        # Uygulama dosyaları
  ├── app/
  └── venv/                    # Python virtual environment
/srv/docker/                   # Docker Compose
  └── docker-compose.yml
/usr/local/bin/                # Shell scriptleri
/var/log/kiosk-setup.log       # Log dosyası
```

## Idempotent Kurulum

`install.sh` birden fazla kez çalıştırılabilir:
- Mevcut kullanıcı config'leri korunur
- Venv zaten varsa atlanır
- Scriptler sadece değişmişse güncellenir
- Systemd service zaten varsa atlanır

## Lisans

MIT License

## Geliştirici

xofyy - https://github.com/xofyy
