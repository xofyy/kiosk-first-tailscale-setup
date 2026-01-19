"""
Kiosk Setup Panel - Tailscale Module
Tailscale Enrollment ve Headscale bağlantısı

Not: Tailscale paketi install.sh'da kuruldu.
Bu modül sadece enrollment ve headscale bağlantısı yapar.
"""

import time
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule
from app.services.system import SystemService
from app.services.hardware import HardwareService
from app.services.enrollment import EnrollmentService

# Sabitler
HEADSCALE_URL = "https://headscale.xofyy.com"
APPROVAL_TIMEOUT = 300  # 5 dakika


@register_module
class TailscaleModule(BaseModule):
    name = "tailscale"
    display_name = "Tailscale"
    description = "Tailscale VPN kurulumu ve Enrollment kayıt"
    order = 2
    dependencies = []  # NVIDIA'dan bağımsız kurulabilir
    
    def _check_prerequisites(self) -> Tuple[bool, str]:
        """İnternet ve enrollment kontrolü"""
        system = SystemService()
        if not system.check_internet():
            return False, "İnternet bağlantısı gerekli"
        
        # Kiosk ID gerekli
        if not self._config.get_kiosk_id():
            return False, "Önce Kiosk ID belirlenmelidir"
        
        return True, ""
    
    def _is_tailscale_installed(self) -> bool:
        """Tailscale kurulu mu kontrol et"""
        result = self.run_command(['which', 'tailscale'], check=False)
        return result.returncode == 0
    
    def _is_tailscale_connected(self) -> bool:
        """Tailscale bağlı mı kontrol et"""
        result = self.run_command(['tailscale', 'status'], check=False)
        return result.returncode == 0
    
    def install(self) -> Tuple[bool, str]:
        """Tailscale kurulumu"""
        try:
            # 1. Hardware ID üret
            hardware = HardwareService()
            hardware_id = hardware.get_hardware_id()
            
            if not hardware_id:
                return False, "Hardware ID üretilemedi"
            
            # Config'e kaydet
            self._config.set_hardware_id(hardware_id)
            self.logger.info(f"Hardware ID: {hardware_id}")
            
            # 2. Kiosk ID al (önceden ayarlanmış olmalı)
            kiosk_id = self._config.get_kiosk_id()
            
            if not kiosk_id:
                return False, "Kiosk ID bulunamadı"
            
            self.logger.info(f"Kiosk ID: {kiosk_id}")
            
            # 3. Enrollment API'ye kayıt
            enrollment = EnrollmentService()
            
            self.logger.info("Enrollment API'ye kayıt yapılıyor...")
            
            # Ek bilgileri al
            motherboard_uuid = hardware.get_motherboard_uuid()
            mac_addresses = hardware.get_mac_addresses()
            
            self.logger.info(f"Motherboard UUID: {motherboard_uuid}")
            self.logger.info(f"MAC Addresses: {mac_addresses}")
            
            enroll_result = enrollment.enroll(
                kiosk_id, 
                hardware_id,
                motherboard_uuid=motherboard_uuid,
                mac_addresses=mac_addresses
            )
            
            if not enroll_result['success']:
                return False, enroll_result.get('error', 'Enrollment başarısız')
            
            self.logger.info(f"Enrollment durumu: {enroll_result.get('status')}")
            
            # 4. Zaten approved mı kontrol et (auth_key response'da olabilir)
            auth_key = enroll_result.get('auth_key')
            
            if not auth_key:
                # 5. Onay bekle - HARDWARE_ID ile!
                self.logger.info("Yönetici onayı bekleniyor...")
                auth_key = enrollment.wait_for_approval(hardware_id, timeout=APPROVAL_TIMEOUT)
            
            if not auth_key:
                return False, "Yönetici onayı alınamadı veya zaman aşımı"

            self.logger.info("Yönetici onayı alındı!")

            # 6. Tailscale kurulu mu kontrol et (install.sh'da kurulmuş olmalı)
            if not self._is_tailscale_installed():
                return False, "Tailscale kurulu değil! install.sh çalıştırıldı mı?"

            self.logger.info("Tailscale kurulu ✓")

            # 7. Tailscaled servisini başlat
            self.logger.info("Tailscaled servisi başlatılıyor...")
            if not self.systemctl('enable', 'tailscaled'):
                self.logger.warning("tailscaled enable edilemedi")
            if not self.systemctl('start', 'tailscaled'):
                self.logger.warning("tailscaled başlatılamadı")
            
            # Servisin başlamasını bekle
            time.sleep(3)
            
            # 8. Headscale'e bağlan (tam parametrelerle!)
            self.logger.info(f"Headscale'e bağlanılıyor: {HEADSCALE_URL}")
            
            result = self.run_command([
                'tailscale', 'up',
                '--login-server', HEADSCALE_URL,
                '--authkey', auth_key,
                '--hostname', kiosk_id.lower(),
                '--advertise-tags=tag:kiosk',
                '--ssh',
                '--accept-dns=true',
                '--accept-routes=false',
                '--reset'
            ], check=False)
            
            if result.returncode != 0:
                self.logger.error(f"Tailscale up hatası: {result.stderr}")
                return False, f"Headscale bağlantısı başarısız: {result.stderr}"
            
            # 9. Bağlantıyı doğrula
            time.sleep(3)
            
            if self._is_tailscale_connected():
                self.logger.info("Tailscale bağlantısı doğrulandı")
                
                # Durum bilgisini logla
                status_result = self.run_command(['tailscale', 'status'], check=False)
                if status_result.returncode == 0:
                    self.logger.info(f"Tailscale durumu:\n{status_result.stdout}")
            else:
                self.logger.warning("Tailscale bağlantısı doğrulanamadı (ama işlem devam ediyor)")
            
            # 10. Kiosk ID'yi MongoDB'ye kaydet (diğer servisler için)
            self._save_kiosk_id_to_mongodb(kiosk_id, hardware_id)

            # 11. Güvenlik yapılandırması (UFW kuralları, SSH, fail2ban)
            # tailscale0 interface artık mevcut, kurallar eklenebilir
            self._configure_security()

            self.logger.info("Tailscale kurulumu tamamlandı")
            return True, "Tailscale kuruldu ve Headscale'e bağlandı"

        except Exception as e:
            self.logger.error(f"Tailscale kurulum hatası: {e}")
            return False, str(e)

    def _configure_security(self) -> bool:
        """
        Tailscale bağlantısı sonrası güvenlik yapılandırması.
        UFW kuralları, SSH config ve fail2ban ayarları.
        """
        self.logger.info("Güvenlik yapılandırması başlıyor...")

        try:
            # 1. UFW tailscale0 kuralları
            self.logger.info("UFW kuralları ekleniyor...")

            ufw_rules = [
                # Tailscale üzerinden SSH
                'ufw allow in on tailscale0 to any port 22 proto tcp',
                # Tailscale üzerinden VNC
                'ufw allow in on tailscale0 to any port 5900 proto tcp',
                # Tailscale üzerinden Panel
                'ufw allow in on tailscale0 to any port 4444 proto tcp',
                # Tailscale üzerinden MongoDB
                'ufw allow in on tailscale0 to any port 27017 proto tcp',
                # LAN'dan SSH engelle (tailscale kuralları öncelikli)
                'ufw deny 22/tcp',
            ]

            for rule in ufw_rules:
                result = self.run_shell(f'{rule} 2>/dev/null || true', check=False)
                self.logger.debug(f"UFW: {rule}")

            self.logger.info("UFW kuralları eklendi")

            # 2. SSH yapılandırması (Tailscale-only)
            self.logger.info("SSH yapılandırılıyor...")

            ssh_config = """# Tailscale-only SSH Configuration
# Bu dosya tailscale modülü tarafından oluşturuldu

PermitRootLogin yes
PasswordAuthentication no
PubkeyAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
UsePAM yes
AllowUsers root aco kiosk
AllowTcpForwarding yes
X11Forwarding no
PermitTunnel no
GatewayPorts no
LoginGraceTime 20
MaxAuthTries 3
MaxSessions 2
ClientAliveInterval 300
ClientAliveCountMax 2
LogLevel VERBOSE
"""
            if self.write_file('/etc/ssh/sshd_config.d/99-tailscale-only.conf', ssh_config):
                self.systemctl('restart', 'sshd')
                self.logger.info("SSH yapılandırması tamamlandı")
            else:
                self.logger.warning("SSH config yazılamadı")

            # 3. Fail2ban yapılandırması
            self.logger.info("Fail2ban yapılandırılıyor...")

            fail2ban_config = """[sshd]
enabled = true
port = ssh
filter = sshd
backend = systemd
maxretry = 3
bantime = 3600
findtime = 600
"""
            if self.write_file('/etc/fail2ban/jail.d/sshd.conf', fail2ban_config):
                self.systemctl('enable', 'fail2ban')
                self.systemctl('restart', 'fail2ban')
                self.logger.info("Fail2ban yapılandırması tamamlandı")
            else:
                self.logger.warning("Fail2ban config yazılamadı")

            self.logger.info("Güvenlik yapılandırması tamamlandı")
            return True

        except Exception as e:
            self.logger.error(f"Güvenlik yapılandırma hatası: {e}")
            return False

    def _save_kiosk_id_to_mongodb(self, kiosk_id: str, hardware_id: str) -> None:
        """Kiosk ID'yi MongoDB'ye kaydet"""
        try:
            import socket
            from datetime import datetime
            from pymongo import MongoClient

            client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
            db = client['kiosk']
            collection = db['settings']

            # Kayıt oluştur/güncelle
            document = {
                'kiosk_id': kiosk_id,
                'hardware_id': hardware_id,
                'hostname': socket.gethostname(),
                'registered_at': datetime.utcnow(),
                'setup_complete': False
            }

            collection.update_one(
                {},
                {'$set': document},
                upsert=True
            )

            client.close()
            self.logger.info(f"Kiosk ID MongoDB'ye kaydedildi: {kiosk_id}")

        except Exception as e:
            self.logger.warning(f"MongoDB kayıt hatası: {e}")
