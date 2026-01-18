"""
Kiosk Setup Panel - Service Checker
Servis durum kontrolü (systemd, port)
"""

import logging
import socket
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def check_systemd_service(service_name: str) -> bool:
    """
    Systemd servisinin aktif olup olmadığını kontrol et
    
    Args:
        service_name: Servis adı (örn: cockpit.socket, nginx)
    
    Returns:
        bool: Servis aktif mi?
    """
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        logger.debug(f"Systemd servis kontrolü başarısız ({service_name}): {e}")
        return False


def check_port_open(port: int, host: str = '127.0.0.1', timeout: float = 2.0) -> bool:
    """
    Belirtilen portun açık olup olmadığını kontrol et
    
    Args:
        port: Port numarası
        host: Host adresi
        timeout: Bağlantı timeout süresi
    
    Returns:
        bool: Port açık mı?
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        return result == 0
    except Exception as e:
        logger.debug(f"Port kontrol hatası ({host}:{port}): {e}")
        return False
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def check_service_status(service_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Servis konfigürasyonuna göre durum kontrolü yap
    
    Args:
        service_config: Servis konfigürasyonu
            - check_type: "systemd" veya "port"
            - check_value: systemd servis adı veya port numarası
            - port: Servisin portu (check_type port ise bu da kullanılabilir)
    
    Returns:
        dict: {
            "active": bool,
            "status": str ("running", "stopped", "unknown")
        }
    """
    check_type = service_config.get('check_type')
    check_value = service_config.get('check_value')
    
    # check_value yoksa port'u kullan
    if check_value is None and check_type == 'port':
        check_value = service_config.get('port')
    
    if check_type == 'systemd' and check_value:
        active = check_systemd_service(str(check_value))
        return {
            "active": active,
            "status": "running" if active else "stopped"
        }
    
    elif check_type == 'port' and check_value:
        try:
            port_num = int(check_value)
            active = check_port_open(port_num)
            return {
                "active": active,
                "status": "running" if active else "stopped"
            }
        except (ValueError, TypeError) as e:
            logger.warning(f"Geçersiz port değeri: {check_value} - {e}")
            return {
                "active": False,
                "status": "unknown"
            }
    
    # Bilinmeyen tip veya değer eksik
    return {
        "active": False,
        "status": "unknown"
    }


def get_all_services_status(services: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Tüm servislerin durumunu kontrol et
    
    Args:
        services: Servis konfigürasyonları dict'i
    
    Returns:
        dict: Her servis için durum bilgisi
    """
    result = {}
    
    for name, config in services.items():
        # Internal servisler (panel) için kontrol yapma
        if config.get('internal'):
            result[name] = {
                "active": True,
                "status": "running",
                "internal": True
            }
        else:
            status = check_service_status(config)
            status['display_name'] = config.get('display_name', name.title())
            status['path'] = config.get('path', f'/{name}/')
            status['port'] = config.get('port')
            result[name] = status
    
    return result
