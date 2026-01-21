"""
ACO Maintenance Panel - System Service
System information and helper functions
"""

import json
import logging
import subprocess
import socket
import os
import ipaddress
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# =============================================================================
# NETWORK INTERFACE DETECTION CONSTANTS
# =============================================================================

# Known motherboard manufacturers - subsystem_vendor IDs
# If a NIC's subsystem_vendor matches one of these, it's likely onboard
MOTHERBOARD_VENDORS = {
    "0x1462": "MSI",
    "0x1043": "ASUS",
    "0x1458": "Gigabyte",
    "0x1849": "ASRock",
    "0x1028": "Dell",
    "0x103c": "HP",
    "0x17aa": "Lenovo",
    "0x8086": "Intel",
    "0x15d9": "Supermicro",
    "0x1025": "Acer",
    "0x104d": "Sony",
    "0x1179": "Toshiba",
    "0x1022": "AMD",
    "0x1297": "Shuttle",
    "0x1565": "Biostar",
    "0x1b4b": "Marvell",
}

# Default IP configurations for each interface type
# Onboard: supports both "network" (with gateway) and "direct" (no gateway) modes
# PCIe: only "direct" mode (typically used for direct device connections)
DEFAULT_IP_CONFIGS = {
    "onboard": {
        "ip": "5.5.5.55",
        "prefix": 24,
        "modes": {
            "network": {
                "gateway": "5.5.5.1",
                "dns": "8.8.8.8",
                "ipv6": "auto"
            },
            "direct": {
                "gateway": None,
                "dns": None,
                "ipv6": "disabled"
            }
        }
    },
    "pcie": {
        "ip": "192.168.1.200",
        "prefix": 24,
        "modes": {
            "direct": {
                "gateway": None,
                "dns": None,
                "ipv6": "disabled"
            }
        }
    },
}


