"""
Kiosk Setup Panel - Page Routes
HTML sayfa endpoint'leri
"""

import os

from flask import Blueprint, render_template, redirect, url_for

from app.config import config
from app.services.system import SystemService
from app.modules import get_all_modules, get_module

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    """Ana sayfa - Kurulum paneli"""
    # config.reload() kaldırıldı - atomic write sayesinde gerek yok
    
    # Sistem bilgilerini al (internet kontrolü YAPMADAN - hızlı sayfa yüklemesi için)
    # Internet bilgileri JavaScript ile async olarak güncellenir (main.js)
    system = SystemService()
    system_info = system.get_system_info_fast()
    
    # Modül listesini al
    modules = get_all_modules()
    module_statuses = config.get_all_module_statuses()
    
    # Network modülü kuruldu mu? (IP ayarı için)
    network_installed = config.is_module_completed('network')
    
    return render_template(
        'index.html',
        system_info=system_info,
        modules=modules,
        module_statuses=module_statuses,
        network_installed=network_installed
    )


@pages_bp.route('/settings')
def settings():
    """Ayarlar sayfası"""
    config.reload()  # Güncel config'i oku
    
    # Modül durumlarını al (kilitli ayarlar için)
    module_statuses = config.get_all_module_statuses()
    
    # Tüm ayarları al
    all_config = config.get_all()
    
    return render_template(
        'settings.html',
        config=all_config,
        module_statuses=module_statuses
    )


@pages_bp.route('/module/<module_name>')
def module_detail(module_name: str):
    """Modül detay sayfası"""
    config.reload()  # Güncel config'i oku
    
    module = get_module(module_name)
    if not module:
        return redirect(url_for('pages.index'))
    
    module_info = module.get_info()
    module_status = config.get_module_status(module_name)
    
    return render_template(
        'module_detail.html',
        module=module_info,
        status=module_status
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
