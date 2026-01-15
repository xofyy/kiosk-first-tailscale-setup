"""
Kiosk Setup Panel - Tailscale Module
Tailscale VPN kurulumu ve Enrollment
"""

from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule
from app.services.system import SystemService
from app.services.hardware import HardwareService
from app.services.enrollment import EnrollmentService
from app.config import config


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
        if not config.get_kiosk_id():
            return False, "Önce Kiosk ID belirlenmelidir"
        
        return True, ""
    
    def install(self) -> Tuple[bool, str]:
        """Tailscale kurulumu"""
        try:
            # 1. Hardware ID üret
            hardware = HardwareService()
            hardware_id = hardware.get_hardware_id()
            
            if not hardware_id:
                return False, "Hardware ID üretilemedi"
            
            # Config'e kaydet
            config.set_hardware_id(hardware_id)
            
            self.logger.info(f"Hardware ID: {hardware_id}")
            
            # 2. Kiosk ID al (önceden ayarlanmış olmalı)
            kiosk_id = config.get_kiosk_id()
            
            if not kiosk_id:
                return False, "Kiosk ID bulunamadı"
            
            self.logger.info(f"Kiosk ID: {kiosk_id}")
            
            # 3. Enrollment API'ye kayıt
            enrollment = EnrollmentService()
            
            self.logger.info("Enrollment API'ye kayıt yapılıyor...")
            
            enroll_result = enrollment.enroll(kiosk_id, hardware_id)
            
            if not enroll_result['success']:
                return False, enroll_result.get('error', 'Enrollment başarısız')
            
            # 4. Yönetici onayı bekle
            self.logger.info("Yönetici onayı bekleniyor...")
            
            auth_key = enrollment.wait_for_approval(kiosk_id, timeout=300)
            
            if not auth_key:
                return False, "Yönetici onayı alınamadı veya zaman aşımı"
            
            self.logger.info("Yönetici onayı alındı!")
            
            # 5. Tailscale kurulumu
            self.logger.info("Tailscale kuruluyor...")
            
            # Tailscale repo ve kurulum
            self.run_shell('curl -fsSL https://tailscale.com/install.sh | sh')
            
            # 6. Headscale'e bağlan
            headscale_url = "https://headscale.xofyy.com"
            
            self.run_command([
                'tailscale', 'up',
                '--login-server', headscale_url,
                '--authkey', auth_key,
                '--hostname', kiosk_id.lower()
            ])
            
            # 7. Tailscale servisini etkinleştir
            self.systemctl('enable', 'tailscaled')
            
            self.logger.info("Tailscale kurulumu tamamlandı")
            return True, "Tailscale kuruldu ve Headscale'e bağlandı"
            
        except Exception as e:
            self.logger.error(f"Tailscale kurulum hatası: {e}")
            return False, str(e)
