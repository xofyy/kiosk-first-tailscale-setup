"""
Kiosk Setup Panel - Hardware Service
Hardware ID generation
"""

import subprocess
import hashlib
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Absolute paths for system commands (/usr/sbin may not be in PATH)
DMIDECODE = '/usr/sbin/dmidecode'
LSBLK = '/usr/bin/lsblk'
UDEVADM = '/usr/bin/udevadm'
HDPARM = '/usr/sbin/hdparm'


class HardwareService:
    """Hardware ID generation and hardware information"""

    def get_hardware_id(self) -> str:
        """
        Generate unique Hardware ID.
        Created from motherboard, RAM and disk serial numbers.
        Format: MOBO_SERIAL:xxx|RAM_SERIALS:xxx|DISK_SERIALS:xxx
        """
        components = self.get_components()

        mb = components.get('motherboard_serial', '')
        ram = components.get('ram_serials', '')
        disk = components.get('disk_serials', '')

        # SHA256 format (compatible with old script)
        sha_input = f"MOBO_SERIAL:{mb}|RAM_SERIALS:{ram}|DISK_SERIALS:{disk}"
        
        # SHA256 hash al ve ilk 16 karakteri kullan (lowercase)
        if mb or ram or disk:
            return hashlib.sha256(sha_input.encode()).hexdigest()[:16]
        
        return ''
    
    def get_components(self) -> Dict[str, str]:
        """Get hardware component information"""
        return {
            'motherboard_serial': self._get_motherboard_serial(),
            'ram_serials': self._get_ram_serials(),
            'disk_serials': self._get_disk_serials()
        }
    
    def _get_motherboard_serial(self) -> str:
        """Get motherboard serial number"""
        try:
            result = subprocess.run(
                [DMIDECODE, '-s', 'baseboard-serial-number'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                serial = result.stdout.strip()
                # Filter invalid values
                if serial and serial.lower() not in ['not specified', 'to be filled', 'default string', 'n/a']:
                    return serial
        except Exception as e:
            logger.debug(f"Could not get motherboard serial: {e}")
        
        # Alternatif: system UUID
        try:
            result = subprocess.run(
                [DMIDECODE, '-s', 'system-uuid'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Could not get system UUID: {e}")
        
        return ''
    
    def _get_ram_serials(self) -> str:
        """Get all RAM module serial numbers (comma-separated)"""
        serials = []
        try:
            result = subprocess.run(
                [DMIDECODE, '-t', 'memory'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Serial Number:' in line:
                        serial = line.split(':')[1].strip()
                        if serial and serial.lower() not in ['not specified', 'unknown', 'n/a', 'no dimm']:
                            serials.append(serial)
        except Exception as e:
            logger.debug(f"Could not get RAM serials: {e}")
        
        return ','.join(serials) if serials else ''
    
    def _get_disk_serials(self) -> str:
        """Get all physical disk serial numbers (comma-separated, sorted)"""
        serials = []

        # Get all disk serials via lsblk (excluding loop=7, ram=1)
        try:
            result = subprocess.run(
                [LSBLK, '-dno', 'NAME,SERIAL', '--exclude', '7,1'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if not line.strip():
                        continue
                    parts = line.split(None, 1)  # Split only at first space
                    if len(parts) >= 2:
                        serial = parts[1].strip()
                        if serial and serial.lower() not in ['n/a', 'unknown', '']:
                            serials.append(serial)
        except Exception as e:
            logger.debug(f"Could not get disk serials (lsblk): {e}")
        
        # Fallback: udevadm ile dene (lsblk serial vermezse)
        if not serials:
            try:
                result = subprocess.run(
                    [LSBLK, '-dno', 'NAME', '--exclude', '7,1'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    for disk_name in result.stdout.strip().split('\n'):
                        disk_name = disk_name.strip()
                        if not disk_name:
                            continue
                        
                        udev_result = subprocess.run(
                            [UDEVADM, 'info', '--query=property', f'--name=/dev/{disk_name}'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        
                        if udev_result.returncode == 0:
                            for prop_line in udev_result.stdout.split('\n'):
                                if prop_line.startswith('ID_SERIAL_SHORT='):
                                    serial = prop_line.split('=')[1].strip()
                                    if serial:
                                        serials.append(serial)
                                        break
            except Exception as e:
                logger.debug(f"Could not get disk serials (udevadm): {e}")

        # Sort (for consistency) and join
        if serials:
            serials.sort()
            return ','.join(serials)
        
        return ''
    
    def get_gpu_info(self) -> Optional[Dict[str, str]]:
        """NVIDIA GPU bilgisini al"""
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                parts = result.stdout.strip().split(', ')
                if len(parts) >= 3:
                    return {
                        'name': parts[0],
                        'driver': parts[1],
                        'memory': parts[2]
                    }
        except Exception as e:
            logger.debug(f"Could not get GPU info: {e}")
        
        return None
    
    def get_cpu_info(self) -> Dict[str, str]:
        """CPU bilgisini al"""
        info = {
            'model': 'Unknown',
            'cores': '0'
        }
        
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('model name'):
                        info['model'] = line.split(':')[1].strip()
                    elif line.startswith('cpu cores'):
                        info['cores'] = line.split(':')[1].strip()
        except Exception as e:
            logger.debug(f"Could not get CPU info: {e}")
        
        return info
    
    def get_motherboard_uuid(self) -> str:
        """Get motherboard UUID"""
        try:
            with open('/sys/class/dmi/id/product_uuid', 'r') as f:
                return f.read().strip()
        except Exception as e:
            logger.debug(f"Could not get motherboard UUID: {e}")
        return ''

    def get_mac_addresses(self) -> str:
        """Get all network interface MAC addresses (comma-separated)"""
        try:
            result = subprocess.run(
                ['ip', 'link', 'show'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                macs = []
                for line in result.stdout.split('\n'):
                    # 'link/ether XX:XX:XX:XX:XX:XX' format
                    if 'link/ether' in line:
                        parts = line.split()
                        for i, p in enumerate(parts):
                            if p == 'link/ether' and i + 1 < len(parts):
                                macs.append(parts[i + 1])
                                break
                return ','.join(macs)
        except Exception as e:
            logger.debug(f"Could not get MAC addresses: {e}")
        return ''
