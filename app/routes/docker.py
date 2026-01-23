"""
Docker Container Management API Routes
Includes REST endpoints and SSE for log streaming
"""

import logging
from flask import Blueprint, jsonify, request, Response
from app.services.docker_manager import DockerManager

docker_bp = Blueprint('docker', __name__)
logger = logging.getLogger(__name__)


@docker_bp.route('/containers')
def list_containers():
    """List all containers with status"""
    try:
        manager = DockerManager()
        containers = manager.get_all_containers()
        return jsonify({"success": True, "containers": containers})
    except Exception as e:
        logger.error(f"Error listing containers: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@docker_bp.route('/containers/<service_name>/status')
def container_status(service_name: str):
    """Get single container status"""
    try:
        manager = DockerManager()
        status = manager.get_container_status(service_name)
        return jsonify({
            "success": True,
            "service_name": service_name,
            "status": status
        })
    except Exception as e:
        logger.error(f"Error getting status for {service_name}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@docker_bp.route('/containers/<service_name>/<action>', methods=['POST'])
def container_action(service_name: str, action: str):
    """
    Execute container action.
    Actions: start, stop, restart
    """
    if action not in ['start', 'stop', 'restart']:
        return jsonify({"success": False, "error": f"Invalid action: {action}"}), 400

    try:
        manager = DockerManager()
        result = manager.container_action(service_name, action)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.error(f"Error executing {action} on {service_name}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@docker_bp.route('/containers/<service_name>/logs')
def container_logs_sse(service_name: str):
    """
    SSE endpoint for streaming container logs.
    Uses Server-Sent Events for real-time streaming.

    Query params:
        tail: Number of lines to show initially (default: 200)
    """
    tail = request.args.get('tail', 200, type=int)

    def generate():
        manager = DockerManager()
        try:
            for line in manager.stream_logs(service_name, tail=tail):
                # SSE format: data: <content>\n\n
                yield f"data: {line}\n\n"
        except GeneratorExit:
            # Client disconnected
            logger.debug(f"SSE client disconnected: {service_name}")
        except Exception as e:
            logger.error(f"SSE error for {service_name}: {e}")
            yield f"data: Error: {e}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # Disable nginx buffering for SSE
        }
    )
