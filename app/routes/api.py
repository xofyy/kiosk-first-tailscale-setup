"""
Kiosk Setup Panel - REST API Routes
API endpoint'leri

MongoDB tabanlı config sistemi.
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

# Aktif kurulum thread'leri (race condition kontrolü için)
_install_threads = {}

# Internet durumu cache'i - anında dönüş için (worker'ı bloke etmez)
_internet_cache = {
    'connected': None,
    'ip': None,
    'dns_working': None,
    'tailscale_ip': None,
    'last_check': 0
}
_cache_lock = threading.Lock()
_CACHE_TTL = 3  # 3 saniye geçerli (hızlı UI güncellemesi için)
_update_in_progress = False


# =============================================================================
# SİSTEM API
# =============================================================================

@api_bp.route('/system/info')
def system_info():
    """Sistem bilgilerini döndür"""
    system = SystemService()
    return jsonify(system.get_system_info())


@api_bp.route('/system/internet')
def internet_status():
    """
    Internet durumu - cache'den anında döner, arka planda günceller.
    Bu sayede worker hiç bloke olmaz ve tab geçişleri anında çalışır.
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
    
    # Cache eski veya boşsa, arka planda güncelle
    if cache_age > _CACHE_TTL and not _update_in_progress:
        _update_in_progress = True
        threading.Thread(target=_update_internet_cache, daemon=True).start()
    
    return jsonify(result)


