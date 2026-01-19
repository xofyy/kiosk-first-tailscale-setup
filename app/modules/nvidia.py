"""
Kiosk Setup Panel - NVIDIA Module
NVIDIA GPU driver kurulumu

Özellikler:
- GPU kontrolü (lspci)
- Secure Boot kontrolü (mokutil)
- Paket kontrolü (dpkg)
- Modül kontrolü (lsmod)
- nvidia-smi doğrulaması
- MOK key yönetimi
- Random MOK password üretimi (1-8 arası 8 hane)
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
    description = "NVIDIA GPU driver kurulumu, MOK key ve GRUB yapılandırması"
    order = 1
    dependencies = []  # İlk modül, bağımlılık yok
    
    def _check_prerequisites(self) -> Tuple[bool, str]:
        """İnternet bağlantısı kontrolü"""
        system = SystemService()
        if not system.check_internet():
            return False, "İnternet bağlantısı gerekli"
        return True, ""
    
    # =========================================================================
    # Durum Kontrol Fonksiyonları
    # =========================================================================
    
    def _has_nvidia_gpu(self) -> bool:
        """NVIDIA GPU var mı? (lspci kontrolü)"""
        try:
            result = self.run_shell('lspci | grep -qi nvidia', check=False)
            return result.returncode == 0
        except Exception:
            return False
    
    def _is_secure_boot_enabled(self) -> bool:
        """Secure Boot açık mı?"""
        try:
            result = self.run_shell('mokutil --sb-state', check=False)
            return 'SecureBoot enabled' in result.stdout
        except Exception:
            return False
    
    def _is_nvidia_working(self) -> bool:
        """nvidia-smi çalışıyor mu? (Sürücü doğrulaması)"""
        try:
            result = self.run_shell('nvidia-smi', check=False)
            return result.returncode == 0
        except Exception:
            return False
    
    def _is_package_installed(self) -> bool:
        """NVIDIA driver paketi kurulu mu?"""
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
        """NVIDIA kernel modülü yüklü mü?"""
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
        NVIDIA Container Toolkit kurulumu.
        Docker ile GPU kullanımı için gerekli.
        NVIDIA driver kurulumu tamamlandıktan sonra çağrılmalı.
        """
        self.logger.info("NVIDIA Container Toolkit kuruluyor...")

        try:
            # 1. GPG key ekle
            result = self.run_shell(
                'curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | '
                'gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg --yes',
                check=False
            )
            if result.returncode != 0:
                self.logger.warning(f"NVIDIA GPG key eklenemedi: {result.stderr}")
                return False

            # 2. Repo ekle
            result = self.run_shell(
                'curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | '
                'sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" | '
                'tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null',
                check=False
            )
            if result.returncode != 0:
                self.logger.warning(f"NVIDIA repo eklenemedi: {result.stderr}")
                return False

            # 3. Paketi kur
            self.run_command(['apt-get', 'update', '-qq'], check=False)
            if not self.apt_install(['nvidia-container-toolkit']):
                self.logger.warning("nvidia-container-toolkit paketi kurulamadı")
                return False

            # 4. Docker daemon.json güncelle
            self.logger.info("Docker NVIDIA runtime yapılandırılıyor...")
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
                self.logger.warning("Docker daemon.json güncellenemedi")
                return False

            # 5. nvidia-ctk ile yapılandır
            self.run_shell('nvidia-ctk runtime configure --runtime=docker', check=False)

            # 6. Docker'ı yeniden başlat
            self.systemctl('restart', 'docker')

            self.logger.info("NVIDIA Container Toolkit kurulumu tamamlandı")
            return True

        except Exception as e:
            self.logger.error(f"Container Toolkit kurulum hatası: {e}")
            return False

    # =========================================================================
    # MOK Key Yönetimi
    # =========================================================================
    
    def _find_mok_key(self) -> str:
        """MOK key dosyasını bul"""
        mok_paths = [
            '/var/lib/shim-signed/mok/MOK.der',
            '/var/lib/dkms/mok.pub',
        ]
        
        for path in mok_paths:
            if os.path.exists(path):
                return path
        
        return ''
    
    def _generate_mok_password(self) -> str:
        """1-8 arası rakamlardan 8 haneli random şifre üret"""
        return ''.join([str(random.randint(1, 8)) for _ in range(8)])

    def _setup_mok(self) -> bool:
        """MOK key'i UEFI'ye kaydet"""
        # MOK password üret veya mevcut olanı al
        mok_password = self.get_config('mok_password')
        if not mok_password:
            mok_password = self._generate_mok_password()
            # MongoDB'ye kaydet
            self._config.set('mok_password', mok_password)
            self.logger.info(f"MOK şifresi oluşturuldu: {mok_password}")

        mok_der = self._find_mok_key()
        
        if not mok_der:
            # MOK oluşturmayı dene
            self.logger.info("MOK anahtarı oluşturuluyor...")
            self.run_shell('update-secureboot-policy --new-key', check=False)
            mok_der = self._find_mok_key()
        
        if not mok_der:
            self.logger.error("MOK anahtar dosyası bulunamadı!")
            return False
        
        # MOK'u kaydet (printf kullan - tüm shell'lerde çalışır)
        self.logger.info(f"MOK anahtarı UEFI'ye kaydediliyor: {mok_der}")
        result = self.run_shell(
            f'printf "%s\\n%s\\n" "{mok_password}" "{mok_password}" | mokutil --import {mok_der}',
            check=False
        )
        
        if result.returncode != 0:
            # Hata mesajını kontrol et
            stderr = result.stderr.lower() if result.stderr else ''
            
            # "key is already enrolled" gibi mesajlar başarı sayılır
            if 'already' in stderr or 'enrolled' in stderr:
                self.logger.info("MOK anahtarı zaten kayıtlı")
                return True
            
            self.logger.error(f"MOK import hatası: {result.stderr}")
            return False
        
        self.logger.info("MOK anahtarı başarıyla kaydedildi")
        return True
    
    # =========================================================================
    # Ana Kurulum Fonksiyonu
    # =========================================================================
    
    def install(self) -> Tuple[bool, str]:
        """
        NVIDIA driver kurulumu
        
        Akış:
        1. GPU yoksa → completed (atlandı)
        2. nvidia-smi çalışıyorsa → completed
        3. Status mok_pending ise → nvidia-smi kontrol
        4. Paket kurulu değilse → apt install
        5. Secure Boot varsa → MOK setup → mok_pending
        6. Secure Boot yoksa → reboot_required
        """
        driver_version = self.get_config('nvidia.driver_version', '535')
        current_status = self._config.get_module_status(self.name)
        
        # =====================================================================
        # 1. GPU Kontrolü
        # =====================================================================
        if not self._has_nvidia_gpu():
            self.logger.info("NVIDIA GPU tespit edilmedi, kurulum atlanıyor")
            return True, "NVIDIA GPU bulunamadı, kurulum atlandı"
        
        self.logger.info("NVIDIA GPU tespit edildi")
        
        # =====================================================================
        # 2. Zaten Çalışıyor mu?
        # =====================================================================
        if self._is_nvidia_working():
            self.logger.info("NVIDIA sürücüsü zaten çalışıyor")
            # Container Toolkit kur (yoksa)
            self._install_container_toolkit()
            return True, "NVIDIA sürücüsü zaten çalışıyor"
        
        # =====================================================================
        # 3. MOK Pending Durumu (Reboot sonrası kontrol)
        # =====================================================================
        if current_status == 'mok_pending':
            self.logger.info("MOK pending durumu kontrol ediliyor...")
            
            if self._is_nvidia_working():
                self.logger.info("MOK onayı tamamlandı, NVIDIA çalışıyor")
                # Container Toolkit kur
                self._install_container_toolkit()
                return True, "MOK onayı tamamlandı, NVIDIA sürücüsü aktif"

            if self._is_module_loaded():
                self.logger.info("NVIDIA modülü yüklü, nvidia-smi bekliyor")
                # Container Toolkit kur
                self._install_container_toolkit()
                return True, "NVIDIA modülü yüklendi"
            
            # Hala çalışmıyor - MOK onayı yapılmamış
            self.logger.warning("MOK onayı hala bekleniyor")
            # Status'u mok_pending olarak bırak
            self._config.set_module_status(self.name, 'mok_pending')
            mok_pwd = self.get_config('mok_password', 'oluşturulmadı')
            return False, f"MOK onayı bekleniyor. Reboot yapın ve mavi ekranda 'Enroll MOK' seçin. Şifre: {mok_pwd}"
        
        # =====================================================================
        # 4. Reboot Required Durumu
        # =====================================================================
        if current_status == 'reboot_required':
            self.logger.info("Reboot required durumu kontrol ediliyor...")

            if self._is_nvidia_working():
                self.logger.info("Reboot sonrası NVIDIA çalışıyor")
                # Container Toolkit kur
                self._install_container_toolkit()
                return True, "NVIDIA sürücüsü aktif"
            
            # Hala çalışmıyor - reboot yapılmamış
            self.logger.warning("Reboot henüz yapılmamış")
            self._config.set_module_status(self.name, 'reboot_required')
            return False, "Değişikliklerin uygulanması için sistem yeniden başlatılmalı"
        
        # =====================================================================
        # 5. Paket Kontrolü ve Kurulum
        # =====================================================================
        if not self._is_package_installed():
            self.logger.info(f"NVIDIA driver {driver_version} kuruluyor...")
            
            # Sadece driver paketini kur (nvidia-utils otomatik gelir)
            packages = [f'nvidia-driver-{driver_version}']
            
            if not self.apt_install(packages):
                return False, "NVIDIA paketleri kurulamadı"
            
            self.logger.info("NVIDIA paketi kuruldu")
        else:
            self.logger.info("NVIDIA paketi zaten kurulu")
        
        # =====================================================================
        # 6. GRUB Yapılandırması (quiet splash + nvidia modeset)
        # =====================================================================
        if not self.configure_grub({'nvidia_modeset': True}):
            self.logger.warning("GRUB yapılandırması başarısız")
        
        # =====================================================================
        # 7. nvidia-persistenced Servisi
        # =====================================================================
        if not self.systemctl('enable', 'nvidia-persistenced'):
            self.logger.warning("nvidia-persistenced enable edilemedi")
        
        # =====================================================================
        # 8. Secure Boot ve MOK Durumu
        # =====================================================================
        if self._is_secure_boot_enabled():
            self.logger.info("Secure Boot aktif, MOK ayarlanıyor...")
            
            if self._setup_mok():
                self.logger.info("MOK kaydedildi, reboot sonrası onay gerekecek")
                self._config.set_module_status(self.name, 'mok_pending')
                mok_pwd = self.get_config('mok_password', 'oluşturulmadı')
                return False, f"NVIDIA kuruldu. Reboot sonrası mavi ekranda 'Enroll MOK' seçin. Şifre: {mok_pwd}"
            else:
                self.logger.warning("MOK ayarlanamadı, yine de reboot gerekli")
                self._config.set_module_status(self.name, 'reboot_required')
                return False, "NVIDIA kuruldu. MOK ayarlanamadı, reboot gerekli"
        else:
            self.logger.info("Secure Boot kapalı, sadece reboot gerekli")
            self._config.set_module_status(self.name, 'reboot_required')
            return False, "NVIDIA kuruldu. Değişikliklerin uygulanması için reboot gerekli"
