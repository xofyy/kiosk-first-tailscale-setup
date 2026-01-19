"""
Kiosk Setup Panel - Base Module Class
Tüm kurulum modüllerinin temel sınıfı

MongoDB tabanlı config sistemi.
"""

import os
import subprocess
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# MongoDB bağlantı ayarları
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "kiosk"
MONGO_COLLECTION = "settings"


class MongoConfig:
    """
    MongoDB tabanlı config yönetimi.
    Singleton pattern ile tek instance.
    """
    _instance = None
    _client = None
    _db = None
    _collection = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _ensure_connection(self):
        """MongoDB bağlantısını sağla"""
        if self._client is None:
            try:
                from pymongo import MongoClient
                self._client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
                self._db = self._client[MONGO_DB]
                self._collection = self._db[MONGO_COLLECTION]
                # Bağlantı testi
                self._client.admin.command('ping')
            except Exception as e:
                logger.warning(f"MongoDB bağlantı hatası: {e}")
                self._client = None
                self._db = None
                self._collection = None

    def _get_settings(self) -> Dict[str, Any]:
        """Settings dökümanını al"""
        self._ensure_connection()
        if self._collection is None:
            return {}

        try:
            doc = self._collection.find_one({})
            return doc if doc else {}
        except Exception as e:
            logger.warning(f"MongoDB okuma hatası: {e}")
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Config değeri al (noktalı notation destekli).
        Örnek: get('modules.nvidia') veya get('kiosk_id')
        """
        settings = self._get_settings()

        # Noktalı notation desteği
        keys = key.split('.')
        value = settings

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

            if value is None:
                return default

        return value

    def set(self, key: str, value: Any) -> bool:
        """
        Config değeri ayarla (noktalı notation destekli).
        """
        self._ensure_connection()
        if self._collection is None:
            return False

        try:
            self._collection.update_one(
                {},
                {'$set': {key: value}},
                upsert=True
            )
            return True
        except Exception as e:
            logger.warning(f"MongoDB yazma hatası: {e}")
            return False

    def get_module_status(self, module_name: str) -> str:
        """Modül durumunu al"""
        return self.get(f'modules.{module_name}', 'pending')

    def set_module_status(self, module_name: str, status: str) -> bool:
        """Modül durumunu ayarla"""
        return self.set(f'modules.{module_name}', status)

    def is_module_completed(self, module_name: str) -> bool:
        """Modül tamamlandı mı?"""
        return self.get_module_status(module_name) == 'completed'

    def get_kiosk_id(self) -> Optional[str]:
        """Kiosk ID'yi al"""
        return self.get('kiosk_id')

    def set_kiosk_id(self, kiosk_id: str) -> bool:
        """Kiosk ID'yi ayarla"""
        return self.set('kiosk_id', kiosk_id)

    def get_hardware_id(self) -> Optional[str]:
        """Hardware ID'yi al"""
        return self.get('hardware_id')

    def set_hardware_id(self, hardware_id: str) -> bool:
        """Hardware ID'yi ayarla"""
        return self.set('hardware_id', hardware_id)

    def save(self):
        """Compatibility method - MongoDB auto-save"""
        pass

    def reload(self):
        """Compatibility method - MongoDB always fresh"""
        pass

    def get_all(self) -> Dict[str, Any]:
        """Tüm settings'i döndür"""
        settings = self._get_settings()
        # _id alanını kaldır
        if '_id' in settings:
            del settings['_id']
        return settings

    def get_all_module_statuses(self) -> Dict[str, str]:
        """Tüm modül durumlarını döndür"""
        modules = self.get('modules', {})
        return modules if isinstance(modules, dict) else {}

    def is_setting_locked(self, key: str) -> bool:
        """
        Ayar kilitli mi? (Artık MongoDB'de lock sistemi yok)
        Tüm ayarlar değiştirilebilir.
        """
        return False

    def set_setup_complete(self, complete: bool) -> bool:
        """
        Kurulum tamamlandı işareti.
        MongoDB'ye yazar ve marker dosyasını senkronize eder.
        """
        result = self.set('setup_complete', complete)

        # Marker dosyasını senkronize et (openbox autostart için)
        marker_file = '/etc/kiosk-setup/.setup-complete'
        try:
            if complete:
                # Dosyayı oluştur
                os.makedirs(os.path.dirname(marker_file), exist_ok=True)
                with open(marker_file, 'w') as f:
                    f.write(f'# Setup completed at {datetime.now().isoformat()}\n')
                logger.info(f"Setup complete marker oluşturuldu: {marker_file}")
            else:
                # Dosyayı sil
                if os.path.exists(marker_file):
                    os.remove(marker_file)
                    logger.info(f"Setup complete marker silindi: {marker_file}")
        except Exception as e:
            logger.warning(f"Marker dosyası senkronizasyon hatası: {e}")

        return result

    def is_setup_complete(self) -> bool:
        """Kurulum tamamlandı mı?"""
        return self.get('setup_complete', False)


