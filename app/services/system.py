"""
ACO Maintenance Panel - System Service
System information and helper functions
"""

import json
import logging
import subprocess
import socket
import os
import time
import sqlite3
import ipaddress
import psutil
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

# =============================================================================
# SYSTEM MONITOR CONSTANTS
# =============================================================================

NETMON_DB_PATH = '/var/lib/netmon/traffic.db'

# Network throughput delta state (persists between API calls within same worker)
_prev_net_bytes = {'rx': 0, 'tx': 0, 'timestamp': 0}


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

                # Get IP mode (network, direct, dhcp)
                ip_mode = self._get_interface_ip_mode(iface_name)

                interfaces.append({
                    "name": iface_name,
                    "type": iface_type,
                    "vendor": vendor_name,
                    "ip": ip_addr,
                    "state": state,
                    "mac": mac,
                    "mode": ip_mode
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

    def _get_interface_ip_mode(self, iface_name: str) -> Optional[str]:
        """
        Detect IP configuration mode for an interface using NetworkManager.

        Returns:
            - "network": Manual IP with gateway (for internet access)
            - "direct": Manual IP without gateway (for direct device connection)
            - "dhcp": Automatic IP via DHCP
            - None: Unknown or no active connection
        """
        try:
            # Get active connection name for the interface
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'NAME,DEVICE', 'connection', 'show', '--active'],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode != 0:
                return None

            # Find connection for this interface
            connection_name = None
            for line in result.stdout.strip().split('\n'):
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 2 and parts[1] == iface_name:
                        connection_name = parts[0]
                        break

            if not connection_name:
                return None

            # Get connection details
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'ipv4.method,ipv4.gateway', 'connection', 'show', connection_name],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode != 0:
                return None

            ipv4_method = None
            ipv4_gateway = None

            for line in result.stdout.strip().split('\n'):
                if line.startswith('ipv4.method:'):
                    ipv4_method = line.split(':', 1)[1].strip()
                elif line.startswith('ipv4.gateway:'):
                    ipv4_gateway = line.split(':', 1)[1].strip()

            # Determine mode based on method and gateway
            if ipv4_method == 'auto':
                return 'dhcp'
            elif ipv4_method == 'manual':
                # Check if gateway is set (not empty, not '--')
                if ipv4_gateway and ipv4_gateway != '--' and ipv4_gateway != '':
                    return 'network'
                else:
                    return 'direct'

            return None
        except Exception as e:
            logger.debug(f"Could not detect IP mode for {iface_name}: {e}")
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
    
    def get_disk_info(self, path: str = '/') -> Dict[str, Any]:
        """Get disk info for a given mount point"""
        try:
            usage = psutil.disk_usage(path)
            return {
                'total_gb': round(usage.total / (1024 ** 3), 1),
                'used_gb': round(usage.used / (1024 ** 3), 1),
                'free_gb': round(usage.free / (1024 ** 3), 1),
                'percent': round(usage.percent, 1)
            }

        except Exception as e:
            logger.debug(f"Could not get disk info for {path}: {e}")
            return {'total_gb': 0, 'used_gb': 0, 'free_gb': 0, 'percent': 0}

    # =========================================================================
    # SYSTEM MONITOR
    # =========================================================================

    def get_cpu_usage(self) -> Dict[str, Any]:
        """Get CPU usage percentage (non-blocking, uses psutil internal state)"""
        try:
            percent = psutil.cpu_percent(interval=None)
            per_cpu = psutil.cpu_percent(interval=None, percpu=True)
            count = psutil.cpu_count(logical=True)
            return {
                'percent': round(percent, 1),
                'per_cpu': [round(p, 1) for p in per_cpu],
                'count': count or 0
            }
        except Exception as e:
            logger.debug(f"Could not get CPU usage: {e}")
            return {'percent': 0, 'per_cpu': [], 'count': 0}

    def get_cpu_temperature(self) -> Optional[float]:
        """Get CPU temperature from /sys/class/hwmon.
        Priority: coretemp (Intel) > k10temp/k8temp (AMD) > cpu_thermal (ARM) > acpitz (ACPI fallback)
        """
        try:
            hwmon_base = '/sys/class/hwmon'
            driver_priority = {'coretemp': 0, 'k10temp': 1, 'k8temp': 1, 'cpu_thermal': 2, 'acpitz': 3}
            best_priority = 999
            best_temp = None

            if os.path.exists(hwmon_base):
                for hwmon in os.listdir(hwmon_base):
                    hwmon_path = os.path.join(hwmon_base, hwmon)
                    name_file = os.path.join(hwmon_path, 'name')
                    if not os.path.exists(name_file):
                        continue
                    with open(name_file, 'r') as f:
                        name = f.read().strip()
                    priority = driver_priority.get(name)
                    if priority is not None and priority < best_priority:
                        temp_file = os.path.join(hwmon_path, 'temp1_input')
                        if os.path.exists(temp_file):
                            with open(temp_file, 'r') as f:
                                best_temp = round(int(f.read().strip()) / 1000, 1)
                            best_priority = priority

            return best_temp
        except Exception as e:
            logger.debug(f"Could not get CPU temperature: {e}")
            return None

    def get_gpu_info(self) -> Optional[Dict[str, Any]]:
        """Get GPU utilization, memory, and temperature from nvidia-smi (single call).
        Returns None if NVIDIA GPU is not available.
        """
        try:
            result = subprocess.run(
                ['nvidia-smi',
                 '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None

            parts = result.stdout.strip().split('\n')[0].split(',')
            if len(parts) < 5:
                return None

            util = int(parts[0].strip())
            mem_used = int(parts[1].strip())
            mem_total = int(parts[2].strip())
            temp = int(parts[3].strip())
            name = parts[4].strip()

            return {
                'name': name,
                'utilization': util,
                'memory_used_mb': mem_used,
                'memory_total_mb': mem_total,
                'memory_percent': int((mem_used / mem_total) * 100) if mem_total > 0 else 0,
                'temperature': temp,
            }
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        except Exception as e:
            logger.debug(f"Could not get GPU info: {e}")
            return None

    def get_network_throughput(self) -> Dict[str, Any]:
        """Get network throughput (bytes/sec) from psutil counters"""
        global _prev_net_bytes

        try:
            counters = psutil.net_io_counters()
            now = time.time()

            rx_bytes = counters.bytes_recv
            tx_bytes = counters.bytes_sent

            elapsed = now - _prev_net_bytes['timestamp']

            if _prev_net_bytes['timestamp'] > 0 and elapsed > 0:
                rx_speed = (rx_bytes - _prev_net_bytes['rx']) / elapsed
                tx_speed = (tx_bytes - _prev_net_bytes['tx']) / elapsed
            else:
                rx_speed = 0
                tx_speed = 0

            _prev_net_bytes = {'rx': rx_bytes, 'tx': tx_bytes, 'timestamp': now}

            return {
                'rx_speed': round(max(rx_speed, 0)),
                'tx_speed': round(max(tx_speed, 0)),
                'rx_total': rx_bytes,
                'tx_total': tx_bytes,
            }
        except Exception as e:
            logger.debug(f"Could not get network throughput: {e}")
            return {'rx_speed': 0, 'tx_speed': 0, 'rx_total': 0, 'tx_total': 0}

    def get_network_history(self, hours: int = 24) -> Dict[str, Any]:
        """Get network history from netmon SQLite database.

        netmon schema (traffic table):
            id INTEGER PRIMARY KEY AUTOINCREMENT
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            app_name TEXT
            remote_ip TEXT
            bytes_sent INTEGER
            bytes_recv INTEGER
        """
        result = {'available': False, 'data': [], 'error': None}

        if not os.path.exists(NETMON_DB_PATH):
            result['error'] = 'netmon database not found'
            return result

        try:
            conn = sqlite3.connect(NETMON_DB_PATH, timeout=3)
            cursor = conn.cursor()

            # Query aggregated traffic per time bucket
            # strftime('%s', timestamp) converts DATETIME text to Unix epoch
            cursor.execute(
                "SELECT strftime('%s', timestamp) AS ts, "
                "       SUM(bytes_recv) AS rx, "
                "       SUM(bytes_sent) AS tx "
                "FROM traffic "
                "WHERE timestamp > datetime('now', ? || ' hours') "
                "GROUP BY strftime('%Y-%m-%d %H:%M', timestamp) "
                "ORDER BY ts ASC",
                (str(-hours),)
            )
            rows = cursor.fetchall()

            data_points = []
            for row in rows:
                ts, rx, tx = row
                if ts is not None:
                    data_points.append({
                        'time': int(ts),
                        'rx': rx or 0,
                        'tx': tx or 0
                    })

            result['available'] = len(data_points) > 0
            result['data'] = data_points
            conn.close()

        except sqlite3.Error as e:
            result['error'] = f'Database error: {str(e)}'
        except Exception as e:
            result['error'] = f'Error: {str(e)}'

        return result

    def get_network_details(self, hours: int = 24) -> Dict[str, Any]:
        """Get detailed network usage by application from netmon database"""
        result = {
            'available': False,
            'time_range': None,
            'total_rx': 0,
            'total_tx': 0,
            'top_apps': [],
            'error': None
        }

        if not os.path.exists(NETMON_DB_PATH):
            result['error'] = 'netmon database not found'
            return result

        try:
            conn = sqlite3.connect(NETMON_DB_PATH, timeout=3)
            cursor = conn.cursor()

            # Get time range of available data (max 24 hours)
            cursor.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM traffic "
                "WHERE timestamp > datetime('now', ? || ' hours')",
                (str(-hours),)
            )
            min_ts, max_ts = cursor.fetchone()

            if not min_ts or not max_ts:
                result['error'] = 'No data available'
                conn.close()
                return result

            # Calculate actual hours of data
            cursor.execute(
                "SELECT (julianday(?) - julianday(?)) * 24",
                (max_ts, min_ts)
            )
            actual_hours = cursor.fetchone()[0] or 0
            actual_hours = min(round(actual_hours, 1), hours)

            # Format time range string
            if actual_hours < 1:
                result['time_range'] = f"Last {int(actual_hours * 60)} minutes"
            elif actual_hours >= 24:
                result['time_range'] = "Last 24 hours"
            else:
                result['time_range'] = f"Last {int(actual_hours)} hours"

            # Get totals
            cursor.execute(
                "SELECT SUM(bytes_recv), SUM(bytes_sent) FROM traffic "
                "WHERE timestamp > datetime('now', ? || ' hours')",
                (str(-hours),)
            )
            total_rx, total_tx = cursor.fetchone()
            result['total_rx'] = total_rx or 0
            result['total_tx'] = total_tx or 0

            # Get top apps by usage
            cursor.execute(
                "SELECT app_name, "
                "       SUM(bytes_recv) as rx, "
                "       SUM(bytes_sent) as tx "
                "FROM traffic "
                "WHERE timestamp > datetime('now', ? || ' hours') "
                "AND app_name IS NOT NULL AND app_name != '' "
                "GROUP BY app_name "
                "ORDER BY (rx + tx) DESC "
                "LIMIT 10",
                (str(-hours),)
            )

            top_apps = []
            for row in cursor.fetchall():
                app_name, rx, tx = row
                if rx or tx:
                    top_apps.append({
                        'name': app_name[:30] if app_name else 'unknown',
                        'rx': rx or 0,
                        'tx': tx or 0
                    })

            result['top_apps'] = top_apps
            result['available'] = len(top_apps) > 0
            conn.close()

        except sqlite3.Error as e:
            result['error'] = f'Database error: {str(e)}'
        except Exception as e:
            result['error'] = f'Error: {str(e)}'

        return result

    def get_system_monitor(self) -> Dict[str, Any]:
        """Collect all system monitor data for the dashboard"""
        disk_data = {'root': self.get_disk_info('/')}

        # Add /data partition if it exists as a separate mount
        if os.path.ismount('/data'):
            disk_data['data'] = self.get_disk_info('/data')

        # GPU info (single nvidia-smi call for utilization + memory + temp)
        gpu_info = self.get_gpu_info()

        # Build temperatures from CPU hwmon + GPU info
        temperatures = {
            'cpu': self.get_cpu_temperature(),
            'gpu': gpu_info['temperature'] if gpu_info else None,
        }

        return {
            'cpu': self.get_cpu_usage(),
            'memory': self.get_memory_info(),
            'disk': disk_data,
            'gpu': gpu_info,
            'temperatures': temperatures,
            'network': self.get_network_throughput(),
        }

    # =========================================================================
    # MONITOR DETAIL METHODS
    # =========================================================================

    # Generic process names that need cmdline for better identification
    GENERIC_PROCESS_NAMES = {
        'MainThread', 'python', 'python3', 'python3.10', 'python3.11', 'python3.12',
        'node', 'ruby', 'perl', 'java', 'php'
    }

    def _get_process_display_name(self, name: str, cmdline: list) -> str:
        """Get a meaningful display name for a process.

        For generic names like 'MainThread' or 'python3', extract a better name
        from cmdline. For specific names like 'chrome', return as-is.
        """
        name = name or 'unknown'

        # If name is specific enough, use it
        if name not in self.GENERIC_PROCESS_NAMES:
            return name

        # Try to get better name from cmdline
        if not cmdline or len(cmdline) < 1:
            return name

        # Get executable name from first element
        exe = os.path.basename(cmdline[0])

        # If there's a second argument (script/file), include it
        if len(cmdline) >= 2:
            script = os.path.basename(cmdline[1])
            # Skip flags (starts with -)
            if not script.startswith('-'):
                return f"{exe} ({script})"

        return exe

    def get_cpu_details(self) -> Dict[str, Any]:
        """Get detailed CPU information for modal view"""
        try:
            # Per-core usage
            per_cpu = psutil.cpu_percent(interval=None, percpu=True)

            # Load average (1, 5, 15 min)
            load_avg = os.getloadavg()

            # CPU frequency
            freq = psutil.cpu_freq()
            frequency = {
                'current': round(freq.current, 0) if freq else None,
                'min': round(freq.min, 0) if freq and freq.min else None,
                'max': round(freq.max, 0) if freq and freq.max else None,
            }

            # Top 5 CPU consuming processes
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent']):
                try:
                    cpu_pct = proc.info.get('cpu_percent') or 0
                    if cpu_pct > 0:
                        processes.append({
                            'pid': proc.info['pid'],
                            'name': self._get_process_display_name(
                                proc.info['name'],
                                proc.info.get('cmdline')
                            )[:30],
                            'cpu_percent': round(cpu_pct, 1)
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            # Sort by CPU and take top 5
            processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
            processes = processes[:5]

            return {
                'overall_percent': round(psutil.cpu_percent(interval=None), 1),
                'per_cpu': [round(p, 1) for p in per_cpu],
                'core_count': psutil.cpu_count(logical=True) or 0,
                'physical_cores': psutil.cpu_count(logical=False) or 0,
                'load_avg': {
                    '1min': round(load_avg[0], 2),
                    '5min': round(load_avg[1], 2),
                    '15min': round(load_avg[2], 2),
                },
                'frequency': frequency,
                'top_processes': processes
            }
        except Exception as e:
            logger.error(f"Could not get CPU details: {e}")
            return {'error': str(e)}

    def get_memory_details(self) -> Dict[str, Any]:
        """Get detailed memory information for modal view"""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Top 5 memory consuming processes
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_percent', 'memory_info']):
                try:
                    mem_pct = proc.info.get('memory_percent') or 0
                    if mem_pct > 0:
                        mem_info = proc.info.get('memory_info')
                        rss_mb = round(mem_info.rss / (1024 * 1024), 1) if mem_info else 0
                        processes.append({
                            'pid': proc.info['pid'],
                            'name': self._get_process_display_name(
                                proc.info['name'],
                                proc.info.get('cmdline')
                            )[:30],
                            'memory_percent': round(mem_pct, 1),
                            'memory_mb': rss_mb
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            # Sort by memory and take top 5
            processes.sort(key=lambda x: x['memory_percent'], reverse=True)
            processes = processes[:5]

            return {
                'total_mb': round(mem.total / (1024 * 1024)),
                'used_mb': round(mem.used / (1024 * 1024)),
                'available_mb': round(mem.available / (1024 * 1024)),
                'percent': round(mem.percent, 1),
                'buffers_mb': round(getattr(mem, 'buffers', 0) / (1024 * 1024)),
                'cached_mb': round(getattr(mem, 'cached', 0) / (1024 * 1024)),
                'swap': {
                    'total_mb': round(swap.total / (1024 * 1024)),
                    'used_mb': round(swap.used / (1024 * 1024)),
                    'percent': round(swap.percent, 1)
                },
                'top_processes': processes
            }
        except Exception as e:
            logger.error(f"Could not get memory details: {e}")
            return {'error': str(e)}

    def get_gpu_details(self) -> Dict[str, Any]:
        """Get detailed GPU utilization information for modal view"""
        try:
            # Basic GPU info
            result = subprocess.run(
                ['nvidia-smi',
                 '--query-gpu=utilization.gpu,utilization.memory,temperature.gpu,power.draw,name,driver_version',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return {'available': False, 'error': 'nvidia-smi failed'}

            parts = result.stdout.strip().split(',')
            if len(parts) < 6:
                return {'available': False, 'error': 'Invalid nvidia-smi output'}

            gpu_util = int(parts[0].strip())
            mem_util = int(parts[1].strip())
            temp = int(parts[2].strip())
            power = parts[3].strip()
            name = parts[4].strip()
            driver = parts[5].strip()

            # Get all GPU processes (Compute + Graphics) with pmon
            # Format: # gpu  pid  type  sm  mem  enc  dec  jpg  ofa  command
            pmon_result = subprocess.run(
                ['nvidia-smi', 'pmon', '-c', '1', '-s', 'u'],
                capture_output=True, text=True, timeout=5
            )

            processes = []
            if pmon_result.returncode == 0:
                for line in pmon_result.stdout.strip().split('\n'):
                    if line.startswith('#') or not line.strip():
                        continue
                    pmon_parts = line.split()
                    if len(pmon_parts) >= 4:
                        try:
                            pid = int(pmon_parts[1])
                            proc_type = pmon_parts[2]  # C=Compute, G=Graphics
                            sm_util = pmon_parts[3]
                            command = pmon_parts[-1] if len(pmon_parts) > 4 else 'unknown'

                            processes.append({
                                'pid': pid,
                                'name': command[:30],
                                'type': proc_type,
                                'gpu_percent': int(sm_util) if sm_util != '-' else None
                            })
                        except (ValueError, IndexError):
                            continue

            # Sort by gpu_percent descending (None values at end)
            processes.sort(key=lambda x: (x['gpu_percent'] is None, -(x['gpu_percent'] or 0)))
            processes = processes[:5]

            return {
                'available': True,
                'name': name,
                'driver_version': driver,
                'utilization': gpu_util,
                'memory_utilization': mem_util,
                'temperature': temp,
                'power_draw': power if power not in ('[N/A]', 'N/A', '') else None,
                'top_processes': processes
            }
        except FileNotFoundError:
            return {'available': False, 'error': 'NVIDIA GPU not available'}
        except subprocess.TimeoutExpired:
            return {'available': False, 'error': 'nvidia-smi timeout'}
        except Exception as e:
            logger.error(f"Could not get GPU details: {e}")
            return {'available': False, 'error': str(e)}

    def get_vram_details(self) -> Dict[str, Any]:
        """Get detailed VRAM usage information for modal view"""
        try:
            # VRAM totals
            result = subprocess.run(
                ['nvidia-smi',
                 '--query-gpu=memory.total,memory.used,memory.free,name',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return {'available': False, 'error': 'nvidia-smi failed'}

            parts = result.stdout.strip().split(',')
            if len(parts) < 4:
                return {'available': False, 'error': 'Invalid nvidia-smi output'}

            total = int(parts[0].strip())
            used = int(parts[1].strip())
            free = int(parts[2].strip())
            name = parts[3].strip()

            # Get all GPU processes (Compute + Graphics) with pmon -s m for memory info
            # Format: # gpu  pid  type  fb  ccpm  command
            pmon_result = subprocess.run(
                ['nvidia-smi', 'pmon', '-c', '1', '-s', 'm'],
                capture_output=True, text=True, timeout=5
            )

            processes = []
            if pmon_result.returncode == 0:
                for line in pmon_result.stdout.strip().split('\n'):
                    if line.startswith('#') or not line.strip():
                        continue
                    pmon_parts = line.split()
                    # Format: gpu, pid, type, fb, ccpm, command
                    if len(pmon_parts) >= 6:
                        try:
                            pid = int(pmon_parts[1])
                            proc_type = pmon_parts[2]  # C=Compute, G=Graphics
                            fb_val = pmon_parts[3]     # fb (VRAM) in MB
                            command = pmon_parts[-1]

                            fb_mb = int(fb_val) if fb_val != '-' else None
                            mem_percent = round((fb_mb / total) * 100, 1) if fb_mb and total > 0 else 0

                            processes.append({
                                'pid': pid,
                                'name': command[:30],
                                'type': proc_type,
                                'memory_mb': fb_mb,
                                'memory_percent': mem_percent
                            })
                        except (ValueError, IndexError):
                            continue

            # Sort by memory_mb descending (None values at end)
            processes.sort(key=lambda x: (x['memory_mb'] is None, -(x['memory_mb'] or 0)))
            processes = processes[:5]

            return {
                'available': True,
                'gpu_name': name,
                'total_mb': total,
                'used_mb': used,
                'free_mb': free,
                'percent': round((used / total) * 100, 1) if total > 0 else 0,
                'top_processes': processes
            }
        except FileNotFoundError:
            return {'available': False, 'error': 'NVIDIA GPU not available'}
        except subprocess.TimeoutExpired:
            return {'available': False, 'error': 'nvidia-smi timeout'}
        except Exception as e:
            logger.error(f"Could not get VRAM details: {e}")
            return {'available': False, 'error': str(e)}

    def _get_top_io_processes(self, limit: int = 5) -> list:
        """Get top I/O consuming processes from /proc/[pid]/io"""
        processes = []

        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pid = proc.info['pid']
                io_path = f'/proc/{pid}/io'
                if not os.path.exists(io_path):
                    continue

                with open(io_path, 'r') as f:
                    io_data = {}
                    for line in f:
                        parts = line.strip().split(': ')
                        if len(parts) == 2:
                            io_data[parts[0]] = int(parts[1])

                read_bytes = io_data.get('read_bytes', 0)
                write_bytes = io_data.get('write_bytes', 0)

                if read_bytes > 0 or write_bytes > 0:
                    processes.append({
                        'pid': pid,
                        'name': self._get_process_display_name(
                            proc.info['name'],
                            proc.info.get('cmdline')
                        )[:30],
                        'read_bytes': read_bytes,
                        'write_bytes': write_bytes
                    })
            except (PermissionError, FileNotFoundError, psutil.NoSuchProcess,
                    psutil.AccessDenied, ValueError, KeyError):
                continue

        processes.sort(key=lambda x: x['read_bytes'] + x['write_bytes'], reverse=True)
        return processes[:limit]

    def _get_largest_directories(self, path: str = '/', limit: int = 5) -> list:
        """Get largest directories using du command"""
        try:
            result = subprocess.run(
                ['du', '-b', '--max-depth=1', path],
                capture_output=True,
                text=True,
                timeout=30
            )

            # Virtual/special directories to skip
            skip_dirs = {'/proc', '/sys', '/dev', '/run', '/snap', '/tmp', '/lost+found'}

            directories = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) == 2:
                    try:
                        size_bytes = int(parts[0])
                        dir_path = parts[1]
                        # Skip root path, virtual dirs, and very small directories
                        if dir_path != path and dir_path not in skip_dirs and size_bytes > 1024 * 1024:
                            directories.append({
                                'path': dir_path,
                                'size_bytes': size_bytes,
                                'size_gb': round(size_bytes / (1024**3), 1)
                            })
                    except ValueError:
                        continue

            directories.sort(key=lambda x: x['size_bytes'], reverse=True)
            return directories[:limit]

        except (subprocess.TimeoutExpired, Exception) as e:
            logger.warning(f"Could not get directory sizes: {e}")
            return []

    def get_disk_details(self) -> Dict[str, Any]:
        """Get detailed disk information for modal view"""
        try:
            partitions = []
            total_size = 0
            total_used = 0

            for part in psutil.disk_partitions(all=False):
                if part.fstype in ('squashfs', 'overlay', 'tmpfs', 'devtmpfs'):
                    continue
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    total_size += usage.total
                    total_used += usage.used
                    partitions.append({
                        'device': part.device,
                        'mountpoint': part.mountpoint,
                        'fstype': part.fstype,
                        'total_gb': round(usage.total / (1024**3), 1),
                        'used_gb': round(usage.used / (1024**3), 1),
                        'free_gb': round(usage.free / (1024**3), 1),
                        'percent': usage.percent
                    })
                except (PermissionError, OSError):
                    continue

            partitions.sort(key=lambda x: x['percent'], reverse=True)

            io = psutil.disk_io_counters()
            io_stats = {
                'read_bytes': io.read_bytes if io else 0,
                'write_bytes': io.write_bytes if io else 0,
                'read_count': io.read_count if io else 0,
                'write_count': io.write_count if io else 0,
            }

            io_processes = self._get_top_io_processes()
            largest_dirs = self._get_largest_directories('/')
            overall_percent = round((total_used / total_size * 100), 1) if total_size > 0 else 0

            return {
                'overall_percent': overall_percent,
                'total_gb': round(total_size / (1024**3), 1),
                'used_gb': round(total_used / (1024**3), 1),
                'free_gb': round((total_size - total_used) / (1024**3), 1),
                'partitions': partitions,
                'io_stats': io_stats,
                'largest_directories': largest_dirs,
                'top_processes': io_processes
            }
        except Exception as e:
            logger.error(f"Could not get disk details: {e}")
            return {'error': str(e)}

    # =========================================================================
    # HOSTNAME MANAGEMENT
    # =========================================================================

    def set_hostname(self, hostname: str) -> dict:
        """
        Set system hostname and update /etc/hosts.

        Args:
            hostname: New hostname (lowercase, RFC 1123 compliant)

        Returns:
            {'success': bool, 'error': str|None}
        """
        import re

        # 1. VALIDATION
        if not hostname:
            return {'success': False, 'error': 'Hostname cannot be empty'}

        if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$', hostname):
            return {'success': False, 'error': 'Invalid hostname format (RFC 1123)'}

        if len(hostname) > 63:
            return {'success': False, 'error': 'Hostname too long (max 63 chars)'}

        # 2. BACKUP
        backup = self._backup_hostname_state()

        # 3. APPLY
        try:
            # Set hostname via hostnamectl
            result = subprocess.run(
                ['hostnamectl', 'set-hostname', hostname],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, 'hostnamectl', result.stderr)

            # Update /etc/hosts
            self._update_hosts_file(hostname)

            logger.info(f"Hostname changed to: {hostname}")
            return {'success': True, 'error': None}

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, IOError) as e:
            error_msg = f"Hostname change failed: {e}"
            logger.error(error_msg)

            # 4. ROLLBACK
            if self._rollback_hostname(backup):
                return {'success': False, 'error': f'{error_msg} (restored)'}
            else:
                return {'success': False, 'error': f'{error_msg} (WARNING: rollback failed!)'}

    def _backup_hostname_state(self) -> dict:
        """Backup current hostname and /etc/hosts"""
        backup = {}
        try:
            result = subprocess.run(['hostname'], capture_output=True, text=True, timeout=5)
            backup['hostname'] = result.stdout.strip()

            if os.path.exists('/etc/hosts'):
                with open('/etc/hosts', 'r') as f:
                    backup['hosts'] = f.read()
        except Exception as e:
            logger.debug(f"Hostname backup warning: {e}")
        return backup

    def _update_hosts_file(self, hostname: str) -> None:
        """Update /etc/hosts with new hostname"""
        import re
        hosts_path = '/etc/hosts'

        with open(hosts_path, 'r') as f:
            content = f.read()

        # Replace existing 127.0.1.1 line
        new_content = re.sub(
            r'^127\.0\.1\.1\s+.*$',
            f'127.0.1.1\t{hostname}',
            content,
            flags=re.MULTILINE
        )

        # Add if not exists
        if '127.0.1.1' not in new_content:
            new_content = re.sub(
                r'^(127\.0\.0\.1\s+localhost.*)$',
                f'\\1\n127.0.1.1\t{hostname}',
                new_content,
                flags=re.MULTILINE
            )

        with open(hosts_path, 'w') as f:
            f.write(new_content)

    def _rollback_hostname(self, backup: dict) -> bool:
        """Restore hostname from backup"""
        try:
            if 'hostname' in backup and backup['hostname']:
                subprocess.run(
                    ['hostnamectl', 'set-hostname', backup['hostname']],
                    check=True, timeout=10
                )
            if 'hosts' in backup:
                with open('/etc/hosts', 'w') as f:
                    f.write(backup['hosts'])
            return True
        except Exception as e:
            logger.warning(f"Hostname rollback failed: {e}")
            return False

    # =========================================================================
    # TEMPORARY IP MANAGEMENT
    # =========================================================================

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
