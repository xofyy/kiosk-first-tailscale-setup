"""
Kiosk Setup Panel - Cockpit Module
Web tabanlı sunucu yönetim paneli

Özellikler:
- Cockpit kurulumu
- Nginx reverse proxy ile entegrasyon (/cockpit/ path)
- Polkit kuralları (kiosk kullanıcı izinleri)
"""

import json
import os
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class CockpitModule(BaseModule):
    name = "cockpit"
    display_name = "Cockpit"
    description = "Web tabanlı sunucu yönetim paneli"
    order = 5
    dependencies = ["nginx"]
    
    def _register_to_nginx(self) -> bool:
        """Cockpit'i nginx servis registry'sine kaydet"""
        try:
            services_file = "/etc/nginx/kiosk-services.json"
            
            # Mevcut servisleri oku
            services = {}
            if os.path.exists(services_file):
                with open(services_file, 'r') as f:
                    services = json.load(f)
            
            # Cockpit ekle
            cockpit_port = self.get_config('cockpit.port', 9090)
            services['cockpit'] = {
                "display_name": "Cockpit",
                "port": cockpit_port,
                "path": "/cockpit/",
                "websocket": True,
                "check_type": "systemd",
                "check_value": "cockpit.socket"
            }
            
            # Kaydet
            with open(services_file, 'w') as f:
                json.dump(services, f, indent=2)
            
            # Nginx config'i yeniden oluştur
            from app.modules.nginx import NginxModule
            nginx = NginxModule(self.config)
            nginx._generate_config()
            nginx._reload_nginx()
            
            self.logger.info("Cockpit nginx'e kaydedildi")
            return True
            
        except Exception as e:
            self.logger.error(f"Nginx kayıt hatası: {e}")
            return False
    
    def install(self) -> Tuple[bool, str]:
        """Cockpit kurulumu"""
        try:
            cockpit_port = self.get_config('cockpit.port', 9090)
            nginx_port = self.get_config('nginx.port', 8080)
            
            # =================================================================
            # 1. Cockpit Paketleri
            # =================================================================
            self.logger.info("Cockpit kuruluyor...")
            
            packages = [
                'cockpit',
                'cockpit-system',
                'cockpit-networkmanager',
                'cockpit-storaged',
                'cockpit-packagekit'
            ]
            
            if not self.apt_install(packages):
                return False, "Cockpit paketleri kurulamadı"
            
            # =================================================================
            # 2. Cockpit Yapılandırması (UrlRoot ve Origins)
            # =================================================================
            self.logger.info("Cockpit yapılandırılıyor...")
            
            cockpit_conf = f"""[WebService]
# Nginx reverse proxy arkasında çalışacak
UrlRoot=/cockpit/
Origins = http://localhost:{nginx_port} https://localhost:{nginx_port}
AllowUnencrypted = true

[Session]
IdleTimeout = 0
"""
            
            os.makedirs('/etc/cockpit', exist_ok=True)
            self.write_file('/etc/cockpit/cockpit.conf', cockpit_conf)
            
            # =================================================================
            # 3. Cockpit Socket Etkinleştir
            # =================================================================
            self.systemctl('enable', 'cockpit.socket')
            self.systemctl('start', 'cockpit.socket')
            
            # =================================================================
            # 4. Polkit Kuralları
            # =================================================================
            self.logger.info("Polkit kuralları oluşturuluyor...")
            
            polkit_content = """// NetworkManager izinleri
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager") == 0 &&
        subject.user == "kiosk") {
        return polkit.Result.YES;
    }
});

// PackageKit izinleri (sınırlı)
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.packagekit") == 0 &&
        subject.user == "kiosk") {
        // Sadece görüntüleme, kurulum değil
        if (action.id == "org.freedesktop.packagekit.system-sources-refresh" ||
            action.id == "org.freedesktop.packagekit.package-info") {
            return polkit.Result.YES;
        }
    }
});
"""
            self.write_file('/etc/polkit-1/rules.d/50-kiosk-network.rules', polkit_content)
            
            # =================================================================
            # 5. Nginx'e Kaydet
            # =================================================================
            self.logger.info("Nginx'e kaydediliyor...")
            self._register_to_nginx()
            
            # =================================================================
            # 6. Doğrulama
            # =================================================================
            import time
            time.sleep(2)
            
            result = self.run_command(['systemctl', 'is-active', 'cockpit.socket'], check=False)
            if result.returncode != 0:
                self.logger.warning("Cockpit socket aktif değil, yeniden başlatılıyor...")
                self.systemctl('restart', 'cockpit.socket')
            
            self.logger.info("Cockpit kurulumu tamamlandı")
            return True, f"Cockpit kuruldu. Erişim: Servisler sekmesinden"
            
        except Exception as e:
            self.logger.error(f"Cockpit kurulum hatası: {e}")
            return False, str(e)
