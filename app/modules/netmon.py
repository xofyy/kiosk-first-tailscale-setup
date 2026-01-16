"""
Kiosk Setup Panel - netmon Module
Ağ izleme servisi
"""

import os
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class NetmonModule(BaseModule):
    name = "netmon"
    display_name = "netmon"
    description = "Ağ trafiği izleme ve kayıt servisi"
    order = 8
    dependencies = ["vnc"]
    
    def install(self) -> Tuple[bool, str]:
        """netmon kurulumu"""
        try:
            # 1. Gerekli paketleri kur
            self.logger.info("netmon bağımlılıkları kuruluyor...")
            
            if not self.apt_install(['git', 'nethogs', 'python3-pip']):
                return False, "netmon bağımlılıkları kurulamadı"
            
            # 2. netmon repo'yu klonla
            netmon_dir = "/opt/netmon"
            
            if os.path.exists(netmon_dir):
                self.run_shell(f'rm -rf {netmon_dir}')
            
            self.logger.info("netmon indiriliyor...")
            self.run_command([
                'git', 'clone',
                'https://github.com/xofyy/netmon.git',
                netmon_dir
            ])
            
            # 3. Python bağımlılıklarını kur
            self.logger.info("Python bağımlılıkları kuruluyor...")
            
            if os.path.exists(f'{netmon_dir}/requirements.txt'):
                self.run_command([
                    'pip3', 'install', '-r',
                    f'{netmon_dir}/requirements.txt'
                ])
            
            # 4. Config dosyası oluştur
            db_write_interval = self.get_config('netmon.db_write_interval', 300)
            retention_days = self.get_config('netmon.retention_days', 90)
            
            config_content = f"""# netmon Configuration

# Network interfaces to monitor (empty = all)
interfaces: []

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
            self.write_file('/etc/netmon/config.yaml', config_content)
            
            # 5. Data dizini
            os.makedirs('/var/lib/netmon', exist_ok=True)
            
            # 6. Systemd service oluştur
            service_content = f"""[Unit]
Description=Network Monitor Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {netmon_dir}/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
            self.write_file('/etc/systemd/system/netmon.service', service_content)
            
            # 7. Servisi etkinleştir ve başlat
            self.run_command(['systemctl', 'daemon-reload'])
            self.systemctl('enable', 'netmon')
            self.systemctl('start', 'netmon')
            
            self.logger.info("netmon kurulumu tamamlandı")
            return True, "netmon kuruldu ve çalışıyor"
            
        except Exception as e:
            self.logger.error(f"netmon kurulum hatası: {e}")
            return False, str(e)