def _update_internet_cache():
    """Arka planda internet durumunu güncelle (worker'ı bloke etmez)"""
    global _update_in_progress
    try:
        system = SystemService()
        
        # Her birini ayrı ayrı güncelle (hata olsa bile diğerleri çalışsın)
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
    """Sistemi yeniden başlat"""
    try:
        subprocess.Popen(['systemctl', 'reboot'])
        return jsonify({'success': True, 'message': 'Sistem yeniden başlatılıyor...'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/system/shutdown', methods=['POST'])
def shutdown_system():
    """Sistemi kapat"""
    try:
        subprocess.Popen(['systemctl', 'poweroff'])
        return jsonify({'success': True, 'message': 'Sistem kapatılıyor...'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# HARDWARE API
# =============================================================================

@api_bp.route('/hardware/id')
def hardware_id():
    """Hardware ID'yi döndür"""
    hw = HardwareService()
    return jsonify({
        'hardware_id': hw.get_hardware_id(),
        'components': hw.get_components()
    })


# =============================================================================
# KIOSK ID API
# =============================================================================

@api_bp.route('/kiosk-id', methods=['GET'])
def get_kiosk_id():
    """Kiosk ID'yi döndür"""
    config.reload()  # Multi-worker sync
    return jsonify({
        'kiosk_id': config.get_kiosk_id(),
        'is_set': bool(config.get_kiosk_id())
    })


@api_bp.route('/kiosk-id', methods=['POST'])
def set_kiosk_id():
    """Kiosk ID'yi ayarla (sadece ilk giriş)"""
    config.reload()  # Multi-worker sync
    # Zaten ayarlanmışsa engelle
    if config.get_kiosk_id():
        return jsonify({
            'success': False, 
            'error': 'Kiosk ID zaten ayarlanmış'
        }), 400
    
    data = request.get_json()
    kiosk_id = data.get('kiosk_id', '').upper().strip()
    
    if not kiosk_id:
        return jsonify({
            'success': False, 
            'error': 'Kiosk ID gerekli'
        }), 400
    
    # ID formatı kontrolü
    import re
    if not re.match(r'^[A-Z0-9_-]+$', kiosk_id):
        return jsonify({
            'success': False,
            'error': 'Geçersiz format. Sadece büyük harf, rakam, tire ve alt çizgi kullanın'
        }), 400
    
    config.set_kiosk_id(kiosk_id)
    
    return jsonify({
        'success': True, 
        'kiosk_id': kiosk_id
    })


# =============================================================================
# CONFIG API
# =============================================================================

@api_bp.route('/config')
def get_config():
    """Tüm yapılandırmayı döndür"""
    config.reload()  # Multi-worker sync
    return jsonify(config.get_all())


@api_bp.route('/config/<path:key>')
def get_config_value(key: str):
    """Belirli bir yapılandırma değerini döndür"""
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
    """Yapılandırmayı güncelle"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'Veri bulunamadı'}), 400
    
    errors = []
    updated = []
    
    for key, value in data.items():
        # Kilitli ayar kontrolü
        if config.is_setting_locked(key):
            errors.append(f'{key} ayarı kilitli')
            continue
        
        # Sistem değerleri değiştirilemez
        if key.startswith('system.') or key.startswith('modules.'):
            errors.append(f'{key} sistem tarafından yönetilir')
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
# MODÜL API
# =============================================================================

@api_bp.route('/modules')
def list_modules():
    """Tüm modülleri listele"""
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
    """Modül bilgilerini döndür"""
    config.reload()  # Multi-worker sync
    module = get_module(module_name)
    
    if not module:
        return jsonify({'error': 'Modül bulunamadı'}), 404
    
    info = module.get_info()
    info['status'] = config.get_module_status(module_name)
    info['can_install'] = module.can_install()
    
    return jsonify(info)


@api_bp.route('/modules/<module_name>/install', methods=['POST'])
def install_module(module_name: str):
    """
    Modül kurulumunu başlat (async - background thread)
    Kurulum arka planda çalışır, API hemen döner
    """
    config.reload()  # Multi-worker sync - kritik: dependency ve status kontrolü için
    module = get_module(module_name)
    
    if not module:
        return jsonify({'success': False, 'error': 'Modül bulunamadı'}), 404
    
    # Kurulabilir mi kontrol et
    can_install, reason = module.can_install()
    if not can_install:
        return jsonify({'success': False, 'error': reason}), 400
    
    # Zaten kurulu mu?
    if config.is_module_completed(module_name):
        return jsonify({'success': False, 'error': 'Modül zaten kurulu'}), 400
    
    # Zaten kuruluyor mu? (thread kontrolü)
    if module_name in _install_threads and _install_threads[module_name].is_alive():
        return jsonify({'success': False, 'error': 'Modül kurulumu zaten devam ediyor'}), 400
    
    # Status'u installing yap
    config.set_module_status(module_name, 'installing')
    logger.info(f"Modül kurulumu başlatılıyor (async): {module_name}")
    
    # Background thread başlat
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
        'message': f'{module_name} kurulumu başlatıldı. Log sayfasından takip edebilirsiniz.'
    })


def _run_install_background(module_name: str):
    """
    Background thread'de modül kurulumu çalıştır.
    Thread içinde hata yakalama ve status güncelleme yapılır.
    """
    module = get_module(module_name)
    if not module:
        logger.error(f"Modül bulunamadı: {module_name}")
        return
    
    try:
        logger.info(f"Background kurulum başladı: {module_name}")
        
        success, message = module.install()
        
        # install() metodu kendi içinde status'u set edebilir 
        # (örn: mok_pending, reboot_required)
        config.reload()  # Güncel status'u oku
        current_status = config.get_module_status(module_name)
        
        if success:
            # install() metodu özel bir status set ettiyse dokunma
            if current_status == 'installing':
                config.set_module_status(module_name, 'completed')
            logger.info(f"Kurulum tamamlandı: {module_name} - {message}")
        else:
            # Modül kendi status'unu set ettiyse (mok_pending, reboot_required) dokunma
            if current_status == 'installing':
                config.set_module_status(module_name, 'failed')
                logger.error(f"Kurulum başarısız: {module_name} - {message}")
            else:
                # mok_pending veya reboot_required - bu da bir "başarı" sayılır
                logger.info(f"Kurulum özel durumda: {module_name} ({current_status}) - {message}")
            
    except Exception as e:
        config.set_module_status(module_name, 'failed')
        logger.exception(f"Kurulum exception: {module_name} - {e}")
    finally:
        # Thread referansını temizle
        if module_name in _install_threads:
            del _install_threads[module_name]


@api_bp.route('/modules/<module_name>/status')
def module_status(module_name: str):
    """Modül durumunu döndür"""
    config.reload()  # Güncel status için
    status = config.get_module_status(module_name)
    return jsonify({
        'module': module_name,
        'status': status
    })


@api_bp.route('/modules/<module_name>/logs')
def module_logs(module_name: str):
    """Modül log'larını döndür"""
    import os
    
    log_dir = '/var/log/kiosk-setup'
    log_file = os.path.join(log_dir, f"{module_name}.log")
    
    # Son N satırı al (query param ile belirlenebilir)
    lines = int(request.args.get('lines', 200))
    
    logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                logs = all_lines[-lines:] if len(all_lines) > lines else all_lines
        except Exception as e:
            logs = [f"Log okuma hatası: {e}"]
    else:
        logs = [f"Log dosyası bulunamadı: {log_file}"]
    
    return jsonify({
        'module': module_name,
        'logs': [line.rstrip() for line in logs],
        'total_lines': len(logs)
    })


# =============================================================================
# IP YAPILANDIRMA API (NetworkManager)
# =============================================================================

@api_bp.route('/network/set-ip', methods=['POST'])
def set_network_ip():
    """
    NetworkManager ile IP yapılandırma
    mode: 'default' → 5.5.5.55/24, gateway 5.5.5.1
    mode: 'dhcp' → DHCP (otomatik)
    """
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'Veri bulunamadı'}), 400

    mode = data.get('mode')

    if mode not in ['default', 'dhcp']:
        return jsonify({'success': False, 'error': 'Geçersiz mod: default veya dhcp'}), 400

    try:
        # Aktif ethernet bağlantısını bul
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
            # Aktif bağlantı yoksa, herhangi bir ethernet bağlantısını bul
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
            return jsonify({'success': False, 'error': 'Ethernet bağlantısı bulunamadı'}), 400

        logger.info(f"IP değiştiriliyor: connection={connection_name}, mode={mode}")

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

        for cmd in cmds:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"nmcli hatası: {result.stderr}")
                return jsonify({'success': False, 'error': result.stderr or 'nmcli hatası'}), 500

        msg = 'Default IP (5.5.5.55) ayarlandı' if mode == 'default' else 'DHCP aktif edildi'
        logger.info(msg)
        return jsonify({'success': True, 'message': msg})

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'İşlem zaman aşımına uğradı'}), 500
    except Exception as e:
        logger.error(f"IP değiştirme hatası: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# KURULUM TAMAMLA API
# =============================================================================

@api_bp.route('/setup/complete', methods=['POST'])
def complete_setup():
    """Kurulumu tamamla"""
    config.reload()  # Multi-worker sync
    
    # Tüm modüller tamamlanmış mı kontrol et
    statuses = config.get_all_module_statuses()
    incomplete = [m for m, s in statuses.items() if s != 'completed']
    
    if incomplete:
        return jsonify({
            'success': False,
            'error': f'Tamamlanmamış modüller: {", ".join(incomplete)}'
        }), 400
    
    try:
        # Kurulum tamamlandı olarak işaretle
        config.set_setup_complete(True)
        
        return jsonify({
            'success': True,
            'message': 'Kurulum tamamlandı! Sistem yeniden başlatılacak...'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/setup/status')
def setup_status():
    """Kurulum durumunu döndür"""
    config.reload()  # Multi-worker sync
    statuses = config.get_all_module_statuses()
    
    total = len(statuses)
    completed = sum(1 for s in statuses.values() if s == 'completed')
    
    return jsonify({
        'complete': config.is_setup_complete(),
        'total_modules': total,
        'completed_modules': completed,
        'progress': int((completed / total) * 100) if total > 0 else 0,
        'module_statuses': statuses
    })
