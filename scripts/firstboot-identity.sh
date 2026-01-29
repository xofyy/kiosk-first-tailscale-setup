#!/bin/bash
set -e

echo "[firstboot] Resetting machine-id..."
rm -f /etc/machine-id
rm -f /var/lib/dbus/machine-id
systemd-machine-id-setup

echo "[firstboot] Resetting SSH host keys..."
rm -f /etc/ssh/ssh_host_*
dpkg-reconfigure openssh-server

echo "[firstboot] Disabling firstboot service..."
systemctl disable firstboot-identity.service

echo "[firstboot] Done."
