"""
Kiosk Setup Panel - Configuration Manager
Merkezi ayar yönetimi modülü
"""

import os
import yaml
from typing import Any, Dict, Optional
from pathlib import Path

CONFIG_FILE = "/etc/kiosk-setup/config.yaml"
DEFAULT_CONFIG_FILE = "/opt/kiosk-setup-panel/config/default.yaml"


class Config:
    """Yapılandırma yönetimi sınıfı"""
    
    _instance: Optional['Config'] = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance
    
    def _load(self) -> None:
        """Config dosyasını yükle"""
        # Önce varsayılan config'i yükle
        if os.path.exists(DEFAULT_CONFIG_FILE):
            with open(DEFAULT_CONFIG_FILE, 'r') as f:
                self._config = yaml.safe_load(f) or {}
        
        # Sonra gerçek config'i üzerine yaz
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                user_config = yaml.safe_load(f) or {}
                self._deep_merge(self._config, user_config)
    
    def _deep_merge(self, base: dict, override: dict) -> None:
        """İki dict'i derin birleştir"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def reload(self) -> None:
        """Config'i yeniden yükle"""
        self._config = {}
        self._load()
    
    def save(self) -> bool:
        """Config'i dosyaya kaydet"""
        try:
            # Dizini oluştur
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)
            return True
        except Exception as e:
            print(f"Config kaydetme hatası: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Nokta notasyonu ile değer al
        Örnek: config.get('kiosk.url')
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        Nokta notasyonu ile değer ayarla
        Örnek: config.set('kiosk.url', 'http://localhost:3000')
        """
        keys = key.split('.')
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def get_all(self) -> Dict[str, Any]:
        """Tüm config'i döndür"""
        return self._config.copy()
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Belirli bir bölümü döndür"""
        return self._config.get(section, {}).copy()
    
    # === Modül Durumları ===
    
    def get_module_status(self, module: str) -> str:
        """Modül durumunu al"""
        return self.get(f'modules.{module}', 'pending')
    
    def set_module_status(self, module: str, status: str) -> None:
        """Modül durumunu ayarla (pending, installing, completed, failed)"""
        self.set(f'modules.{module}', status)
        self.save()
    
    def is_module_completed(self, module: str) -> bool:
        """Modül tamamlanmış mı?"""
        return self.get_module_status(module) == 'completed'
    
    def get_all_module_statuses(self) -> Dict[str, str]:
        """Tüm modül durumlarını döndür"""
        return self.get_section('modules')
    
    # === Kilitli Ayarlar ===
    
    def is_setting_locked(self, key: str) -> bool:
        """
        Ayar kilitli mi kontrol et.
        İlgili modül kurulduktan sonra bazı ayarlar kilitlenir.
        """
        lock_rules = {
            'network.dns_servers': 'network',
            'vnc.port': 'vnc',
            'cockpit.port': 'cockpit',
            'nvidia.driver_version': 'nvidia',
            'docker.compose_path': 'docker',
            'mongodb.data_path': 'docker',
            'mongodb.port': 'docker',
        }
        
        if key in lock_rules:
            module = lock_rules[key]
            return self.is_module_completed(module)
        
        return False
    
    # === Sistem Değerleri ===
    
    def get_kiosk_id(self) -> str:
        """Kiosk ID'yi al"""
        return self.get('system.kiosk_id', '')
    
    def set_kiosk_id(self, kiosk_id: str) -> None:
        """Kiosk ID'yi ayarla"""
        self.set('system.kiosk_id', kiosk_id)
        self.save()
    
    def get_hardware_id(self) -> str:
        """Hardware ID'yi al"""
        return self.get('system.hardware_id', '')
    
    def set_hardware_id(self, hardware_id: str) -> None:
        """Hardware ID'yi ayarla"""
        self.set('system.hardware_id', hardware_id)
        self.save()
    
    def is_setup_complete(self) -> bool:
        """Kurulum tamamlanmış mı?"""
        return self.get('system.setup_complete', False)
    
    def set_setup_complete(self, complete: bool = True) -> None:
        """Kurulum tamamlandı olarak işaretle"""
        self.set('system.setup_complete', complete)
        self.save()
        
        # Flag dosyası oluştur
        if complete:
            Path('/etc/kiosk-setup/.setup-complete').touch()


# Singleton instance
config = Config()
