"""
Kiosk Setup Panel - System Service
Sistem bilgileri ve yardımcı fonksiyonlar
"""

import subprocess
import socket
import os
from typing import Dict, Any, Optional


class SystemService:
    """Sistem bilgileri ve operasyonları"""
    
    def get_system_info(self) -> Dict[str, Any]:
        """Tüm sistem bilgilerini topla"""
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
        Internet kontrolü YAPMADAN hızlı sistem bilgisi.
        Tab geçişlerini bloke etmez. Internet bilgileri JS ile async güncellenir.
        
        Internet yokken sayfa geçişlerinin yavaşlamasını önler.
        """
        return {
            'hostname': self.get_hostname(),
            'ip_address': None,  # JS güncelleyecek
            'tailscale_ip': None,  # JS güncelleyecek
            'internet': None,  # JS güncelleyecek
            'dns_working': None,  # JS güncelleyecek
            'interfaces': self.get_network_interfaces(),  # Bu hızlı (local)
            'uptime': self.get_uptime(),  # Bu hızlı (/proc okuma)
            'memory': self.get_memory_info(),  # Bu hızlı (/proc okuma)
            'disk': self.get_disk_info(),  # Bu hızlı (statvfs)
        }
    
    def get_hostname(self) -> str:
        """Hostname'i al"""
        return socket.gethostname()
    
    def get_ip_address(self) -> Optional[str]:
        """Ana IP adresini al"""
        try:
            # Default route üzerinden IP al
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.3)  # 300ms timeout - hızlı UI güncellemesi için
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None
    
    def get_tailscale_ip(self) -> Optional[str]:
        """Tailscale IP adresini al"""
        try:
            result = subprocess.run(
                ['tailscale', 'ip', '-4'],
                capture_output=True,
                text=True,
                timeout=0.5  # 500ms timeout - hızlı UI güncellemesi için
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
    
    def get_network_interfaces(self) -> Dict[str, Dict[str, str]]:
        """Ağ arayüzlerini listele"""
        interfaces = {}
        
        try:
            # ip addr ile arayüzleri al
            result = subprocess.run(
                ['ip', '-j', 'addr'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                
                for iface in data:
                    name = iface.get('ifname', '')
                    
                    # lo ve docker arayüzlerini atla
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
                    
        except Exception:
            pass
        
        return interfaces
    
    def check_internet(self) -> bool:
        """İnternet bağlantısını kontrol et"""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=0.3)  # 300ms timeout
            return True
        except OSError:
            return False
    
    def check_dns(self) -> bool:
        """DNS çözümleme kontrolü"""
        try:
            socket.setdefaulttimeout(0.3)  # 300ms timeout
            socket.gethostbyname("google.com")
            return True
        except (socket.error, socket.timeout):
            return False
        finally:
            socket.setdefaulttimeout(None)
    
    def get_uptime(self) -> str:
        """Sistem uptime'ını al"""
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
                
        except Exception:
            return "N/A"
    
    def get_memory_info(self) -> Dict[str, Any]:
        """Bellek bilgisini al"""
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
            
        except Exception:
            return {'total_mb': 0, 'used_mb': 0, 'free_mb': 0, 'percent': 0}
    
    def get_disk_info(self) -> Dict[str, Any]:
        """Disk bilgisini al (root partition)"""
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
            
        except Exception:
            return {'total_gb': 0, 'used_gb': 0, 'free_gb': 0, 'percent': 0}
    
    def set_temporary_ip(
        self,
        interface: str,
        ip: str,
        netmask: str,
        gateway: str,
        dns: str
    ) -> bool:
        """
        Geçici statik IP ayarla.
        Bu ayar NetworkManager kurulana kadar geçerlidir.
        """
        try:
            # IP ayarla
            subprocess.run(
                ['ip', 'addr', 'flush', 'dev', interface],
                check=True
            )
            
            # CIDR hesapla
            cidr = self._netmask_to_cidr(netmask)
            
            subprocess.run(
                ['ip', 'addr', 'add', f'{ip}/{cidr}', 'dev', interface],
                check=True
            )
            
            subprocess.run(
                ['ip', 'link', 'set', interface, 'up'],
                check=True
            )
            
            # Gateway ayarla
            subprocess.run(
                ['ip', 'route', 'add', 'default', 'via', gateway],
                check=False  # Zaten varsa hata verebilir
            )
            
            # DNS ayarla (geçici)
            with open('/etc/resolv.conf', 'w') as f:
                f.write(f"nameserver {dns}\n")
            
            return True
            
        except Exception as e:
            print(f"IP ayarlama hatası: {e}")
            return False
    
    def _netmask_to_cidr(self, netmask: str) -> int:
        """Netmask'i CIDR notasyonuna çevir"""
        return sum([bin(int(x)).count('1') for x in netmask.split('.')])
