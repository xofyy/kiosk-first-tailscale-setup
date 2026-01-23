"""
Docker Container Management Service
Reads compose configuration and manages container lifecycle
"""

import os
import subprocess
import logging
from typing import Dict, List, Any, Optional, Generator

logger = logging.getLogger(__name__)

# Web UI services (services with iframe access)
WEB_UI_SERVICES = {
    "mechcontroller": {
        "display_name": "Mechatronic Controller",
        "port": 1234,
        "path": "/pro",
    },
    "scanners": {
        "display_name": "Scanners Dashboard",
        "port": 504,
        "path": "/",
    },
    "printer": {
        "display_name": "Printer Panel",
        "port": 5200,
        "path": "/printer",
    },
    "camera": {
        "display_name": "Camera Controller",
        "port": 5100,
        "path": "/",
    }
}


class DockerManager:
    """Manages Docker containers via docker compose"""

    DEFAULT_COMPOSE_PATH = "/srv/docker"

    def __init__(self, compose_path: Optional[str] = None):
        self.compose_path = compose_path or self.DEFAULT_COMPOSE_PATH
        self.compose_file = os.path.join(self.compose_path, "docker-compose.yml")

    def get_compose_services(self) -> List[str]:
        """
        Read service names from docker compose config (merged yml + override).
        Maintains order from compose files.
        Returns empty list if error.
        """
        try:
            # Use 'docker compose config' to get merged configuration
            result = subprocess.run(
                ['docker', 'compose', '-f', self.compose_file, 'config', '--services'],
                capture_output=True, text=True, timeout=10,
                cwd=self.compose_path
            )

            if result.returncode == 0 and result.stdout.strip():
                # Returns service names, one per line
                return result.stdout.strip().split('\n')
            return []

        except subprocess.TimeoutExpired:
            logger.error("Timeout getting compose services")
            return []
        except Exception as e:
            logger.error(f"Error getting compose services: {e}")
            return []

    def get_container_status(self, service_name: str) -> str:
        """
        Get container status using docker compose ps.
        Returns: running, exited, paused, restarting, created, dead, not_found, unknown
        """
        try:
            result = subprocess.run(
                ['docker', 'compose', '-f', self.compose_file,
                 'ps', '--format', '{{.State}}', service_name],
                capture_output=True, text=True, timeout=10,
                cwd=self.compose_path
            )

            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().lower()
            return "not_found"

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout checking status for {service_name}")
            return "unknown"
        except Exception as e:
            logger.error(f"Error checking container status: {e}")
            return "unknown"

    def get_all_containers(self) -> List[Dict[str, Any]]:
        """
        Get all containers merged with web UI config.
        Returns containers in compose file order.
        """
        containers = []
        compose_services = self.get_compose_services()

        for idx, service_name in enumerate(compose_services):
            status = self.get_container_status(service_name)

            # Check if this is a web UI service
            web_ui_config = WEB_UI_SERVICES.get(service_name, {})

            container_info = {
                "service_name": service_name,
                "display_name": web_ui_config.get("display_name", service_name.replace("_", " ").title()),
                "type": "webui" if service_name in WEB_UI_SERVICES else "background",
                "status": status,
                "order": idx
            }

            # Add web UI specific fields
            if service_name in WEB_UI_SERVICES:
                container_info["port"] = web_ui_config.get("port")
                container_info["path"] = web_ui_config.get("path", "/")

            containers.append(container_info)

        return containers

    def container_action(self, service_name: str, action: str) -> Dict[str, Any]:
        """
        Execute container action: start, stop, restart
        Returns dict with success boolean and optional error message.
        """
        if action not in ['start', 'stop', 'restart']:
            return {"success": False, "error": f"Invalid action: {action}"}

        try:
            result = subprocess.run(
                ['docker', 'compose', '-f', self.compose_file,
                 action, service_name],
                capture_output=True, text=True, timeout=60,
                cwd=self.compose_path
            )

            if result.returncode == 0:
                return {"success": True, "message": f"{action.capitalize()} successful"}
            else:
                error_msg = result.stderr.strip() if result.stderr else "Command failed"
                return {"success": False, "error": error_msg}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Operation timed out"}
        except Exception as e:
            logger.error(f"Container action error: {e}")
            return {"success": False, "error": str(e)}

    def stream_logs(self, service_name: str, tail: int = 200) -> Generator[str, None, None]:
        """
        Stream container logs using docker compose logs -f.
        Yields log lines as they arrive.
        """
        process = None
        try:
            process = subprocess.Popen(
                ['docker', 'compose', '-f', self.compose_file,
                 'logs', '--tail', str(tail), '-f', '--no-color', service_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=self.compose_path
            )

            for line in iter(process.stdout.readline, ''):
                if line:
                    yield line.rstrip('\n')

        except Exception as e:
            logger.error(f"Log streaming error: {e}")
            yield f"Error streaming logs: {e}"
        finally:
            if process:
                process.kill()
                process.wait()
