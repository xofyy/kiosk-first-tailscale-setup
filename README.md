# Kiosk Tailscale Setup Sistemi

Ubuntu Server için otomatik Tailscale kurulum ve merkezi enrollment sistemi.

## Özellikler

- Açılışta otomatik çalışma
- Donanım tabanlı benzersiz ID üretimi
- Merkezi enrollment API ile güvenli cihaz kaydı
- Yönetici onayı gerektiren kayıt sistemi
- Headscale sunucusuna otomatik bağlantı
- Kurulum tamamlanana kadar login engelleme
- Hata durumunda otomatik yeniden deneme
- Mevcut Tailscale bağlantısı kontrolü (gereksiz kurulumu atlar)

## Dosya Yapısı

```
kiosk-first-tailscale-setup/
├── install.sh              # Kurulum scripti (paketler, service, override oluşturur)
├── setup-kiosk.sh          # Ana setup scripti
├── hardware-unique-id.sh   # Donanım tabanlı benzersiz ID üretici
└── README.md               # Bu dosya
```

### Kurulum Sonrası Oluşan Dosyalar

```
/usr/local/bin/setup-kiosk.sh                              # Ana script
/usr/local/lib/kiosk/hardware-unique-id.sh                 # Hardware ID scripti
/etc/systemd/system/kiosk-setup.service                    # Systemd service
/etc/systemd/system/getty@tty1.service.d/10-kiosk-setup.conf  # Getty override
/etc/systemd/system/getty@tty2.service.d/10-kiosk-setup.conf
/etc/systemd/system/getty@tty3.service.d/10-kiosk-setup.conf
/etc/kiosk-setup/                                          # Config dizini
├── kiosk-id                                               # Girilen Kiosk ID
├── hardware-id                                            # Üretilen Hardware ID
└── .setup-complete                                        # Kurulum tamamlandı flag'i
```

## Gereksinimler

### Sistem Gereksinimleri

