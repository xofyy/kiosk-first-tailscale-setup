"""
ACO Maintenance Panel - Security Module
UFW Firewall and SSH security configuration
"""

from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class SecurityModule(BaseModule):
    name = "security"
    display_name = "Security"
    description = "UFW Firewall and SSH security configuration"
    order = 11
    dependencies = ["netmon", "collector", "docker"]
    
    def install(self) -> Tuple[bool, str]:
        """Security configuration"""
        try:
            vnc_port = self.get_config('vnc.port', 5900)
            
            # 1. UFW installation
            self.logger.info("Installing UFW...")

            if not self.apt_install(['ufw']):
                return False, "Could not install UFW"
            
            # 2. UFW rules
            self.logger.info("Configuring UFW rules...")

            # Reset first
            result = self.run_shell('/usr/sbin/ufw --force reset', check=False)
            if result.returncode != 0:
                self.logger.warning(f"UFW reset failed: {result.stderr}")

            # Default policies
            self.run_command(['/usr/sbin/ufw', 'default', 'deny', 'incoming'])
            self.run_command(['/usr/sbin/ufw', 'default', 'allow', 'outgoing'])
            self.run_command(['/usr/sbin/ufw', 'default', 'deny', 'routed'])  # For Docker routing

            # SSH over Tailscale
            self.run_shell('/usr/sbin/ufw allow in on tailscale0 to any port 22 proto tcp')
            
            # VNC over Tailscale
            self.run_shell(f'/usr/sbin/ufw allow in on tailscale0 to any port {vnc_port} proto tcp')
            
            # Panel over Tailscale (VPN access only)
            self.run_shell('/usr/sbin/ufw allow in on tailscale0 to any port 4444 proto tcp')
            
            # MongoDB over Tailscale
            self.run_shell('/usr/sbin/ufw allow in on tailscale0 to any port 27017 proto tcp')
            
            # Block SSH from LAN (except Tailscale)
            # Note: tailscale0 rule comes first, so Tailscale access is allowed
            self.run_shell('/usr/sbin/ufw deny 22/tcp comment "Deny SSH from LAN"')
            
            # Enable UFW
            result = self.run_shell('/usr/sbin/ufw --force enable', check=False)
            if result.returncode != 0:
                return False, f"Could not enable UFW: {result.stderr}"
            
            # 3. SSH configuration
            self.logger.info("Configuring SSH security...")
            
            ssh_config = """# Tailscale-only SSH Configuration
# /etc/ssh/sshd_config.d/99-tailscale-only.conf

# Root can only access via Tailscale SSH
PermitRootLogin yes

# CLASSIC SSH COMPLETELY DISABLED
# These settings block SSH over LAN/WAN
# Tailscale SSH (via PAM) continues to work
PasswordAuthentication no
PubkeyAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no

# PAM required for Tailscale SSH
UsePAM yes

# Allowed users
AllowUsers root aco kiosk

# Required for VNC port-forward
AllowTcpForwarding yes

# Security: X11 and tunnel disabled
X11Forwarding no
PermitTunnel no
GatewayPorts no

# Brute-force protection
LoginGraceTime 20
MaxAuthTries 3
MaxSessions 2

# Keepalive - cleanup on connection drop
ClientAliveInterval 300
ClientAliveCountMax 2

# Detailed log (for security monitoring)
LogLevel VERBOSE
"""
            if not self.write_file('/etc/ssh/sshd_config.d/99-tailscale-only.conf', ssh_config):
                return False, "Could not write SSH config"

            # Restart SSH service
            if not self.systemctl('restart', 'sshd'):
                self.logger.warning("Could not restart SSHD")
            
            # 4. Fail2ban (optional but recommended)
            self.logger.info("Installing Fail2ban...")
            
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
                    self.logger.warning("Could not write Fail2ban config")
                else:
                    if not self.systemctl('enable', 'fail2ban'):
                        self.logger.warning("Could not enable fail2ban")
                    if not self.systemctl('restart', 'fail2ban'):
                        self.logger.warning("Could not restart fail2ban")
            
            self.logger.info("Security configuration completed")
            return True, "UFW and SSH security configuration completed"

        except Exception as e:
            self.logger.error(f"Security configuration error: {e}")
            return False, str(e)
