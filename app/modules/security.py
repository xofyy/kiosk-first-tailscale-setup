"""
Kiosk Setup Panel - Security Module
UFW Firewall ve SSH güvenlik yapılandırması
"""

from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class SecurityModule(BaseModule):
    name = "security"
    display_name = "Security"
    description = "UFW Firewall ve SSH güvenlik yapılandırması"
    order = 11
    dependencies = ["netmon", "collector", "docker"]
    
    def install(self) -> Tuple[bool, str]:
        """Güvenlik yapılandırması"""
        try:
            vnc_port = self.get_config('vnc.port', 5900)
            cockpit_port = self.get_config('cockpit.port', 9090)
            
            # 1. UFW kurulumu
            self.logger.info("UFW kuruluyor...")
            
            if not self.apt_install(['ufw']):
                return False, "UFW kurulamadı"
            
            # 2. UFW kuralları
            self.logger.info("UFW kuralları yapılandırılıyor...")
            
            # Önce sıfırla
            self.run_shell('ufw --force reset')
            
            # Varsayılan politikalar
            self.run_command(['ufw', 'default', 'deny', 'incoming'])
            self.run_command(['ufw', 'default', 'allow', 'outgoing'])
            
            # Tailscale üzerinden SSH
            self.run_shell('ufw allow in on tailscale0 to any port 22 proto tcp')
            
            # Tailscale üzerinden VNC
            self.run_shell(f'ufw allow in on tailscale0 to any port {vnc_port} proto tcp')
            
            # Tailscale üzerinden Cockpit
            self.run_shell(f'ufw allow in on tailscale0 to any port {cockpit_port} proto tcp')
            
            # Panel erişimi (yerel ağ ve Tailscale)
            self.run_shell('ufw allow 8080/tcp')
            
            # LAN'dan SSH engelle (Tailscale hariç)
            # Not: tailscale0 kuralı önce geldiği için Tailscale üzerinden erişim açık
            
            # UFW'yi etkinleştir
            self.run_shell('ufw --force enable')
            
            # 3. SSH yapılandırması
            self.logger.info("SSH güvenlik yapılandırması...")
            
            ssh_config = """# Tailscale-only SSH Configuration
# /etc/ssh/sshd_config.d/99-tailscale-only.conf

# Parola ile giriş kapalı
PasswordAuthentication no

# Public key ile giriş kapalı (Tailscale kullanılacak)
PubkeyAuthentication no

# PAM aktif (Tailscale auth için)
UsePAM yes

# İzin verilen kullanıcılar
AllowUsers root aco kiosk

# Brute-force koruması
MaxAuthTries 3
MaxSessions 2

# Bağlantı timeout
ClientAliveInterval 300
ClientAliveCountMax 2

# Logging
LogLevel VERBOSE
"""
            self.write_file('/etc/ssh/sshd_config.d/99-tailscale-only.conf', ssh_config)
            
            # SSH servisini yeniden başlat
            self.systemctl('restart', 'sshd')
            
            # 4. Fail2ban (opsiyonel ama önerilen)
            self.logger.info("Fail2ban kuruluyor...")
            
            if self.apt_install(['fail2ban']):
                fail2ban_config = """[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
"""
                self.write_file('/etc/fail2ban/jail.d/sshd.conf', fail2ban_config)
                
                self.systemctl('enable', 'fail2ban')
                self.systemctl('restart', 'fail2ban')
            
            self.logger.info("Güvenlik yapılandırması tamamlandı")
            return True, "UFW ve SSH güvenlik yapılandırması tamamlandı"
            
        except Exception as e:
            self.logger.error(f"Güvenlik yapılandırma hatası: {e}")
            return False, str(e)
