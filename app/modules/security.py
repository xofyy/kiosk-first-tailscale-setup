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
            
            # 1. UFW kurulumu
            self.logger.info("UFW kuruluyor...")
            
            if not self.apt_install(['ufw']):
                return False, "UFW kurulamadı"
            
            # 2. UFW kuralları
            self.logger.info("UFW kuralları yapılandırılıyor...")
            
            # Önce sıfırla
            result = self.run_shell('/usr/sbin/ufw --force reset', check=False)
            if result.returncode != 0:
                self.logger.warning(f"UFW reset başarısız: {result.stderr}")
            
            # Varsayılan politikalar
            self.run_command(['/usr/sbin/ufw', 'default', 'deny', 'incoming'])
            self.run_command(['/usr/sbin/ufw', 'default', 'allow', 'outgoing'])
            self.run_command(['/usr/sbin/ufw', 'default', 'deny', 'routed'])  # Docker routing için
            
            # Tailscale üzerinden SSH
            self.run_shell('/usr/sbin/ufw allow in on tailscale0 to any port 22 proto tcp')
            
            # Tailscale üzerinden VNC
            self.run_shell(f'/usr/sbin/ufw allow in on tailscale0 to any port {vnc_port} proto tcp')
            
            # Tailscale üzerinden Panel (sadece VPN erişimi)
            self.run_shell('/usr/sbin/ufw allow in on tailscale0 to any port 4444 proto tcp')
            
            # Tailscale üzerinden MongoDB
            self.run_shell('/usr/sbin/ufw allow in on tailscale0 to any port 27017 proto tcp')
            
            # LAN'dan SSH engelle (Tailscale hariç)
            # Not: tailscale0 kuralı önce geldiği için Tailscale üzerinden erişim açık
            self.run_shell('/usr/sbin/ufw deny 22/tcp comment "Deny SSH from LAN"')
            
            # UFW'yi etkinleştir
            result = self.run_shell('/usr/sbin/ufw --force enable', check=False)
            if result.returncode != 0:
                return False, f"UFW etkinleştirilemedi: {result.stderr}"
            
            # 3. SSH yapılandırması
            self.logger.info("SSH güvenlik yapılandırması...")
            
            ssh_config = """# Tailscale-only SSH Configuration
# /etc/ssh/sshd_config.d/99-tailscale-only.conf

# Root sadece Tailscale SSH ile erişebilir
PermitRootLogin yes

# KLASİK SSH TAMAMEN KAPALI
# Bu ayarlar LAN/WAN üzerinden SSH'ı engeller
# Tailscale SSH (PAM üzerinden) çalışmaya devam eder
PasswordAuthentication no
PubkeyAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no

# Tailscale SSH için PAM gerekli
UsePAM yes

# İzin verilen kullanıcılar
AllowUsers root aco kiosk

# VNC port-forward için gerekli
AllowTcpForwarding yes

# Güvenlik: X11 ve tunnel kapalı
X11Forwarding no
PermitTunnel no
GatewayPorts no

# Brute-force koruması
LoginGraceTime 20
MaxAuthTries 3
MaxSessions 2

# Keepalive - bağlantı kopması durumunda temizlik
ClientAliveInterval 300
ClientAliveCountMax 2

# Detaylı log (güvenlik izleme için)
LogLevel VERBOSE
"""
            if not self.write_file('/etc/ssh/sshd_config.d/99-tailscale-only.conf', ssh_config):
                return False, "SSH config yazılamadı"
            
            # SSH servisini yeniden başlat
            if not self.systemctl('restart', 'sshd'):
                self.logger.warning("SSHD yeniden başlatılamadı")
            
            # 4. Fail2ban (opsiyonel ama önerilen)
            self.logger.info("Fail2ban kuruluyor...")
            
            if self.apt_install(['fail2ban']):
                fail2ban_config = """[sshd]
enabled = true
port = ssh
filter = sshd
backend = systemd
maxretry = 3
bantime = 3600
findtime = 600
"""
                if not self.write_file('/etc/fail2ban/jail.d/sshd.conf', fail2ban_config):
                    self.logger.warning("Fail2ban config yazılamadı")
                else:
                    if not self.systemctl('enable', 'fail2ban'):
                        self.logger.warning("fail2ban enable edilemedi")
                    if not self.systemctl('restart', 'fail2ban'):
                        self.logger.warning("fail2ban yeniden başlatılamadı")
            
            self.logger.info("Güvenlik yapılandırması tamamlandı")
            return True, "UFW ve SSH güvenlik yapılandırması tamamlandı"
            
        except Exception as e:
            self.logger.error(f"Güvenlik yapılandırma hatası: {e}")
            return False, str(e)
