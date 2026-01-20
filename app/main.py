"""
ACO Maintenance Panel - Flask Application Entry Point

MongoDB-based config system.
"""

import os
import logging
import subprocess
from flask import Flask

from app.modules.base import mongo_config as config
from app.routes.pages import pages_bp
from app.routes.api import api_bp

# Logging configuration
os.makedirs('/var/log/aco-panel', exist_ok=True)  # Create log directory
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/aco-panel/main.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def check_pending_modules():
    """
    Check modules with mok_pending and reboot_required status at startup.
    For automatic status update after reboot.
    """
    config.reload()
    statuses = config.get_all_module_statuses()

    for module_name, status in statuses.items():
        if status == 'mok_pending' or status == 'reboot_required':
            logger.info(f"Checking pending module: {module_name} ({status})")

            # Special check for NVIDIA module
            if module_name == 'nvidia':
                try:
                    result = subprocess.run(
                        ['nvidia-smi'],
                        capture_output=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        logger.info(f"NVIDIA is working, setting status to completed")
                        config.set_module_status('nvidia', 'completed')
                    else:
                        logger.warning(f"NVIDIA not yet working, keeping status: {status}")
                except FileNotFoundError:
                    logger.warning("nvidia-smi not found")
                except Exception as e:
                    logger.warning(f"NVIDIA check error: {e}")


def create_app() -> Flask:
    """Create and configure Flask application"""

    # Flask app
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static'
    )

    # Secret key
    app.secret_key = os.urandom(24)

    # Jinja2 settings
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # Register blueprints
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Context processor - variables available in all templates
    @app.context_processor
    def inject_globals():
        return {
            'config': config,
            'is_setup_complete': config.is_setup_complete(),
            'rvm_id': config.get_rvm_id(),
        }

    logger.info("ACO Maintenance Panel started")

    return app


# App instance for Gunicorn
app = create_app()

# Check pending modules at startup
check_pending_modules()


if __name__ == '__main__':
    # Development server
    app.run(host='0.0.0.0', port=4444, debug=True)
