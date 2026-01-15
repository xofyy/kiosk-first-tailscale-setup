"""
Kiosk Setup Panel - Base Module Class
Tüm kurulum modüllerinin temel sınıfı
"""

import os
import subprocess
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime

from app.config import config

logger = logging.getLogger(__name__)

# Log dizini
LOG_DIR = '/var/log/kiosk-setup'


def setup_module_logger(module_name: str) -> logging.Logger:
    """
    Modül için özel logger oluştur.
    Her modül kendi log dosyasına yazar.
    """
    # Log dizinini oluştur
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Logger oluştur
    module_logger = logging.getLogger(f"module.{module_name}")
    module_logger.setLevel(logging.DEBUG)
    
    # Mevcut handler'ları temizle (tekrarlayan log'ları önle)
    module_logger.handlers.clear()
    
    # Dosya handler'ı
    log_file = os.path.join(LOG_DIR, f"{module_name}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # Format
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    module_logger.addHandler(file_handler)
    
    # Ayrıca main.log'a da yaz
    main_log = os.path.join(LOG_DIR, 'main.log')
    main_handler = logging.FileHandler(main_log, encoding='utf-8')
    main_handler.setLevel(logging.INFO)
    main_handler.setFormatter(formatter)
    module_logger.addHandler(main_handler)
    
    return module_logger


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
        self.logger = setup_module_logger(self.name)
        self._log_file = os.path.join(LOG_DIR, f"{self.name}.log")
    
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
        """APT ile paket kur (noninteractive, real-time log)"""
        if not packages:
            return True
        
        self.logger.info(f"Paketler kuruluyor: {', '.join(packages)}")
        
        # Noninteractive environment
        env = os.environ.copy()
        env['DEBIAN_FRONTEND'] = 'noninteractive'
        env['NEEDRESTART_MODE'] = 'a'  # Otomatik restart, sormaz
        
        try:
            # Önce update (real-time log)
            self.logger.info("APT güncelleniyor...")
            self._run_apt_with_logging(['apt-get', 'update', '-q'], env)
            
            # Paketleri kur (real-time log)
            self.logger.info(f"Paketler kuruluyor: {' '.join(packages)}")
            self._run_apt_with_logging(
                ['apt-get', 'install', '-y', '-q'] + packages,
                env,
                timeout=900  # 15 dakika
            )
            
            self.logger.info("APT kurulumu tamamlandı")
            return True
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"APT kurulum zaman aşımı: {packages}")
            return False
        except Exception as e:
            self.logger.error(f"APT kurulum hatası: {e}")
            return False
    
    def _run_apt_with_logging(
        self, 
        command: List[str], 
        env: dict,
        timeout: int = 300
    ) -> None:
        """APT komutunu çalıştır ve çıktıyı real-time logla"""
        self.logger.debug(f"Çalıştırılıyor: {' '.join(command)}")
        
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1  # Line buffered
        )
        
        start_time = datetime.now()
        
        try:
            # Çıktıyı satır satır oku ve logla
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    self._log_apt_output(line)
                
                # Timeout kontrolü
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > timeout:
                    process.kill()
                    raise subprocess.TimeoutExpired(command, timeout)
            
            # Sonucu bekle
            return_code = process.wait()
            
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, command)
                
        except Exception:
            process.kill()
            raise
    
    def _log_apt_output(self, line: str) -> None:
        """APT çıktısını log dosyasına yaz"""
        # Önemli satırları INFO olarak, diğerlerini DEBUG olarak logla
        important_keywords = [
            'Setting up', 'Unpacking', 'Processing', 'Selecting',
            'Get:', 'Hit:', 'Fetched', 'upgraded', 'newly installed',
            'Reading', 'Building', 'error', 'warning', 'E:', 'W:'
        ]
        
        is_important = any(kw.lower() in line.lower() for kw in important_keywords)
        
        if is_important:
            self.logger.info(f"[APT] {line}")
        else:
            self.logger.debug(f"[APT] {line}")
    
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
    
    def set_module_status(self, status: str) -> None:
        """Bu modülün durumunu ayarla"""
        self.logger.info(f"Modül durumu değişti: {status}")
        config.set_module_status(self.name, status)