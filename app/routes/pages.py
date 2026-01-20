"""
ACO Maintenance Panel - Page Routes
HTML page endpoints

MongoDB-based config system.
"""

import os

from flask import Blueprint, render_template

from app.modules.base import mongo_config as config
from app.services.system import SystemService
from app.modules import get_all_modules

pages_bp = Blueprint('pages', __name__)


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
    from app.modules import get_module

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
    import json
    import os

    config.reload()  # Read current config

    from app.services.service_checker import get_all_services_status

    # Get services from config
    services_config = config.get('services', {})

    # Also check nginx services.json if exists
    nginx_services_file = '/etc/nginx/aco-services.json'
    if os.path.exists(nginx_services_file):
        try:
            with open(nginx_services_file, 'r') as f:
                nginx_services = json.load(f)
                # Merge services from nginx with config
                for name, svc in nginx_services.items():
                    if name not in services_config and not svc.get('internal'):
                        services_config[name] = svc
        except Exception:
            pass
    
    # Check status of each service
    services_status = get_all_services_status(services_config)

    # Filter internal services (like panel)
    visible_services = {
        name: status for name, status in services_status.items()
        if not status.get('internal', False)
    }
    
    # Is nginx installed? (package-based or module-based)
    nginx_installed = os.path.exists('/usr/sbin/nginx') or config.is_module_completed('nginx')
    
    return render_template(
        'services.html',
        services=visible_services,
        nginx_installed=nginx_installed
    )


@pages_bp.route('/logs')
def logs():
    """Log viewing page (module filtered)"""
    import os
    from flask import request

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
