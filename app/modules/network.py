"""
Kiosk Setup Panel - Network Module
NetworkManager ve DNS yapılandırması

Özellikler:
- NetworkManager kurulumu
- cloud-init network devre dışı
- Netplan → NetworkManager geçişi
- systemd-resolved DNS yapılandırması (Domains=~.)
- systemd-networkd MASK
- DNS doğrulama
- nmcli bağlantı yenileme
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
    description = "NetworkManager kurulumu, DNS yapılandırması"
    order = 3
    dependencies = ["nvidia", "tailscale"]
    
    # =========================================================================
    # DURUM KONTROL FONKSİYONLARI
    # =========================================================================
    
    def _is_nm_installed(self) -> bool:
        """NetworkManager paketi kurulu mu?"""
        result = self.run_shell('dpkg -l | grep -q "ii  network-manager "', check=False)
        return result.returncode == 0
    
    def _is_nm_active(self) -> bool:
        """NetworkManager servisi aktif mi?"""
        result = self.run_command(['systemctl', 'is-active', 'NetworkManager'], check=False)
        return result.returncode == 0
    
    def _is_cloud_init_disabled(self) -> bool:
        """cloud-init network devre dışı mı?"""
        return os.path.exists('/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg')
    
    def _is_networkd_masked(self) -> bool:
        """systemd-networkd-wait-online masked mı?"""
        result = self.run_command(
            ['systemctl', 'is-enabled', 'systemd-networkd-wait-online'], 
            check=False
        )
        return 'masked' in result.stdout.lower()
    
    def _is_netplan_nm_configured(self) -> bool:
        """Netplan NetworkManager kullanacak şekilde yapılandırılmış mı?"""
        netplan_file = '/etc/netplan/01-network-manager.yaml'
        if not os.path.exists(netplan_file):
            return False
        
        try:
            with open(netplan_file, 'r') as f:
                return 'renderer: NetworkManager' in f.read()
        except Exception:
            return False
    
    # =========================================================================
    # YAPILANDIRMA FONKSİYONLARI
    # =========================================================================
    
    def _backup_netplan(self) -> None:
        """Mevcut netplan dosyalarını yedekle"""
        for f in glob.glob('/etc/netplan/*.yaml'):
            if not f.endswith('.bak'):
                backup_path = f + '.bak'
                if not os.path.exists(backup_path):
                    shutil.copy(f, backup_path)
                    self.logger.info(f"Yedeklendi: {f} → {backup_path}")
    
    def _move_old_netplan(self) -> None:
        """Eski netplan dosyalarını backup dizinine taşı"""
        backup_dir = '/etc/netplan/backup'
        os.makedirs(backup_dir, exist_ok=True)
        
        for f in glob.glob('/etc/netplan/*.yaml'):
            # Bizim dosyamızı ve .bak dosyalarını atla
            if '01-network-manager' in f or f.endswith('.bak'):
                continue
            
            dest = os.path.join(backup_dir, os.path.basename(f))
            shutil.move(f, dest)
            self.logger.info(f"Taşındı: {f} → {dest}")
    
    def _mask_networkd(self) -> None:
        """systemd-networkd servislerini mask et"""
        # MASK - disable'dan daha güçlü, boot hızını artırır
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
        """DNS çalışıyor mu doğrula (ping ile)"""
        for i in range(retries):
            self.logger.info(f"DNS doğrulama denemesi {i + 1}/{retries}...")
            result = self.run_command(
                ['ping', '-c', '1', '-W', '5', 'archive.ubuntu.com'], 
                check=False
            )
            if result.returncode == 0:
                return True
            time.sleep(2)
        return False
    
    def _refresh_nm_connection(self) -> None:
        """nmcli ile bağlantıyı yenile"""
        self.logger.info("Bağlantı yenileniyor (nmcli)...")
        
        # Aktif interface'i bul ve bağlantıyı yenile
        self.run_shell(
            'IFACE=$(ip route | grep default | awk \'{print $5}\' | head -1); '
            'CON=$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep "$IFACE" | cut -d: -f1); '
            '[ -n "$CON" ] && nmcli con down "$CON" 2>/dev/null; '
            'sleep 2; '
            '[ -n "$CON" ] && nmcli con up "$CON" 2>/dev/null || true',
            check=False
        )
    
    # =========================================================================
    # ANA KURULUM
    # =========================================================================
    
    def install(self) -> Tuple[bool, str]:
        """
        Network yapılandırması
        
        Akış:
        1. NetworkManager kurulumu (yoksa)
        2. cloud-init network devre dışı (yoksa)
        3. Netplan yedekleme
        4. Netplan yapılandırma
        5. Eski netplan dosyalarını taşıma
        6. netplan apply
        7. systemd-networkd-wait-online MASK
        8. systemd-networkd devre dışı
        9. DNS yapılandırma (Domains=~. dahil)
        10. DNS doğrulama
        11. NetworkManager servisleri
        12. nmcli bağlantı yenileme
        13. Son kontrol
        """
        try:
            # =================================================================
            # 1. NetworkManager Kurulumu
            # =================================================================
            if not self._is_nm_installed():
                self.logger.info("NetworkManager kuruluyor...")
                if not self.apt_install(['network-manager']):
                    return False, "NetworkManager kurulamadı"
            else:
                self.logger.info("NetworkManager zaten kurulu")
            
            # =================================================================
            # 2. cloud-init Network Devre Dışı
            # =================================================================
            if not self._is_cloud_init_disabled():
                self.logger.info("cloud-init network devre dışı bırakılıyor...")
                cloud_init_content = "network: {config: disabled}"
                self.write_file(
                    '/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg', 
                    cloud_init_content
                )
            else:
                self.logger.info("cloud-init network zaten devre dışı")
            
            # =================================================================
            # 3. Netplan Yedekleme
            # =================================================================
            self.logger.info("Mevcut netplan dosyaları yedekleniyor...")
            self._backup_netplan()
            
            # =================================================================
            # 4. Netplan Yapılandırma
            # =================================================================
            if not self._is_netplan_nm_configured():
                self.logger.info("Netplan yapılandırılıyor...")
                netplan_content = """# Network configuration managed by NetworkManager
