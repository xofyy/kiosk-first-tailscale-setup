"""
Kiosk Setup Panel - Hardware Service
Hardware ID üretimi
"""

import subprocess
import hashlib
from typing import Dict, Optional

# Absolute paths for system commands (PATH'te /usr/sbin olmayabilir)
DMIDECODE = '/usr/sbin/dmidecode'
LSBLK = '/usr/bin/lsblk'
UDEVADM = '/usr/bin/udevadm'
HDPARM = '/usr/sbin/hdparm'


class HardwareService:
    """Hardware ID üretimi ve donanım bilgileri"""
    
    def get_hardware_id(self) -> str:
        """
        Benzersiz Hardware ID üret.
        Anakart, RAM ve disk seri numaralarından oluşturulur.
        """
        components = self.get_components()
        
        # Bileşen değerlerini birleştir
        combined = '|'.join([
            components.get('motherboard_serial', ''),
            components.get('ram_serial', ''),
            components.get('disk_serial', '')
        ])
        
        # SHA256 hash al ve ilk 16 karakteri kullan
        if combined.strip('|'):
            hash_obj = hashlib.sha256(combined.encode())
            return hash_obj.hexdigest()[:16].upper()
        
        return ''
    
    def get_components(self) -> Dict[str, str]:
        """Donanım bileşen bilgilerini al"""
        return {
            'motherboard_serial': self._get_motherboard_serial(),
            'ram_serial': self._get_ram_serial(),
            'disk_serial': self._get_disk_serial()
        }
    
    def _get_motherboard_serial(self) -> str:
        """Anakart seri numarasını al"""
        try:
            result = subprocess.run(
                [DMIDECODE, '-s', 'baseboard-serial-number'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                serial = result.stdout.strip()
                # Geçersiz değerleri filtrele
                if serial and serial.lower() not in ['not specified', 'to be filled', 'default string', 'n/a']:
                    return serial
        except Exception:
            pass
        
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
        except Exception:
            pass
        
        return ''
    
    def _get_ram_serial(self) -> str:
        """RAM seri numarasını al (ilk modül)"""
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
                        if serial and serial.lower() not in ['not specified', 'unknown', 'n/a']:
                            return serial
        except Exception:
            pass
        
        return ''
    
    def _get_disk_serial(self) -> str:
        """Ana disk seri numarasını al"""
        try:
            # lsblk ile root disk'i bul
            result = subprocess.run(
                [LSBLK, '-no', 'PKNAME', '/'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                disk = result.stdout.strip()
                
                if disk:
                    # udevadm ile seri numarasını al
                    result = subprocess.run(
                        [UDEVADM, 'info', '--query=property', f'--name=/dev/{disk}'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if line.startswith('ID_SERIAL=') or line.startswith('ID_SERIAL_SHORT='):
                                serial = line.split('=')[1].strip()
                                if serial:
                                    return serial
        except Exception:
            pass
        
        # Alternatif: hdparm
        try:
            result = subprocess.run(
                [HDPARM, '-I', '/dev/sda'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Serial Number:' in line:
                        return line.split(':')[1].strip()
        except Exception:
            pass
        
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
        except Exception:
            pass
        
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
        except Exception:
            pass
        
        return info
    
    def get_motherboard_uuid(self) -> str:
        """Anakart UUID'sini al"""
        try:
            with open('/sys/class/dmi/id/product_uuid', 'r') as f:
                return f.read().strip()
        except Exception:
            pass
        return ''
    
    def get_mac_addresses(self) -> str:
        """Tüm network interface MAC adreslerini al (virgülle ayrılmış)"""
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
                    # 'link/ether XX:XX:XX:XX:XX:XX' formatı
                    if 'link/ether' in line:
                        parts = line.split()
                        for i, p in enumerate(parts):
                            if p == 'link/ether' and i + 1 < len(parts):
                                macs.append(parts[i + 1])
                                break
                return ','.join(macs)
        except Exception:
            pass
        return ''
