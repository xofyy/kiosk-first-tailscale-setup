"""
Kiosk Setup Panel - VNC Module
x11vnc uzak masaüstü kurulumu
"""

import os
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class VNCModule(BaseModule):
    name = "vnc"
    display_name = "VNC"
    description = "x11vnc uzak masaüstü erişimi (localhost-only, SSH tunnel ile)"
    order = 7
    dependencies = ["kiosk"]
    
    def install(self) -> Tuple[bool, str]:
        """VNC kurulumu"""
        try:
            kiosk_user = "kiosk"
            kiosk_home = f"/home/{kiosk_user}"
            
            # 1. x11vnc kurulumu
            self.logger.info("x11vnc kuruluyor...")
            
            if not self.apt_install(['x11vnc']):
                return False, "x11vnc kurulamadı"
            
            # 2. VNC şifresi oluştur
            vnc_password = self.get_config('passwords.vnc', '')
            vnc_dir = f"{kiosk_home}/.vnc"
            
            os.makedirs(vnc_dir, exist_ok=True)
            
            if vnc_password:
                self.logger.info("VNC şifresi ayarlanıyor...")
                self.run_shell(f'x11vnc -storepasswd "{vnc_password}" {vnc_dir}/passwd')
            
            # Dizin sahipliği
            self.run_shell(f'chown -R {kiosk_user}:{kiosk_user} {vnc_dir}')
            
            # 3. x11vnc systemd service oluştur
            vnc_port = self.get_config('vnc.port', 5900)
            localhost_only = self.get_config('vnc.localhost_only', True)
            
            listen_arg = '-localhost' if localhost_only else ''
            passwd_arg = f'-rfbauth {vnc_dir}/passwd' if vnc_password else ''
            
            service_content = f"""[Unit]
Description=x11vnc VNC Server
After=display-manager.service network.target

[Service]
Type=simple
User={kiosk_user}
Environment=DISPLAY=:0
ExecStart=/usr/bin/x11vnc -display :0 -forever -shared {listen_arg} -rfbport {vnc_port} {passwd_arg} -noxdamage
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
            self.write_file('/etc/systemd/system/x11vnc.service', service_content)
            
            # 4. Servisi etkinleştir
            self.run_command(['systemctl', 'daemon-reload'])
            self.systemctl('enable', 'x11vnc')
            
            # X11 çalışıyorsa servisi başlat
            try:
                self.systemctl('start', 'x11vnc')
            except Exception:
                self.logger.info("x11vnc servisi X11 başladıktan sonra çalışacak")
            
            message = f"x11vnc kuruldu. Port: {vnc_port}"
            if localhost_only:
                message += " (localhost-only, SSH tunnel ile erişin)"
            
            self.logger.info("VNC kurulumu tamamlandı")
            return True, message
            
        except Exception as e:
            self.logger.error(f"VNC kurulum hatası: {e}")
            return False, str(e)
