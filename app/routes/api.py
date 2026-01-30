"""
ACO Maintenance Panel - REST API Routes
API endpoints

MongoDB-based config system.
"""

import os
import re
import subprocess
import threading
import logging
import time
from flask import Blueprint, jsonify, request

from app.modules.base import mongo_config as config
from app.services.system import SystemService, DEFAULT_IP_CONFIGS
from app.services.hardware import HardwareService
from app.modules import get_module, get_all_modules

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)

# Active installation threads (for race condition control)
_install_threads = {}

# Internet status cache - for instant response (doesn't block worker)
_internet_cache = {
    'connected': None,
    'ip': None,
    'dns_working': None,
    'tailscale_ip': None,
    'last_check': 0
}
_cache_lock = threading.Lock()
_CACHE_TTL = 3  # Valid for 3 seconds (for fast UI updates)
_update_in_progress = False


# =============================================================================
# SYSTEM API
# =============================================================================

@api_bp.route('/system/info')
def system_info():
    """Return system information"""
    system = SystemService()
    return jsonify(system.get_system_info())


@api_bp.route('/system/internet')
def internet_status():
    """
    Internet status - returns from cache instantly, updates in background.
    This way the worker never blocks and tab switches work instantly.
    """
    global _update_in_progress

    with _cache_lock:
        cache_age = time.time() - _internet_cache['last_check']
        result = {
            'connected': _internet_cache['connected'],
            'ip': _internet_cache['ip'],
            'dns_working': _internet_cache['dns_working'],
            'tailscale_ip': _internet_cache['tailscale_ip']
        }

    # If cache is stale or empty, update in background
    if cache_age > _CACHE_TTL and not _update_in_progress:
        _update_in_progress = True
        threading.Thread(target=_update_internet_cache, daemon=True).start()
    
    return jsonify(result)


def _update_internet_cache():
    """Update internet status in background (doesn't block worker)"""
    global _update_in_progress
    try:
        system = SystemService()

        # Update each one separately (others continue even if one fails)
        connected = None
        ip = None
        dns_working = None
        tailscale_ip = None
        
        try:
            connected = system.check_internet()
        except Exception as e:
            logger.debug(f"Internet check failed: {e}")

        try:
            ip = system.get_ip_address()
        except Exception as e:
            logger.debug(f"IP address check failed: {e}")

        try:
            dns_working = system.check_dns()
        except Exception as e:
            logger.debug(f"DNS check failed: {e}")

        try:
            tailscale_ip = system.get_tailscale_ip()
        except Exception as e:
            logger.debug(f"Tailscale IP check failed: {e}")
        
        with _cache_lock:
            _internet_cache['connected'] = connected
            _internet_cache['ip'] = ip
            _internet_cache['dns_working'] = dns_working
            _internet_cache['tailscale_ip'] = tailscale_ip
            _internet_cache['last_check'] = time.time()
            
    except Exception as e:
        logger.warning(f"Internet cache update failed: {e}")
    finally:
        _update_in_progress = False


