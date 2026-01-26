"""
ACO Maintenance Panel - Display Module
Display screen configuration

Features:
- Kiosk user password
- GRUB rotation (console fbcon)
- Touch matrix (Xorg config)

Note: Screen rotation and Chromium URL are read from
config.yaml at runtime by scripts. This module only updates
system files (GRUB, Xorg config).
"""

import os
from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class DisplayModule(BaseModule):
    name = "display"
    display_name = "Display"
    description = "Screen rotation, touch configuration, user password"
    order = 6
    dependencies = ["cockpit"]

    def _configure_touch(self, vendor_id: str, matrix: str) -> bool:
        """
        Update Xorg touch config file (idempotent)

        Args:
            vendor_id: Touch device USB vendor:product ID (e.g., 222a:0001)
            matrix: TransformationMatrix value (e.g., 0 1 0 -1 0 1 0 0 1)

        Returns:
            bool: Success status
        """
        touch_conf = f'''Section "InputClass"
    Identifier "Touchscreen Rotation"
    MatchUSBID "{vendor_id}"
    MatchIsTouchscreen "on"
    Option "TransformationMatrix" "{matrix}"
EndSection
'''
        conf_path = '/etc/X11/xorg.conf.d/99-touch-rotation.conf'

        # Idempotent: Only write if there's a change
        if os.path.exists(conf_path):
            try:
                with open(conf_path) as f:
                    if f.read().strip() == touch_conf.strip():
                        self.logger.info("Touch config already up to date")
                        return True
            except IOError as e:
                self.logger.warning(f"Could not read existing touch config: {e}")

        # Create directory
        os.makedirs('/etc/X11/xorg.conf.d', exist_ok=True)

        # Write config file
        if not self.write_file(conf_path, touch_conf):
            self.logger.warning("Could not write touch config")
            return False

        self.logger.info("Touch config updated")
        return True

    def _set_kiosk_password(self, password: str) -> bool:
        """
        Set kiosk user password
        Fault-tolerant with multiple methods
        """
        if not password:
            self.logger.warning("Kiosk password not specified!")
            return True  # No password is not an error, continue

        self.logger.info("Setting kiosk user password...")

        # Method 1: chpasswd (preferred, fast)
        if os.path.exists('/usr/sbin/chpasswd'):
            result = self.run_shell(
                f'echo "kiosk:{password}" | /usr/sbin/chpasswd',
                check=False
            )
            if result.returncode == 0:
                self.logger.info("Password set (chpasswd)")
                return True
            self.logger.warning(f"chpasswd failed: {result.stderr}")

        # Method 2: Install passwd package and retry
        self.logger.info("chpasswd not found, installing passwd package...")
        self.apt_install(['passwd'])

        if os.path.exists('/usr/sbin/chpasswd'):
            result = self.run_shell(
                f'echo "kiosk:{password}" | /usr/sbin/chpasswd',
                check=False
            )
            if result.returncode == 0:
                self.logger.info("Password set (chpasswd)")
                return True
            self.logger.warning(f"chpasswd failed again: {result.stderr}")

        # Method 3: openssl + usermod (fallback)
        self.logger.info("Trying alternative method (usermod)...")
        result = self.run_shell(
            f'usermod --password $(openssl passwd -6 "{password}") kiosk',
            check=False
        )
        if result.returncode == 0:
            self.logger.info("Password set (usermod)")
            return True

        self.logger.error(f"Could not set password! Last error: {result.stderr}")
        return False

    def install(self) -> Tuple[bool, str]:
        """
        Display configuration

        Flow:
        1. Kiosk user password (from config)
        2. GRUB rotation - for console (from config)
        3. Touch matrix - Xorg config (from config)

        Note: Screen rotation and URL settings are read from config
        by display-init.sh and chromium-kiosk.sh.
        """
        try:
            # =================================================================
            # 1. Kiosk User Password
            # =================================================================
            kiosk_password = self.get_config('passwords.kiosk', '')

            if not self._set_kiosk_password(kiosk_password):
                return False, "Could not set kiosk password"

            # =================================================================
            # 2. GRUB Rotation (for console)
            # =================================================================
            grub_rotation = self.get_config('display.grub_rotation', 1)
            self.logger.info(f"Setting GRUB rotation: {grub_rotation}")
            if not self.configure_grub({'grub_rotation': grub_rotation}):
                self.logger.warning("Could not set GRUB rotation")

            # =================================================================
            # 3. Touch Matrix - Xorg Config
            # =================================================================
            touch_vendor = self.get_config('display.touch_vendor_id', '222a:0001')
            touch_matrix = self.get_config('display.touch_matrix', '0 1 0 -1 0 1 0 0 1')
            self.logger.info(f"Setting touch config: {touch_vendor}")
            if not self._configure_touch(touch_vendor, touch_matrix):
                self.logger.warning("Could not set touch config")

            # =================================================================
            # 4. Information
            # =================================================================
            self.logger.info("Screen rotation and URL settings will be applied after X restart")

            self.logger.info("Display configuration completed")
            return True, "Display configured (X restart recommended for changes)"

        except Exception as e:
            self.logger.error(f"Display configuration error: {e}")
            return False, str(e)
