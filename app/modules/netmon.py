"""
Kiosk Setup Panel - netmon Module
Ağ izleme servisi
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
            
            # 3. pip, setuptools, wheel güncelle (UNKNOWN sorunu için şart)
            # NOT: /usr/bin/pip3 kullanıyoruz çünkü panel virtualenv içinde çalışıyor
            self.logger.info("pip, setuptools, wheel güncelleniyor...")
            self.run_shell('/usr/bin/pip3 install --upgrade pip setuptools wheel')
            
            # 4. UNKNOWN paketini kaldır (varsa)
            self.run_shell('/usr/bin/pip3 uninstall -y UNKNOWN 2>/dev/null || true')
            
            # 5. Build cache temizle (tüm egg-info dizinleri dahil)
            self.run_shell(f'rm -rf {netmon_dir}/build {netmon_dir}/*.egg-info')
            
            # 6. netmon'u pip ile kur (CLI aracını oluşturur: /usr/local/bin/netmon)
            self.logger.info("netmon paketi kuruluyor...")
            self.run_shell(f'cd {netmon_dir} && /usr/bin/pip3 install --no-cache-dir --force-reinstall .')
            
            # 7. Config dosyası oluştur
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
            self.write_file('/etc/netmon/config.yaml', config_content)
            
            # 8. Data dizini
            os.makedirs('/var/lib/netmon', exist_ok=True)
            
            # 9. Repo'daki systemd service dosyasını kopyala
            self.logger.info("Systemd service kuruluyor...")
            self.run_shell(f'cp {netmon_dir}/systemd/netmon.service /etc/systemd/system/')
            
            # 10. Servisi etkinleştir ve başlat
            self.run_command(['systemctl', 'daemon-reload'])
            self.systemctl('enable', 'netmon')
            self.systemctl('start', 'netmon')
            
            # =================================================================
            # Kurulum Sonrası Doğrulama
            # =================================================================
            time.sleep(2)
            
            result = self.run_command(['systemctl', 'is-active', 'netmon'], check=False)
            if result.returncode != 0:
                self.logger.warning("netmon servisi başlatılamadı")
                return False, "netmon servisi başlatılamadı"
            
            self.logger.info("netmon servisi doğrulandı")
            self.logger.info("netmon kurulumu tamamlandı")
            return True, "netmon kuruldu ve çalışıyor"
            
        except Exception as e:
            self.logger.error(f"netmon kurulum hatası: {e}")
            return False, str(e)
