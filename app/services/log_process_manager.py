"""
Log Process Manager - Singleton
Manages all log streaming subprocess'es centrally to prevent leaks.
"""

import time
import logging
import threading
import subprocess
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# Constants
COMPOSE_PATH = "/srv/docker"
STALE_TIMEOUT = 300  # 5 minutes


class LogProcessManager:
    """
    Singleton pattern for single instance.
    Thread-safe subprocess management.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._streams: Dict[str, Dict[str, Any]] = {}
                    cls._instance._streams_lock = threading.Lock()
        return cls._instance

    def get_or_create_stream(self, session_id: str, service_name: str, tail: str = '300', since: str = '') -> Optional[subprocess.Popen]:
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
            if existing:
                self._kill_process(existing.get("process"))

            # Build command with filter parameters
            cmd = ['docker', 'compose', 'logs', '--tail', tail]
            if since:
                cmd.extend(['--since', since])
            cmd.extend(['-f', '-t', '--no-color', service_name])

            # Start new process
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    cwd=COMPOSE_PATH
                )

                self._streams[session_id] = {
                    "process": process,
                    "service": service_name,
                    "created_at": time.time(),
                    "tail": tail,
                    "since": since
                }

                logger.debug(f"Started log stream: {session_id} -> {service_name} (tail={tail}, since={since or 'all'})")
                return process

            except Exception as e:
                logger.error(f"Failed to start log stream: {e}")
                return None

    def stop_stream(self, session_id: str) -> bool:
        """Stop and cleanup stream for session."""
        with self._streams_lock:
            stream = self._streams.pop(session_id, None)
            if stream:
                self._kill_process(stream.get("process"))
                logger.debug(f"Stopped log stream: {session_id}")
                return True
            return False

    def cleanup_stale_streams(self) -> int:
        """
        Cleanup old (5min+) streams.
        Should be called periodically.
        """
        now = time.time()
        stale_sessions = []

        with self._streams_lock:
            for session_id, stream in self._streams.items():
                # Dead process or too old
                process = stream.get("process")
                created_at = stream.get("created_at", 0)

                if process is None or process.poll() is not None:
                    stale_sessions.append(session_id)
                elif now - created_at > STALE_TIMEOUT:
                    stale_sessions.append(session_id)

            for session_id in stale_sessions:
                stream = self._streams.pop(session_id, None)
                if stream:
                    self._kill_process(stream.get("process"))

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
            for session_id, stream in list(self._streams.items()):
                self._kill_process(stream.get("process"))
            self._streams.clear()
        logger.info("All log streams shut down")

    def _kill_process(self, process: Optional[subprocess.Popen]):
        """Safely kill a process."""
        if process is None:
            return
        try:
            if process.poll() is None:  # Still running
                process.kill()
                process.wait(timeout=5)
        except Exception as e:
            logger.warning(f"Error killing process: {e}")


# Singleton instance
log_process_manager = LogProcessManager()
