"""
ACO Maintenance Panel - Base Module Class
Base class for all installation modules

MongoDB-based config system.
"""

import os
import subprocess
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# MongoDB connection settings
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "aco"
MONGO_COLLECTION = "settings"


class MongoConfig:
    """
    MongoDB-based config management.
    Singleton pattern with single instance.
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
        """Ensure MongoDB connection"""
        if self._client is None:
            try:
                from pymongo import MongoClient
                self._client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
                self._db = self._client[MONGO_DB]
                self._collection = self._db[MONGO_COLLECTION]
                # Connection test
                self._client.admin.command('ping')
            except Exception as e:
                logger.warning(f"MongoDB connection error: {e}")
                self._client = None
                self._db = None
                self._collection = None

    def _get_settings(self) -> Dict[str, Any]:
        """Get settings document"""
        self._ensure_connection()
        if self._collection is None:
            return {}

        try:
            doc = self._collection.find_one({})
            return doc if doc else {}
        except Exception as e:
            logger.warning(f"MongoDB read error: {e}")
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get config value (dot notation supported).
        Example: get('modules.nvidia') or get('rvm_id')
        """
        settings = self._get_settings()

        # Dot notation support
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
        Set config value (dot notation supported).
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
            logger.warning(f"MongoDB write error: {e}")
            return False

    def get_module_status(self, module_name: str) -> str:
        """Get module status"""
        return self.get(f'modules.{module_name}', 'pending')

    def set_module_status(self, module_name: str, status: str) -> bool:
        """Set module status"""
        return self.set(f'modules.{module_name}', status)

    def is_module_completed(self, module_name: str) -> bool:
        """Is module completed?"""
        return self.get_module_status(module_name) == 'completed'

    def get_rvm_id(self) -> Optional[str]:
        """Get RVM ID"""
        return self.get('rvm_id')

    def set_rvm_id(self, rvm_id: str) -> bool:
        """Set RVM ID"""
        return self.set('rvm_id', rvm_id)

    def set_core_configuration(self, serial_number: str) -> bool:
        """
        Save core configuration to admin.configurations.

        Document format:
        {
            "type": "core",
            "serialNumber": "<RVM_ID>",
            "isActive": "inactive"
        }

        Returns: True if successful, False otherwise
        """
        try:
            from pymongo import MongoClient
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            admin_db = client['admin']
            configurations = admin_db['configurations']

            configurations.update_one(
                {'type': 'core'},
                {'$set': {
                    'type': 'core',
                    'serialNumber': serial_number,
                    'isActive': 'inactive'
                }},
                upsert=True
            )
            client.close()
            logger.info(f"Saved to admin.configurations: {serial_number}")
            return True
        except Exception as e:
            logger.warning(f"admin.configurations write error: {e}")
            return False

    def get_hardware_id(self) -> Optional[str]:
        """Get Hardware ID"""
        return self.get('hardware_id')

    def set_hardware_id(self, hardware_id: str) -> bool:
        """Set Hardware ID"""
        return self.set('hardware_id', hardware_id)

    def save(self):
        """Compatibility method - MongoDB auto-save"""
        pass

    def reload(self):
        """Compatibility method - MongoDB always fresh"""
        pass

    def get_all(self) -> Dict[str, Any]:
        """Return all settings"""
        settings = self._get_settings()
        # Remove _id field
        if '_id' in settings:
            del settings['_id']
        return settings

    def get_all_module_statuses(self) -> Dict[str, str]:
        """Return all module statuses"""
        modules = self.get('modules', {})
        return modules if isinstance(modules, dict) else {}

    def is_setting_locked(self, key: str) -> bool:
        """
        Is setting locked? (No lock system in MongoDB anymore)
        All settings are modifiable.
        """
        return False

    def set_setup_complete(self, complete: bool) -> bool:
        """
        Setup complete flag.
        Writes to MongoDB and syncs the marker file.
        """
        result = self.set('setup_complete', complete)

        # Sync marker file (for openbox autostart)
        marker_file = '/etc/aco-panel/.setup-complete'
        try:
            if complete:
                # Create file
                os.makedirs(os.path.dirname(marker_file), exist_ok=True)
                with open(marker_file, 'w') as f:
                    f.write(f'# Setup completed at {datetime.now().isoformat()}\n')
                logger.info(f"Setup complete marker created: {marker_file}")
            else:
                # Delete file
                if os.path.exists(marker_file):
                    os.remove(marker_file)
                    logger.info(f"Setup complete marker deleted: {marker_file}")
        except Exception as e:
            logger.warning(f"Marker file sync error: {e}")

        return result

    def is_setup_complete(self) -> bool:
        """Is setup complete?"""
        return self.get('setup_complete', False)

    # =========================================================================
    # System Configuration Getters (with defaults)
    # =========================================================================

    def get_headscale_url(self) -> str:
        """Get Headscale URL"""
        return self.get('system.headscale_url', 'https://headscale.xofyy.com')

    def get_enrollment_url(self) -> str:
        """Get Enrollment API URL"""
        return self.get('system.enrollment_url', 'https://enrollment.xofyy.com')


