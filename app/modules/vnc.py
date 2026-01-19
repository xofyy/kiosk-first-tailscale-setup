"""
Kiosk Setup Panel - VNC Module
x11vnc remote desktop installation
"""

import os
import time
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class VNCModule(BaseModule):
    name = "vnc"
    display_name = "VNC"
    description = "x11vnc remote desktop access (localhost-only, via SSH tunnel)"
    order = 7
    dependencies = ["kiosk"]
    
    def install(self) -> Tuple[bool, str]:
        """VNC installation"""
        try:
            kiosk_user = "kiosk"
            kiosk_home = f"/home/{kiosk_user}"
            
            # 1. x11vnc installation
            self.logger.info("Installing x11vnc...")

            if not self.apt_install(['x11vnc']):
                return False, "Could not install x11vnc"
            
            # 2. Create VNC password
            vnc_password = self.get_config('passwords.vnc', '')
            vnc_dir = f"{kiosk_home}/.vnc"
            
            os.makedirs(vnc_dir, exist_ok=True)
            
            if vnc_password:
                self.logger.info("Setting VNC password...")
                result = self.run_shell(f'x11vnc -storepasswd "{vnc_password}" {vnc_dir}/passwd', check=False)
                if result.returncode != 0:
                    self.logger.warning(f"Could not set VNC password: {result.stderr}")
            else:
                self.logger.warning("VNC password not specified! Security risk.")
            
            # Directory ownership
            result = self.run_shell(f'chown -R {kiosk_user}:{kiosk_user} {vnc_dir}', check=False)
            if result.returncode != 0:
                self.logger.warning(f"Could not set VNC directory ownership: {result.stderr}")
            
            # 3. Create x11vnc systemd service
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
            if not self.write_file('/etc/systemd/system/x11vnc.service', service_content):
                return False, "Could not write x11vnc service file"
            
            # 4. Enable service
            self.run_command(['systemctl', 'daemon-reload'])
            if not self.systemctl('enable', 'x11vnc'):
                self.logger.warning("Could not enable x11vnc")
            
            # Start service if X11 is running
            try:
                self.systemctl('start', 'x11vnc')
            except Exception:
                self.logger.info("x11vnc service will start after X11 is ready")
            
            # =================================================================
            # Post-Installation Verification
            # =================================================================
            time.sleep(2)
            
            # Service check
            result = self.run_command(['systemctl', 'is-active', 'x11vnc'], check=False)
            if result.returncode != 0:
                self.logger.warning("x11vnc service could not start (will start after X11 is ready)")
            else:
                self.logger.info("x11vnc service verified")
            
            # Port check (only if service is active)
            if result.returncode == 0:
                port_result = self.run_shell(f'ss -tlnp | grep :{vnc_port}', check=False)
                if port_result.returncode != 0:
                    self.logger.warning(f"VNC port ({vnc_port}) not open yet")
                else:
                    self.logger.info(f"VNC port ({vnc_port}) verified")
            
            message = f"x11vnc installed. Port: {vnc_port}"
            if localhost_only:
                message += " (localhost-only, access via SSH tunnel)"
            
            self.logger.info("VNC installation completed")
            return True, message

        except Exception as e:
            self.logger.error(f"VNC installation error: {e}")
            return False, str(e)
