"""
Kiosk Setup Panel - Tailscale Module
Tailscale VPN kurulumu ve Enrollment
"""

import time
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule
from app.services.system import SystemService
from app.services.hardware import HardwareService
from app.services.enrollment import EnrollmentService
# DIP: Global config import kaldırıldı, self._config kullanılıyor

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
            
            # 6. Tailscale kurulu mu kontrol et
            if self._is_tailscale_installed():
                self.logger.info("Tailscale zaten kurulu")
            else:
                self.logger.info("Tailscale kuruluyor...")
                result = self.run_shell('curl -fsSL https://tailscale.com/install.sh | sh', check=False)
                if result.returncode != 0:
                    return False, f"Tailscale kurulum scripti başarısız: {result.stderr}"
                
                # Kurulum doğrulaması
                if not self._is_tailscale_installed():
                    return False, "Tailscale kurulumu başarısız"
                self.logger.info("Tailscale kuruldu")
            
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
            
            self.logger.info("Tailscale kurulumu tamamlandı")
            return True, "Tailscale kuruldu ve Headscale'e bağlandı"
            
        except Exception as e:
            self.logger.error(f"Tailscale kurulum hatası: {e}")
            return False, str(e)
