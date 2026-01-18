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
            if not self.systemctl('enable', 'prometheus-node-exporter'):
                self.logger.warning("prometheus-node-exporter enable edilemedi")
            if not self.systemctl('start', 'prometheus-node-exporter'):
                self.logger.warning("prometheus-node-exporter başlatılamadı")
            
            # 3. collector-agent repo'yu klonla
            if os.path.exists(collector_dir):
                self.run_shell(f'rm -rf {collector_dir}')
            
            self.logger.info("collector-agent indiriliyor...")
            result = self.run_command([
                'git', 'clone',
                'https://github.com/xofyy/collector-agent.git',
                collector_dir
            ], check=False)
            if result.returncode != 0:
                return False, f"collector-agent repo klonlanamadı: {result.stderr}"
            
            # 4. pip, setuptools, wheel güncelle (UNKNOWN sorunu için şart)
            # NOT: /usr/bin/pip3 kullanıyoruz çünkü panel virtualenv içinde çalışıyor
            self.logger.info("pip, setuptools, wheel güncelleniyor...")
            self.run_shell('/usr/bin/pip3 install --upgrade pip setuptools wheel')
            
            # 5. UNKNOWN paketini kaldır (varsa)
            self.run_shell('/usr/bin/pip3 uninstall -y UNKNOWN 2>/dev/null || true')
            
            # 6. Build cache temizle (tüm egg-info dizinleri dahil)
            self.run_shell(f'rm -rf {collector_dir}/build {collector_dir}/*.egg-info')
            
            # 7. collector-agent'ı pip ile kur
            self.logger.info("collector-agent paketi kuruluyor...")
            result = self.run_shell(f'cd {collector_dir} && /usr/bin/pip3 install --no-cache-dir --force-reinstall .', check=False)
            if result.returncode != 0:
                return False, f"collector-agent paketi kurulamadı: {result.stderr}"
            
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
            if not self.write_file('/etc/collector-agent/config.yaml', config_content):
                return False, "Collector config yazılamadı"
            
            # 9. Repo'daki systemd service dosyasını kopyala
            self.logger.info("Systemd service kuruluyor...")
            result = self.run_shell(f'cp {collector_dir}/systemd/collector-agent.service /etc/systemd/system/', check=False)
            if result.returncode != 0:
                return False, "Systemd service dosyası kopyalanamadı"
            
            # 10. Servisi etkinleştir ve başlat
            self.run_command(['systemctl', 'daemon-reload'])
            if not self.systemctl('enable', 'collector-agent'):
                self.logger.warning("collector-agent enable edilemedi")
            if not self.systemctl('start', 'collector-agent'):
                self.logger.warning("collector-agent başlatılamadı")
            
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
