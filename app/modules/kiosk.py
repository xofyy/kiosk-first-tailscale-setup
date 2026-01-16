"""
Kiosk Setup Panel - Kiosk Module
Kiosk ekran yapılandırması

Özellikler:
- Kiosk kullanıcı şifresi
- GRUB rotation (console fbcon)
- Touch matrix (Xorg config)

Not: Ekran rotasyonu ve Chromium URL, scriptler tarafından
config.yaml'dan runtime'da okunur. Bu modül sadece sistem
dosyalarını (GRUB, Xorg config) günceller.
"""

import os
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class KioskModule(BaseModule):
    name = "kiosk"
    display_name = "Kiosk"
    description = "Ekran rotasyonu, touch yapılandırması, kullanıcı şifresi"
    order = 5
    dependencies = ["cockpit"]
    
    def _configure_touch(self, vendor_id: str, matrix: str) -> None:
        """
        Xorg touch config dosyasını güncelle (idempotent)
        
        Args:
            vendor_id: Touch cihazının USB vendor:product ID'si (örn: 222a:0001)
            matrix: TransformationMatrix değeri (örn: 0 1 0 -1 0 1 0 0 1)
        """
        touch_conf = f'''Section "InputClass"
    Identifier "Touchscreen Rotation"
    MatchUSBID "{vendor_id}"
    MatchIsTouchscreen "on"
    Option "TransformationMatrix" "{matrix}"
EndSection
'''
        conf_path = '/etc/X11/xorg.conf.d/99-touch-rotation.conf'
        
        # İdempotent: Sadece değişiklik varsa yaz
        if os.path.exists(conf_path):
            with open(conf_path) as f:
                if f.read().strip() == touch_conf.strip():
                    self.logger.info("Touch config zaten güncel")
                    return
        
        # Dizini oluştur
        os.makedirs('/etc/X11/xorg.conf.d', exist_ok=True)
        
        # Config dosyasını yaz
        self.write_file(conf_path, touch_conf)
        self.logger.info("Touch config güncellendi")
    
    def install(self) -> Tuple[bool, str]:
        """
        Kiosk yapılandırması
        
        Akış:
        1. Kiosk kullanıcı şifresi (config'den)
        2. GRUB rotation - console için (config'den)
        3. Touch matrix - Xorg config (config'den)
        
        Not: Ekran rotasyonu ve URL ayarları display-init.sh ve
        chromium-kiosk.sh tarafından config'den okunur.
        """
        try:
            # =================================================================
            # 1. Kiosk Kullanıcı Şifresi
            # =================================================================
            kiosk_password = self.get_config('passwords.kiosk', '')
            
            if kiosk_password:
                self.logger.info("Kiosk kullanıcı şifresi ayarlanıyor...")
                self.run_shell(f'echo "kiosk:{kiosk_password}" | chpasswd')
            else:
                self.logger.info("Kiosk şifresi config'de belirtilmemiş, atlanıyor")
            
            # =================================================================
            # 2. GRUB Rotation (console için)
            # =================================================================
            grub_rotation = self.get_config('kiosk.grub_rotation', 1)
            self.logger.info(f"GRUB rotation ayarlanıyor: {grub_rotation}")
            self.configure_grub({'grub_rotation': grub_rotation})
            
            # =================================================================
            # 3. Touch Matrix - Xorg Config
            # =================================================================
            touch_vendor = self.get_config('kiosk.touch_vendor_id', '222a:0001')
            touch_matrix = self.get_config('kiosk.touch_matrix', '0 1 0 -1 0 1 0 0 1')
            self.logger.info(f"Touch config ayarlanıyor: {touch_vendor}")
            self._configure_touch(touch_vendor, touch_matrix)
            
            # =================================================================
            # 4. Bilgilendirme
            # =================================================================
            self.logger.info("Ekran rotasyonu ve URL ayarları X restart sonrası uygulanır")
            
            self.logger.info("Kiosk yapılandırması tamamlandı")
            return True, "Kiosk yapılandırıldı (değişiklikler için X restart önerilir)"
            
        except Exception as e:
            self.logger.error(f"Kiosk yapılandırma hatası: {e}")
            return False, str(e)
