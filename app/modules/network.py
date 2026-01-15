"""
Kiosk Setup Panel - Network Module
NetworkManager ve DNS yapılandırması
"""

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
    
    def install(self) -> Tuple[bool, str]:
        """Network yapılandırması"""
        try:
            # 1. NetworkManager kurulumu
            self.logger.info("NetworkManager kuruluyor...")
            
            if not self.apt_install(['network-manager']):
                return False, "NetworkManager kurulamadı"
            
            # 2. cloud-init network yapılandırmasını devre dışı bırak
            self.logger.info("cloud-init network devre dışı bırakılıyor...")
            
            cloud_init_content = "network: {config: disabled}"
            self.write_file('/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg', cloud_init_content)
            
            # 3. Netplan → NetworkManager geçişi
            self.logger.info("Netplan yapılandırması güncelleniyor...")
            
            netplan_content = """# Network configuration managed by NetworkManager
network:
  version: 2
  renderer: NetworkManager
"""
            self.write_file('/etc/netplan/01-network-manager.yaml', netplan_content)
            
            # Eski netplan dosyalarını kaldır
            import glob
            import os
            for f in glob.glob('/etc/netplan/*.yaml'):
                if '01-network-manager' not in f:
                    os.remove(f)
                    self.logger.info(f"Kaldırıldı: {f}")
            
            # netplan apply
            self.run_command(['netplan', 'apply'])
            
            # 4. systemd-resolved DNS yapılandırması
            self.logger.info("DNS yapılandırılıyor...")
            
            dns_servers = self.get_config('network.dns_servers', ['8.8.8.8', '8.8.4.4'])
            dns_str = ' '.join(dns_servers)
            
            resolved_content = f"""[Resolve]
DNS={dns_str}
FallbackDNS=1.1.1.1 9.9.9.9
DNSStubListener=yes
"""
            self.write_file('/etc/systemd/resolved.conf', resolved_content)
            
            # systemd-resolved yeniden başlat
            self.systemctl('restart', 'systemd-resolved')
            
            # 5. systemd-networkd devre dışı
            self.systemctl('disable', 'systemd-networkd')
            self.systemctl('stop', 'systemd-networkd')
            
            # 6. NetworkManager servislerini etkinleştir
            self.systemctl('enable', 'NetworkManager')
            self.systemctl('start', 'NetworkManager')
            self.systemctl('enable', 'NetworkManager-wait-online')
            
            self.logger.info("Network yapılandırması tamamlandı")
            return True, "NetworkManager kuruldu ve yapılandırıldı"
            
        except Exception as e:
            self.logger.error(f"Network kurulum hatası: {e}")
            return False, str(e)
