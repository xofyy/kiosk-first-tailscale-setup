"""
Log Stream Manager - Docker API
Manages container log streams via Docker socket API
"""

import time
import logging
import threading
import docker
from typing import Dict, Optional, Any, Generator
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Constants
STALE_TIMEOUT = 300  # 5 minutes


class LogStreamManager:
    """
    Singleton pattern for single instance.
    Thread-safe log stream management via Docker API.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._docker_client = docker.from_env()
                    cls._instance._streams: Dict[str, Dict[str, Any]] = {}
                    cls._instance._streams_lock = threading.Lock()
        return cls._instance

    def get_or_create_stream(
        self, session_id: str, service_name: str,
        tail: str = '300', since: str = ''
    ) -> Optional[Generator]:
        """
        Create a new stream for session.
        Always starts fresh - no reuse to ensure consistent log output.

        Args:
            session_id: Unique client session identifier
            service_name: Docker compose service name
            tail: Number of historical lines (default: 300)
            since: Time filter (e.g., '1h', '6h', '24h', '168h')
        """
        with self._streams_lock:
            # Always cleanup existing stream first (no reuse)
            existing = self._streams.pop(session_id, None)

            # Find container by service label
            try:
                containers = self._docker_client.containers.list(
                    filters={'label': f'com.docker.compose.service={service_name}'}
                )

                if not containers:
                    logger.warning(f"No container found for service: {service_name}")
                    return None

                container = containers[0]

                # Parse since parameter (convert '1h' → datetime)
                since_timestamp = None
                if since:
                    since_timestamp = self._parse_since(since)

                # Create log stream (Generator)
                log_stream = container.logs(
                    stream=True,
                    follow=True,
                    tail=int(tail),
                    since=since_timestamp,
                    timestamps=True
                )

                # Track stream
                self._streams[session_id] = {
                    "generator": log_stream,
                    "container": container,
                    "container_id": container.id,
                    "service": service_name,
                    "created_at": time.time(),
                    "tail": tail,
                    "since": since
                }

                logger.debug(f"Started log stream: {session_id} -> {service_name} (tail={tail}, since={since or 'all'})")
                return log_stream

            except Exception as e:
                logger.error(f"Failed to start log stream: {e}")
                return None

    def stop_stream(self, session_id: str) -> bool:
        """Stop and cleanup stream for session."""
        with self._streams_lock:
            stream = self._streams.pop(session_id, None)
            if stream:
                # Generator stops when reference is lost (no explicit kill needed)
                logger.debug(f"Stopped log stream: {session_id}")
                return True
            return False

    def cleanup_stale_streams(self) -> int:
        """
        Cleanup old (5min+) streams and detect dead containers.
        Should be called periodically.
        """
        now = time.time()
        stale_sessions = []

        with self._streams_lock:
            for session_id, stream in self._streams.items():
                # Dead container or too old
                created_at = stream.get("created_at", 0)
                container = stream.get("container")

                # Check if container still exists
                try:
                    container.reload()
                    if now - created_at > STALE_TIMEOUT:
                        stale_sessions.append(session_id)
                except:
                    # Container gone or not accessible
                    stale_sessions.append(session_id)

            for session_id in stale_sessions:
                self._streams.pop(session_id, None)

        if stale_sessions:
            logger.info(f"Cleaned up {len(stale_sessions)} stale log streams")

        return len(stale_sessions)

    def get_active_count(self) -> int:
        """Get number of active streams."""
        with self._streams_lock:
            return len(self._streams)

    def shutdown(self):
        """Close all streams (graceful shutdown)."""
        with self._streams_lock:
            self._streams.clear()
        logger.info("All log streams shut down")

    def _parse_since(self, since: str) -> Optional[datetime]:
        """
        Convert since parameter to datetime object.

        Args:
            since: Time string ('1h', '6h', '24h', '168h')

        Returns:
            datetime object or None
        """
        mappings = {
            '1h': timedelta(hours=1),
            '6h': timedelta(hours=6),
            '24h': timedelta(hours=24),
            '168h': timedelta(hours=168)
        }
        delta = mappings.get(since)
        if delta:
            return datetime.utcnow() - delta
        return None


# Singleton instance
log_process_manager = LogStreamManager()