class SystemService:
    """System information and operations"""

    def get_system_info(self) -> Dict[str, Any]:
        """Collect all system information"""
        return {
            'hostname': self.get_hostname(),
            'ip_address': self.get_ip_address(),
            'tailscale_ip': self.get_tailscale_ip(),
            'internet': self.check_internet(),
            'dns_working': self.check_dns(),
            'interfaces': self.get_network_interfaces(),
            'uptime': self.get_uptime(),
            'memory': self.get_memory_info(),
            'disk': self.get_disk_info(),
        }
    
    def get_system_info_fast(self) -> Dict[str, Any]:
        """
        Fast system info WITHOUT internet check.
        Doesn't block tab switches. Internet info updated async via JS.

        Prevents page transitions from slowing down when no internet.
        """
        return {
            'hostname': self.get_hostname(),
            'ip_address': None,  # JS will update
            'tailscale_ip': None,  # JS will update
            'internet': None,  # JS will update
            'dns_working': None,  # JS will update
            'interfaces': self.get_network_interfaces(),  # Fast (local)
            'uptime': self.get_uptime(),  # Fast (/proc read)
            'kernel': self.get_kernel_version(),  # Fast (/proc read)
            'os_info': self.get_os_info(),  # Fast (file read)
            'memory': self.get_memory_info(),  # Fast (/proc read)
            'disk': self.get_disk_info(),  # Fast (statvfs)
        }
    
    def get_hostname(self) -> str:
        """Get hostname"""
        return socket.gethostname()
    
    def get_ip_address(self) -> Optional[str]:
        """Get main IP address"""
        s = None
        try:
            # Get IP via default route
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.3)  # 300ms timeout - fast UI update
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception as e:
            logger.debug(f"Could not get IP address: {e}")
            return None
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
    
    def get_tailscale_ip(self) -> Optional[str]:
        """Get Tailscale IP address"""
        try:
            result = subprocess.run(
                ['tailscale', 'ip', '-4'],
                capture_output=True,
                text=True,
                timeout=0.5  # 500ms timeout - fast UI update
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Could not get Tailscale IP: {e}")
        return None
    
    def get_network_interfaces(self) -> Dict[str, Dict[str, str]]:
        """List network interfaces"""
        interfaces = {}

        try:
            # Get interfaces via ip addr
            result = subprocess.run(
                ['ip', '-j', 'addr'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                
                for iface in data:
                    name = iface.get('ifname', '')

                    # Skip lo and docker interfaces
                    if name in ['lo'] or name.startswith('docker') or name.startswith('br-'):
                        continue
                    
                    addr_info = iface.get('addr_info', [])
                    ipv4 = None
                    
                    for addr in addr_info:
                        if addr.get('family') == 'inet':
                            ipv4 = addr.get('local')
                            break
                    
                    interfaces[name] = {
                        'state': iface.get('operstate', 'unknown'),
                        'ip': ipv4 or 'N/A',
                        'mac': iface.get('address', 'N/A')
                    }
                    
        except Exception as e:
            logger.debug(f"Could not get network interfaces: {e}")

        return interfaces

    def get_ethernet_interfaces(self) -> List[Dict[str, Any]]:
        """
        Detect physical ethernet interfaces with onboard/pcie classification.
        Uses subsystem_vendor to distinguish onboard NICs from PCIe add-on cards.

        Returns:
            List of interface dicts:
            [
                {
                    "name": "enp4s0",
                    "type": "onboard",      # or "pcie"
                    "vendor": "MSI",        # motherboard vendor or chip vendor
                    "ip": "192.168.1.50",   # or None
                    "state": "up",          # or "down"
                    "mac": "d8:bb:c1:4e:a9:6e"
                },
                ...
            ]
        """
        interfaces = []

        try:
            # Get all network interfaces from /sys/class/net
            net_path = '/sys/class/net'

            if not os.path.exists(net_path):
                return interfaces

            for iface_name in os.listdir(net_path):
                iface_path = os.path.join(net_path, iface_name)

                # Skip virtual interfaces
                if iface_name in ['lo']:
                    continue
                if iface_name.startswith(('docker', 'veth', 'br-', 'tailscale', 'virbr')):
                    continue

                # Check if it's a physical device (has 'device' symlink)
                device_path = os.path.join(iface_path, 'device')
                if not os.path.exists(device_path):
                    continue

                # Skip wireless interfaces
                wireless_path = os.path.join(iface_path, 'wireless')
                if os.path.exists(wireless_path):
                    continue

                # Get subsystem_vendor to determine onboard vs pcie
                subsystem_vendor_path = os.path.join(device_path, 'subsystem_vendor')
                iface_type = "pcie"  # Default to PCIe
                vendor_name = "Unknown"

                if os.path.exists(subsystem_vendor_path):
                    try:
                        with open(subsystem_vendor_path, 'r') as f:
                            vendor_id = f.read().strip()

                        if vendor_id in MOTHERBOARD_VENDORS:
                            iface_type = "onboard"
                            vendor_name = MOTHERBOARD_VENDORS[vendor_id]
                        else:
                            # Try to get vendor name from udevadm or keep as vendor_id
                            vendor_name = self._get_vendor_name(iface_name) or vendor_id
                    except Exception:
                        pass

                # Get IP address and state
                ip_addr = None
                state = "down"
                mac = "N/A"

                # Get operstate
                operstate_path = os.path.join(iface_path, 'operstate')
                if os.path.exists(operstate_path):
                    try:
                        with open(operstate_path, 'r') as f:
                            state = f.read().strip().lower()
                    except Exception:
                        pass

                # Get MAC address
                address_path = os.path.join(iface_path, 'address')
                if os.path.exists(address_path):
                    try:
                        with open(address_path, 'r') as f:
                            mac = f.read().strip()
                    except Exception:
                        pass

                # Get IP address via ip command
                try:
                    result = subprocess.run(
                        ['ip', '-4', '-o', 'addr', 'show', iface_name],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        # Parse: "2: enp4s0    inet 192.168.1.50/24 ..."
                        parts = result.stdout.split()
                        for i, part in enumerate(parts):
                            if part == 'inet' and i + 1 < len(parts):
                                ip_addr = parts[i + 1].split('/')[0]
                                break
                except Exception:
                    pass

                interfaces.append({
                    "name": iface_name,
                    "type": iface_type,
                    "vendor": vendor_name,
                    "ip": ip_addr,
                    "state": state,
                    "mac": mac
                })

            # Sort: onboard first, then by name
            interfaces.sort(key=lambda x: (0 if x['type'] == 'onboard' else 1, x['name']))

        except Exception as e:
            logger.error(f"Could not get ethernet interfaces: {e}")

        return interfaces

    def _get_vendor_name(self, iface_name: str) -> Optional[str]:
        """Get vendor name from udevadm for a network interface"""
        try:
            result = subprocess.run(
                ['udevadm', 'info', '-p', f'/sys/class/net/{iface_name}'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'ID_VENDOR_FROM_DATABASE=' in line:
                        return line.split('=', 1)[1].strip()
        except Exception:
            pass
        return None

    def check_internet(self) -> bool:
        """Check internet connection"""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=0.3)  # 300ms timeout
            return True
        except OSError:
            return False
    
    def check_dns(self) -> bool:
        """DNS resolution check"""
        try:
            socket.setdefaulttimeout(0.3)  # 300ms timeout
            socket.gethostbyname("google.com")
            return True
        except (socket.error, socket.timeout):
            return False
        finally:
            socket.setdefaulttimeout(None)
    
    def get_uptime(self) -> str:
        """Get system uptime"""
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
            
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            
            if days > 0:
                return f"{days}g {hours}s {minutes}d"
            elif hours > 0:
                return f"{hours}s {minutes}d"
            else:
                return f"{minutes}d"
                
        except Exception as e:
            logger.debug(f"Could not get uptime: {e}")
            return "N/A"

    def get_kernel_version(self) -> str:
        """Get kernel version"""
        try:
            with open('/proc/version', 'r') as f:
                version_line = f.readline()
                # Extract version number (e.g., "5.15.0-generic")
                parts = version_line.split()
                if len(parts) >= 3:
                    return parts[2]
            return "N/A"
        except Exception as e:
            logger.debug(f"Could not get kernel version: {e}")
            return "N/A"

    def get_os_info(self) -> Dict[str, str]:
        """Get OS information from /etc/os-release"""
        try:
            os_info = {'name': 'Linux', 'version': ''}
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    for line in f:
                        if line.startswith('PRETTY_NAME='):
                            # Remove quotes and newline
                            os_info['name'] = line.split('=', 1)[1].strip().strip('"')
                        elif line.startswith('VERSION_ID='):
                            os_info['version'] = line.split('=', 1)[1].strip().strip('"')
            return os_info
        except Exception as e:
            logger.debug(f"Could not get OS info: {e}")
            return {'name': 'Linux', 'version': ''}

    def get_memory_info(self) -> Dict[str, Any]:
        """Get memory info"""
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip().split()[0]
                        meminfo[key] = int(value)
            
            total = meminfo.get('MemTotal', 0) / 1024  # MB
            free = meminfo.get('MemAvailable', 0) / 1024  # MB
            used = total - free
            
            return {
                'total_mb': int(total),
                'used_mb': int(used),
                'free_mb': int(free),
                'percent': int((used / total) * 100) if total > 0 else 0
            }
            
        except Exception as e:
            logger.debug(f"Could not get memory info: {e}")
            return {'total_mb': 0, 'used_mb': 0, 'free_mb': 0, 'percent': 0}
    
    def get_disk_info(self) -> Dict[str, Any]:
        """Get disk info (root partition)"""
        try:
            stat = os.statvfs('/')
            total = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)  # GB
            free = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)  # GB
            used = total - free
            
            return {
                'total_gb': round(total, 1),
                'used_gb': round(used, 1),
                'free_gb': round(free, 1),
                'percent': int((used / total) * 100) if total > 0 else 0
            }
            
        except Exception as e:
            logger.debug(f"Could not get disk info: {e}")
            return {'total_gb': 0, 'used_gb': 0, 'free_gb': 0, 'percent': 0}
    
    def set_temporary_ip(
        self,
        interface: str,
        ip: str,
        netmask: str,
        gateway: str,
        dns: str
    ) -> dict:
        """
        Set temporary static IP - protected version.
        This setting is valid until NetworkManager is installed.

        Returns: {'success': bool, 'error': str|None}
        """

        # 1. VALIDATION - Check first, then apply

        # Does interface exist?
        if not os.path.exists(f'/sys/class/net/{interface}'):
            return {'success': False, 'error': f'Interface not found: {interface}'}

        # Is IP format valid?
        try:
            ip_obj = ipaddress.ip_address(ip)
            gw_obj = ipaddress.ip_address(gateway)
            network = ipaddress.ip_network(f"{ip}/{netmask}", strict=False)
        except ValueError as e:
            return {'success': False, 'error': f'Invalid IP format: {e}'}

        # Is gateway in the same subnet?
        if gw_obj not in network:
            return {'success': False, 'error': f"Gateway ({gateway}) not in IP subnet"}
        
        # 2. BACKUP - Save current state
        backup = self._backup_network_state(interface)

        # 3. APPLY - Execute operations in order
        try:
            # Stop DHCP (if running, won't error if not)
            dhclient = self._find_dhclient()
            if dhclient:
                subprocess.run(
                    [dhclient, '-r', interface],
                    check=False, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, timeout=10
                )
            subprocess.run(
                ['pkill', '-f', f'dhclient.*{interface}'],
                check=False, stderr=subprocess.DEVNULL, timeout=5
            )
            
            # Clear current IP
            subprocess.run(
                ['ip', 'addr', 'flush', 'dev', interface],
                check=True, timeout=10
            )
            
            # Add new IP
            cidr = self._netmask_to_cidr(netmask)
            subprocess.run(
                ['ip', 'addr', 'add', f'{ip}/{cidr}', 'dev', interface],
                check=True, timeout=10
            )
            subprocess.run(
                ['ip', 'link', 'set', interface, 'up'],
                check=True, timeout=10
            )
            
            # FIRST delete current route, THEN add new one
            subprocess.run(
                ['ip', 'route', 'del', 'default'],
                check=False, stderr=subprocess.DEVNULL, timeout=10
            )
            subprocess.run(
                ['ip', 'route', 'add', 'default', 'via', gateway],
                check=True, timeout=10
            )
            
            # Set DNS
            with open('/etc/resolv.conf', 'w') as f:
                f.write(f"nameserver {dns}\n")
            
            return {'success': True, 'error': None}
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            # 4. ROLLBACK - Revert on error
            error_msg = f"IP setting error: {e}"
            rollback_ok = self._rollback_network(interface, backup)

            if rollback_ok:
                return {'success': False, 'error': f'{error_msg} (old settings restored)'}
            else:
                return {'success': False, 'error': f'{error_msg} (WARNING: Rollback failed!)'}

    def _netmask_to_cidr(self, netmask: str) -> int:
        """Convert netmask to CIDR notation"""
        return sum([bin(int(x)).count('1') for x in netmask.split('.')])
    
    def reset_to_dhcp(self, interface: str) -> dict:
        """
        Reset to DHCP - protected version.
        Removes static IP setting and restarts DHCP client.

        Returns: {'success': bool, 'error': str|None}
        """

        # Interface check
        if not os.path.exists(f'/sys/class/net/{interface}'):
            return {'success': False, 'error': f'Interface not found: {interface}'}

        # dhclient check - Check FIRST, do nothing if not found!
        dhclient = self._find_dhclient()
        if not dhclient:
            return {'success': False, 'error': 'dhclient not found! isc-dhcp-client package required.'}
        
        try:
            # IP temizle
            subprocess.run(
                ['ip', 'addr', 'flush', 'dev', interface],
                check=True, timeout=10
            )
            
            # Route temizle
            subprocess.run(
                ['ip', 'route', 'del', 'default'],
                check=False, stderr=subprocess.DEVNULL, timeout=10
            )
            
            # DHCP release
            subprocess.run(
                [dhclient, '-r', interface],
                check=False, timeout=10
            )
            
            # Start DHCP
            subprocess.run(
                [dhclient, interface],
                check=True, timeout=30
            )

            return {'success': True, 'error': None}

        except subprocess.CalledProcessError as e:
            return {'success': False, 'error': f'DHCP error: {e}'}
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'DHCP timeout (30s)'}

    def _backup_network_state(self, interface: str) -> dict:
        """Backup current network state"""
        backup = {}
        try:
            # Current IP info
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show', interface],
                capture_output=True, text=True, timeout=5
            )
            backup['ip_info'] = result.stdout
            
            # Current default route
            result = subprocess.run(
                ['ip', 'route', 'show', 'default'],
                capture_output=True, text=True, timeout=5
            )
            backup['default_route'] = result.stdout.strip()
            
            # Current DNS
            if os.path.exists('/etc/resolv.conf'):
                with open('/etc/resolv.conf', 'r') as f:
                    backup['dns'] = f.read()
        except Exception as e:
            logger.debug(f"Could not backup network: {e}")
        return backup

    def _rollback_network(self, interface: str, backup: dict) -> bool:
        """Restore network configuration (with DHCP)"""
        try:
            # Restore DNS
            if 'dns' in backup:
                with open('/etc/resolv.conf', 'w') as f:
                    f.write(backup['dns'])

            # Get new IP via dhclient (safest way)
            dhclient = self._find_dhclient()
            
            if dhclient:
                subprocess.run(
                    ['ip', 'addr', 'flush', 'dev', interface],
                    check=False, timeout=10
                )
                subprocess.run(
                    [dhclient, interface],
                    check=True, timeout=30
                )
                return True
            
            return False
        except Exception as e:
            logger.warning(f"Network rollback failed: {e}")
            return False
    
    def _find_dhclient(self) -> Optional[str]:
        """Find dhclient binary"""
        paths = ['/sbin/dhclient', '/usr/sbin/dhclient']
        return next((p for p in paths if os.path.exists(p)), None)

    def get_component_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all system components for dashboard.
        Returns dict with status info for each component.
        """
        return {
            'docker': self._check_docker_status(),
            'mongodb': self._check_mongodb_status(),
            'nvidia': self._check_nvidia_status(),
            'tailscale': self._check_tailscale_status(),
        }

    def _check_docker_status(self) -> Dict[str, Any]:
        """Check Docker service status"""
        try:
            # Check if Docker service is running
            result = subprocess.run(
                ['systemctl', 'is-active', 'docker'],
                capture_output=True, text=True, timeout=5
            )
            is_running = result.stdout.strip() == 'active'

            # Get Docker version if running
            version = None
            if is_running:
                ver_result = subprocess.run(
                    ['docker', '--version'],
                    capture_output=True, text=True, timeout=5
                )
                if ver_result.returncode == 0:
                    # "Docker version 24.0.5, build ..."
                    parts = ver_result.stdout.strip().split()
                    if len(parts) >= 3:
                        version = parts[2].rstrip(',')

            return {
                'status': 'running' if is_running else 'stopped',
                'ok': is_running,
                'version': version,
                'label': 'Docker'
            }
        except Exception as e:
            logger.debug(f"Docker check error: {e}")
            return {'status': 'error', 'ok': False, 'version': None, 'label': 'Docker'}

    def _check_mongodb_status(self) -> Dict[str, Any]:
        """Check MongoDB container status"""
        try:
            # Check if MongoDB container is running (try multiple container names)
            is_running = False
            container_names = ['local_database', 'mongodb', 'mongo']

            for name in container_names:
                result = subprocess.run(
                    ['docker', 'ps', '--filter', f'name={name}', '--format', '{{.Status}}'],
                    capture_output=True, text=True, timeout=10
                )
                status_output = result.stdout.strip()
                if status_output and 'Up' in status_output:
                    is_running = True
                    break

            # If not found by name, try by image
            if not is_running:
                result = subprocess.run(
                    ['docker', 'ps', '--filter', 'ancestor=mongo', '--format', '{{.Status}}'],
                    capture_output=True, text=True, timeout=10
                )
                status_output = result.stdout.strip()
                is_running = 'Up' in status_output if status_output else False

            return {
                'status': 'running' if is_running else 'stopped',
                'ok': is_running,
                'info': 'Container' if is_running else None,
                'label': 'MongoDB'
            }
        except Exception as e:
            logger.debug(f"MongoDB check error: {e}")
            return {'status': 'error', 'ok': False, 'info': None, 'label': 'MongoDB'}

    def _check_nvidia_status(self) -> Dict[str, Any]:
        """Check NVIDIA driver status"""
        from app.modules.base import mongo_config as config

        try:
            # Get module status from MongoDB
            module_status = config.get_module_status('nvidia')

            # Check if nvidia-smi works
            nvidia_working = False
            driver_version = None
            gpu_name = None

            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=driver_version,name', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                nvidia_working = True
                parts = result.stdout.strip().split(', ')
                if len(parts) >= 1:
                    driver_version = parts[0]
                if len(parts) >= 2:
                    gpu_name = parts[1]

            # Determine display status
            if module_status == 'completed' and nvidia_working:
                status = 'working'
                ok = True
            elif module_status == 'mok_pending':
                status = 'mok_pending'
                ok = False
            elif module_status == 'reboot_required':
                status = 'reboot_required'
                ok = False
            elif module_status == 'completed' and not nvidia_working:
                status = 'not_working'
                ok = False
            else:
                status = 'not_installed'
                ok = False

            return {
                'status': status,
                'ok': ok,
                'version': driver_version,
                'gpu': gpu_name,
                'module_status': module_status,
                'label': 'NVIDIA'
            }
        except Exception as e:
            logger.debug(f"NVIDIA check error: {e}")
            return {'status': 'not_installed', 'ok': False, 'version': None, 'gpu': None, 'label': 'NVIDIA'}

    def _check_tailscale_status(self) -> Dict[str, Any]:
        """Check Tailscale connection status"""
        from app.modules.base import mongo_config as config

        try:
            # Get module status from MongoDB
            module_status = config.get_module_status('remote-connection')

            # Check if Tailscale is connected
            is_connected = False
            tailscale_ip = None

            result = subprocess.run(
                ['tailscale', 'status', '--json'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                try:
                    status_json = json.loads(result.stdout)
                    backend_state = status_json.get('BackendState', '')
                    is_connected = backend_state == 'Running'

                    # Get Tailscale IP
                    if is_connected:
                        tailscale_ips = status_json.get('TailscaleIPs', [])
                        if tailscale_ips:
                            # Prefer IPv4
                            for ip in tailscale_ips:
                                if '.' in ip:
                                    tailscale_ip = ip
                                    break
                            if not tailscale_ip:
                                tailscale_ip = tailscale_ips[0]
                except json.JSONDecodeError:
                    pass

            # Determine display status
            if module_status == 'completed' and is_connected:
                status = 'connected'
                ok = True
            elif module_status == 'completed' and not is_connected:
                status = 'disconnected'
                ok = False
            else:
                status = 'not_enrolled'
                ok = False

            return {
                'status': status,
                'ok': ok,
                'ip': tailscale_ip,
                'module_status': module_status,
                'label': 'Remote Connection'
            }
        except Exception as e:
            logger.debug(f"Tailscale check error: {e}")
            return {'status': 'not_installed', 'ok': False, 'ip': None, 'label': 'Remote Connection'}
