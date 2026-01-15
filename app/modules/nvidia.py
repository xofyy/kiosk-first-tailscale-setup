"""
Kiosk Setup Panel - NVIDIA Module
NVIDIA GPU driver kurulumu
"""

from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule
from app.services.system import SystemService


@register_module
class NvidiaModule(BaseModule):
    name = "nvidia"
    display_name = "NVIDIA Driver"
    description = "NVIDIA GPU driver kurulumu, MOK key ve GRUB yapılandırması"
    order = 1
    dependencies = []  # İlk modül, bağımlılık yok
    
    def _check_prerequisites(self) -> Tuple[bool, str]:
        """İnternet bağlantısı kontrolü"""
        system = SystemService()
        if not system.check_internet():
            return False, "İnternet bağlantısı gerekli"
        return True, ""
    
    def install(self) -> Tuple[bool, str]:
        """NVIDIA driver kurulumu"""
        try:
            driver_version = self.get_config('nvidia.driver_version', '535')
            mok_password = self.get_config('passwords.mok', '12345678')
            
            self.logger.info(f"NVIDIA driver {driver_version} kuruluyor...")
            
            # 1. Gerekli paketleri kur
            packages = [
                f'nvidia-driver-{driver_version}',
                'nvidia-utils-{}'.format(driver_version),
                'mokutil'
            ]
            
            if not self.apt_install(packages):
                return False, "NVIDIA paketleri kurulamadı"
            
            # 2. MOK key kontrolü ve import
            # Secure Boot aktifse MOK key import et
            try:
                result = self.run_shell('mokutil --sb-state', check=False)
                if 'SecureBoot enabled' in result.stdout:
                    self.logger.info("Secure Boot aktif, MOK key ayarlanıyor...")
                    
                    # MOK key import (şifre otomatik girilir)
                    mok_der = '/var/lib/shim-signed/mok/MOK.der'
                    
                    # MOK key varsa import et
                    import os
                    if os.path.exists(mok_der):
                        # mokutil --import için şifreyi pipe ile gönder
                        self.run_shell(
                            f'echo -e "{mok_password}\\n{mok_password}" | mokutil --import {mok_der}',
                            check=False
                        )
                        self.logger.info("MOK key import edildi. Reboot sonrası onay gerekecek.")
            except Exception as e:
                self.logger.warning(f"MOK key kontrolü hatası: {e}")
            
            # 3. GRUB yapılandırması
            grub_file = '/etc/default/grub'
            try:
                with open(grub_file, 'r') as f:
                    grub_content = f.read()
                
                # nvidia-drm.modeset=1 ekle
                if 'nvidia-drm.modeset=1' not in grub_content:
                    grub_content = grub_content.replace(
                        'GRUB_CMDLINE_LINUX_DEFAULT="',
                        'GRUB_CMDLINE_LINUX_DEFAULT="nvidia-drm.modeset=1 '
                    )
                    
                    with open(grub_file, 'w') as f:
                        f.write(grub_content)
                    
                    # update-grub
                    self.run_command(['update-grub'])
                    self.logger.info("GRUB yapılandırması güncellendi")
                    
            except Exception as e:
                self.logger.warning(f"GRUB yapılandırma hatası: {e}")
            
            # 4. nvidia-persistenced servisi
            self.systemctl('enable', 'nvidia-persistenced')
            
            self.logger.info("NVIDIA driver kurulumu tamamlandı")
            return True, "NVIDIA driver kuruldu. Secure Boot aktifse, reboot sonrası MOK onayı gerekebilir."
            
        except Exception as e:
            self.logger.error(f"NVIDIA kurulum hatası: {e}")
            return False, str(e)
