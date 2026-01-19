"""
Kiosk Setup Panel - Flask Application Entry Point
"""

import os
import logging
import subprocess
from flask import Flask

from app.config import config
from app.routes.pages import pages_bp
from app.routes.api import api_bp

# Logging yapılandırması
os.makedirs('/var/log/kiosk-setup', exist_ok=True)  # Log dizinini oluştur
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/kiosk-setup/main.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def check_pending_modules():
    """
    Startup'ta mok_pending ve reboot_required durumundaki modülleri kontrol et.
    Reboot sonrası otomatik status güncelleme için.
    """
    config.reload()
    statuses = config.get_all_module_statuses()
    
    for module_name, status in statuses.items():
        if status == 'mok_pending' or status == 'reboot_required':
            logger.info(f"Pending modül kontrol ediliyor: {module_name} ({status})")
            
            # NVIDIA modülü için özel kontrol
            if module_name == 'nvidia':
                try:
                    result = subprocess.run(
                        ['nvidia-smi'],
                        capture_output=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        logger.info(f"NVIDIA çalışıyor, status completed yapılıyor")
                        config.set_module_status('nvidia', 'completed')
                    else:
                        logger.warning(f"NVIDIA henüz çalışmıyor, status korunuyor: {status}")
                except FileNotFoundError:
                    logger.warning("nvidia-smi bulunamadı")
                except Exception as e:
                    logger.warning(f"NVIDIA kontrol hatası: {e}")


def create_app() -> Flask:
    """Flask uygulamasını oluştur ve yapılandır"""
    
    # Flask app
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static'
    )
    
    # Secret key
    app.secret_key = os.urandom(24)
    
    # Jinja2 ayarları
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    
    # Blueprint'leri kaydet
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Context processor - tüm template'lerde kullanılabilir değişkenler
    @app.context_processor
    def inject_globals():
        return {
            'config': config,
            'is_setup_complete': config.is_setup_complete(),
            'kiosk_id': config.get_kiosk_id(),
        }
    
    logger.info("Kiosk Setup Panel başlatıldı")
    
    return app


# Gunicorn için app instance
app = create_app()

# Startup'ta pending modülleri kontrol et
check_pending_modules()


if __name__ == '__main__':
    # Development server
    app.run(host='0.0.0.0', port=4444, debug=True)