network:
  version: 2
  renderer: NetworkManager
"""
                self.write_file('/etc/netplan/01-network-manager.yaml', netplan_content)
            else:
                self.logger.info("Netplan zaten yapılandırılmış")
            
            # =================================================================
            # 5. Eski Netplan Dosyalarını Taşı
            # =================================================================
            self.logger.info("Eski netplan dosyaları taşınıyor...")
            self._move_old_netplan()
            
            # =================================================================
            # 6. netplan apply
            # =================================================================
            self.logger.info("netplan apply çalıştırılıyor...")
            result = self.run_command(['/usr/sbin/netplan', 'apply'], check=False)
            if result.returncode != 0:
                self.logger.warning(f"netplan apply uyarısı: {result.stderr}")
            
            # =================================================================
            # 7. systemd-networkd-wait-online MASK
            # =================================================================
            if not self._is_networkd_masked():
                self.logger.info("systemd-networkd-wait-online mask ediliyor...")
                self._mask_networkd()
            else:
                self.logger.info("systemd-networkd-wait-online zaten masked")
            
            # =================================================================
            # 8. systemd-networkd Devre Dışı
            # =================================================================
            self.logger.info("systemd-networkd devre dışı bırakılıyor...")
            self.systemctl('disable', 'systemd-networkd')
            self.systemctl('stop', 'systemd-networkd')
            
            # =================================================================
            # 9. DNS Yapılandırma (Domains=~. dahil)
            # =================================================================
            self.logger.info("DNS yapılandırılıyor (Domains=~.)...")
            
            dns_servers = self.get_config('network.dns_servers', ['8.8.8.8', '8.8.4.4'])
            dns_str = ' '.join(dns_servers)
            
            resolved_content = f"""[Resolve]
DNS={dns_str}
FallbackDNS=1.1.1.1 9.9.9.9
Domains=~.
DNSStubListener=yes
"""
            self.write_file('/etc/systemd/resolved.conf', resolved_content)
            
            # systemd-resolved yeniden başlat
            self.systemctl('restart', 'systemd-resolved')
            
            # =================================================================
            # 10. DNS Doğrulama
            # =================================================================
            self.logger.info("DNS doğrulanıyor...")
            if not self._verify_dns(retries=3):
                self.logger.error("DNS doğrulaması başarısız!")
                return False, "DNS doğrulaması başarısız! Ağ bağlantısını kontrol edin."
            self.logger.info("DNS doğrulandı ✓")
            
            # =================================================================
            # 11. NetworkManager Servisleri
            # =================================================================
            self.logger.info("NetworkManager servisleri etkinleştiriliyor...")
            self.systemctl('enable', 'NetworkManager')
            self.systemctl('start', 'NetworkManager')
            self.systemctl('enable', 'NetworkManager-wait-online')
            
            # =================================================================
            # 12. nmcli Bağlantı Yenileme
            # =================================================================
            self._refresh_nm_connection()
            
            # =================================================================
            # 13. Son Kontrol
            # =================================================================
            time.sleep(2)  # Servisin stabilize olmasını bekle
            
            if not self._is_nm_active():
                self.logger.error("NetworkManager aktif değil!")
                return False, "NetworkManager başlatılamadı"
            
            self.logger.info("Network yapılandırması tamamlandı ✓")
            return True, "NetworkManager kuruldu ve yapılandırıldı"
            
        except Exception as e:
            self.logger.error(f"Network kurulum hatası: {e}")
            return False, str(e)
