"""
ACO Maintenance Panel - Docker Module
Docker Engine, NVIDIA Container Toolkit and MongoDB installation
"""

import json
import os
import time
from typing import Tuple, Dict, Any
from datetime import datetime

from app.modules import register_module
from app.modules.base import BaseModule
# DIP: Global config import removed, using self._config


@register_module
class DockerModule(BaseModule):
    name = "docker"
    display_name = "Docker"
    description = "Docker Engine, NVIDIA Container Toolkit ve MongoDB"
    order = 10
    dependencies = ["vnc"]
    
    SERVICES_FILE = "/etc/nginx/aco-services.json"
    NGINX_CONFIG_FILE = "/etc/nginx/sites-available/aco-panel"
    
    def install(self) -> Tuple[bool, str]:
        """Docker installation"""
        try:
            compose_path = self.get_config('docker.compose_path', '/srv/docker')
            registry_url = self.get_config('registry.url', 'acolinux.azurecr.io')
            registry_user = self.get_config('registry.username', '')
            registry_pass = self.get_config('registry.password', '')
            
            # 1. Remove old Docker packages
            self.logger.info("Removing old Docker packages...")
            
            old_packages = [
                'docker.io', 'docker-doc', 'docker-compose',
                'docker-compose-v2', 'podman-docker', 'containerd', 'runc'
            ]
            
            for pkg in old_packages:
                self.run_shell(f'apt-get remove -y {pkg} 2>/dev/null || true')
            
            # 2. Docker repo and GPG key
            self.logger.info("Adding Docker repository...")
            
            # Required packages
            if not self.apt_install([
                'ca-certificates', 'curl', 'gnupg',
                'python3-pip', 'python3-docker', 'python3-pymongo'
            ]):
                return False, "Could not install Docker dependencies"
            
            # GPG key
            self.run_shell('install -m 0755 -d /etc/apt/keyrings')
            result = self.run_shell(
                'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | '
                'gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes',
                check=False
            )
            if result.returncode != 0:
                return False, f"Could not download Docker GPG key: {result.stderr}"
            self.run_shell('chmod a+r /etc/apt/keyrings/docker.gpg')
            
            # Add repo
            result = self.run_shell(
                'echo "deb [arch=$(dpkg --print-architecture) '
                'signed-by=/etc/apt/keyrings/docker.gpg] '
                'https://download.docker.com/linux/ubuntu '
                '$(. /etc/os-release && echo $VERSION_CODENAME) stable" | '
                'tee /etc/apt/sources.list.d/docker.list > /dev/null',
                check=False
            )
            if result.returncode != 0:
                return False, f"Could not add Docker repo: {result.stderr}"
            
            # 3. Install Docker packages
            self.logger.info("Installing Docker...")
            
            self.run_command(['apt-get', 'update', '-qq'])
            
            docker_packages = [
                'docker-ce',
                'docker-ce-cli',
                'containerd.io',
                'docker-compose-plugin',
                'docker-buildx-plugin'
            ]
            
            if not self.apt_install(docker_packages):
                return False, "Could not install Docker packages"
            
            # 4. NVIDIA availability check
            nvidia_available = self.run_shell('nvidia-smi >/dev/null 2>&1', check=False).returncode == 0
            if nvidia_available:
                self.logger.info("NVIDIA GPU detected")
            else:
                self.logger.info("NVIDIA GPU not found, Container Toolkit will be skipped")
            
            # 5. Docker daemon.json configuration (NVIDIA conditional)
            self.logger.info("Configuring Docker...")
            
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
                return False, "Could not write Docker daemon.json"
            
            # 6. NVIDIA Container Toolkit (only if NVIDIA present)
            if nvidia_available:
                self.logger.info("Installing NVIDIA Container Toolkit...")

                # NVIDIA repo - may have network error
                result = self.run_shell(
                    'curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | '
                    'gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg --yes',
                    check=False
                )
                if result.returncode != 0:
                    self.logger.warning(f"Could not download NVIDIA GPG key: {result.stderr}")
                else:
                    result = self.run_shell(
                        'curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | '
                        'sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" | '
                        'tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null',
                        check=False
                    )
                    if result.returncode != 0:
                        self.logger.warning(f"Could not add NVIDIA repo: {result.stderr}")
                    else:
                        self.run_command(['apt-get', 'update', '-qq'])
                        if not self.apt_install(['nvidia-container-toolkit']):
                            self.logger.warning("Could not install NVIDIA Container Toolkit")
                        else:
                            # nvidia-ctk configuration
                            self.run_shell('nvidia-ctk runtime configure --runtime=docker || true')
            
            # 7. Start Docker service
            if not self.systemctl('enable', 'docker'):
                self.logger.warning("Could not enable Docker")
            if not self.systemctl('restart', 'docker'):
                self.logger.warning("Could not restart Docker")
            
            # 8. Installation verification
            time.sleep(2)
            
            result = self.run_command(['docker', '--version'], check=False)
            if result.returncode != 0:
                return False, "Could not verify Docker installation"
            self.logger.info(f"Docker: {result.stdout.strip()}")
            
            result = self.run_command(['docker', 'compose', 'version'], check=False)
            if result.returncode != 0:
                return False, "Could not verify Docker Compose installation"
            self.logger.info(f"Docker Compose: {result.stdout.strip()}")
            
            self.logger.info("Docker installation verified")
            
            # 9. Create Compose directory
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
                    self.logger.warning(f"Registry login failed: {result.stderr}")
            
            # 11. Create docker-compose.yml
            self.logger.info("Creating docker-compose.yml...")
            
            mongodb_tag = self.get_config('mongodb.tag', 'latest')
            mongodb_data_path = self.get_config('mongodb.data_path', '/data/mongo-data')
            
            # MongoDB data directory
            os.makedirs(mongodb_data_path, exist_ok=True)
            
            compose_content = f"""# Docker Compose Configuration
# Generated by ACO Maintenance Panel

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
                return False, "Could not write docker-compose.yml"
            
            # 12. Docker compose up
            self.logger.info("Starting MongoDB container...")
            
            result = self.run_shell(f'cd {compose_path} && docker compose up -d', check=False)
            if result.returncode != 0:
                return False, f"Could not start Docker compose: {result.stderr}"
            
            # 12.1 Wait until MongoDB is ready (60 second timeout)
            self.logger.info("Waiting for MongoDB to be ready...")
            mongodb_ready = False
            for i in range(60):
                result = self.run_shell(
                    'docker exec local_database mongosh --eval "db.runCommand({ping:1})" 2>/dev/null',
                    check=False
                )
                if result.returncode == 0:
                    self.logger.info("MongoDB ready")
                    mongodb_ready = True
                    break
                if i % 10 == 0 and i > 0:
                    self.logger.info(f"Waiting for MongoDB... ({i}/60 seconds)")
                time.sleep(1)
            
            if not mongodb_ready:
                return False, "Could not start MongoDB (60 second timeout)"
            
            # 13. Save RVM ID to MongoDB
            self._save_rvm_id_to_mongodb()
            
            # 14. Register Mechatronic Controller to Nginx
            if not self._register_mechatronic_to_nginx():
                self.logger.warning("Mechatronic nginx registration failed (installation continues)")
            
            self.logger.info("Docker installation completed")
            return True, "Docker, NVIDIA Container Toolkit and MongoDB installed"

        except Exception as e:
            self.logger.error(f"Docker installation error: {e}")
            return False, str(e)
    
    def _save_rvm_id_to_mongodb(self) -> None:
        """Save RVM ID to MongoDB"""
        client = None
        try:
            import socket
            try:
                from pymongo import MongoClient
            except ImportError:
                self.logger.warning("pymongo not found, skipping MongoDB registration")
                return

            rvm_id = self._config.get_rvm_id()
            hardware_id = self._config.get_hardware_id()

            if not rvm_id:
                self.logger.warning("RVM ID not found, skipping MongoDB registration")
                return

            # MongoDB connection
            client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
            db = client['aco']
            collection = db['settings']

            # Create/update record
            document = {
                'rvm_id': rvm_id,
                'hardware_id': hardware_id,
                'hostname': socket.gethostname(),
                'registered_at': datetime.utcnow()
            }

            collection.update_one(
                {'rvm_id': rvm_id},
                {'$set': document},
                upsert=True
            )

            self.logger.info(f"RVM ID saved to MongoDB: {rvm_id}")

        except Exception as e:
            self.logger.warning(f"MongoDB registration error: {e}")
        finally:
            if client:
                client.close()
    
    def _register_mechatronic_to_nginx(self) -> bool:
        """Add Mechatronic Controller to Nginx config"""
        try:
            nginx_port = self.get_config('nginx.port', 4444)
            mech_config = self.get_config('services.mechcontroller', {})
            
            if not mech_config:
                self.logger.warning("Mechatronic Controller config not found")
                return False
            
            # 1. Read existing services from Services.json
            services = {}
            if os.path.exists(self.SERVICES_FILE):
                try:
                    with open(self.SERVICES_FILE, 'r') as f:
                        services = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    self.logger.warning(f"Could not read Services.json: {e}")
                    services = {}
            
            # 2. Add Mechatronic
            services['mechcontroller'] = {
                "display_name": mech_config.get('display_name', 'Mechatronic Controller'),
                "port": mech_config.get('port', 1234),
                "path": mech_config.get('path', '/mechatronic_controller/'),
                "websocket": mech_config.get('websocket', False),
                "check_type": mech_config.get('check_type', 'port'),
                "check_value": mech_config.get('check_value', 1234)
            }
            
            # 3. Save to Services.json
            with open(self.SERVICES_FILE, 'w') as f:
                json.dump(services, f, indent=2)
            
            # 4. Regenerate Nginx config
            self._regenerate_nginx_config(services, nginx_port)
            
            # 5. Nginx test and reload
            result = self.run_command(['/usr/sbin/nginx', '-t'], check=False)
            if result.returncode != 0:
                self.logger.error(f"Nginx config error: {result.stderr}")
                return False
            
            self.systemctl('reload', 'nginx')
            
            self.logger.info("Mechatronic Controller registered to nginx")
            return True
            
        except Exception as e:
            self.logger.error(f"Nginx registration error: {e}")
            return False

    def _regenerate_nginx_config(self, services: Dict[str, Any], nginx_port: int) -> None:
        """Regenerate nginx config file based on services"""
        
        config_content = f"""# ACO Panel - Nginx Reverse Proxy
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
            
            # For root path (panel)
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
                # Cockpit special configuration
                config_content += f"""    # Cockpit static files
    location /cockpit/static/ {{
        proxy_pass http://127.0.0.1:{port}/cockpit/cockpit/static/;
        proxy_set_header Host $host:$server_port;
    }}

    # Cockpit main
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

        # for iframe
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;
    }}

"""
            else:
                # Other services (including Mechatronic)
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
                # Mechatronic sub_filter (HTML path rewrite)
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
                    config_content += f"""    # Mechatronic socket.io (for root path access)
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