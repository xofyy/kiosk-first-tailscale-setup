"""
ACO Maintenance Panel - Installation Modules
Module registry and helper functions
"""

from typing import Dict, List, Optional
from app.modules.base import BaseModule

# Module registry
_modules: Dict[str, BaseModule] = {}


def register_module(module_class: type) -> type:
    """Module registration decorator"""
    instance = module_class()
    _modules[instance.name] = instance
    return module_class


def get_module(name: str) -> Optional[BaseModule]:
    """Get module by name"""
    return _modules.get(name)


def get_all_modules() -> List[BaseModule]:
    """Return all modules sorted by order"""
    return sorted(_modules.values(), key=lambda m: m.order)


def get_module_names() -> List[str]:
    """Return all module names"""
    return list(_modules.keys())


# Import modules (auto-registered via register_module decorator)
# Only active modules - others are installed via install.sh
from app.modules.nvidia import NvidiaModule
from app.modules.tailscale import TailscaleModule

# Inactive modules (files exist but not imported):
# - network.py
# - cockpit.py
# - display.py
# - vnc.py
# - netmon.py
# - collector.py
# - docker.py
# - security.py
