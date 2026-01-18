"""
Kiosk Setup Panel - System Service
Sistem bilgileri ve yardımcı fonksiyonlar
"""

import json
import logging
import subprocess
import socket
import os
import ipaddress
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


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
        s = None
        try:
            # Default route üzerinden IP al
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.3)  # 300ms timeout - hızlı UI güncellemesi için
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception as e:
            logger.debug(f"IP adresi alınamadı: {e}")
            return None
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
    
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
        except Exception as e:
            logger.debug(f"Tailscale IP alınamadı: {e}")
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
                    
        except Exception as e:
            logger.debug(f"Network interfaces alınamadı: {e}")
        
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
                
        except Exception as e:
            logger.debug(f"Uptime alınamadı: {e}")
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
            
        except Exception as e:
            logger.debug(f"Memory bilgisi alınamadı: {e}")
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
            
        except Exception as e:
            logger.debug(f"Disk bilgisi alınamadı: {e}")
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
        Geçici statik IP ayarla - korumalı versiyon.
        Bu ayar NetworkManager kurulana kadar geçerlidir.
        
        Returns: {'success': bool, 'error': str|None}
        """
        
        # 1. VALIDATION - Önce kontrol et, sonra uygula
        
        # Interface var mı?
        if not os.path.exists(f'/sys/class/net/{interface}'):
            return {'success': False, 'error': f'Interface bulunamadı: {interface}'}
        
        # IP formatı geçerli mi?
        try:
            ip_obj = ipaddress.ip_address(ip)
            gw_obj = ipaddress.ip_address(gateway)
            network = ipaddress.ip_network(f"{ip}/{netmask}", strict=False)
        except ValueError as e:
            return {'success': False, 'error': f'Geçersiz IP formatı: {e}'}
        
        # Gateway aynı subnet'te mi?
        if gw_obj not in network:
            return {'success': False, 'error': f"Gateway ({gateway}) IP subnet'inde değil"}
        
        # 2. BACKUP - Mevcut durumu kaydet
        backup = self._backup_network_state(interface)
        
        # 3. UYGULA - Sırayla işlemleri yap
        try:
            # DHCP'yi durdur (varsa, hata vermez)
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
            
            # Mevcut IP'yi temizle
            subprocess.run(
                ['ip', 'addr', 'flush', 'dev', interface],
                check=True, timeout=10
            )
            
            # Yeni IP ekle
            cidr = self._netmask_to_cidr(netmask)
            subprocess.run(
                ['ip', 'addr', 'add', f'{ip}/{cidr}', 'dev', interface],
                check=True, timeout=10
            )
            subprocess.run(
                ['ip', 'link', 'set', interface, 'up'],
                check=True, timeout=10
            )
            
            # ÖNCE mevcut route'u sil, SONRA yenisini ekle
            subprocess.run(
                ['ip', 'route', 'del', 'default'],
                check=False, stderr=subprocess.DEVNULL, timeout=10
            )
            subprocess.run(
                ['ip', 'route', 'add', 'default', 'via', gateway],
                check=True, timeout=10
            )
            
            # DNS ayarla
            with open('/etc/resolv.conf', 'w') as f:
                f.write(f"nameserver {dns}\n")
            
            return {'success': True, 'error': None}
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            # 4. ROLLBACK - Hata durumunda geri al
            error_msg = f"IP ayarlama hatası: {e}"
            rollback_ok = self._rollback_network(interface, backup)
            
            if rollback_ok:
                return {'success': False, 'error': f'{error_msg} (eski ayarlar geri yüklendi)'}
            else:
                return {'success': False, 'error': f'{error_msg} (UYARI: Geri yükleme başarısız!)'}
    
    def _netmask_to_cidr(self, netmask: str) -> int:
        """Netmask'i CIDR notasyonuna çevir"""
        return sum([bin(int(x)).count('1') for x in netmask.split('.')])
    
    def reset_to_dhcp(self, interface: str) -> dict:
        """
        DHCP'ye geri dön - korumalı versiyon.
        Statik IP ayarını kaldırıp DHCP client'ı yeniden başlatır.
        
        Returns: {'success': bool, 'error': str|None}
        """
        
        # Interface kontrolü
        if not os.path.exists(f'/sys/class/net/{interface}'):
            return {'success': False, 'error': f'Interface bulunamadı: {interface}'}
        
        # dhclient kontrolü - ÖNCE kontrol et, yoksa hiçbir şey yapma!
        dhclient = self._find_dhclient()
        if not dhclient:
            return {'success': False, 'error': 'dhclient bulunamadı! isc-dhcp-client paketi gerekli.'}
        
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
            
            # DHCP başlat
            subprocess.run(
                [dhclient, interface],
                check=True, timeout=30
            )
            
            return {'success': True, 'error': None}
            
        except subprocess.CalledProcessError as e:
            return {'success': False, 'error': f'DHCP hatası: {e}'}
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'DHCP zaman aşımı (30s)'}
    
    def _backup_network_state(self, interface: str) -> dict:
        """Mevcut ağ durumunu yedekle"""
        backup = {}
        try:
            # Mevcut IP bilgisi
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show', interface],
                capture_output=True, text=True, timeout=5
            )
            backup['ip_info'] = result.stdout
            
            # Mevcut default route
            result = subprocess.run(
                ['ip', 'route', 'show', 'default'],
                capture_output=True, text=True, timeout=5
            )
            backup['default_route'] = result.stdout.strip()
            
            # Mevcut DNS
            if os.path.exists('/etc/resolv.conf'):
                with open('/etc/resolv.conf', 'r') as f:
                    backup['dns'] = f.read()
        except Exception as e:
            logger.debug(f"Network backup alınamadı: {e}")
        return backup
    
    def _rollback_network(self, interface: str, backup: dict) -> bool:
        """Ağ yapılandırmasını geri yükle (DHCP ile)"""
        try:
            # DNS'i geri yükle
            if 'dns' in backup:
                with open('/etc/resolv.conf', 'w') as f:
                    f.write(backup['dns'])
            
            # dhclient ile yeniden IP al (en güvenli yol)
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
            logger.warning(f"Network rollback başarısız: {e}")
            return False
    
    def _find_dhclient(self) -> Optional[str]:
        """dhclient binary'sini bul"""
        paths = ['/sbin/dhclient', '/usr/sbin/dhclient']
        return next((p for p in paths if os.path.exists(p)), None)
