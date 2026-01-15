"""
Kiosk Setup Panel - Kiosk Module
Kiosk ekran yapılandırması
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
    order = 4
    dependencies = ["network"]
    
    def install(self) -> Tuple[bool, str]:
        """Kiosk yapılandırması"""
        try:
            kiosk_user = "kiosk"
            kiosk_home = f"/home/{kiosk_user}"
            
            # 1. Kiosk kullanıcı şifresi
            kiosk_password = self.get_config('passwords.kiosk', '')
            
            if kiosk_password:
                self.logger.info("Kiosk kullanıcı şifresi ayarlanıyor...")
                self.run_shell(f'echo "{kiosk_user}:{kiosk_password}" | chpasswd')
            
            # 2. Display init script yapılandırması
            self.logger.info("Display yapılandırması ayarlanıyor...")
            
            rotation = self.get_config('kiosk.rotation', 'right')
            
            # xrandr rotation mapping
            rotation_map = {
                'normal': 'normal',
                'right': 'right',
                'left': 'left',
                'inverted': 'inverted'
            }
            xrandr_rotation = rotation_map.get(rotation, 'normal')
            
            display_init_content = f"""#!/bin/bash
# Kiosk Display Init Script

# Ekran koruyucu devre dışı
xset s off
xset -dpms
xset s noblank

# Ekran rotasyonu
xrandr --output $(xrandr | grep ' connected' | head -1 | cut -d' ' -f1) --rotate {xrandr_rotation}

# Touch kalibrasyon (gerekirse)
# xinput set-prop "device" "Coordinate Transformation Matrix" 0 1 0 -1 0 1 0 0 1
"""
            self.write_file('/usr/local/bin/display-init.sh', display_init_content, mode=0o755)
            
            # 3. Touch rotasyon yapılandırması
            touch_vendor = self.get_config('kiosk.touch_vendor_id', '222a:0001')
            touch_matrix = self.get_config('kiosk.touch_matrix', '0 1 0 -1 0 1 0 0 1')
            
            touch_conf = f"""# Touch screen rotation
Section "InputClass"
    Identifier "Touchscreen rotation"
    MatchUSBID "{touch_vendor}"
    Option "TransformationMatrix" "{touch_matrix}"
EndSection
"""
            self.write_file('/etc/X11/xorg.conf.d/99-touch-rotation.conf', touch_conf)
            
            # 4. GRUB rotation (console için)
            grub_rotation = self.get_config('kiosk.grub_rotation', 1)
            
            grub_file = '/etc/default/grub'
            try:
                with open(grub_file, 'r') as f:
                    grub_content = f.read()
                
                # fbcon=rotate ekle
                if f'fbcon=rotate:{grub_rotation}' not in grub_content:
                    grub_content = grub_content.replace(
                        'GRUB_CMDLINE_LINUX_DEFAULT="',
                        f'GRUB_CMDLINE_LINUX_DEFAULT="fbcon=rotate:{grub_rotation} '
                    )
                    
                    with open(grub_file, 'w') as f:
                        f.write(grub_content)
                    
                    self.run_command(['update-grub'])
            except Exception as e:
                self.logger.warning(f"GRUB güncelleme hatası: {e}")
            
            # 5. Chromium kiosk URL yapılandırması
            kiosk_url = self.get_config('kiosk.url', 'http://localhost:3000')
            
            chromium_kiosk_content = f"""#!/bin/bash
# Chromium Kiosk Mode

URL="{kiosk_url}"

# Chromium başlat
exec chromium-browser \\
    --kiosk \\
    --noerrdialogs \\
    --disable-infobars \\
    --disable-session-crashed-bubble \\
    --disable-restore-session-state \\
    --disable-features=TranslateUI \\
    --check-for-update-interval=31536000 \\
    --no-first-run \\
    --start-fullscreen \\
    --window-size=1920,1080 \\
    --window-position=0,0 \\
    "$URL"
"""
            self.write_file('/usr/local/bin/chromium-kiosk.sh', chromium_kiosk_content, mode=0o755)
            
            self.logger.info("Kiosk yapılandırması tamamlandı")
            return True, "Kiosk yapılandırıldı"
            
        except Exception as e:
            self.logger.error(f"Kiosk yapılandırma hatası: {e}")
            return False, str(e)
