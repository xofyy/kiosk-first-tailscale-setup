"""
ACO Maintenance Panel - Service Checker
Service status check (systemd, port)
"""

import logging
import socket
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def check_systemd_service(service_name: str) -> bool:
    """
    Check if systemd service is active

    Args:
        service_name: Service name (e.g., cockpit.socket, nginx)

    Returns:
        bool: Is service active?
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
        logger.debug(f"Systemd service check failed ({service_name}): {e}")
        return False


def check_port_open(port: int, host: str = '127.0.0.1', timeout: float = 2.0) -> bool:
    """
    Check if specified port is open

    Args:
        port: Port number
        host: Host address
        timeout: Connection timeout duration

    Returns:
        bool: Is port open?
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        return result == 0
    except Exception as e:
        logger.debug(f"Port check error ({host}:{port}): {e}")
        return False
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def check_service_status(service_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check status based on service configuration

    Args:
        service_config: Service configuration
            - check_type: "systemd" or "port"
            - check_value: systemd service name or port number
            - port: Service port (can be used if check_type is port)

    Returns:
        dict: {
            "active": bool,
            "status": str ("running", "stopped", "unknown")
        }
    """
    check_type = service_config.get('check_type')
    check_value = service_config.get('check_value')
    
    # Use port if check_value is not set
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
            logger.warning(f"Invalid port value: {check_value} - {e}")
            return {
                "active": False,
                "status": "unknown"
            }

    # Unknown type or missing value
    return {
        "active": False,
        "status": "unknown"
    }


def get_all_services_status(services: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Check status of all services

    Args:
        services: Service configurations dict

    Returns:
        dict: Status info for each service
    """
    result = {}

    for name, config in services.items():
        # Don't check internal services (panel)
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
