"""
Kiosk Setup Panel - Docker Module
Docker Engine, NVIDIA Container Toolkit ve MongoDB kurulumu
"""

import json
import os
import time
from typing import Tuple, Dict, Any
from datetime import datetime

from app.modules import register_module
from app.modules.base import BaseModule
# DIP: Global config import kaldırıldı, self._config kullanılıyor


@register_module
class DockerModule(BaseModule):
    name = "docker"
    display_name = "Docker"
    description = "Docker Engine, NVIDIA Container Toolkit ve MongoDB"
    order = 10
    dependencies = ["vnc"]
    
    SERVICES_FILE = "/etc/nginx/kiosk-services.json"
    NGINX_CONFIG_FILE = "/etc/nginx/sites-available/kiosk-panel"
    
    def install(self) -> Tuple[bool, str]:
        """Docker kurulumu"""
        try:
            compose_path = self.get_config('docker.compose_path', '/srv/docker')
            registry_url = self.get_config('registry.url', 'acolinux.azurecr.io')
            registry_user = self.get_config('registry.username', '')
            registry_pass = self.get_config('registry.password', '')
            
            # 1. Eski Docker paketlerini kaldır
            self.logger.info("Eski Docker paketleri kaldırılıyor...")
            
            old_packages = [
                'docker.io', 'docker-doc', 'docker-compose',
                'docker-compose-v2', 'podman-docker', 'containerd', 'runc'
            ]
            
            for pkg in old_packages:
                self.run_shell(f'apt-get remove -y {pkg} 2>/dev/null || true')
            
            # 2. Docker repo ve GPG key
            self.logger.info("Docker repository ekleniyor...")
            
            # Gerekli paketler
            if not self.apt_install([
                'ca-certificates', 'curl', 'gnupg',
                'python3-pip', 'python3-docker', 'python3-pymongo'
            ]):
                return False, "Docker bağımlılıkları kurulamadı"
            
            # GPG key
            self.run_shell('install -m 0755 -d /etc/apt/keyrings')
            result = self.run_shell(
                'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | '
                'gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes',
                check=False
            )
            if result.returncode != 0:
                return False, f"Docker GPG key indirilemedi: {result.stderr}"
            self.run_shell('chmod a+r /etc/apt/keyrings/docker.gpg')
            
            # Repo ekle
            result = self.run_shell(
                'echo "deb [arch=$(dpkg --print-architecture) '
                'signed-by=/etc/apt/keyrings/docker.gpg] '
                'https://download.docker.com/linux/ubuntu '
                '$(. /etc/os-release && echo $VERSION_CODENAME) stable" | '
                'tee /etc/apt/sources.list.d/docker.list > /dev/null',
                check=False
            )
            if result.returncode != 0:
                return False, f"Docker repo eklenemedi: {result.stderr}"
            
            # 3. Docker paketlerini kur
            self.logger.info("Docker kuruluyor...")
            
            self.run_command(['apt-get', 'update', '-qq'])
            
            docker_packages = [
                'docker-ce',
                'docker-ce-cli',
                'containerd.io',
                'docker-compose-plugin',
                'docker-buildx-plugin'
            ]
            
            if not self.apt_install(docker_packages):
                return False, "Docker paketleri kurulamadı"
            
            # 4. NVIDIA varlık kontrolü
            nvidia_available = self.run_shell('nvidia-smi >/dev/null 2>&1', check=False).returncode == 0
            if nvidia_available:
                self.logger.info("NVIDIA GPU tespit edildi")
            else:
                self.logger.info("NVIDIA GPU bulunamadı, Container Toolkit atlanacak")
            
            # 5. Docker daemon.json yapılandırması (NVIDIA koşullu)
            self.logger.info("Docker yapılandırılıyor...")
            
            if nvidia_available:
                daemon_config = """{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2",
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    }
}
"""
            else:
                daemon_config = """{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2"
}
"""
            if not self.write_file('/etc/docker/daemon.json', daemon_config):
                return False, "Docker daemon.json yazılamadı"
            
            # 6. NVIDIA Container Toolkit (sadece NVIDIA varsa)
            if nvidia_available:
                self.logger.info("NVIDIA Container Toolkit kuruluyor...")
                
                # NVIDIA repo - network hatası olabilir
                result = self.run_shell(
                    'curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | '
                    'gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg --yes',
                    check=False
                )
                if result.returncode != 0:
                    self.logger.warning(f"NVIDIA GPG key indirilemedi: {result.stderr}")
                else:
                    result = self.run_shell(
                        'curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | '
                        'sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" | '
                        'tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null',
                        check=False
                    )
                    if result.returncode != 0:
                        self.logger.warning(f"NVIDIA repo eklenemedi: {result.stderr}")
                    else:
                        self.run_command(['apt-get', 'update', '-qq'])
                        if not self.apt_install(['nvidia-container-toolkit']):
                            self.logger.warning("NVIDIA Container Toolkit kurulamadı")
                        else:
                            # nvidia-ctk yapılandırması
                            self.run_shell('nvidia-ctk runtime configure --runtime=docker || true')
            
            # 7. Docker servisini başlat
            if not self.systemctl('enable', 'docker'):
                self.logger.warning("Docker enable edilemedi")
            if not self.systemctl('restart', 'docker'):
                self.logger.warning("Docker yeniden başlatılamadı")
            
            # 8. Kurulum doğrulaması
            time.sleep(2)
            
            result = self.run_command(['docker', '--version'], check=False)
            if result.returncode != 0:
                return False, "Docker kurulumu doğrulanamadı"
            self.logger.info(f"Docker: {result.stdout.strip()}")
            
            result = self.run_command(['docker', 'compose', 'version'], check=False)
            if result.returncode != 0:
                return False, "Docker Compose kurulumu doğrulanamadı"
            self.logger.info(f"Docker Compose: {result.stdout.strip()}")
            
            self.logger.info("Docker kurulumu doğrulandı")
            
            # 9. Compose dizini oluştur
            os.makedirs(compose_path, exist_ok=True)
            
            # 10. Registry login
            if registry_user and registry_pass:
                self.logger.info(f"Registry login: {registry_url}")
                result = self.run_shell(
                    f'echo "{registry_pass}" | docker login {registry_url} '
                    f'-u {registry_user} --password-stdin',
                    check=False
                )
                if result.returncode != 0:
                    self.logger.warning(f"Registry login başarısız: {result.stderr}")
            
            # 11. docker-compose.yml oluştur
            self.logger.info("docker-compose.yml oluşturuluyor...")
            
            mongodb_tag = self.get_config('mongodb.tag', 'latest')
            mongodb_data_path = self.get_config('mongodb.data_path', '/home/aco/mongo-data')
            
            # MongoDB data dizini
            os.makedirs(mongodb_data_path, exist_ok=True)
            
            compose_content = f"""# Docker Compose Configuration
# Generated by Kiosk Setup Panel

services:
  local_database:
    image: {registry_url}/mongodb:{mongodb_tag}
    container_name: local_database
    network_mode: host
    restart: always
    volumes:
      - {mongodb_data_path}:/data/db
"""
            if not self.write_file(f'{compose_path}/docker-compose.yml', compose_content):
                return False, "docker-compose.yml yazılamadı"
            
            # 12. Docker compose up
            self.logger.info("MongoDB container başlatılıyor...")
            
            result = self.run_shell(f'cd {compose_path} && docker compose up -d', check=False)
            if result.returncode != 0:
                return False, f"Docker compose başlatılamadı: {result.stderr}"
            
            # 12.1 MongoDB hazır olana kadar bekle (60 saniye timeout)
            self.logger.info("MongoDB'nin hazır olması bekleniyor...")
            mongodb_ready = False
            for i in range(60):
                result = self.run_shell(
                    'docker exec local_database mongosh --eval "db.runCommand({ping:1})" 2>/dev/null',
                    check=False
                )
                if result.returncode == 0:
                    self.logger.info("MongoDB hazır")
                    mongodb_ready = True
                    break
                if i % 10 == 0 and i > 0:
                    self.logger.info(f"MongoDB bekleniyor... ({i}/60 saniye)")
                time.sleep(1)
            
            if not mongodb_ready:
                return False, "MongoDB başlatılamadı (60 saniye timeout)"
            
            # 13. Kiosk ID'yi MongoDB'ye kaydet
            self._save_kiosk_id_to_mongodb()
            
            # 14. Mechatronic Controller'ı Nginx'e kaydet
            if not self._register_mechatronic_to_nginx():
                self.logger.warning("Mechatronic nginx kaydı başarısız (kurulum devam ediyor)")
            
            self.logger.info("Docker kurulumu tamamlandı")
            return True, "Docker, NVIDIA Container Toolkit ve MongoDB kuruldu"
            
        except Exception as e:
            self.logger.error(f"Docker kurulum hatası: {e}")
            return False, str(e)
    
    def _save_kiosk_id_to_mongodb(self) -> None:
        """Kiosk ID'yi MongoDB'ye kaydet"""
        client = None
        try:
            import socket
            try:
                from pymongo import MongoClient
            except ImportError:
                self.logger.warning("pymongo bulunamadı, MongoDB kaydı atlanıyor")
                return
            
            kiosk_id = self._config.get_kiosk_id()
            hardware_id = self._config.get_hardware_id()
            
            if not kiosk_id:
                self.logger.warning("Kiosk ID bulunamadı, MongoDB kaydı atlanıyor")
                return
            
            # MongoDB bağlantısı
            client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
            db = client['kiosk']
            collection = db['settings']
            
            # Kayıt oluştur/güncelle
            document = {
                'kiosk_id': kiosk_id,
                'hardware_id': hardware_id,
                'hostname': socket.gethostname(),
                'registered_at': datetime.utcnow()
            }
            
            collection.update_one(
                {'kiosk_id': kiosk_id},
                {'$set': document},
                upsert=True
            )
            
            self.logger.info(f"Kiosk ID MongoDB'ye kaydedildi: {kiosk_id}")
            
        except Exception as e:
            self.logger.warning(f"MongoDB kayıt hatası: {e}")
        finally:
            if client:
                client.close()
    
    def _register_mechatronic_to_nginx(self) -> bool:
        """Mechatronic Controller'ı Nginx config'e ekle"""
        try:
            nginx_port = self.get_config('nginx.port', 8080)
            mech_config = self.get_config('services.mechcontroller', {})
            
            if not mech_config:
                self.logger.warning("Mechatronic Controller config bulunamadı")
                return False
            
            # 1. Services.json'dan mevcut servisleri oku
            services = {}
            if os.path.exists(self.SERVICES_FILE):
                try:
                    with open(self.SERVICES_FILE, 'r') as f:
                        services = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    self.logger.warning(f"Services.json okunamadı: {e}")
                    services = {}
            
            # 2. Mechatronic ekle
            services['mechcontroller'] = {
                "display_name": mech_config.get('display_name', 'Mechatronic Controller'),
                "port": mech_config.get('port', 1234),
                "path": mech_config.get('path', '/mechatronic_controller/'),
                "websocket": mech_config.get('websocket', False),
                "check_type": mech_config.get('check_type', 'port'),
                "check_value": mech_config.get('check_value', 1234)
            }
            
            # 3. Services.json'a kaydet
            with open(self.SERVICES_FILE, 'w') as f:
                json.dump(services, f, indent=2)
            
            # 4. Nginx config'i yeniden oluştur
            self._regenerate_nginx_config(services, nginx_port)
            
            # 5. Nginx test ve reload
            result = self.run_command(['/usr/sbin/nginx', '-t'], check=False)
            if result.returncode != 0:
                self.logger.error(f"Nginx config hatası: {result.stderr}")
                return False
            
            self.systemctl('reload', 'nginx')
            
            self.logger.info("Mechatronic Controller nginx'e kaydedildi")
            return True
            
        except Exception as e:
            self.logger.error(f"Nginx kayıt hatası: {e}")
            return False
    
    def _regenerate_nginx_config(self, services: Dict[str, Any], nginx_port: int) -> None:
        """Nginx config dosyasını servislere göre yeniden oluştur"""
        
        config_content = f"""# Kiosk Panel - Nginx Reverse Proxy
# Auto-generated by Docker module

server {{
    listen {nginx_port};
    server_name localhost;
    add_header X-Content-Type-Options "nosniff" always;
    client_max_body_size 100M;
    proxy_connect_timeout 60;
    proxy_send_timeout 60;
    proxy_read_timeout 60;

"""
        
        for name, service in services.items():
            path = service.get('path', f'/{name}/')
            port = service.get('port', 5000)
            websocket = service.get('websocket', False)
            
            # Root path (panel) için
            if path == "/":
                config_content += f"""    # {service.get('display_name', name)}
    location / {{
        proxy_pass http://127.0.0.1:{port}/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

"""
            elif name == 'cockpit':
                # Cockpit özel yapılandırma
                config_content += f"""    # Cockpit static dosyaları
    location /cockpit/static/ {{
        proxy_pass http://127.0.0.1:{port}/cockpit/cockpit/static/;
        proxy_set_header Host $host:$server_port;
    }}

    # Cockpit ana
    location /cockpit/ {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host:$server_port;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Origin http://localhost:{nginx_port};

        # WebSocket
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;

        # iframe için
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;
    }}

"""
            else:
                # Diğer servisler (Mechatronic dahil)
                config_content += f"""    # {service.get('display_name', name)}
    location {path} {{
        proxy_pass http://127.0.0.1:{port}/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
"""
                if websocket:
                    config_content += """        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
"""
                # Mechatronic için sub_filter (HTML path rewrite)
                if name == 'mechcontroller':
                    config_content += f"""
        # HTML path rewrite
        sub_filter 'src="/' 'src="{path}';
        sub_filter 'href="/' 'href="{path}';
        sub_filter "src='/" "src='{path}";
        sub_filter "href='/" "href='{path}";
        sub_filter_once off;
        sub_filter_types text/html;
        proxy_set_header Accept-Encoding "";
"""
                config_content += "    }\n\n"
                
                # Mechatronic root path endpoints (socket.io ve API)
                if name == 'mechcontroller':
                    config_content += f"""    # Mechatronic socket.io (root path erişimi için)
    location /socket.io/ {{
        proxy_pass http://127.0.0.1:{port}/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }}

    # Mechatronic API endpoint
    location = /ip-config {{
        proxy_pass http://127.0.0.1:{port}/ip-config;
        proxy_set_header Host $host;
    }}

"""
        
        config_content += "}\n"
        
        self.write_file(self.NGINX_CONFIG_FILE, config_content)