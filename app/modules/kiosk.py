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
    order = 6
    dependencies = ["cockpit"]
    
    def _configure_touch(self, vendor_id: str, matrix: str) -> bool:
        """
        Xorg touch config dosyasını güncelle (idempotent)
        
        Args:
            vendor_id: Touch cihazının USB vendor:product ID'si (örn: 222a:0001)
            matrix: TransformationMatrix değeri (örn: 0 1 0 -1 0 1 0 0 1)
        
        Returns:
            bool: Başarılı mı
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
            try:
                with open(conf_path) as f:
                    if f.read().strip() == touch_conf.strip():
                        self.logger.info("Touch config zaten güncel")
                        return True
            except IOError as e:
                self.logger.warning(f"Mevcut touch config okunamadı: {e}")
        
        # Dizini oluştur
        os.makedirs('/etc/X11/xorg.conf.d', exist_ok=True)
        
        # Config dosyasını yaz
        if not self.write_file(conf_path, touch_conf):
            self.logger.warning("Touch config yazılamadı")
            return False
        
        self.logger.info("Touch config güncellendi")
        return True
    
    def _set_kiosk_password(self, password: str) -> bool:
        """
        Kiosk kullanıcı şifresini ayarla
        Birden fazla yöntem deneyerek hata toleranslı çalışır
        """
        if not password:
            self.logger.warning("Kiosk şifresi belirtilmemiş!")
            return True  # Şifre yoksa hata değil, devam et
        
        self.logger.info("Kiosk kullanıcı şifresi ayarlanıyor...")
        
        # Yöntem 1: chpasswd (tercih edilen, hızlı)
        if os.path.exists('/usr/sbin/chpasswd'):
            result = self.run_shell(
                f'echo "kiosk:{password}" | /usr/sbin/chpasswd',
                check=False
            )
            if result.returncode == 0:
                self.logger.info("Şifre ayarlandı (chpasswd)")
                return True
            self.logger.warning(f"chpasswd başarısız: {result.stderr}")
        
        # Yöntem 2: passwd paketi kur ve tekrar dene
        self.logger.info("chpasswd bulunamadı, passwd paketi kuruluyor...")
        self.apt_install(['passwd'])
        
        if os.path.exists('/usr/sbin/chpasswd'):
            result = self.run_shell(
                f'echo "kiosk:{password}" | /usr/sbin/chpasswd',
                check=False
            )
            if result.returncode == 0:
                self.logger.info("Şifre ayarlandı (chpasswd)")
                return True
            self.logger.warning(f"chpasswd tekrar başarısız: {result.stderr}")
        
        # Yöntem 3: openssl + usermod (fallback)
        self.logger.info("Alternatif yöntem deneniyor (usermod)...")
        result = self.run_shell(
            f'usermod --password $(openssl passwd -6 "{password}") kiosk',
            check=False
        )
        if result.returncode == 0:
            self.logger.info("Şifre ayarlandı (usermod)")
            return True
        
        self.logger.error(f"Şifre ayarlanamadı! Son hata: {result.stderr}")
        return False
    
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
            
            if not self._set_kiosk_password(kiosk_password):
                return False, "Kiosk şifresi ayarlanamadı"
            
            # =================================================================
            # 2. GRUB Rotation (console için)
            # =================================================================
            grub_rotation = self.get_config('kiosk.grub_rotation', 1)
            self.logger.info(f"GRUB rotation ayarlanıyor: {grub_rotation}")
            if not self.configure_grub({'grub_rotation': grub_rotation}):
                self.logger.warning("GRUB rotation ayarlanamadı")
            
            # =================================================================
            # 3. Touch Matrix - Xorg Config
            # =================================================================
            touch_vendor = self.get_config('kiosk.touch_vendor_id', '222a:0001')
            touch_matrix = self.get_config('kiosk.touch_matrix', '0 1 0 -1 0 1 0 0 1')
            self.logger.info(f"Touch config ayarlanıyor: {touch_vendor}")
            if not self._configure_touch(touch_vendor, touch_matrix):
                self.logger.warning("Touch config ayarlanamadı")
            
            # =================================================================
            # 4. Bilgilendirme
            # =================================================================
            self.logger.info("Ekran rotasyonu ve URL ayarları X restart sonrası uygulanır")
            
            self.logger.info("Kiosk yapılandırması tamamlandı")
            return True, "Kiosk yapılandırıldı (değişiklikler için X restart önerilir)"
            
        except Exception as e:
            self.logger.error(f"Kiosk yapılandırma hatası: {e}")
            return False, str(e)
