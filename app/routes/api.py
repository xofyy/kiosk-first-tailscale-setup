"""
ACO Maintenance Panel - REST API Routes
API endpoints

MongoDB-based config system.
"""

import subprocess
import threading
import logging
import time
from flask import Blueprint, jsonify, request

from app.modules.base import mongo_config as config
from app.services.system import SystemService
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
        except Exception:
            pass
        
        try:
            ip = system.get_ip_address()
        except Exception:
            pass
        
        try:
            dns_working = system.check_dns()
        except Exception:
            pass
        
        try:
            tailscale_ip = system.get_tailscale_ip()
        except Exception:
            pass
        
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


@api_bp.route('/system/shutdown', methods=['POST'])
def shutdown_system():
    """Shutdown the system"""
    try:
        subprocess.Popen(['systemctl', 'poweroff'])
        return jsonify({'success': True, 'message': 'System shutting down...'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
    config.reload()  # Multi-worker sync

    # Block if Remote Connection is already installed (hostname is locked)
    if config.get_module_status('remote-connection') == 'completed':
        return jsonify({
            'success': False,
            'error': 'Cannot change RVM ID after Tailscale installation'
        }), 400

    data = request.get_json()
    rvm_id = data.get('rvm_id', '').upper().strip()

    if not rvm_id:
        return jsonify({
            'success': False,
            'error': 'RVM ID required'
        }), 400

    # ID format check
    import re
    if not re.match(r'^[A-Z0-9_-]+$', rvm_id):
        return jsonify({
            'success': False,
            'error': 'Invalid format. Use only uppercase letters, numbers, hyphens and underscores'
        }), 400

    config.set_rvm_id(rvm_id)

    return jsonify({
        'success': True,
        'rvm_id': rvm_id
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
    import os

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
# IP CONFIGURATION API (NetworkManager)
# =============================================================================

@api_bp.route('/network/set-ip', methods=['POST'])
def set_network_ip():
    """
    IP configuration with NetworkManager
    mode: 'default' → 5.5.5.55/24, gateway 5.5.5.1
    mode: 'dhcp' → DHCP (automatic)
    """
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'No data found'}), 400

    mode = data.get('mode')

    if mode not in ['default', 'dhcp']:
        return jsonify({'success': False, 'error': 'Invalid mode: use default or dhcp'}), 400

    try:
        # Find active ethernet connection
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show', '--active'],
            capture_output=True, text=True, timeout=10
        )

        connection_name = None
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split(':')
                if len(parts) >= 2 and parts[1] == '802-3-ethernet':
                    connection_name = parts[0]
                    break

        if not connection_name:
            # If no active connection, find any ethernet connection
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split(':')
                    if len(parts) >= 2 and parts[1] == '802-3-ethernet':
                        connection_name = parts[0]
                        break

        if not connection_name:
            return jsonify({'success': False, 'error': 'Ethernet connection not found'}), 400

        logger.info(f"Changing IP: connection={connection_name}, mode={mode}")

        if mode == 'default':
            # Statik IP: 5.5.5.55/24, gateway 5.5.5.1
            cmds = [
                ['nmcli', 'connection', 'modify', connection_name,
                 'ipv4.addresses', '5.5.5.55/24',
                 'ipv4.gateway', '5.5.5.1',
                 'ipv4.dns', '8.8.8.8',
                 'ipv4.method', 'manual'],
                ['nmcli', 'connection', 'up', connection_name]
            ]
        else:
            # DHCP
            cmds = [
                ['nmcli', 'connection', 'modify', connection_name,
                 'ipv4.addresses', '',
                 'ipv4.gateway', '',
                 'ipv4.dns', '',
                 'ipv4.method', 'auto'],
                ['nmcli', 'connection', 'up', connection_name]
            ]

        # Run modify command (blocking - need to verify success)
        result = subprocess.run(cmds[0], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.error(f"nmcli modify error: {result.stderr}")
            return jsonify({'success': False, 'error': result.stderr or 'nmcli error'}), 500

        # Run connection up (non-blocking - don't wait for IP change)
        subprocess.Popen(cmds[1])

        msg = 'Default IP (5.5.5.55) set' if mode == 'default' else 'DHCP enabled'
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
