"""
Kiosk Setup Panel - Docker Module
Docker Engine, NVIDIA Container Toolkit ve MongoDB kurulumu
"""

import os
import time
from typing import Tuple
from datetime import datetime

from app.modules import register_module
from app.modules.base import BaseModule
from app.config import config


@register_module
class DockerModule(BaseModule):
    name = "docker"
    display_name = "Docker"
    description = "Docker Engine, NVIDIA Container Toolkit ve MongoDB"
    order = 10
    dependencies = ["vnc"]
    
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
            self.apt_install([
                'ca-certificates', 'curl', 'gnupg',
                'python3-pip', 'python3-docker', 'python3-pymongo'
            ])
            
            # GPG key
            self.run_shell('install -m 0755 -d /etc/apt/keyrings')
            self.run_shell(
                'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | '
                'gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes'
            )
            self.run_shell('chmod a+r /etc/apt/keyrings/docker.gpg')
            
            # Repo ekle
            self.run_shell(
                'echo "deb [arch=$(dpkg --print-architecture) '
                'signed-by=/etc/apt/keyrings/docker.gpg] '
                'https://download.docker.com/linux/ubuntu '
                '$(. /etc/os-release && echo $VERSION_CODENAME) stable" | '
                'tee /etc/apt/sources.list.d/docker.list > /dev/null'
            )
            
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
            self.write_file('/etc/docker/daemon.json', daemon_config)
            
            # 6. NVIDIA Container Toolkit (sadece NVIDIA varsa)
            if nvidia_available:
                self.logger.info("NVIDIA Container Toolkit kuruluyor...")
                
                # NVIDIA repo
                self.run_shell(
                    'curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | '
                    'gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg --yes'
                )
                
                self.run_shell(
                    'curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | '
                    'sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" | '
                    'tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null'
                )
                
                self.run_command(['apt-get', 'update', '-qq'])
                self.apt_install(['nvidia-container-toolkit'])
                
                # nvidia-ctk yapılandırması
                self.run_shell('nvidia-ctk runtime configure --runtime=docker || true')
            
            # 7. Docker servisini başlat
            self.systemctl('enable', 'docker')
            self.systemctl('restart', 'docker')
            
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
                self.run_shell(
                    f'echo "{registry_pass}" | docker login {registry_url} '
                    f'-u {registry_user} --password-stdin'
                )
            
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
            self.write_file(f'{compose_path}/docker-compose.yml', compose_content)
            
            # 12. Docker compose up
            self.logger.info("MongoDB container başlatılıyor...")
            
            self.run_shell(f'cd {compose_path} && docker compose up -d')
            
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
            
            self.logger.info("Docker kurulumu tamamlandı")
            return True, "Docker, NVIDIA Container Toolkit ve MongoDB kuruldu"
            
        except Exception as e:
            self.logger.error(f"Docker kurulum hatası: {e}")
            return False, str(e)
    
    def _save_kiosk_id_to_mongodb(self) -> None:
        """Kiosk ID'yi MongoDB'ye kaydet"""
        try:
            import socket
            try:
                from pymongo import MongoClient
            except ImportError:
                self.logger.warning("pymongo bulunamadı, MongoDB kaydı atlanıyor")
                return
            
            kiosk_id = config.get_kiosk_id()
            hardware_id = config.get_hardware_id()
            
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
            
            client.close()
            self.logger.info(f"Kiosk ID MongoDB'ye kaydedildi: {kiosk_id}")
            
        except Exception as e:
            self.logger.warning(f"MongoDB kayıt hatası: {e}")
