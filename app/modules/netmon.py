"""
Kiosk Setup Panel - netmon Module
Network monitoring service
"""

import os
import time
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class NetmonModule(BaseModule):
    name = "netmon"
    display_name = "netmon"
    description = "Network traffic monitoring and logging service"
    order = 8
    dependencies = ["vnc"]
    
    def install(self) -> Tuple[bool, str]:
        """netmon installation"""
        try:
            # 1. Install required packages
            self.logger.info("Installing netmon dependencies...")

            if not self.apt_install(['git', 'nethogs', 'python3-pip']):
                return False, "Could not install netmon dependencies"
            
            # 2. Clone netmon repo
            netmon_dir = "/opt/netmon"
            
            if os.path.exists(netmon_dir):
                self.run_shell(f'rm -rf {netmon_dir}')
            
            self.logger.info("Downloading netmon...")
            result = self.run_command([
                'git', 'clone',
                'https://github.com/xofyy/netmon.git',
                netmon_dir
            ], check=False)
            if result.returncode != 0:
                return False, f"Could not clone netmon repo: {result.stderr}"
            
            # 3. Update pip, setuptools, wheel (required for UNKNOWN issue)
            # NOTE: Using /usr/bin/pip3 because panel runs in virtualenv
            self.logger.info("Updating pip, setuptools, wheel...")
            self.run_shell('/usr/bin/pip3 install --upgrade pip setuptools wheel')
            
            # 4. Remove UNKNOWN package (if exists)
            self.run_shell('/usr/bin/pip3 uninstall -y UNKNOWN 2>/dev/null || true')
            
            # 5. Clean build cache (including all egg-info directories)
            self.run_shell(f'rm -rf {netmon_dir}/build {netmon_dir}/*.egg-info')
            
            # 6. Install netmon with pip (creates CLI tool: /usr/local/bin/netmon)
            self.logger.info("Installing netmon package...")
            result = self.run_shell(f'cd {netmon_dir} && /usr/bin/pip3 install --no-cache-dir --force-reinstall .', check=False)
            if result.returncode != 0:
                return False, f"Could not install netmon package: {result.stderr}"
            
            # 7. Create config file
            db_write_interval = self.get_config('netmon.db_write_interval', 300)
            retention_days = self.get_config('netmon.retention_days', 90)
            
            config_content = f"""# netmon Configuration

# Database write interval (seconds)
db_write_interval: {db_write_interval}

# Data retention period (days)
data_retention_days: {retention_days}

# Log level
log_level: INFO

# Database path
database_path: /var/lib/netmon/data.db
"""
            os.makedirs('/etc/netmon', exist_ok=True)
            if not self.write_file('/etc/netmon/config.yaml', config_content):
                return False, "Could not write netmon config"
            
            # 8. Data directory
            os.makedirs('/var/lib/netmon', exist_ok=True)
            
            # 9. Copy systemd service file from repo
            self.logger.info("Installing Systemd service...")
            result = self.run_shell(f'cp {netmon_dir}/systemd/netmon.service /etc/systemd/system/', check=False)
            if result.returncode != 0:
                return False, "Could not copy Systemd service file"
            
            # 10. Enable and start service
            self.run_command(['systemctl', 'daemon-reload'])
            if not self.systemctl('enable', 'netmon'):
                self.logger.warning("Could not enable netmon")
            if not self.systemctl('start', 'netmon'):
                self.logger.warning("Could not start netmon")
            
            # =================================================================
            # Post-Installation Verification
            # =================================================================
            time.sleep(2)
            
            result = self.run_command(['systemctl', 'is-active', 'netmon'], check=False)
            if result.returncode != 0:
                self.logger.warning("Could not start netmon service")
                return False, "Could not start netmon service"

            self.logger.info("netmon service verified")
            self.logger.info("netmon installation completed")
            return True, "netmon installed and running"

        except Exception as e:
            self.logger.error(f"netmon installation error: {e}")
            return False, str(e)