# Global config instance
mongo_config = MongoConfig()

# Log directory
LOG_DIR = '/var/log/aco-panel'


def setup_module_logger(module_name: str) -> logging.Logger:
    """
    Create custom logger for module.
    Each module writes to its own log file.
    """
    # Create log directory
    os.makedirs(LOG_DIR, exist_ok=True)

    # Create logger
    module_logger = logging.getLogger(f"module.{module_name}")
    module_logger.setLevel(logging.DEBUG)
    module_logger.propagate = False  # Don't propagate to root logger (prevents duplicate logs)

    # Clear existing handlers (prevent duplicate logs)
    module_logger.handlers.clear()

    # File handler
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

    # Also write to main.log
    main_log = os.path.join(LOG_DIR, 'main.log')
    main_handler = logging.FileHandler(main_log, encoding='utf-8')
    main_handler.setLevel(logging.INFO)
    main_handler.setFormatter(formatter)
    module_logger.addHandler(main_handler)
    
    return module_logger


class BaseModule(ABC):
    """
    Abstract base class for installation modules.
    All modules must inherit from this class.
    """

    # Should be overridden by subclasses
    name: str = ""
    display_name: str = ""
    description: str = ""
    order: int = 0
    dependencies: List[str] = []
    
    def __init__(self, config_instance: 'MongoConfig' = None):
        """
        BaseModule constructor.

        Args:
            config_instance: Optional config object (for DIP).
                             If None, global mongo_config is used.
                             Mock config can be passed for testing.
        """
        # MongoDB-based config
        if config_instance is None:
            self._config = mongo_config
        else:
            self._config = config_instance

        self.logger = setup_module_logger(self.name)
        self._log_file = os.path.join(LOG_DIR, f"{self.name}.log")
    
    def get_info(self) -> Dict[str, Any]:
        """Return module information"""
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
        Check if module can be installed.
        Returns: (can_install, reason)
        """
        # Already installed?
        if self._config.is_module_completed(self.name):
            return False, "Module already installed"

        # Currently installing?
        if self._config.get_module_status(self.name) == 'installing':
            return False, "Module installation in progress"

        # Dependencies installed?
        for dep in self.dependencies:
            if not self._config.is_module_completed(dep):
                return False, f"Dependency not installed: {dep}"

        # Custom checks (can be overridden in subclass)
        can, reason = self._check_prerequisites()
        if not can:
            return False, reason

        return True, "Can be installed"
    
    def _check_prerequisites(self) -> Tuple[bool, str]:
        """
        Custom prerequisite checks.
        Subclasses can override.
        """
        return True, ""
    
    @abstractmethod
    def install(self) -> Tuple[bool, str]:
        """
        Perform module installation.
        Must be implemented by subclasses.
        Returns: (success, message)
        """
        pass

    def uninstall(self) -> Tuple[bool, str]:
        """
        Module removal (optional).
        Subclasses can override.
        """
        return False, "This module cannot be removed"

    # === Helper Methods ===
    
    def run_command(
        self,
        command: List[str],
        check: bool = True,
        capture_output: bool = True,
        timeout: Optional[int] = None
    ) -> subprocess.CompletedProcess:
        """Run command"""
        self.logger.info(f"Command: {' '.join(command)}")

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
            self.logger.error(f"Command error: {e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            self.logger.error(f"Command timeout: {command}")
            raise
    
    def run_shell(
        self,
        command: str,
        check: bool = True,
        capture_output: bool = True,
        timeout: Optional[int] = None
    ) -> subprocess.CompletedProcess:
        """Run shell command"""
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
            self.logger.error(f"Shell error: {e.stderr}")
            raise
    
    def apt_install(self, packages: List[str]) -> bool:
        """Install packages via APT (noninteractive, real-time log)"""
        if not packages:
            return True

        self.logger.info(f"Installing packages: {', '.join(packages)}")
        
        # Noninteractive environment
        env = os.environ.copy()
        env['DEBIAN_FRONTEND'] = 'noninteractive'
        env['NEEDRESTART_MODE'] = 'a'  # Auto restart, no prompt

        try:
            # First update (real-time log)
            self.logger.info("Updating APT...")
            self._run_apt_with_logging(['apt-get', 'update', '-q'], env)
            
            # Install packages (real-time log)
            self.logger.info(f"Installing packages: {' '.join(packages)}")
            self._run_apt_with_logging(
                ['apt-get', 'install', '-y', '-q'] + packages,
                env,
                timeout=900  # 15 dakika
            )
            
            self.logger.info("APT installation completed")
            return True

        except subprocess.TimeoutExpired:
            self.logger.error(f"APT installation timeout: {packages}")
            return False
        except Exception as e:
            self.logger.error(f"APT installation error: {e}")
            return False
    
    def _run_apt_with_logging(
        self, 
        command: List[str], 
        env: dict,
        timeout: int = 300
    ) -> None:
        """Run APT command and log output in real-time"""
        self.logger.debug(f"Running: {' '.join(command)}")
        
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
            # Read and log output line by line
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    self._log_apt_output(line)

                # Timeout check
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > timeout:
                    process.kill()
                    raise subprocess.TimeoutExpired(command, timeout)
            
            # Wait for result
            return_code = process.wait()
            
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, command)
                
        except Exception:
            process.kill()
            raise
    
    def _log_apt_output(self, line: str) -> None:
        """Write APT output to log file"""
        # Log important lines as INFO, others as DEBUG
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
        """Systemd service control"""
        try:
            self.run_command(['systemctl', action, service])
            return True
        except Exception:
            return False
    
    def write_file(self, path: str, content: str, mode: int = 0o644) -> bool:
        """Write file"""
        try:
            # Create directory
            os.makedirs(os.path.dirname(path), exist_ok=True)

            with open(path, 'w') as f:
                f.write(content)

            os.chmod(path, mode)
            self.logger.info(f"File written: {path}")
            return True
        except Exception as e:
            self.logger.error(f"File write error: {e}")
            return False
    
    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render Jinja2 template"""
        from jinja2 import Environment, FileSystemLoader
        
        template_dirs = [
            '/opt/aco-panel/templates',
            'templates'
        ]
        
        for template_dir in template_dirs:
            try:
                env = Environment(loader=FileSystemLoader(template_dir))
                template = env.get_template(template_name)
                return template.render(**context)
            except Exception:
                continue
        
        raise FileNotFoundError(f"Template not found: {template_name}")

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get config value"""
        return self._config.get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """Set config value"""
        self._config.set(key, value)
        self._config.save()
    
    def set_module_status(self, status: str) -> None:
        """Set this module's status"""
        self.logger.info(f"Module status changed: {status}")
        self._config.set_module_status(self.name, status)
    
    def configure_grub(self, params: Dict[str, Any] = None) -> bool:
        """
        Configure GRUB parameters centrally.

        Args:
            params: Optional parameters
                - nvidia_modeset: If True, add nvidia-drm.modeset=1
                - grub_rotation: Int value to add fbcon=rotate:X

        By default 'quiet splash' is always added.

        Returns:
            Success status
        """
        params = params or {}
        grub_file = '/etc/default/grub'
        
        try:
            with open(grub_file, 'r') as f:
                grub_content = f.read()
            
            original_content = grub_content
            
            # 1. quiet splash check (always)
            if 'quiet' not in grub_content or 'splash' not in grub_content:
                # Add quiet splash if not present
                if 'GRUB_CMDLINE_LINUX_DEFAULT="' in grub_content:
                    grub_content = grub_content.replace(
                        'GRUB_CMDLINE_LINUX_DEFAULT="',
                        'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash '
                    )
                    self.logger.info("GRUB: quiet splash added")

            # 2. nvidia-drm.modeset=1 check
            if params.get('nvidia_modeset') and 'nvidia-drm.modeset=1' not in grub_content:
                grub_content = grub_content.replace(
                    'GRUB_CMDLINE_LINUX_DEFAULT="',
                    'GRUB_CMDLINE_LINUX_DEFAULT="nvidia-drm.modeset=1 '
                )
                self.logger.info("GRUB: nvidia-drm.modeset=1 added")

            # 3. fbcon rotation check (validated: 0-3)
            grub_rotation = params.get('grub_rotation')
            if grub_rotation is not None:
                try:
                    rotation_val = int(grub_rotation)
                    if rotation_val not in (0, 1, 2, 3):
                        self.logger.warning(f"Invalid grub_rotation value: {grub_rotation}, must be 0-3")
                        rotation_val = None
                except (ValueError, TypeError):
                    self.logger.warning(f"Invalid grub_rotation type: {grub_rotation}")
                    rotation_val = None

                if rotation_val is not None and 'fbcon=rotate:' not in grub_content:
                    grub_content = grub_content.replace(
                        'GRUB_CMDLINE_LINUX_DEFAULT="',
                        f'GRUB_CMDLINE_LINUX_DEFAULT="fbcon=rotate:{rotation_val} '
                    )
                    self.logger.info(f"GRUB: fbcon=rotate:{rotation_val} added")
            
            # Any changes?
            if grub_content != original_content:
                with open(grub_file, 'w') as f:
                    f.write(grub_content)

                # Run grub-mkconfig (update-grub script causes PATH issues)
                self.logger.info("Updating GRUB configuration...")

                # Try UEFI path first, then BIOS path
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
                        self.logger.info(f"GRUB configuration updated: {grub_cfg}")
                    else:
                        self.logger.warning(f"grub-mkconfig warning: {result.stderr}")
                else:
                    self.logger.warning("GRUB config directory not found, skipping")
            else:
                self.logger.info("GRUB configuration already up to date")
            
            return True
            
        except FileNotFoundError:
            self.logger.warning(f"GRUB file not found: {grub_file}")
            return False
        except Exception as e:
            self.logger.warning(f"GRUB configuration error: {e}")
            return False