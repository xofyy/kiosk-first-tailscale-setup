"""
ACO Maintenance Panel - Network Module
NetworkManager and DNS configuration

Features:
- NetworkManager installation
- cloud-init network disabled
- Netplan to NetworkManager transition
- systemd-resolved DNS configuration (Domains=~.)
- systemd-networkd MASK
- DNS verification
- nmcli connection refresh
"""

import os
import glob
import shutil
import time
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class NetworkModule(BaseModule):
    name = "network"
    display_name = "Network"
    description = "NetworkManager installation, DNS configuration"
    order = 3
    dependencies = ["nvidia", "tailscale"]
    
    # =========================================================================
    # STATUS CHECK FUNCTIONS
    # =========================================================================
    
    def _is_nm_installed(self) -> bool:
        """Is NetworkManager package installed?"""
        result = self.run_shell('dpkg -l | grep -q "ii  network-manager "', check=False)
        return result.returncode == 0
    
    def _is_nm_active(self) -> bool:
        """Is NetworkManager service active?"""
        result = self.run_command(['systemctl', 'is-active', 'NetworkManager'], check=False)
        return result.returncode == 0
    
    def _is_cloud_init_disabled(self) -> bool:
        """Is cloud-init network disabled?"""
        return os.path.exists('/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg')
    
    def _is_networkd_masked(self) -> bool:
        """Is systemd-networkd-wait-online masked?"""
        result = self.run_command(
            ['systemctl', 'is-enabled', 'systemd-networkd-wait-online'], 
            check=False
        )
        return 'masked' in result.stdout.lower()
    
    def _is_netplan_nm_configured(self) -> bool:
        """Is Netplan configured to use NetworkManager?"""
        netplan_file = '/etc/netplan/01-network-manager.yaml'
        if not os.path.exists(netplan_file):
            return False
        
        try:
            with open(netplan_file, 'r') as f:
                return 'renderer: NetworkManager' in f.read()
        except Exception:
            return False
    
    def _get_default_interface(self) -> str:
        """Find the default network interface"""
        result = self.run_shell(
            "ip route | grep default | awk '{print $5}' | head -1",
            check=False
        )
        interface = result.stdout.strip()
        return interface if interface else 'eth0'
    
    def _wait_for_network(self, timeout: int = 60) -> bool:
        """Wait until network connection is active"""
        self.logger.info("Waiting for network connection...")
        for attempt in range(timeout // 5):
            time.sleep(5)
            # Gateway'e ping
            result = self.run_shell(
                "ping -c 1 -W 2 $(ip route | grep default | awk '{print $3}' | head -1) 2>/dev/null",
                check=False
            )
            if result.returncode == 0:
                self.logger.info(f"Network connection active ({(attempt+1)*5}s)")
                return True
        self.logger.warning("Could not reach gateway")
        return False
    
    def _is_fully_configured(self) -> bool:
        """Is all network configuration completed?"""
        # Is NM installed and active?
        if not self._is_nm_installed() or not self._is_nm_active():
            return False
        
        # Is cloud-init disabled?
        if not self._is_cloud_init_disabled():
            return False
        
        # Is Netplan correctly configured?
        netplan_file = '/etc/netplan/01-network-manager.yaml'
        try:
            with open(netplan_file, 'r') as f:
                content = f.read()
                if 'use-dns: false' not in content:
                    return False
        except Exception:
            return False
        
        # Is resolved.conf correct?
        try:
            with open('/etc/systemd/resolved.conf', 'r') as f:
                content = f.read()
                if 'Domains=~.' not in content:
                    return False
        except Exception:
            return False
        
        # Is networkd masked?
        if not self._is_networkd_masked():
            return False
        
        return True
    
    # =========================================================================
    # CONFIGURATION FUNCTIONS
    # =========================================================================
    
    def _backup_netplan(self) -> None:
        """Backup existing netplan files"""
        for f in glob.glob('/etc/netplan/*.yaml'):
            if not f.endswith('.bak'):
                backup_path = f + '.bak'
                if not os.path.exists(backup_path):
                    shutil.copy(f, backup_path)
                    self.logger.info(f"Backed up: {f} -> {backup_path}")
    
    def _move_old_netplan(self) -> None:
        """Move old netplan files to backup directory"""
        backup_dir = '/etc/netplan/backup'
        os.makedirs(backup_dir, exist_ok=True)
        
        for f in glob.glob('/etc/netplan/*.yaml'):
            # Skip our file and .bak files
            if '01-network-manager' in f or f.endswith('.bak'):
                continue
            
            dest = os.path.join(backup_dir, os.path.basename(f))
            shutil.move(f, dest)
            self.logger.info(f"Moved: {f} -> {dest}")
    
    def _mask_networkd(self) -> None:
        """Mask systemd-networkd services"""
        # MASK - stronger than disable, improves boot speed
        self.run_command(
            ['systemctl', 'mask', 'systemd-networkd-wait-online.service'], 
            check=False
        )
        self.run_command(
            ['systemctl', 'stop', 'systemd-networkd-wait-online.service'], 
            check=False
        )
        self.logger.info("systemd-networkd-wait-online masked")
    
    def _verify_dns(self, retries: int = 3) -> bool:
        """Verify DNS is working (via ping)"""
        for i in range(retries):
            self.logger.info(f"DNS verification attempt {i + 1}/{retries}...")
            result = self.run_command(
                ['ping', '-c', '1', '-W', '5', 'archive.ubuntu.com'], 
                check=False
            )
            if result.returncode == 0:
                return True
            time.sleep(2)
        return False
    
    def _refresh_nm_connection(self) -> None:
        """Refresh connection with nmcli"""
        self.logger.info("Refreshing connection (nmcli)...")
        
        # Find active interface and refresh connection
        self.run_shell(
            'IFACE=$(ip route | grep default | awk \'{print $5}\' | head -1); '
            'CON=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep "$IFACE" | cut -d: -f1); '
            '[ -n "$CON" ] && nmcli con down "$CON" 2>/dev/null; '
            'sleep 2; '
            '[ -n "$CON" ] && nmcli con up "$CON" 2>/dev/null || true',
            check=False
        )
    
    # =========================================================================
    # MAIN INSTALLATION
    # =========================================================================
    
    def install(self) -> Tuple[bool, str]:
        """
        Network configuration

        Flow:
        1. NetworkManager installation (if not present)
        2. cloud-init network disabled (if not already)
        3. Netplan backup
        4. Netplan configuration
        5. Move old netplan files
        6. netplan apply
        7. systemd-networkd-wait-online MASK
        8. systemd-networkd disabled
        9. DNS configuration (including Domains=~.)
        10. DNS verification
        11. NetworkManager services
        12. nmcli connection refresh
        13. Final check
        """
        try:
            # =================================================================
            # QUICK CHECK - Skip if already configured
            # =================================================================
            if self._is_fully_configured():
                self.logger.info("Network already configured")
                return True, "Network already configured"
            
            # =================================================================
            # 1. NetworkManager Installation
            # =================================================================
            if not self._is_nm_installed():
                self.logger.info("Installing NetworkManager...")
                if not self.apt_install(['network-manager']):
                    return False, "Could not install NetworkManager"
            else:
                self.logger.info("NetworkManager already installed")
            
            # =================================================================
            # 2. cloud-init Network Disabled
            # =================================================================
            if not self._is_cloud_init_disabled():
                self.logger.info("Disabling cloud-init network...")
                cloud_init_content = "network: {config: disabled}"
                if not self.write_file(
                    '/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg',
                    cloud_init_content
                ):
                    self.logger.warning("Could not write cloud-init config")
            else:
                self.logger.info("cloud-init network already disabled")
            
            # =================================================================
            # 3. Netplan Backup
            # =================================================================
            self.logger.info("Backing up existing netplan files...")
            self._backup_netplan()
            
            # =================================================================
            # 4. Netplan Configuration
            # =================================================================
            self.logger.info("Configuring Netplan...")
            
            # Get interface and DNS information
            interface = self._get_default_interface()
            dns_servers = self.get_config('network.dns_servers', ['8.8.8.8', '8.8.4.4'])
            dns_yaml = '\n'.join([f'          - {dns}' for dns in dns_servers])
            
            netplan_content = f"""# Network configuration managed by NetworkManager
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    {interface}:
      dhcp4: true
      dhcp4-overrides:
        use-dns: false
      nameservers:
        addresses:
{dns_yaml}
"""
            if not self.write_file('/etc/netplan/01-network-manager.yaml', netplan_content):
                return False, "Could not write Netplan config"
            self.logger.info(f"Netplan configured (interface: {interface})")
            
            # =================================================================
            # 5. Move Old Netplan Files
            # =================================================================
            self.logger.info("Moving old netplan files...")
            self._move_old_netplan()
            
            # =================================================================
            # 6. netplan apply
            # =================================================================
            self.logger.info("Running netplan apply...")
            result = self.run_command(['/usr/sbin/netplan', 'apply'], check=False)
            if result.returncode != 0:
                self.logger.warning(f"netplan apply warning: {result.stderr}")

            # Wait until network stabilizes
            if not self._wait_for_network(timeout=60):
                self.logger.warning("Network connection may have been temporarily interrupted")
            
            # =================================================================
            # 7. systemd-networkd-wait-online MASK
            # =================================================================
            if not self._is_networkd_masked():
                self.logger.info("Masking systemd-networkd-wait-online...")
                self._mask_networkd()
            else:
                self.logger.info("systemd-networkd-wait-online already masked")
            
            # =================================================================
            # 8. systemd-networkd Disabled
            # =================================================================
            self.logger.info("Disabling systemd-networkd...")
            if not self.systemctl('disable', 'systemd-networkd'):
                self.logger.warning("Could not disable systemd-networkd")
            if not self.systemctl('stop', 'systemd-networkd'):
                self.logger.warning("Could not stop systemd-networkd")
            
            # =================================================================
            # 9. DNS Configuration (including Domains=~.)
            # =================================================================
            self.logger.info("Configuring DNS (Domains=~.)...")
            
            dns_servers = self.get_config('network.dns_servers', ['8.8.8.8', '8.8.4.4'])
            dns_str = ' '.join(dns_servers)
            
            resolved_content = f"""[Resolve]
DNS={dns_str}
FallbackDNS=1.1.1.1 9.9.9.9
Domains=~.
DNSStubListener=yes
"""
            if not self.write_file('/etc/systemd/resolved.conf', resolved_content):
                return False, "Could not write DNS config"

            # Restart systemd-resolved
            if not self.systemctl('restart', 'systemd-resolved'):
                self.logger.warning("Could not restart systemd-resolved")
            time.sleep(3)  # Wait for DNS service to be ready
            
            # =================================================================
            # 10. DNS Verification
            # =================================================================
            self.logger.info("Verifying DNS...")
            if not self._verify_dns(retries=3):
                self.logger.error("DNS verification failed!")
                return False, "DNS verification failed! Check network connection."
            self.logger.info("DNS verified")
            
            # =================================================================
            # 11. NetworkManager Services
            # =================================================================
            self.logger.info("Enabling NetworkManager services...")
            if not self.systemctl('enable', 'NetworkManager'):
                self.logger.warning("Could not enable NetworkManager")
            if not self.systemctl('start', 'NetworkManager'):
                self.logger.warning("Could not start NetworkManager")
            if not self.systemctl('enable', 'NetworkManager-wait-online'):
                self.logger.warning("Could not enable NetworkManager-wait-online")
            
            # =================================================================
            # 12. nmcli Connection Refresh
            # =================================================================
            self._refresh_nm_connection()
            time.sleep(5)  # Wait for connection to stabilize
            
            # =================================================================
            # 13. Final Check
            # =================================================================
            time.sleep(2)  # Wait for service to stabilize

            if not self._is_nm_active():
                self.logger.error("NetworkManager is not active!")
                return False, "Could not start NetworkManager"

            self.logger.info("Network configuration completed")
            return True, "NetworkManager installed and configured"

        except Exception as e:
            self.logger.error(f"Network installation error: {e}")
            return False, str(e)
