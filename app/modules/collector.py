"""
Kiosk Setup Panel - collector Module
Sistem metrik toplama servisi
"""

import os
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class CollectorModule(BaseModule):
    name = "collector"
    display_name = "collector"
    description = "Sistem metrikleri toplama servisi (Prometheus node_exporter)"
    order = 9
    dependencies = ["vnc"]
    
    def install(self) -> Tuple[bool, str]:
        """collector kurulumu"""
        try:
            # 1. Gerekli paketleri kur
            self.logger.info("collector bağımlılıkları kuruluyor...")
            
            packages = ['git', 'python3-pip', 'prometheus-node-exporter']
            
            if not self.apt_install(packages):
                return False, "collector bağımlılıkları kurulamadı"
            
            # 2. collector-agent repo'yu klonla
            collector_dir = "/opt/collector-agent"
            
            if os.path.exists(collector_dir):
                self.run_shell(f'rm -rf {collector_dir}')
            
            self.logger.info("collector-agent indiriliyor...")
            self.run_command([
                'git', 'clone',
                'https://github.com/xofyy/collector-agent.git',
                collector_dir
            ])
            
            # 3. Python bağımlılıklarını kur
            self.logger.info("Python bağımlılıkları kuruluyor...")
            
            if os.path.exists(f'{collector_dir}/requirements.txt'):
                self.run_command([
                    'pip3', 'install', '-r',
                    f'{collector_dir}/requirements.txt'
                ])
            
            # 4. Config dosyası oluştur
            interval = self.get_config('collector.interval', 30)
            
            config_content = f"""# collector-agent Configuration

# Collection interval (seconds)
interval: {interval}

# Node exporter
node_exporter:
  enabled: true
  port: 9100

# NVIDIA SMI metrics
nvidia_smi:
  enabled: true

# System metrics
system:
  cpu: true
  memory: true
  disk: true
  network: true

# Output
output:
  type: prometheus
  port: 9101
"""
            os.makedirs('/etc/collector-agent', exist_ok=True)
            self.write_file('/etc/collector-agent/config.yaml', config_content)
            
            # 5. prometheus-node-exporter servisini etkinleştir
            self.systemctl('enable', 'prometheus-node-exporter')
            self.systemctl('start', 'prometheus-node-exporter')
            
            # 6. collector-agent systemd service
            service_content = f"""[Unit]
Description=Collector Agent Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {collector_dir}/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
            self.write_file('/etc/systemd/system/collector-agent.service', service_content)
            
            # 7. Servisi etkinleştir ve başlat
            self.run_command(['systemctl', 'daemon-reload'])
            self.systemctl('enable', 'collector-agent')
            self.systemctl('start', 'collector-agent')
            
            self.logger.info("collector kurulumu tamamlandı")
            return True, "collector-agent ve prometheus-node-exporter kuruldu"
            
        except Exception as e:
            self.logger.error(f"collector kurulum hatası: {e}")
            return False, str(e)