- **Ubuntu Server** (18.04+)
- **Python3** (JSON parsing için - Ubuntu'da varsayılan olarak yüklü)
- **Root yetkisi** (kurulum ve çalışma için)

### Enrollment API Sunucusu

Bu sistem merkezi bir Enrollment API sunucusu gerektirir. Detaylar için: `enrollment-api/README.md`

Sunucu adresi `setup-kiosk.sh` içinde tanımlıdır:
```bash
ENROLLMENT_SERVER="https://enrollment.xofyy.com"
HEADSCALE_SERVER="https://headscale.xofyy.com"
```

## Kurulum

### Yöntem 1: Git Clone (Önerilen)

```bash
# Kiosk makinesinde çalıştırın
git clone https://github.com/xofyy/kiosk-first-tailscale-setup.git
cd kiosk-first-tailscale-setup
sudo bash install.sh
sudo reboot
```

### Yöntem 2: SCP ile Kopyalama

```bash
# 1. Dosyaları kiosk makinesine kopyalayın
scp -r kiosk-first-tailscale-setup/ user@kiosk:/tmp/

# 2. Kiosk'ta kurulumu çalıştırın
ssh user@kiosk "sudo bash /tmp/kiosk-first-tailscale-setup/install.sh"

# 3. Sistemi yeniden başlatın
ssh user@kiosk "sudo reboot"
```

### Kurulum Scripti Ne Yapar?

1. Gerekli paketleri kurar: `curl`, `dmidecode`, `iputils-ping`
2. Scriptleri kopyalar
3. `kiosk-setup.service` oluşturur
4. Getty override'ları oluşturur (`10-kiosk-setup.conf`)
5. Servisi etkinleştirir

## Kullanım Akışı

```
┌─────────────────────────────────────────────────────────────┐
│ 1. İlk Açılış                                               │
│    → kiosk-setup.service başlar                             │
│    → Getty (login) engellenir                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Bağlantı Kontrolleri                                     │
│    → İnternet bağlantısı kontrol edilir                     │
│    → DNS çözümlemesi kontrol edilir                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Hardware ID Üretimi                                      │
│    → Anakart, RAM, Disk seri numaraları toplanır            │
│    → 16 karakterlik benzersiz ID üretilir (SHA256)          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Kiosk ID Girişi                                          │
│    → Kullanıcıdan benzersiz bir ID istenir (örn: LOBBY-01)  │
│    → Sadece BÜYÜK harf, rakam, tire (-) ve alt çizgi (_)    │
│    → Bu ID, Tailscale hostname'i olarak kullanılır          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Enrollment Kaydı                                         │
│    → Hardware ID ve Kiosk ID, Enrollment API'ye gönderilir  │
│    → Yönetici onayı beklenir (polling)                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Yönetici Onayı (Sunucu Tarafı)                           │
│    → enroll list                                            │
│    → enroll approve <hardware_id> --yes                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Tailscale Kurulumu                                       │
│    → Auth key alınır                                        │
│    → Tailscale kurulur                                      │
│    → Headscale'e bağlanır                                   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Tamamlandı                                               │
│    → .setup-complete flag'i oluşturulur                     │
│    → Sistem yeniden başlar                                  │
│    → Normal kullanıma geçilir                               │
└─────────────────────────────────────────────────────────────┘
```

## Yönetim Komutları

### Yeniden Kurulum Tetikleme

```bash
# Kurulum flag'ini sil ve yeniden başlat
sudo rm /etc/kiosk-setup/.setup-complete
sudo reboot
```

### Kiosk ve Hardware ID'yi Görme

```bash
cat /etc/kiosk-setup/kiosk-id
cat /etc/kiosk-setup/hardware-id
```

### Tailscale Durumu

```bash
tailscale status
tailscale status --json | jq
```

### Servis Durumu

```bash
systemctl status kiosk-setup.service
```

### Logları Görme

```bash
journalctl -u kiosk-setup.service -f
```

### Hardware ID Üreticiyi Test Etme

```bash
# Tüm bilgiler
sudo /usr/local/lib/kiosk/hardware-unique-id.sh

# Sadece kısa ID
sudo /usr/local/lib/kiosk/hardware-unique-id.sh --short

# JSON formatında
sudo /usr/local/lib/kiosk/hardware-unique-id.sh --json
```

## Konfigürasyon

### Sunucu Adreslerini Değiştirme

`setup-kiosk.sh` dosyasında:

```bash
HEADSCALE_SERVER="https://headscale.xofyy.com"
ENROLLMENT_SERVER="https://enrollment.xofyy.com"
```

### Tailscale Parametreleri

`setup-kiosk.sh` içindeki `connect_tailscale` fonksiyonunda:

```bash
tailscale up \
    --login-server "$HEADSCALE_SERVER" \
    --authkey "$AUTH_KEY" \
    --hostname="$hostname" \
    --advertise-tags=tag:kiosk \
    --ssh \
    --accept-dns=true \
    --accept-routes=false \
    --reset
```

## Sorun Giderme

### Setup Ekranında Takıldı

1. Başka bir TTY'ye geçin (Ctrl+Alt+F2)
2. SSH ile bağlanın (eğer erişilebiliyorsa)
3. Logları kontrol edin: `journalctl -u kiosk-setup.service`

### Enrollment Onayı Gelmiyor

1. Enrollment API sunucusunun çalıştığını kontrol edin
2. `enroll list` ile pending kayıtları görün
3. `enroll approve <hardware_id> --yes` ile onaylayın

### Tailscale Bağlanmıyor

1. Auth key'in geçerli olduğunu kontrol edin (1 saatlik ömrü var)
2. Headscale sunucusunun erişilebilir olduğunu kontrol edin
3. DNS çözümlemesini kontrol edin: `nslookup headscale.xofyy.com`

### ID Değiştirmek İstiyorum

```bash
sudo rm /etc/kiosk-setup/kiosk-id
sudo rm /etc/kiosk-setup/.setup-complete
sudo reboot
```

### Hardware ID Sıfırlamak İstiyorum

```bash
sudo rm /etc/kiosk-setup/hardware-id
sudo rm /etc/kiosk-setup/.setup-complete
sudo reboot
```

## Ansible Entegrasyonu

Getty override dosyaları numaralı isimle oluşturulur (`10-kiosk-setup.conf`), böylece Ansible sonradan autologin ekleyebilir:

```
/etc/systemd/system/getty@tty1.service.d/
├── 10-kiosk-setup.conf    # Bu sistem tarafından oluşturulur
└── 20-autologin.conf      # Ansible tarafından eklenebilir
```

Systemd tüm `.conf` dosyalarını alfabetik sırayla birleştirir, çakışma olmaz.

## Güvenlik Notları

1. **Hardware ID**: Donanım bileşenlerinden üretilir, cihaza özgüdür
2. **Auth Key**: Enrollment API tarafından üretilir, tek kullanımlık ve 1 saatlik ömrü vardır
3. **Yönetici Onayı**: Her cihaz kaydı manuel onay gerektirir
4. **Tag Sistemi**: Kiosk'lar `tag:kiosk` ile etiketlenir, ACL'lerle yönetilebilir

## Lisans

MIT