@api_bp.route('/system/reboot', methods=['POST'])
def reboot_system():
    """Reboot the system"""
    try:
        subprocess.Popen(['systemctl', 'reboot'])
        return jsonify({'success': True, 'message': 'System rebooting...'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/system/components')
def system_components():
    """Return system component statuses (Docker, MongoDB, Tailscale, NVIDIA)"""
    system = SystemService()
    components = system.get_component_statuses()
    return jsonify(components)


@api_bp.route('/system/monitor')
def system_monitor():
    """Return system monitor data (CPU, memory, disk, temp, network speed)"""
    system = SystemService()
    return jsonify(system.get_system_monitor())


@api_bp.route('/system/monitor/cpu/details')
def cpu_details():
    """Return detailed CPU info: per-core usage, top processes, load avg"""
    system = SystemService()
    return jsonify(system.get_cpu_details())


@api_bp.route('/system/monitor/memory/details')
def memory_details():
    """Return detailed memory info: breakdown, top processes, swap"""
    system = SystemService()
    return jsonify(system.get_memory_details())


@api_bp.route('/system/monitor/gpu/details')
def gpu_details():
    """Return detailed GPU info: utilization, top processes"""
    system = SystemService()
    return jsonify(system.get_gpu_details())


@api_bp.route('/system/monitor/vram/details')
def vram_details():
    """Return detailed VRAM info: per-process memory usage"""
    system = SystemService()
    return jsonify(system.get_vram_details())


@api_bp.route('/system/monitor/disk/details')
def disk_details():
    """Return detailed disk info: partitions, I/O stats, top processes"""
    system = SystemService()
    return jsonify(system.get_disk_details())


@api_bp.route('/system/monitor/network/details')
def network_details():
    """Return detailed network usage by application"""
    system = SystemService()
    return jsonify(system.get_network_details())


@api_bp.route('/system/network-history')
def network_history():
    """Return network traffic history from netmon database"""
    hours = request.args.get('hours', 24, type=int)
    hours = min(hours, 168)  # max 7 days
    system = SystemService()
    return jsonify(system.get_network_history(hours))


@api_bp.route('/system/timezone')
def get_timezone():
    """Return current timezone, NTP status, and available timezones"""
    try:
        current_tz = 'UTC'
        try:
            result = subprocess.run(
                ['timedatectl', 'show', '--property=Timezone', '--value'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                current_tz = result.stdout.strip()
        except Exception:
            try:
                with open('/etc/timezone', 'r') as f:
                    current_tz = f.read().strip()
            except Exception:
                pass

        ntp_active = False
        try:
            result = subprocess.run(
                ['timedatectl', 'show', '--property=NTP', '--value'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                ntp_active = result.stdout.strip().lower() == 'yes'
        except Exception:
            pass

        timezones = []
        try:
            result = subprocess.run(
                ['timedatectl', 'list-timezones'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                timezones = [tz.strip() for tz in result.stdout.strip().split('\n') if tz.strip()]
        except Exception:
            pass

        return jsonify({
            'timezone': current_tz,
            'ntp': ntp_active,
            'timezones': timezones
        })
    except Exception as e:
        logger.error(f"Timezone info error: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/system/timezone', methods=['POST'])
def set_timezone():
    """Set system timezone"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    timezone = data.get('timezone', '').strip()
    if not timezone:
        return jsonify({'success': False, 'error': 'Timezone required'}), 400

    if '/' not in timezone and timezone not in ('UTC', 'GMT'):
        return jsonify({'success': False, 'error': 'Invalid timezone format'}), 400

    try:
        result = subprocess.run(
            ['timedatectl', 'list-timezones'],
            capture_output=True, text=True, timeout=10
        )
        valid_timezones = result.stdout.strip().split('\n')
        if timezone not in valid_timezones:
            return jsonify({'success': False, 'error': f'Unknown timezone: {timezone}'}), 400

        result = subprocess.run(
            ['timedatectl', 'set-timezone', timezone],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return jsonify({'success': False, 'error': result.stderr or 'Failed to set timezone'}), 500

        logger.info(f"Timezone changed to: {timezone}")
        return jsonify({'success': True, 'timezone': timezone})

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Operation timed out'}), 500
    except Exception as e:
        logger.error(f"Timezone change error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/system/keyboard')
def get_keyboard():
    """Return current keyboard layout"""
    try:
        layout = 'us'
        result = subprocess.run(
            ['localectl', 'status'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'X11 Layout' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        layout = parts[1].strip()
                    break
        return jsonify({'layout': layout})
    except Exception as e:
        logger.error(f"Keyboard info error: {e}")
        return jsonify({'layout': 'us', 'error': str(e)})


@api_bp.route('/system/keyboard', methods=['POST'])
def set_keyboard():
    """Set keyboard layout (persistent + immediate X11 + console)"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    layout = data.get('layout', '').strip().lower()
    if not layout:
        return jsonify({'success': False, 'error': 'Layout required'}), 400

    allowed_layouts = [
        'tr', 'us', 'de', 'fr', 'es', 'it', 'ru', 'ar', 'pt', 'nl',
        'pl', 'sv', 'no', 'da', 'fi', 'el', 'hu', 'cs', 'ro', 'bg',
        'hr', 'sk', 'sl', 'uk', 'az', 'gb', 'br', 'jp', 'kr'
    ]
    if layout not in allowed_layouts:
        return jsonify({'success': False, 'error': f'Unsupported layout: {layout}'}), 400

    errors = []
    try:
        # Persistent: write to X11 + console config files
        result = subprocess.run(
            ['localectl', 'set-x11-keymap', layout],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            errors.append(f'localectl error: {result.stderr}')

        # Immediate X11 effect (kiosk user's display)
        subprocess.run(
            ['sudo', '-u', 'kiosk', 'env', 'DISPLAY=:0', 'setxkbmap', layout],
            capture_output=True, text=True, timeout=5
        )

        # Immediate console effect
        subprocess.run(
            ['setupcon', '--force'],
            capture_output=True, text=True, timeout=5
        )
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Operation timed out'}), 500
    except Exception as e:
        logger.error(f"Keyboard change error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

    if errors:
        return jsonify({'success': False, 'error': '; '.join(errors)}), 500

    logger.info(f"Keyboard layout changed to: {layout}")
    return jsonify({'success': True, 'layout': layout})


# =============================================================================
# HARDWARE API
# =============================================================================

@api_bp.route('/hardware/id')
def hardware_id():
    """Return Hardware ID"""
    hw = HardwareService()
    return jsonify({
        'hardware_id': hw.get_hardware_id(),
        'components': hw.get_components()
    })


# =============================================================================
# RVM ID API
# =============================================================================

@api_bp.route('/rvm-id', methods=['GET'])
def get_rvm_id():
    """Return RVM ID"""
    config.reload()  # Multi-worker sync
    return jsonify({
        'rvm_id': config.get_rvm_id(),
        'is_set': bool(config.get_rvm_id())
    })


@api_bp.route('/rvm-id', methods=['POST'])
def set_rvm_id():
    """Set or update RVM ID (blocked after Tailscale installation)"""
    config.reload()

    # Block if Remote Connection already installed
    if config.get_module_status('remote-connection') == 'completed':
        return jsonify({
            'success': False,
            'error': 'Cannot change RVM ID after Tailscale installation'
        }), 400

    data = request.get_json()
    rvm_id = data.get('rvm_id', '').upper().strip()

    # Input validation
    if not rvm_id:
        return jsonify({'success': False, 'error': 'RVM ID required'}), 400

    if not re.match(r'^[A-Z0-9_-]+$', rvm_id):
        return jsonify({
            'success': False,
            'error': 'Invalid format. Use only uppercase letters, numbers, hyphens and underscores'
        }), 400

    hostname = rvm_id.lower()

    # 1. Set system hostname
    system = SystemService()
    result = system.set_hostname(hostname)
    if not result['success']:
        return jsonify({'success': False, 'error': result['error']}), 500

    # 2. Save to admin.configurations
    if not config.set_core_configuration(rvm_id):
        return jsonify({
            'success': False,
            'error': 'Failed to save to admin.configurations'
        }), 500

    # 3. Save RVM ID to aco.settings
    config.set_rvm_id(rvm_id)
    logger.info(f"RVM ID set to: {rvm_id}, hostname: {hostname}")

    return jsonify({
        'success': True,
        'rvm_id': rvm_id,
        'hostname': hostname
    })


# =============================================================================
# CONFIG API
# =============================================================================

@api_bp.route('/config')
def get_config():
    """Return all configuration"""
    config.reload()  # Multi-worker sync
    return jsonify(config.get_all())


@api_bp.route('/config/<path:key>')
def get_config_value(key: str):
    """Return a specific configuration value"""
    key = key.replace('/', '.')
    value = config.get(key)
    locked = config.is_setting_locked(key)
    
    return jsonify({
        'key': key,
        'value': value,
        'locked': locked
    })


@api_bp.route('/config', methods=['POST'])
def update_config():
    """Update configuration"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No data found'}), 400
    
    errors = []
    updated = []
    
    for key, value in data.items():
        # Check locked setting
        if config.is_setting_locked(key):
            errors.append(f'{key} setting is locked')
            continue

        # System values cannot be changed
        if key.startswith('system.') or key.startswith('modules.'):
            errors.append(f'{key} is managed by system')
            continue
        
        config.set(key, value)
        updated.append(key)
    
    if updated:
        config.save()
    
    return jsonify({
        'success': len(errors) == 0,
        'updated': updated,
        'errors': errors
    })


# =============================================================================
# MODULE API
# =============================================================================

@api_bp.route('/modules')
def list_modules():
    """List all modules"""
    config.reload()  # Multi-worker sync
    modules = get_all_modules()
    statuses = config.get_all_module_statuses()
    
    result = []
    for module in modules:
        info = module.get_info()
        info['status'] = statuses.get(info['name'], 'pending')
        result.append(info)
    
    return jsonify(result)


@api_bp.route('/modules/<module_name>')
def module_info(module_name: str):
    """Return module information"""
    config.reload()  # Multi-worker sync
    module = get_module(module_name)
    
    if not module:
        return jsonify({'error': 'Module not found'}), 404
    
    info = module.get_info()
    info['status'] = config.get_module_status(module_name)
    info['can_install'] = module.can_install()
    
    return jsonify(info)


@api_bp.route('/modules/<module_name>/install', methods=['POST'])
def install_module(module_name: str):
    """
    Start module installation (async - background thread)
    Installation runs in background, API returns immediately
    """
    config.reload()  # Multi-worker sync - critical for dependency and status check
    module = get_module(module_name)
    
    if not module:
        return jsonify({'success': False, 'error': 'Module not found'}), 404
    
    # Check if installable
    can_install, reason = module.can_install()
    if not can_install:
        return jsonify({'success': False, 'error': reason}), 400

    # Already installed?
    if config.is_module_completed(module_name):
        return jsonify({'success': False, 'error': 'Module already installed'}), 400

    # Already installing? (thread check)
    if module_name in _install_threads and _install_threads[module_name].is_alive():
        return jsonify({'success': False, 'error': 'Module installation already in progress'}), 400

    # Set status to installing
    config.set_module_status(module_name, 'installing')
    logger.info(f"Starting module installation (async): {module_name}")

    # Start background thread
    thread = threading.Thread(
        target=_run_install_background,
        args=(module_name,),
        daemon=True,
        name=f"install-{module_name}"
    )
    _install_threads[module_name] = thread
    thread.start()
    
    return jsonify({
        'success': True,
        'status': 'installing',
        'message': f'{module_name} installation started. You can follow from the log page.'
    })


def _run_install_background(module_name: str):
    """
    Run module installation in background thread.
    Error handling and status updates are done within the thread.
    """
    module = get_module(module_name)
    if not module:
        logger.error(f"Module not found: {module_name}")
        return

    try:
        logger.info(f"Background installation started: {module_name}")

        success, message = module.install()

        # install() method may set status internally
        # (e.g. mok_pending, reboot_required)
        config.reload()  # Read current status
        current_status = config.get_module_status(module_name)

        if success:
            # Don't touch if install() set a special status
            if current_status == 'installing':
                config.set_module_status(module_name, 'completed')
            logger.info(f"Installation completed: {module_name} - {message}")
        else:
            # Don't touch if module set its own status (mok_pending, reboot_required)
            if current_status == 'installing':
                config.set_module_status(module_name, 'failed')
                logger.error(f"Installation failed: {module_name} - {message}")
            else:
                # mok_pending or reboot_required - this is also considered "success"
                logger.info(f"Installation in special state: {module_name} ({current_status}) - {message}")

    except Exception as e:
        config.set_module_status(module_name, 'failed')
        logger.exception(f"Installation exception: {module_name} - {e}")
    finally:
        # Clean up thread reference
        if module_name in _install_threads:
            del _install_threads[module_name]


@api_bp.route('/modules/<module_name>/status')
def module_status(module_name: str):
    """Return module status"""
    config.reload()  # For current status
    status = config.get_module_status(module_name)
    return jsonify({
        'module': module_name,
        'status': status
    })


# =============================================================================
# NVIDIA MOK API
# =============================================================================

@api_bp.route('/nvidia/mok-info')
def nvidia_mok_info():
    """
    NVIDIA MOK status information.
    Used to show warning if MOK was skipped.
    """
    module = get_module('nvidia')
    if not module:
        return jsonify({'error': 'NVIDIA module not found'}), 404

    try:
        info = module.get_mok_info()
        return jsonify(info)
    except Exception as e:
        logger.error(f"MOK info error: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/nvidia/mok-reimport', methods=['POST'])
def nvidia_mok_reimport():
    """
    Re-import MOK.
    If user skipped at boot, this endpoint allows re-importing.
    """
    module = get_module('nvidia')
    if not module:
        return jsonify({'success': False, 'error': 'NVIDIA module not found'}), 404

    try:
        success, message = module.reimport_mok()
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        logger.error(f"MOK reimport error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/modules/<module_name>/logs')
def module_logs(module_name: str):
    """Return module logs"""
    log_dir = '/var/log/aco-panel'
    log_file = os.path.join(log_dir, f"{module_name}.log")

    # Get last N lines (configurable via query param)
    lines = int(request.args.get('lines', 200))

    logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                logs = all_lines[-lines:] if len(all_lines) > lines else all_lines
        except Exception as e:
            logs = [f"Log read error: {e}"]
    else:
        logs = [f"Log file not found: {log_file}"]
    
    return jsonify({
        'module': module_name,
        'logs': [line.rstrip() for line in logs],
        'total_lines': len(logs)
    })


# =============================================================================
# NETWORK INTERFACE API
# =============================================================================

@api_bp.route('/network/interfaces')
def get_network_interfaces():
    """
    List all physical ethernet interfaces with onboard/pcie classification.

    Response:
    {
        "interfaces": [
            {"name": "enp4s0", "type": "onboard", "vendor": "MSI", "ip": "...", "state": "up", "mac": "..."},
            {"name": "enp5s0", "type": "pcie", "vendor": "Realtek", "ip": "...", "state": "up", "mac": "..."}
        ],
        "default_ips": {
            "onboard": {"ip": "5.5.5.55", "prefix": 24, "gateway": "5.5.5.1", "dns": "8.8.8.8"},
            "pcie": {"ip": "192.168.1.200", "prefix": 24, "gateway": "192.168.1.1", "dns": "8.8.8.8"}
        }
    }
    """
    system = SystemService()
    interfaces = system.get_ethernet_interfaces()

    return jsonify({
        'interfaces': interfaces,
        'default_ips': DEFAULT_IP_CONFIGS
    })


# =============================================================================
# IP CONFIGURATION API (NetworkManager)
# =============================================================================

@api_bp.route('/network/set-ip', methods=['POST'])
def set_network_ip():
    """
    IP configuration with NetworkManager for a specific interface.

    Request body:
    {
        "interface": "enp4s0",  # Required: interface name
        "mode": "network|direct|dhcp"  # Required
    }

    Modes:
    - network: Static IP with gateway (for network with internet)
    - direct: Static IP without gateway (for direct device connection)
    - dhcp: Automatic configuration

    Default IPs:
    - onboard: 5.5.5.55/24 (network mode has gateway, direct mode doesn't)
    - pcie: 192.168.1.200/24 (direct mode only - no gateway)
    """
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'No data found'}), 400

    interface_name = data.get('interface')
    mode = data.get('mode')

    if not interface_name:
        return jsonify({'success': False, 'error': 'Interface name required'}), 400

    if mode not in ['network', 'direct', 'dhcp']:
        return jsonify({'success': False, 'error': 'Invalid mode: use network, direct or dhcp'}), 400

    try:
        # Get interface type (onboard/pcie) to determine default IP
        system = SystemService()
        interfaces = system.get_ethernet_interfaces()
        interface_info = next((i for i in interfaces if i['name'] == interface_name), None)

        if not interface_info:
            return jsonify({'success': False, 'error': f'Interface not found: {interface_name}'}), 400

        interface_type = interface_info.get('type', 'pcie')

        # Validate mode is available for this interface type
        type_config = DEFAULT_IP_CONFIGS.get(interface_type, DEFAULT_IP_CONFIGS['pcie'])
        if mode != 'dhcp' and mode not in type_config.get('modes', {}):
            return jsonify({'success': False, 'error': f'Mode {mode} not available for {interface_type} interface'}), 400

        # Find NetworkManager connection for this interface
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show'],
            capture_output=True, text=True, timeout=10
        )

        connection_name = None
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split(':')
                # parts: [NAME, TYPE, DEVICE]
                if len(parts) >= 3 and parts[1] == '802-3-ethernet' and parts[2] == interface_name:
                    connection_name = parts[0]
                    break

        # If no connection for this device, try to find by device name or create one
        if not connection_name:
            # Try with just the interface name as connection
            connection_name = interface_name

        logger.info(f"Changing IP: interface={interface_name}, connection={connection_name}, mode={mode}, type={interface_type}")

        if mode in ['network', 'direct']:
            # Get IP config based on interface type
            ip_with_prefix = f"{type_config['ip']}/{type_config['prefix']}"
            mode_config = type_config['modes'][mode]

            # Build nmcli command
            cmd = ['nmcli', 'connection', 'modify', connection_name,
                   'ipv4.addresses', ip_with_prefix,
                   'ipv4.method', 'manual']

            # Add gateway if specified
            if mode_config.get('gateway'):
                cmd.extend(['ipv4.gateway', mode_config['gateway']])
                cmd.extend(['ipv4.never-default', 'no'])  # Gateway varsa, default route olsun
            else:
                cmd.extend(['ipv4.gateway', ''])
                cmd.extend(['ipv4.never-default', 'yes'])  # Gateway yoksa, default route olmasın

            # Add DNS if specified
            if mode_config.get('dns'):
                cmd.extend(['ipv4.dns', mode_config['dns']])
            else:
                cmd.extend(['ipv4.dns', ''])

            # Set IPv6 method
            ipv6_method = mode_config.get('ipv6', 'auto')
            cmd.extend(['ipv6.method', ipv6_method])

            cmds = [cmd, ['nmcli', 'connection', 'up', connection_name]]

            if mode == 'network':
                msg = f"Network IP ({type_config['ip']}) set on {interface_name}"
            else:
                msg = f"Direct IP ({type_config['ip']}) set on {interface_name}"
        else:
            # DHCP - gateway DHCP'den alınacak, default route olmalı
            cmds = [
                ['nmcli', 'connection', 'modify', connection_name,
                 'ipv4.addresses', '',
                 'ipv4.gateway', '',
                 'ipv4.dns', '',
                 'ipv4.method', 'auto',
                 'ipv4.never-default', 'no',  # DHCP gateway default route olsun
                 'ipv6.method', 'auto'],
                ['nmcli', 'connection', 'up', connection_name]
            ]
            msg = f'DHCP enabled on {interface_name}'

        # Run modify command (blocking - need to verify success)
        result = subprocess.run(cmds[0], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.error(f"nmcli modify error: {result.stderr}")
            return jsonify({'success': False, 'error': result.stderr or 'nmcli error'}), 500

        # Run connection up (non-blocking - don't wait for IP change)
        subprocess.Popen(cmds[1])

        logger.info(msg)
        return jsonify({'success': True, 'message': msg})

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Operation timed out'}), 500
    except Exception as e:
        logger.error(f"IP change error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# SETUP COMPLETE API
# =============================================================================

@api_bp.route('/setup/complete', methods=['POST'])
def complete_setup():
    """Complete setup"""
    config.reload()  # Multi-worker sync

    # Check if all modules are completed
    statuses = config.get_all_module_statuses()
    incomplete = [m for m, s in statuses.items() if s != 'completed']

    if incomplete:
        return jsonify({
            'success': False,
            'error': f'Incomplete modules: {", ".join(incomplete)}'
        }), 400

    try:
        # Mark setup as complete
        config.set_setup_complete(True)

        return jsonify({
            'success': True,
            'message': 'Setup complete! System will reboot...'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/setup/status')
def setup_status():
    """Return setup status"""
    config.reload()  # Multi-worker sync

    # Get defined modules (actual module count, not MongoDB entries)
    defined_modules = get_all_modules()
    module_names = [m.name for m in defined_modules]
    total = len(module_names)

    # Get statuses from MongoDB
    statuses = config.get_all_module_statuses()

    # Count completed modules (only from defined modules)
    completed = sum(1 for name in module_names if statuses.get(name) == 'completed')

    return jsonify({
        'complete': config.is_setup_complete(),
        'total_modules': total,
        'completed_modules': completed,
        'progress': int((completed / total) * 100) if total > 0 else 0,
        'module_statuses': {name: statuses.get(name, 'pending') for name in module_names}
    })


# =============================================================================
# NVR CAMERA API
# =============================================================================

@api_bp.route('/nvr/config')
def get_nvr_config():
    """Get NVR credentials (password masked)"""
    config.reload()
    username = config.get('nvr.username', '')
    password = config.get('nvr.password', '')

    return jsonify({
        'configured': bool(username and password),
        'username': username,
        'has_password': bool(password)
    })


@api_bp.route('/nvr/config', methods=['POST'])
def set_nvr_config():
    """Save NVR credentials"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password required'}), 400

    config.set('nvr.username', username)
    config.set('nvr.password', password)

    return jsonify({'success': True, 'message': 'NVR credentials saved'})


@api_bp.route('/nvr/test')
def test_nvr_connection():
    """Test NVR connection via ISAPI"""
    from app.services.nvr import NvrService
    nvr = NvrService()
    result = nvr.test_connection()
    return jsonify(result)


@api_bp.route('/nvr/channels')
def get_nvr_channels():
    """Discover camera channels via ISAPI"""
    from app.services.nvr import NvrService
    nvr = NvrService()
    result = nvr.discover_channels()
    return jsonify(result)


@api_bp.route('/nvr/stream/start', methods=['POST'])
def start_nvr_stream():
    """Start a camera stream in go2rtc"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data'}), 400

    channel_id = data.get('channel_id')
    if not channel_id:
        return jsonify({'success': False, 'error': 'channel_id required'}), 400

    try:
        channel_id = int(channel_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid channel_id'}), 400

    from app.services.nvr import NvrService
    nvr = NvrService()
    result = nvr.start_stream(channel_id)
    return jsonify(result)


@api_bp.route('/nvr/stream/stop', methods=['POST'])
def stop_nvr_stream():
    """Stop a camera stream in go2rtc"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data'}), 400

    stream_name = data.get('stream_name', '')
    if not stream_name or not stream_name.startswith('camera_'):
        return jsonify({'success': False, 'error': 'Invalid stream name'}), 400

    from app.services.nvr import NvrService
    nvr = NvrService()
    result = nvr.stop_stream(stream_name)
    return jsonify(result)


@api_bp.route('/nvr/streams')
def get_nvr_streams():
    """Get active streams from go2rtc"""
    from app.services.nvr import NvrService
    nvr = NvrService()
    result = nvr.get_active_streams()
    return jsonify(result)


@api_bp.route('/nvr/stream/stop-all', methods=['POST'])
def stop_all_nvr_streams():
    """Stop all camera streams"""
    from app.services.nvr import NvrService
    nvr = NvrService()
    result = nvr.stop_all_streams()
    return jsonify(result)
