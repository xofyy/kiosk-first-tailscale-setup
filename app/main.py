"""
Kiosk Setup Panel - Flask Application Entry Point
"""

import os
import logging
from flask import Flask

from app.config import config
from app.routes.pages import pages_bp
from app.routes.api import api_bp

# Logging yapılandırması
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/kiosk-setup.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


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


if __name__ == '__main__':
    # Development server
    app.run(host='0.0.0.0', port=8080, debug=True)
