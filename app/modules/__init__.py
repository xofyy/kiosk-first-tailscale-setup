"""
Kiosk Setup Panel - Installation Modules
Modül registry ve yardımcı fonksiyonlar
"""

from typing import Dict, List, Optional
from app.modules.base import BaseModule

# Modül registry
_modules: Dict[str, BaseModule] = {}


def register_module(module_class: type) -> type:
    """Modül kayıt decorator'ı"""
    instance = module_class()
    _modules[instance.name] = instance
    return module_class


def get_module(name: str) -> Optional[BaseModule]:
    """İsme göre modül al"""
    return _modules.get(name)


def get_all_modules() -> List[BaseModule]:
    """Tüm modülleri sıralı olarak döndür"""
    return sorted(_modules.values(), key=lambda m: m.order)


def get_module_names() -> List[str]:
    """Tüm modül isimlerini döndür"""
    return list(_modules.keys())


# Modülleri import et (register_module decorator ile otomatik kaydolurlar)
# Sadece aktif modüller - diğerleri install.sh'da kuruldu
from app.modules.nvidia import NvidiaModule
from app.modules.tailscale import TailscaleModule

# İnaktif modüller (dosyalar mevcut ama import edilmiyor):
# - network.py
# - cockpit.py
# - kiosk.py
# - vnc.py
# - netmon.py
# - collector.py
# - docker.py
# - security.py
