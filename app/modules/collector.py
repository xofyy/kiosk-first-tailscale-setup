"""
ACO Maintenance Panel - collector Module
System metrics collection service
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
    description = "System metrics collection service (Prometheus node_exporter)"
    order = 9
    dependencies = ["vnc"]
    
    def install(self) -> Tuple[bool, str]:
        """collector installation"""
        try:
            collector_dir = "/opt/collector-agent"
            
            # 1. Install required packages
            self.logger.info("Installing collector dependencies...")
            
            packages = ['git', 'python3-pip', 'prometheus-node-exporter']
            
            if not self.apt_install(packages):
                return False, "Could not install collector dependencies"
            
            # 2. Enable prometheus-node-exporter service
            self.logger.info("Starting Node Exporter...")
            if not self.systemctl('enable', 'prometheus-node-exporter'):
                self.logger.warning("Could not enable prometheus-node-exporter")
            if not self.systemctl('start', 'prometheus-node-exporter'):
                self.logger.warning("Could not start prometheus-node-exporter")
            
            # 3. Clone collector-agent repo
            if os.path.exists(collector_dir):
                self.run_shell(f'rm -rf {collector_dir}')
            
            self.logger.info("Downloading collector-agent...")
            result = self.run_command([
                'git', 'clone',
                'https://github.com/xofyy/collector-agent.git',
                collector_dir
            ], check=False)
            if result.returncode != 0:
                return False, f"Could not clone collector-agent repo: {result.stderr}"
            
            # 4. Update pip, setuptools, wheel (required for UNKNOWN issue)
            # NOTE: Using /usr/bin/pip3 because panel runs in virtualenv
            self.logger.info("Updating pip, setuptools, wheel...")
            self.run_shell('/usr/bin/pip3 install --upgrade pip setuptools wheel')
            
            # 5. Remove UNKNOWN package (if exists)
            self.run_shell('/usr/bin/pip3 uninstall -y UNKNOWN 2>/dev/null || true')
            
            # 6. Clean build cache (including all egg-info directories)
            self.run_shell(f'rm -rf {collector_dir}/build {collector_dir}/*.egg-info')
            
            # 7. Install collector-agent with pip
            self.logger.info("Installing collector-agent package...")
            result = self.run_shell(f'cd {collector_dir} && /usr/bin/pip3 install --no-cache-dir --force-reinstall .', check=False)
            if result.returncode != 0:
                return False, f"Could not install collector-agent package: {result.stderr}"
            
            # 8. Create config directory and file
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
                return False, "Could not write Collector config"
            
            # 9. Copy systemd service file from repo
            self.logger.info("Installing Systemd service...")
            result = self.run_shell(f'cp {collector_dir}/systemd/collector-agent.service /etc/systemd/system/', check=False)
            if result.returncode != 0:
                return False, "Could not copy Systemd service file"
            
            # 10. Enable and start service
            self.run_command(['systemctl', 'daemon-reload'])
            if not self.systemctl('enable', 'collector-agent'):
                self.logger.warning("Could not enable collector-agent")
            if not self.systemctl('start', 'collector-agent'):
                self.logger.warning("Could not start collector-agent")
            
            # =================================================================
            # Post-Installation Verification
            # =================================================================
            time.sleep(2)
            
            result = self.run_command(['systemctl', 'is-active', 'collector-agent'], check=False)
            if result.returncode != 0:
                self.logger.warning("Could not start collector-agent service")
                return False, "Could not start collector-agent service"

            self.logger.info("collector-agent service verified")
            self.logger.info("collector installation completed")
            return True, "collector-agent and prometheus-node-exporter installed"

        except Exception as e:
            self.logger.error(f"collector installation error: {e}")
            return False, str(e)
