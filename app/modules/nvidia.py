"""
Kiosk Setup Panel - NVIDIA Module
NVIDIA GPU driver installation

Features:
- GPU detection (lspci)
- Secure Boot check (mokutil)
- Package check (dpkg)
- Module check (lsmod)
- nvidia-smi verification
- MOK key management
- Random MOK password generation (8 digits, 1-8)
"""

import os
import random
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule
from app.services.system import SystemService


@register_module
class NvidiaModule(BaseModule):
    name = "nvidia"
    display_name = "NVIDIA Driver"
    description = "NVIDIA GPU driver installation, MOK key and GRUB configuration"
    order = 1
    dependencies = []  # First module, no dependencies

    def _check_prerequisites(self) -> Tuple[bool, str]:
        """Check internet connection"""
        system = SystemService()
        if not system.check_internet():
            return False, "Internet connection required"
        return True, ""
    
    # =========================================================================
    # Status Check Functions
    # =========================================================================

    def _has_nvidia_gpu(self) -> bool:
        """Check if NVIDIA GPU exists (lspci)"""
        try:
            result = self.run_shell('lspci | grep -qi nvidia', check=False)
            return result.returncode == 0
        except Exception:
            return False
    
    def _is_secure_boot_enabled(self) -> bool:
        """Check if Secure Boot is enabled"""
        try:
            result = self.run_shell('mokutil --sb-state', check=False)
            return 'SecureBoot enabled' in result.stdout
        except Exception:
            return False
    
    def _is_nvidia_working(self) -> bool:
        """Check if nvidia-smi works (driver verification)"""
        try:
            result = self.run_shell('nvidia-smi', check=False)
            return result.returncode == 0
        except Exception:
            return False
    
    def _is_package_installed(self) -> bool:
        """Check if NVIDIA driver package is installed"""
        driver_version = self.get_config('nvidia.driver_version', '535')
        try:
            result = self.run_shell(
                f'dpkg -l | grep -q "nvidia-driver-{driver_version}"',
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _is_module_loaded(self) -> bool:
        """Check if NVIDIA kernel module is loaded"""
        try:
            result = self.run_shell('lsmod | grep -q "^nvidia "', check=False)
            return result.returncode == 0
        except Exception:
            return False
    
    # =========================================================================
    # NVIDIA Container Toolkit
    # =========================================================================

    def _install_container_toolkit(self) -> bool:
        """
        NVIDIA Container Toolkit installation.
        Required for GPU usage with Docker.
        Should be called after NVIDIA driver installation.
        """
        self.logger.info("Installing NVIDIA Container Toolkit...")

        try:
            # 1. GPG key ekle
            result = self.run_shell(
                'curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | '
                'gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg --yes',
                check=False
            )
            if result.returncode != 0:
                self.logger.warning(f"Failed to add NVIDIA GPG key: {result.stderr}")
                return False

            # 2. Add repo
            result = self.run_shell(
                'curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | '
                'sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" | '
                'tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null',
                check=False
            )
            if result.returncode != 0:
                self.logger.warning(f"Failed to add NVIDIA repo: {result.stderr}")
                return False

            # 3. Install package
            self.run_command(['apt-get', 'update', '-qq'], check=False)
            if not self.apt_install(['nvidia-container-toolkit']):
                self.logger.warning("Failed to install nvidia-container-toolkit package")
                return False

            # 4. Update Docker daemon.json
            self.logger.info("Configuring Docker NVIDIA runtime...")
            daemon_config = """{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2",
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    }
}
"""
            if not self.write_file('/etc/docker/daemon.json', daemon_config):
                self.logger.warning("Failed to update Docker daemon.json")
                return False

            # 5. Configure with nvidia-ctk
            self.run_shell('nvidia-ctk runtime configure --runtime=docker', check=False)

            # 6. Restart Docker
            self.systemctl('restart', 'docker')

            self.logger.info("NVIDIA Container Toolkit installation completed")
            return True

        except Exception as e:
            self.logger.error(f"Container Toolkit installation error: {e}")
            return False

    # =========================================================================
    # MOK Key Management
    # =========================================================================

    def _find_mok_key(self) -> str:
        """Find MOK key file"""
        mok_paths = [
            '/var/lib/shim-signed/mok/MOK.der',
            '/var/lib/dkms/mok.pub',
        ]

        for path in mok_paths:
            if os.path.exists(path):
                return path

        return ''

    def _generate_mok_password(self) -> str:
        """Generate 8-digit random password using digits 1-8"""
        return ''.join([str(random.randint(1, 8)) for _ in range(8)])

    def _is_mok_enrolled(self) -> bool:
        """
        Check if MOK key is enrolled in UEFI.

        NOTE: This function is kept for reference only.
        Actual check is done in _detect_mok_status() using nvidia-smi.
        """
        try:
            result = self.run_shell('mokutil --list-enrolled 2>/dev/null | grep -q "Kiosk\\|DKMS"', check=False)
            return result.returncode == 0
        except Exception:
            return False

    def _is_mok_pending(self) -> bool:
        """
        Check if MOK import is pending.
        i.e., MOK screen will appear on next boot.
        """
        try:
            result = self.run_shell('mokutil --list-new 2>/dev/null', check=False)
            # If there's output, it means pending
            return bool(result.stdout.strip())
        except Exception:
            return False

    def _detect_mok_status(self) -> str:
        """
        Detect MOK status.

        OUTCOME-BASED detection: Checks the actual outcome (is nvidia-smi working?).
        Old key-based detection gave wrong results because old enrolled keys
        matched the pattern but weren't valid for current DKMS module.

        Returns:
            'enrolled': NVIDIA working (key enrolled and correct)
            'pending': Key imported, waiting for reboot
            'skipped': Rebooted but NVIDIA not working (user skipped MOK)
            'not_needed': Secure Boot disabled
            'no_key': MOK key file not found
            'not_installed': NVIDIA package not installed
        """
        # 1. If Secure Boot is disabled, MOK is not needed
        if not self._is_secure_boot_enabled():
            return 'not_needed'

        # 2. If NVIDIA package is not installed
        if not self._is_package_installed():
            return 'not_installed'

        # 3. If nvidia-smi works = enrolled and correct key
        #    This is the most reliable detection method
        if self._is_nvidia_working():
            return 'enrolled'

        # 4. Does MOK key file exist?
        mok_key = self._find_mok_key()
        if not mok_key:
            return 'no_key'

        # 5. Is there a pending import? (mokutil --list-new has output)
        if self._is_mok_pending():
            return 'pending'

        # 6. nvidia-smi not working, no pending import
        #    = Rebooted but user skipped MOK enrollment
        return 'skipped'

    def reimport_mok(self) -> Tuple[bool, str]:
        """
        Re-import MOK.
        Used when user skipped MOK enrollment at boot.
        """
        if not self._is_secure_boot_enabled():
            return False, "Secure Boot disabled, MOK not needed"

        mok_status = self._detect_mok_status()

        if mok_status == 'enrolled':
            return True, "MOK already enrolled"

        if mok_status == 'pending':
            mok_pwd = self.get_config('mok_password', 'unknown')
            return False, f"MOK import already pending. Reboot and enter password: {mok_pwd}"

        # Re-import
        self.logger.info("Re-importing MOK...")

        if self._setup_mok():
            self._config.set_module_status(self.name, 'mok_pending')
            mok_pwd = self.get_config('mok_password', 'unknown')
            return True, f"MOK re-imported. Password after reboot: {mok_pwd}"
        else:
            return False, "MOK import failed"

    def get_mok_info(self) -> dict:
        """
        Return MOK status info for panel.
        """
        mok_status = self._detect_mok_status()
        mok_password = self.get_config('mok_password')

        info = {
            'status': mok_status,
            'password': mok_password,
            'secure_boot': self._is_secure_boot_enabled(),
            'nvidia_working': self._is_nvidia_working(),
            'module_loaded': self._is_module_loaded(),
            'package_installed': self._is_package_installed(),
        }

        # Status messages
        status_messages = {
            'enrolled': 'MOK enrolled and NVIDIA working',
            'pending': f'MOK import pending. Reboot required, password: {mok_password}',
            'skipped': f'MOK skipped! NVIDIA not working. Re-import required. Password: {mok_password}',
            'not_needed': 'Secure Boot disabled, MOK not needed',
            'no_key': 'MOK key file not found',
            'not_installed': 'NVIDIA package not installed yet',
        }
        info['message'] = status_messages.get(mok_status, 'Unknown status')

        # Action required?
        info['action_required'] = mok_status in ('pending', 'skipped')
        info['can_reimport'] = mok_status == 'skipped'

        return info

    def _setup_mok(self) -> bool:
        """Register MOK key with UEFI"""
        # Generate or get existing MOK password
        mok_password = self.get_config('mok_password')
        if not mok_password:
            mok_password = self._generate_mok_password()
            # Save to MongoDB
            self._config.set('mok_password', mok_password)
            self.logger.info(f"MOK password generated: {mok_password}")

        mok_der = self._find_mok_key()

        if not mok_der:
            # Try to create MOK key
            self.logger.info("Creating MOK key...")
            self.run_shell('update-secureboot-policy --new-key', check=False)
            mok_der = self._find_mok_key()

        if not mok_der:
            self.logger.error("MOK key file not found!")
            return False

        # Register MOK (use printf - works in all shells)
        self.logger.info(f"Registering MOK key with UEFI: {mok_der}")
        result = self.run_shell(
            f'printf "%s\\n%s\\n" "{mok_password}" "{mok_password}" | mokutil --import {mok_der}',
            check=False
        )

        if result.returncode != 0:
            # Check error message
            stderr = result.stderr.lower() if result.stderr else ''

            # "key is already enrolled" messages count as success
            if 'already' in stderr or 'enrolled' in stderr:
                self.logger.info("MOK key already enrolled")
                return True

            self.logger.error(f"MOK import error: {result.stderr}")
            return False

        self.logger.info("MOK key registered successfully")
        return True
    
    # =========================================================================
    # Main Installation Function
    # =========================================================================

    def install(self) -> Tuple[bool, str]:
        """
        NVIDIA driver installation

        Flow:
        1. No GPU → completed (skipped)
        2. nvidia-smi works → completed
        3. Status mok_pending → check nvidia-smi
        4. Package not installed → apt install
        5. Secure Boot enabled → MOK setup → mok_pending
        6. Secure Boot disabled → reboot_required
        """
        driver_version = self.get_config('nvidia.driver_version', '535')
        current_status = self._config.get_module_status(self.name)
        
        # =====================================================================
        # 1. GPU Check
        # =====================================================================
        if not self._has_nvidia_gpu():
            self.logger.info("No NVIDIA GPU detected, skipping installation")
            return True, "No NVIDIA GPU found, installation skipped"

        self.logger.info("NVIDIA GPU detected")

        # =====================================================================
        # 2. Already Working?
        # =====================================================================
        if self._is_nvidia_working():
            self.logger.info("NVIDIA driver already working")
            # Install Container Toolkit (if not present)
            self._install_container_toolkit()
            return True, "NVIDIA driver already working"

        # =====================================================================
        # 3. MOK Pending Status (Post-reboot check)
        # =====================================================================
        if current_status == 'mok_pending':
            self.logger.info("Checking MOK pending status...")

            if self._is_nvidia_working():
                self.logger.info("MOK enrollment completed, NVIDIA working")
                # Install Container Toolkit
                self._install_container_toolkit()
                return True, "MOK enrollment completed, NVIDIA driver active"

            if self._is_module_loaded():
                self.logger.info("NVIDIA module loaded, waiting for nvidia-smi")
                # Install Container Toolkit
                self._install_container_toolkit()
                return True, "NVIDIA module loaded"

            # Still not working - MOK not enrolled
            self.logger.warning("MOK enrollment still pending")
            # Keep status as mok_pending
            self._config.set_module_status(self.name, 'mok_pending')
            mok_pwd = self.get_config('mok_password', 'not generated')
            return False, f"MOK enrollment pending. Reboot and select 'Enroll MOK' on blue screen. Password: {mok_pwd}"
        
        # =====================================================================
        # 4. Reboot Required Status
        # =====================================================================
        if current_status == 'reboot_required':
            self.logger.info("Checking reboot required status...")

            if self._is_nvidia_working():
                self.logger.info("NVIDIA working after reboot")
                # Install Container Toolkit
                self._install_container_toolkit()
                return True, "NVIDIA driver active"

            # Still not working - reboot not done
            self.logger.warning("Reboot not done yet")
            self._config.set_module_status(self.name, 'reboot_required')
            return False, "System reboot required for changes to take effect"

        # =====================================================================
        # 5. Package Check and Installation
        # =====================================================================
        if not self._is_package_installed():
            self.logger.info(f"Installing NVIDIA driver {driver_version}...")

            # Install only driver package (nvidia-utils comes automatically)
            packages = [f'nvidia-driver-{driver_version}']

            if not self.apt_install(packages):
                return False, "Failed to install NVIDIA packages"

            self.logger.info("NVIDIA package installed")
        else:
            self.logger.info("NVIDIA package already installed")

        # =====================================================================
        # 6. GRUB Configuration (quiet splash + nvidia modeset)
        # =====================================================================
        if not self.configure_grub({'nvidia_modeset': True}):
            self.logger.warning("GRUB configuration failed")

        # =====================================================================
        # 7. nvidia-persistenced Service
        # =====================================================================
        if not self.systemctl('enable', 'nvidia-persistenced'):
            self.logger.warning("Failed to enable nvidia-persistenced")

        # =====================================================================
        # 8. Secure Boot and MOK Status
        # =====================================================================
        if self._is_secure_boot_enabled():
            self.logger.info("Secure Boot active, setting up MOK...")

            if self._setup_mok():
                self.logger.info("MOK registered, approval needed after reboot")
                self._config.set_module_status(self.name, 'mok_pending')
                mok_pwd = self.get_config('mok_password', 'not generated')
                return False, f"NVIDIA installed. Select 'Enroll MOK' on blue screen after reboot. Password: {mok_pwd}"
            else:
                self.logger.warning("Failed to setup MOK, reboot still required")
                self._config.set_module_status(self.name, 'reboot_required')
                return False, "NVIDIA installed. MOK setup failed, reboot required"
        else:
            self.logger.info("Secure Boot disabled, only reboot required")
            self._config.set_module_status(self.name, 'reboot_required')
            return False, "NVIDIA installed. Reboot required for changes to take effect"
