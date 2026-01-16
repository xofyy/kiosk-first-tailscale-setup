"""
Kiosk Setup Panel - Kiosk Module
Kiosk ekran yapılandırması
"""

from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class KioskModule(BaseModule):
    name = "kiosk"
    display_name = "Kiosk"
    description = "Ekran rotasyonu, touch yapılandırması, kullanıcı şifresi"
    order = 4
    dependencies = ["network"]
    
    def install(self) -> Tuple[bool, str]:
        """
        Kiosk yapılandırması
        
        Not: Display init, touch config ve chromium scriptleri
        install.sh tarafından scripts/ klasöründen kopyalanır.
        Bu modül sadece runtime ayarlarını yapar.
        """
        try:
            # 1. Kiosk kullanıcı şifresi
            kiosk_password = self.get_config('passwords.kiosk', '')
            
            if kiosk_password:
                self.logger.info("Kiosk kullanıcı şifresi ayarlanıyor...")
                self.run_shell(f'echo "kiosk:{kiosk_password}" | chpasswd')
            else:
                self.logger.info("Kiosk şifresi config'de belirtilmemiş, atlanıyor")
            
            # 2. GRUB rotation (console için)
            grub_rotation = self.get_config('kiosk.grub_rotation', 1)
            self.logger.info(f"GRUB rotation ayarlanıyor: {grub_rotation}")
            self.configure_grub({'grub_rotation': grub_rotation})
            
            self.logger.info("Kiosk yapılandırması tamamlandı")
            return True, "Kiosk yapılandırıldı"
            
        except Exception as e:
            self.logger.error(f"Kiosk yapılandırma hatası: {e}")
            return False, str(e)
