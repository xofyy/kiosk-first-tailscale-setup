"""
Kiosk Setup Panel - collector Module
Sistem metrik toplama servisi
"""

import os
import time
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
            collector_dir = "/opt/collector-agent"
            
            # 1. Gerekli paketleri kur
            self.logger.info("collector bağımlılıkları kuruluyor...")
            
            packages = ['git', 'python3-pip', 'prometheus-node-exporter']
            
            if not self.apt_install(packages):
                return False, "collector bağımlılıkları kurulamadı"
            
            # 2. prometheus-node-exporter servisini etkinleştir
            self.logger.info("Node Exporter başlatılıyor...")
            self.systemctl('enable', 'prometheus-node-exporter')
            self.systemctl('start', 'prometheus-node-exporter')
            
            # 3. collector-agent repo'yu klonla
            if os.path.exists(collector_dir):
                self.run_shell(f'rm -rf {collector_dir}')
            
            self.logger.info("collector-agent indiriliyor...")
            self.run_command([
                'git', 'clone',
                'https://github.com/xofyy/collector-agent.git',
                collector_dir
            ])
            
            # 4. pip, setuptools, wheel güncelle (UNKNOWN sorunu için şart)
            self.logger.info("pip, setuptools, wheel güncelleniyor...")
            self.run_shell('pip3 install --upgrade pip setuptools wheel')
            
            # 5. UNKNOWN paketini kaldır (varsa)
            self.run_shell('pip3 uninstall -y UNKNOWN 2>/dev/null || true')
            
            # 6. Build cache temizle
            for cache_dir in ['UNKNOWN.egg-info', 'build']:
                cache_path = f'{collector_dir}/{cache_dir}'
                if os.path.exists(cache_path):
                    self.run_shell(f'rm -rf {cache_path}')
            
            # 7. collector-agent'ı pip ile kur
            self.logger.info("collector-agent paketi kuruluyor...")
            self.run_shell(f'cd {collector_dir} && pip3 install . --no-cache-dir --force-reinstall')
            
            # 8. Config dizini ve dosyası oluştur
            interval = self.get_config('collector.interval', 30)
            
            config_content = f"""# collector-agent Configuration

# Collection interval (seconds)
interval: {interval}

# Node exporter
node_exporter:
  enabled: true
  url: "http://localhost:9100/metrics"
  timeout: 5

# NVIDIA SMI metrics
nvidia_smi:
  enabled: true

# Logging
logging:
  level: INFO
  file: /var/log/collector-agent.log
"""
            os.makedirs('/etc/collector-agent', exist_ok=True)
            self.write_file('/etc/collector-agent/config.yaml', config_content)
            
            # 9. Repo'daki systemd service dosyasını kopyala
            self.logger.info("Systemd service kuruluyor...")
            self.run_shell(f'cp {collector_dir}/systemd/collector-agent.service /etc/systemd/system/')
            
            # 10. Servisi etkinleştir ve başlat
            self.run_command(['systemctl', 'daemon-reload'])
            self.systemctl('enable', 'collector-agent')
            self.systemctl('start', 'collector-agent')
            
            # =================================================================
            # Kurulum Sonrası Doğrulama
            # =================================================================
            time.sleep(2)
            
            result = self.run_command(['systemctl', 'is-active', 'collector-agent'], check=False)
            if result.returncode != 0:
                self.logger.warning("collector-agent servisi başlatılamadı")
                return False, "collector-agent servisi başlatılamadı"
            
            self.logger.info("collector-agent servisi doğrulandı")
            self.logger.info("collector kurulumu tamamlandı")
            return True, "collector-agent ve prometheus-node-exporter kuruldu"
            
        except Exception as e:
            self.logger.error(f"collector kurulum hatası: {e}")
            return False, str(e)
