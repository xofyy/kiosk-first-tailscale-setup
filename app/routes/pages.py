"""
Kiosk Setup Panel - Page Routes
HTML sayfa endpoint'leri

MongoDB tabanlı config sistemi.
"""

import os

from flask import Blueprint, render_template

from app.modules.base import mongo_config as config
from app.services.system import SystemService
from app.modules import get_all_modules

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def home():
    """Anasayfa - Sistem durumu ve IP yapılandırma"""
    system = SystemService()
    system_info = system.get_system_info_fast()

    return render_template(
        'home.html',
        system_info=system_info
    )


@pages_bp.route('/kurulum')
def install():
    """Kurulum sayfası - Modül kurulumları"""
    # Modül listesini al
    modules = get_all_modules()
    module_statuses = config.get_all_module_statuses()

    return render_template(
        'install.html',
        modules=modules,
        module_statuses=module_statuses
    )


@pages_bp.route('/services')
def services():
    """Servisler sayfası - iframe ile servis erişimi"""
    import json
    import os
    
    config.reload()  # Güncel config'i oku
    
    from app.services.service_checker import get_all_services_status
    
    # Servisleri config'den al
    services_config = config.get('services', {})
    
    # Nginx services.json varsa onu da kontrol et
    nginx_services_file = '/etc/nginx/kiosk-services.json'
    if os.path.exists(nginx_services_file):
        try:
            with open(nginx_services_file, 'r') as f:
                nginx_services = json.load(f)
                # Nginx'ten gelen servisleri config ile birleştir
                for name, svc in nginx_services.items():
                    if name not in services_config and not svc.get('internal'):
                        services_config[name] = svc
        except Exception:
            pass
    
    # Her servisin durumunu kontrol et
    services_status = get_all_services_status(services_config)
    
    # Internal servisleri filtrele (panel gibi)
    visible_services = {
        name: status for name, status in services_status.items()
        if not status.get('internal', False)
    }
    
    # Nginx kurulu mu? (paket bazlı veya modül bazlı)
    nginx_installed = os.path.exists('/usr/sbin/nginx') or config.is_module_completed('nginx')
    
    return render_template(
        'services.html',
        services=visible_services,
        nginx_installed=nginx_installed
    )


@pages_bp.route('/logs')
def logs():
    """Log görüntüleme sayfası (modül filtreli)"""
    import os
    from flask import request
    
    config.reload()  # Güncel config'i oku
    
    # Modül parametresi
    module = request.args.get('module', '')
    
    # Log dizini
    log_dir = '/var/log/kiosk-setup'
    
    # Mevcut modül log dosyalarını listele
    available_modules = []
    if os.path.exists(log_dir):
        for f in os.listdir(log_dir):
            if f.endswith('.log') and f != 'main.log':
                available_modules.append(f.replace('.log', ''))
    
    # Hangi log dosyasını okuyacağız?
    if module and module in available_modules:
        log_file = os.path.join(log_dir, f'{module}.log')
    else:
        # Tüm loglar (main.log)
        log_file = os.path.join(log_dir, 'main.log')
        module = ''  # Reset module param
    
    logs = []
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                logs = f.readlines()[-200:]  # Son 200 satır
        else:
            logs = ['Log dosyası henüz oluşturulmadı']
    except Exception as e:
        logs = [f'Hata: {str(e)}']
    
    return render_template(
        'logs.html', 
        logs=logs, 
        current_module=module,
        available_modules=sorted(available_modules)
    )
