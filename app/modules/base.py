"""
Kiosk Setup Panel - Base Module Class
Tüm kurulum modüllerinin temel sınıfı
"""

import subprocess
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List, Optional

from app.config import config

logger = logging.getLogger(__name__)


class BaseModule(ABC):
    """
    Kurulum modülleri için abstract base class.
    Tüm modüller bu sınıftan türetilmelidir.
    """
    
    # Alt sınıflar tarafından override edilmeli
    name: str = ""
    display_name: str = ""
    description: str = ""
    order: int = 0
    dependencies: List[str] = []
    
    def __init__(self):
        self.logger = logging.getLogger(f"module.{self.name}")
    
    def get_info(self) -> Dict[str, Any]:
        """Modül bilgilerini döndür"""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'order': self.order,
            'dependencies': self.dependencies,
            'status': config.get_module_status(self.name)
        }
    
    def can_install(self) -> Tuple[bool, str]:
        """
        Modül kurulabilir mi kontrol et.
        Returns: (kurulabilir_mi, sebep)
        """
        # Zaten kurulu mu?
        if config.is_module_completed(self.name):
            return False, "Modül zaten kurulu"
        
        # Şu an kuruluyor mu?
        if config.get_module_status(self.name) == 'installing':
            return False, "Modül kurulumu devam ediyor"
        
        # Bağımlılıklar kurulu mu?
        for dep in self.dependencies:
            if not config.is_module_completed(dep):
                return False, f"Bağımlılık kurulu değil: {dep}"
        
        # Özel kontroller (alt sınıfta override edilebilir)
        can, reason = self._check_prerequisites()
        if not can:
            return False, reason
        
        return True, "Kurulabilir"
    
    def _check_prerequisites(self) -> Tuple[bool, str]:
        """
        Özel ön koşul kontrolleri.
        Alt sınıflar override edebilir.
        """
        return True, ""
    
    @abstractmethod
    def install(self) -> Tuple[bool, str]:
        """
        Modül kurulumunu gerçekleştir.
        Alt sınıflar tarafından implement edilmeli.
        Returns: (başarılı_mı, mesaj)
        """
        pass
    
    def uninstall(self) -> Tuple[bool, str]:
        """
        Modül kaldırma (opsiyonel).
        Alt sınıflar override edebilir.
        """
        return False, "Bu modül kaldırılamaz"
    
    # === Yardımcı Metodlar ===
    
    def run_command(
        self,
        command: List[str],
        check: bool = True,
        capture_output: bool = True,
        timeout: Optional[int] = None
    ) -> subprocess.CompletedProcess:
        """Komut çalıştır"""
        self.logger.info(f"Komut: {' '.join(command)}")
        
        try:
            result = subprocess.run(
                command,
                check=check,
                capture_output=capture_output,
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Komut hatası: {e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            self.logger.error(f"Komut zaman aşımı: {command}")
            raise
    
    def run_shell(
        self,
        command: str,
        check: bool = True,
        capture_output: bool = True,
        timeout: Optional[int] = None
    ) -> subprocess.CompletedProcess:
        """Shell komutu çalıştır"""
        self.logger.info(f"Shell: {command}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                check=check,
                capture_output=capture_output,
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Shell hatası: {e.stderr}")
            raise
    
    def apt_install(self, packages: List[str]) -> bool:
        """APT ile paket kur (noninteractive)"""
        if not packages:
            return True
        
        self.logger.info(f"Paketler kuruluyor: {', '.join(packages)}")
        
        # Noninteractive environment
        import os
        env = os.environ.copy()
        env['DEBIAN_FRONTEND'] = 'noninteractive'
        env['NEEDRESTART_MODE'] = 'a'  # Otomatik restart, sormaz
        
        try:
            # Önce update
            subprocess.run(
                ['apt-get', 'update', '-qq'],
                check=True,
                capture_output=True,
                text=True,
                env=env
            )
            
            # Paketleri kur
            subprocess.run(
                ['apt-get', 'install', '-y', '-qq'] + packages,
                check=True,
                capture_output=True,
                text=True,
                timeout=900,  # 15 dakika (NVIDIA gibi büyük paketler için)
                env=env
            )
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"APT kurulum hatası: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            self.logger.error(f"APT kurulum zaman aşımı: {packages}")
            return False
        except Exception as e:
            self.logger.error(f"APT kurulum hatası: {e}")
            return False
    
    def systemctl(self, action: str, service: str) -> bool:
        """Systemd servis kontrolü"""
        try:
            self.run_command(['systemctl', action, service])
            return True
        except Exception:
            return False
    
    def write_file(self, path: str, content: str, mode: int = 0o644) -> bool:
        """Dosya yaz"""
        import os
        try:
            # Dizini oluştur
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            with open(path, 'w') as f:
                f.write(content)
            
            os.chmod(path, mode)
            self.logger.info(f"Dosya yazıldı: {path}")
            return True
        except Exception as e:
            self.logger.error(f"Dosya yazma hatası: {e}")
            return False
    
    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Jinja2 template render et"""
        from jinja2 import Environment, FileSystemLoader
        
        template_dirs = [
            '/opt/kiosk-setup-panel/templates',
            'templates'
        ]
        
        for template_dir in template_dirs:
            try:
                env = Environment(loader=FileSystemLoader(template_dir))
                template = env.get_template(template_name)
                return template.render(**context)
            except Exception:
                continue
        
        raise FileNotFoundError(f"Template bulunamadı: {template_name}")
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Config değeri al"""
        return config.get(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """Config değeri ayarla"""
        config.set(key, value)
        config.save()