# Global config instance
mongo_config = MongoConfig()

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
    
    def __init__(self, config_instance: 'MongoConfig' = None):
        """
        BaseModule constructor.

        Args:
            config_instance: Opsiyonel config nesnesi (DIP için).
                             None ise global mongo_config kullanılır.
                             Test için mock config geçilebilir.
        """
        # MongoDB tabanlı config
        if config_instance is None:
            self._config = mongo_config
        else:
            self._config = config_instance

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
            'status': self._config.get_module_status(self.name)
        }
    
    def can_install(self) -> Tuple[bool, str]:
        """
        Modül kurulabilir mi kontrol et.
        Returns: (kurulabilir_mi, sebep)
        """
        # Zaten kurulu mu?
        if self._config.is_module_completed(self.name):
            return False, "Modül zaten kurulu"
        
        # Şu an kuruluyor mu?
        if self._config.get_module_status(self.name) == 'installing':
            return False, "Modül kurulumu devam ediyor"
        
        # Bağımlılıklar kurulu mu?
        for dep in self.dependencies:
            if not self._config.is_module_completed(dep):
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
        return self._config.get(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """Config değeri ayarla"""
        self._config.set(key, value)
        self._config.save()
    
    def set_module_status(self, status: str) -> None:
        """Bu modülün durumunu ayarla"""
        self.logger.info(f"Modül durumu değişti: {status}")
        self._config.set_module_status(self.name, status)
    
    def configure_grub(self, params: Dict[str, Any] = None) -> bool:
        """
        GRUB parametrelerini merkezi olarak yapılandır.
        
        Args:
            params: Opsiyonel parametreler
                - nvidia_modeset: True ise nvidia-drm.modeset=1 ekle
                - grub_rotation: int değer ile fbcon=rotate:X ekle
        
        Varsayılan olarak 'quiet splash' her zaman eklenir.
        
        Returns:
            Başarılı mı
        """
        params = params or {}
        grub_file = '/etc/default/grub'
        
        try:
            with open(grub_file, 'r') as f:
                grub_content = f.read()
            
            original_content = grub_content
            
            # 1. quiet splash kontrolü (her zaman)
            if 'quiet' not in grub_content or 'splash' not in grub_content:
                # quiet splash yoksa ekle
                if 'GRUB_CMDLINE_LINUX_DEFAULT="' in grub_content:
                    grub_content = grub_content.replace(
                        'GRUB_CMDLINE_LINUX_DEFAULT="',
                        'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash '
                    )
                    self.logger.info("GRUB: quiet splash eklendi")
            
            # 2. nvidia-drm.modeset=1 kontrolü
            if params.get('nvidia_modeset') and 'nvidia-drm.modeset=1' not in grub_content:
                grub_content = grub_content.replace(
                    'GRUB_CMDLINE_LINUX_DEFAULT="',
                    'GRUB_CMDLINE_LINUX_DEFAULT="nvidia-drm.modeset=1 '
                )
                self.logger.info("GRUB: nvidia-drm.modeset=1 eklendi")
            
            # 3. fbcon rotation kontrolü
            grub_rotation = params.get('grub_rotation')
            if grub_rotation is not None and 'fbcon=rotate:' not in grub_content:
                grub_content = grub_content.replace(
                    'GRUB_CMDLINE_LINUX_DEFAULT="',
                    f'GRUB_CMDLINE_LINUX_DEFAULT="fbcon=rotate:{grub_rotation} '
                )
                self.logger.info(f"GRUB: fbcon=rotate:{grub_rotation} eklendi")
            
            # Değişiklik var mı?
            if grub_content != original_content:
                with open(grub_file, 'w') as f:
                    f.write(grub_content)
                
                # grub-mkconfig çalıştır (update-grub scripti PATH sorunu yaratıyor)
                self.logger.info("GRUB yapılandırması güncelleniyor...")
                
                # Önce UEFI yolunu dene, yoksa BIOS yolu
                grub_cfg_paths = [
                    '/boot/grub/grub.cfg',           # Standart
                    '/boot/efi/EFI/ubuntu/grub.cfg', # UEFI Ubuntu
                ]
                
                grub_cfg = None
                for path in grub_cfg_paths:
                    if os.path.exists(os.path.dirname(path)):
                        grub_cfg = path
                        break
                
                if grub_cfg:
                    result = self.run_command(
                        ['/usr/sbin/grub-mkconfig', '-o', grub_cfg],
                        check=False
                    )
                    
                    if result.returncode == 0:
                        self.logger.info(f"GRUB yapılandırması güncellendi: {grub_cfg}")
                    else:
                        self.logger.warning(f"grub-mkconfig uyarısı: {result.stderr}")
                else:
                    self.logger.warning("GRUB config dizini bulunamadı, atlanıyor")
            else:
                self.logger.info("GRUB yapılandırması zaten güncel")
            
            return True
            
        except FileNotFoundError:
            self.logger.warning(f"GRUB dosyası bulunamadı: {grub_file}")
            return False
        except Exception as e:
            self.logger.warning(f"GRUB yapılandırma hatası: {e}")
            return False