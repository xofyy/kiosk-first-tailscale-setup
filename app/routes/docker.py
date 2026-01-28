"""
Docker Container Management API Routes
Includes REST endpoints and SSE for log streaming
"""

import uuid
import logging
from flask import Blueprint, jsonify, request, Response
from app.services.docker_manager import DockerManager
from app.services.log_process_manager import log_process_manager

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
        session_id: Client session identifier (optional, auto-generated if missing)
        tail: Number of lines to show initially (default: 300, max: 1000)
        since: Time filter (e.g., '1h', '6h', '24h', '168h' for 7 days)
    """
    # Session ID - get from client or generate new one
    session_id = request.args.get('session_id') or str(uuid.uuid4())

    # Extract and validate tail parameter (10-1000)
    tail = request.args.get('tail', '300')
    try:
        tail_int = max(10, min(1000, int(tail)))
        tail = str(tail_int)
    except ValueError:
        tail = '300'

    # Extract and validate since parameter (whitelist)
    since = request.args.get('since', '')
    allowed_since = {'', '1h', '6h', '24h', '168h'}
    if since not in allowed_since:
        since = ''

    # Cleanup stale streams on each request
    log_process_manager.cleanup_stale_streams()

    def generate():
        manager = DockerManager()
        line_count = 0
        try:
            for line in manager.stream_logs(session_id, service_name, tail=tail, since=since):
                line_count += 1
                yield f"data: {line}\n\n"
        except GeneratorExit:
            logger.debug(f"SSE disconnected: {session_id} ({line_count} lines)")
        except Exception as e:
            logger.error(f"SSE error {service_name}: {e}")
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


@docker_bp.route('/containers/logs/stop', methods=['POST'])
def stop_log_stream():
    """
    Explicit log stream stop endpoint.
    Called by client when modal is closed (optional but recommended).
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id')

    if session_id:
        stopped = log_process_manager.stop_stream(session_id)
        return jsonify({"success": stopped})

    return jsonify({"success": False, "error": "session_id required"}), 400
