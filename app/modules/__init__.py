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
from app.modules.nvidia import NvidiaModule
from app.modules.tailscale import TailscaleModule
from app.modules.network import NetworkModule
from app.modules.cockpit import CockpitModule
from app.modules.kiosk import KioskModule
from app.modules.vnc import VNCModule
from app.modules.netmon import NetmonModule
from app.modules.collector import CollectorModule
from app.modules.docker import DockerModule
from app.modules.security import SecurityModule
