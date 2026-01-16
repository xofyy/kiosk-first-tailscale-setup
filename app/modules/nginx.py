"""
Kiosk Setup Panel - Nginx Module
Reverse proxy - tüm servisleri tek origin altında toplar

Özellikler:
- Nginx kurulumu ve yapılandırması
- Servis registry (diğer modüller servis kaydeder)
- Dinamik config üretimi
- WebSocket desteği (Cockpit için)
"""

import json
import os
from typing import Dict, Tuple, Any

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class NginxModule(BaseModule):
    name = "nginx"
    display_name = "Nginx"
    description = "Reverse proxy - servisleri tek noktadan sunar"
    order = 4
    dependencies = ["network"]
    
    # Sabit yollar
    NGINX_CONF_PATH = "/etc/nginx/sites-available/kiosk-panel"
    NGINX_ENABLED_PATH = "/etc/nginx/sites-enabled/kiosk-panel"
    SERVICES_FILE = "/etc/nginx/kiosk-services.json"
    
    def _get_nginx_port(self) -> int:
        """Nginx'in dinleyeceği port"""
        return self.get_config('nginx.port', 8080)
    
    def _get_panel_port(self) -> int:
        """Panel (Gunicorn) portu"""
        return self.get_config('nginx.panel_port', 5000)
    
    def _load_services(self) -> Dict[str, Any]:
        """Kayıtlı servisleri yükle"""
        if os.path.exists(self.SERVICES_FILE):
            try:
                with open(self.SERVICES_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Varsayılan servisler (panel her zaman var)
        return {
            "panel": {
                "display_name": "Panel",
                "port": self._get_panel_port(),
                "path": "/",
                "websocket": False,
                "internal": True  # UI'da gösterme
            }
        }
    
    def _save_services(self, services: Dict[str, Any]) -> None:
        """Servisleri kaydet"""
        os.makedirs(os.path.dirname(self.SERVICES_FILE), exist_ok=True)
        with open(self.SERVICES_FILE, 'w') as f:
            json.dump(services, f, indent=2)
    
    def register_service(self, name: str, port: int, path: str, 
                         display_name: str = None, websocket: bool = False) -> bool:
        """
        Nginx'e servis kaydet
        
        Args:
            name: Servis adı (benzersiz)
            port: Servisin dinlediği port
            path: URL path (örn: /cockpit/)
            display_name: Görüntüleme adı
            websocket: WebSocket desteği gerekli mi?
        
        Returns:
            bool: Başarılı mı?
        """
        try:
            services = self._load_services()
            
            services[name] = {
                "display_name": display_name or name.title(),
                "port": port,
                "path": path,
                "websocket": websocket
            }
            
            self._save_services(services)
            self._generate_config()
            self._reload_nginx()
            
            self.logger.info(f"Servis kaydedildi: {name} -> {path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Servis kayıt hatası: {e}")
            return False
    
    def unregister_service(self, name: str) -> bool:
        """Servisi kaldır"""
        try:
            services = self._load_services()
            
            if name in services and name != "panel":
                del services[name]
                self._save_services(services)
                self._generate_config()
                self._reload_nginx()
                
                self.logger.info(f"Servis kaldırıldı: {name}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Servis kaldırma hatası: {e}")
            return False
    
    def _generate_config(self) -> None:
        """Nginx config dosyasını oluştur"""
        services = self._load_services()
        nginx_port = self._get_nginx_port()
        
        # Config header
        config = f"""# Kiosk Panel - Nginx Reverse Proxy
# Auto-generated - Do not edit manually

server {{
    listen {nginx_port};
    server_name localhost;
    
    # Güvenlik headers
    add_header X-Content-Type-Options "nosniff" always;
    
    # Client body size (upload için)
    client_max_body_size 100M;
    
    # Proxy timeout
    proxy_connect_timeout 60;
    proxy_send_timeout 60;
    proxy_read_timeout 60;
    
"""
        
        # Her servis için location bloğu
        for name, service in services.items():
            path = service['path']
            port = service['port']
            websocket = service.get('websocket', False)
            
            config += f"""    # {service.get('display_name', name)}
    location {path} {{
        proxy_pass http://127.0.0.1:{port}/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
"""
            
            if websocket:
                config += """        
        # WebSocket desteği
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
"""
            
            config += "    }\n\n"
        
        # Config footer
        config += "}\n"
        
        # Dosyaya yaz
        self.write_file(self.NGINX_CONF_PATH, config)
    
    def _reload_nginx(self) -> bool:
        """Nginx'i reload et"""
        result = self.run_command(['nginx', '-t'], check=False)
        if result.returncode != 0:
            self.logger.error(f"Nginx config hatası: {result.stderr}")
            return False
        
        self.systemctl('reload', 'nginx')
        return True
    
    def _is_nginx_installed(self) -> bool:
        """Nginx kurulu mu?"""
        result = self.run_shell('dpkg -l | grep -q "ii  nginx "', check=False)
        return result.returncode == 0
    
    def install(self) -> Tuple[bool, str]:
        """
        Nginx kurulumu ve yapılandırması
        
        Akış:
        1. Nginx paketini kur
        2. Default site'ı kaldır
        3. Servisler dosyasını oluştur (panel ile)
        4. Nginx config oluştur
        5. Site'ı etkinleştir
        6. Nginx'i başlat
        """
        try:
            # =================================================================
            # 1. Nginx Kurulumu
            # =================================================================
            if not self._is_nginx_installed():
                self.logger.info("Nginx kuruluyor...")
                if not self.apt_install(['nginx']):
                    return False, "Nginx kurulamadı"
            else:
                self.logger.info("Nginx zaten kurulu")
            
            # =================================================================
            # 2. Default Site'ı Kaldır
            # =================================================================
            default_site = "/etc/nginx/sites-enabled/default"
            if os.path.exists(default_site):
                os.remove(default_site)
                self.logger.info("Default nginx site kaldırıldı")
            
            # =================================================================
            # 3. Servisler Dosyası
            # =================================================================
            self.logger.info("Servisler kaydı oluşturuluyor...")
            
            # Panel servisi (her zaman var)
            services = {
                "panel": {
                    "display_name": "Panel",
                    "port": self._get_panel_port(),
                    "path": "/",
                    "websocket": False,
                    "internal": True
                }
            }
            
            # Config'den tanımlı servisleri ekle
            configured_services = self.get_config('services', {})
            for name, svc_config in configured_services.items():
                if name not in services:
                    services[name] = {
                        "display_name": svc_config.get('display_name', name.title()),
                        "port": svc_config.get('port', 0),
                        "path": svc_config.get('path', f'/{name}/'),
                        "websocket": svc_config.get('websocket', False),
                        "check_type": svc_config.get('check_type'),
                        "check_value": svc_config.get('check_value')
                    }
            
            self._save_services(services)
            
            # =================================================================
            # 4. Nginx Config Oluştur
            # =================================================================
            self.logger.info("Nginx yapılandırması oluşturuluyor...")
            self._generate_config()
            
            # =================================================================
            # 5. Site'ı Etkinleştir
            # =================================================================
            if not os.path.exists(self.NGINX_ENABLED_PATH):
                os.symlink(self.NGINX_CONF_PATH, self.NGINX_ENABLED_PATH)
                self.logger.info("Nginx site etkinleştirildi")
            
            # =================================================================
            # 6. Nginx'i Başlat
            # =================================================================
            self.logger.info("Nginx başlatılıyor...")
            
            # Config test
            result = self.run_command(['nginx', '-t'], check=False)
            if result.returncode != 0:
                self.logger.error(f"Nginx config hatası: {result.stderr}")
                return False, f"Nginx config hatası: {result.stderr}"
            
            self.systemctl('enable', 'nginx')
            self.systemctl('restart', 'nginx')
            
            # =================================================================
            # 7. Doğrulama
            # =================================================================
            import time
            time.sleep(2)
            
            result = self.run_command(['systemctl', 'is-active', 'nginx'], check=False)
            if result.returncode != 0:
                return False, "Nginx başlatılamadı"
            
            nginx_port = self._get_nginx_port()
            self.logger.info(f"Nginx kurulumu tamamlandı (port: {nginx_port})")
            return True, f"Nginx kuruldu ve çalışıyor (:{nginx_port})"
            
        except Exception as e:
            self.logger.error(f"Nginx kurulum hatası: {e}")
            return False, str(e)
