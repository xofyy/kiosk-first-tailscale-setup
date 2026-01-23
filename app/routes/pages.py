"""
ACO Maintenance Panel - Page Routes
HTML page endpoints

MongoDB-based config system.
"""

import os

from flask import Blueprint, render_template, request

from app.modules.base import mongo_config as config
from app.services.system import SystemService
from app.modules import get_all_modules, get_module
from app.services.service_checker import get_all_services_status

pages_bp = Blueprint('pages', __name__)

# Hardcoded services configuration (accessed via iframe)
SERVICES = {
    "mechcontroller": {
        "display_name": "Mechatronic Controller",
        "port": 1234,
        "check_type": "port"
    },
    "scanners": {
        "display_name": "Scanners Dashboard",
        "port": 504,
        "check_type": "port"
    },
    "printer": {
        "display_name": "Printer Panel",
        "port": 5200,
        "check_type": "port"
    },
    "camera": {
        "display_name": "Camera Controller",
        "port": 5100,
        "check_type": "port"
    }
}


@pages_bp.route('/')
def home():
    """Home page - System status and IP configuration"""
    system = SystemService()
    system_info = system.get_system_info_fast()

    # Check if Tailscale/Remote Connection is completed (for rvm_id edit permission)
    tailscale_completed = config.get_module_status('remote-connection') == 'completed'

    # Get component statuses for dashboard
    component_statuses = system.get_component_statuses()

    return render_template(
        'home.html',
        system_info=system_info,
        tailscale_completed=tailscale_completed,
        components=component_statuses
    )


@pages_bp.route('/install')
def install():
    """Installation page - Module installations"""
    # Get module list
    modules = get_all_modules()
    module_statuses = config.get_all_module_statuses()

    # Get MOK info for NVIDIA module (server-side render for faster display)
    mok_info = None
    nvidia_module = get_module('nvidia')
    if nvidia_module:
        try:
            mok_info = nvidia_module.get_mok_info()
        except Exception:
            pass

    return render_template(
        'install.html',
        modules=modules,
        module_statuses=module_statuses,
        mok_info=mok_info
    )


@pages_bp.route('/services')
def services():
    """Services page - Service access via iframe"""
    services_status = get_all_services_status(SERVICES)
    return render_template('services.html', services=services_status)


@pages_bp.route('/logs')
def logs():
    """Log viewing page (module filtered)"""
    config.reload()  # Read current config

    # Module parameter
    module = request.args.get('module', '')

    # Log directory
    log_dir = '/var/log/aco-panel'

    # List available module log files
    available_modules = []
    if os.path.exists(log_dir):
        for f in os.listdir(log_dir):
            if f.endswith('.log') and f != 'main.log':
                available_modules.append(f.replace('.log', ''))

    # Which log file to read?
    if module and module in available_modules:
        log_file = os.path.join(log_dir, f'{module}.log')
    else:
        # All logs (main.log)
        log_file = os.path.join(log_dir, 'main.log')
        module = ''  # Reset module param

    logs = []
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                logs = f.readlines()[-200:]  # Last 200 lines
        else:
            logs = ['Log file not yet created']
    except Exception as e:
        logs = [f'Error: {str(e)}']

    return render_template(
        'logs.html',
        logs=logs,
        current_module=module,
        available_modules=sorted(available_modules)
    )
