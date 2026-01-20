"""
ACO Maintenance Panel - Tailscale Module
Tailscale Enrollment and Headscale connection

Note: Tailscale package is installed in install.sh.
This module only handles enrollment and headscale connection.
"""

import time
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule
from app.services.system import SystemService
from app.services.hardware import HardwareService
from app.services.enrollment import EnrollmentService

# Constants
APPROVAL_TIMEOUT = None  # Wait indefinitely for admin approval


@register_module
class TailscaleModule(BaseModule):
    name = "remote-connection"
    display_name = "Remote Connection"
    description = "Remote connection setup and Enrollment registration"
    order = 1
    dependencies = []  # First module - VPN connection required before other modules

    def _check_prerequisites(self) -> Tuple[bool, str]:
        """Check internet and enrollment requirements"""
        system = SystemService()
        if not system.check_internet():
            return False, "Internet connection required"

        # RVM ID required
        if not self._config.get_rvm_id():
            return False, "RVM ID must be set first"

        return True, ""

    def _is_tailscale_installed(self) -> bool:
        """Check if Tailscale is installed"""
        result = self.run_command(['which', 'tailscale'], check=False)
        return result.returncode == 0

    def _is_tailscale_connected(self) -> bool:
        """Check if Tailscale is connected"""
        result = self.run_command(['tailscale', 'status'], check=False)
        return result.returncode == 0

    def install(self) -> Tuple[bool, str]:
        """
        Tailscale installation.
        Idempotent - skips if already connected to Headscale.
        """
        try:
            # 0. Already connected check (idempotent)
            if self._is_tailscale_connected():
                self.logger.info("Tailscale already connected, skipping installation")
                return True, "Tailscale already connected"

            # 1. Generate Hardware ID
            hardware = HardwareService()
            hardware_id = hardware.get_hardware_id()

            if not hardware_id:
                return False, "Failed to generate Hardware ID"

            # Save to config
            self._config.set_hardware_id(hardware_id)
            self.logger.info(f"Hardware ID: {hardware_id}")

            # 2. Get RVM ID (should be set beforehand)
            rvm_id = self._config.get_rvm_id()

            if not rvm_id:
                return False, "RVM ID not found"

            self.logger.info(f"RVM ID: {rvm_id}")

            # 3. Register with Enrollment API
            enrollment_url = self._config.get_enrollment_url()
            enrollment = EnrollmentService(api_url=enrollment_url)

            self.logger.info(f"Registering with Enrollment API: {enrollment_url}")

            # Get additional info
            motherboard_uuid = hardware.get_motherboard_uuid()
            mac_addresses = hardware.get_mac_addresses()

            self.logger.info(f"Motherboard UUID: {motherboard_uuid}")
            self.logger.info(f"MAC Addresses: {mac_addresses}")

            enroll_result = enrollment.enroll(
                rvm_id,
                hardware_id,
                motherboard_uuid=motherboard_uuid,
                mac_addresses=mac_addresses
            )

            if not enroll_result['success']:
                return False, enroll_result.get('error', 'Enrollment failed')

            self.logger.info(f"Enrollment status: {enroll_result.get('status')}")

            # 4. Check if already approved (auth_key might be in response)
            auth_key = enroll_result.get('auth_key')

            if not auth_key:
                # 5. Wait for approval - with HARDWARE_ID!
                self.logger.info("Waiting for admin approval...")
                auth_key = enrollment.wait_for_approval(hardware_id, timeout=APPROVAL_TIMEOUT)

            if not auth_key:
                return False, "Admin approval not received or timeout"

            self.logger.info("Admin approval received!")

            # 6. Check if Tailscale is installed (should be installed by install.sh)
            if not self._is_tailscale_installed():
                return False, "Tailscale not installed! Was install.sh run?"

            self.logger.info("Tailscale installed")

            # 7. Start tailscaled service
            self.logger.info("Starting tailscaled service...")
            if not self.systemctl('enable', 'tailscaled'):
                return False, "Failed to enable tailscaled service"
            if not self.systemctl('start', 'tailscaled'):
                return False, "Failed to start tailscaled service"

            # Wait for service to start
            time.sleep(3)

            # Verify tailscaled is running
            if not self.systemctl('is-active', 'tailscaled'):
                return False, "Tailscaled service is not running"

            # 8. Connect to Headscale (with full parameters!)
            headscale_url = self._config.get_headscale_url()
            self.logger.info(f"Connecting to Headscale: {headscale_url}")

            result = self.run_command([
                'tailscale', 'up',
                '--login-server', headscale_url,
                '--authkey', auth_key,
                '--hostname', rvm_id.lower(),
                '--advertise-tags=tag:kiosk',
                '--ssh',
                '--accept-dns=true',
                '--accept-routes=false',
                '--reset'
            ], check=False)

            if result.returncode != 0:
                self.logger.error(f"Tailscale up error: {result.stderr}")
                return False, f"Headscale connection failed: {result.stderr}"

            # 9. Verify connection
            time.sleep(3)

            if not self._is_tailscale_connected():
                self.logger.error("Tailscale connection not verified")
                return False, "Tailscale connection to Headscale could not be verified"

            self.logger.info("Tailscale connection verified")

            # Log status info
            status_result = self.run_command(['tailscale', 'status'], check=False)
            if status_result.returncode == 0:
                self.logger.info(f"Tailscale status:\n{status_result.stdout}")

            # 10. Save RVM ID to MongoDB (for other services)
            mongo_ok, mongo_error = self._save_rvm_id_to_mongodb(rvm_id, hardware_id)
            if not mongo_ok:
                return False, f"MongoDB save failed: {mongo_error}"

            # 11. Security configuration (UFW rules, SSH, fail2ban)
            # tailscale0 interface is now available, rules can be added
            security_ok, security_error = self._configure_security()
            if not security_ok:
                return False, f"Security configuration failed: {security_error}"

            self.logger.info("Tailscale installation completed")
            return True, "Tailscale installed and connected to Headscale"

        except Exception as e:
            self.logger.error(f"Tailscale installation error: {e}")
            return False, str(e)

    def _configure_security(self) -> Tuple[bool, str]:
        """
        Security configuration after Tailscale connection.
        UFW rules, SSH config and fail2ban settings.
        Idempotent - skips if already configured.
        Returns (success, error_message)
        """
        self.logger.info("Starting security configuration...")

        try:
            # 1. Check if UFW is installed
            ufw_check = self.run_shell('which /usr/sbin/ufw', check=False)
            if ufw_check.returncode != 0:
                self.logger.error("UFW is not installed!")
                return False, "UFW is not installed. Run install.sh first."

            # 2. Check if already configured (idempotent)
            ufw_status = self.run_shell('/usr/sbin/ufw status', check=False)
            if 'tailscale0' in ufw_status.stdout and 'Status: active' in ufw_status.stdout:
                self.logger.info("UFW already configured with tailscale0 rules, skipping")
                return True, ""

            # 3. UFW configuration (from scratch)
            self.logger.info("Configuring UFW...")

            # Reset first
            self.run_shell('/usr/sbin/ufw --force reset 2>/dev/null || true', check=False)

            # Default policies
            self.run_shell('/usr/sbin/ufw default deny incoming', check=False)
            self.run_shell('/usr/sbin/ufw default allow outgoing', check=False)
            self.run_shell('/usr/sbin/ufw default deny routed', check=False)

            # Tailscale0 interface permissions
            ufw_rules = [
                # SSH via Tailscale
                ('/usr/sbin/ufw allow in on tailscale0 to any port 22 proto tcp', '22/tcp on tailscale0'),
                # VNC via Tailscale
                ('/usr/sbin/ufw allow in on tailscale0 to any port 5900 proto tcp', '5900/tcp on tailscale0'),
                # Panel via Tailscale
                ('/usr/sbin/ufw allow in on tailscale0 to any port 4444 proto tcp', '4444/tcp on tailscale0'),
                # MongoDB via Tailscale
                ('/usr/sbin/ufw allow in on tailscale0 to any port 27017 proto tcp', '27017/tcp on tailscale0'),
                # Deny SSH from LAN (tailscale rules take priority)
                ('/usr/sbin/ufw deny 22/tcp', '22/tcp'),
            ]

            rules_added = 0
            for rule_cmd, rule_check in ufw_rules:
                result = self.run_shell(rule_cmd, check=False)
                if result.returncode == 0:
                    self.logger.info(f"UFW rule added: {rule_check}")
                    rules_added += 1
                else:
                    self.logger.error(f"Failed to add UFW rule: {rule_cmd} - {result.stderr}")

            self.logger.info(f"UFW: {rules_added}/{len(ufw_rules)} rules added")

            # Check if any rules were added
            if rules_added == 0:
                return False, "Failed to add any UFW rules"

            # Enable UFW
            ufw_enable_result = self.run_shell('/usr/sbin/ufw --force enable', check=False)
            if ufw_enable_result.returncode == 0:
                self.logger.info("UFW enabled")
            else:
                self.logger.error(f"Failed to enable UFW: {ufw_enable_result.stderr}")
                return False, f"Failed to enable UFW: {ufw_enable_result.stderr}"

            # Verify: UFW status and rules
            ufw_status = self.run_shell('/usr/sbin/ufw status', check=False)
            if 'active' in ufw_status.stdout.lower():
                self.logger.info("UFW status verified: active")

                # Verify rules
                rules_verified = 0
                for _, rule_check in ufw_rules:
                    if rule_check in ufw_status.stdout:
                        rules_verified += 1
                    else:
                        self.logger.warning(f"UFW rule not found: {rule_check}")

                self.logger.info(f"UFW rules verified: {rules_verified}/{len(ufw_rules)}")
            else:
                self.logger.error(f"UFW not active! Status: {ufw_status.stdout.strip()}")
                return False, "UFW failed to activate"

            # 3. SSH configuration (Tailscale-only)
            self.logger.info("Configuring SSH...")

            ssh_config = """# Tailscale-only SSH Configuration
# This file was created by tailscale module

PermitRootLogin yes
PasswordAuthentication no
PubkeyAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
UsePAM yes
AllowUsers root aco kiosk
AllowTcpForwarding yes
X11Forwarding no
PermitTunnel no
GatewayPorts no
LoginGraceTime 20
MaxAuthTries 3
MaxSessions 2
ClientAliveInterval 300
ClientAliveCountMax 2
LogLevel VERBOSE
"""
            if not self.write_file('/etc/ssh/sshd_config.d/99-tailscale-only.conf', ssh_config):
                self.logger.error("Failed to write SSH config")
                return False, "Failed to write SSH configuration"

            if not self.systemctl('restart', 'sshd'):
                self.logger.error("Failed to restart SSHD")
                return False, "Failed to restart SSH service"

            self.logger.info("SSH configuration completed")

            # 4. Fail2ban configuration
            self.logger.info("Configuring Fail2ban...")

            # Check if fail2ban is installed
            fail2ban_check = self.run_shell('which fail2ban-client', check=False)
            if fail2ban_check.returncode != 0:
                self.logger.error("Fail2ban is not installed!")
                return False, "Fail2ban is not installed. Run install.sh first."

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
                self.logger.error("Failed to write Fail2ban config")
                return False, "Failed to write Fail2ban configuration"

            self.systemctl('enable', 'fail2ban')
            if not self.systemctl('restart', 'fail2ban'):
                self.logger.error("Failed to restart Fail2ban")
                return False, "Failed to restart Fail2ban service"

            self.logger.info("Fail2ban configuration completed")

            self.logger.info("Security configuration completed")
            return True, ""

        except Exception as e:
            self.logger.error(f"Security configuration error: {e}")
            return False, str(e)

    def _save_rvm_id_to_mongodb(self, rvm_id: str, hardware_id: str) -> Tuple[bool, str]:
        """Save RVM ID to MongoDB. Returns (success, error_message)"""
        try:
            import socket
            from datetime import datetime
            from pymongo import MongoClient

            client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
            db = client['aco']
            collection = db['settings']

            # Create/update record
            document = {
                'rvm_id': rvm_id,
                'hardware_id': hardware_id,
                'hostname': socket.gethostname(),
                'registered_at': datetime.utcnow(),
                'setup_complete': False
            }

            result = collection.update_one(
                {},
                {'$set': document},
                upsert=True
            )

            client.close()

            if result.modified_count > 0 or result.upserted_id:
                self.logger.info(f"RVM ID saved to MongoDB: {rvm_id}")
                return True, ""
            else:
                self.logger.error("MongoDB update returned no changes")
                return False, "MongoDB update failed - no changes made"

        except Exception as e:
            self.logger.error(f"MongoDB save error: {e}")
            return False, f"MongoDB error: {str(e)}"
