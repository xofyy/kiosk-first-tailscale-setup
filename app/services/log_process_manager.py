"""
Log Stream Manager - Singleton
Manages Docker log streams using Docker SDK.
Thread-safe stream management with since parameter support.
"""

import time
import logging
import threading
from typing import Dict, Optional, Any, Generator

import docker
from docker.errors import NotFound, APIError

logger = logging.getLogger(__name__)

# Constants
COMPOSE_PATH = "/srv/docker"
STALE_TIMEOUT = 120  # 2 minutes (reduced from 5 for better cleanup)
COMPOSE_PROJECT_LABEL = "com.docker.compose.service"

# Since parameter mapping (string -> seconds)
SINCE_MAPPING = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "all": None
}


class LogStreamManager:
    """
    Singleton pattern for single instance.
    Thread-safe Docker SDK stream management.
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
                    cls._instance._client = None
        return cls._instance

    def _get_client(self) -> docker.DockerClient:
        """Get or create Docker client (lazy initialization)."""
        if self._client is None:
            try:
                self._client = docker.from_env()
            except Exception as e:
                logger.error(f"Failed to connect to Docker: {e}")
                raise
        return self._client

    def _get_container_by_service(self, service_name: str) -> Optional[Any]:
        """
        Find container by docker-compose service name.
        Uses the com.docker.compose.service label.
        """
        try:
            client = self._get_client()
            containers = client.containers.list(
                all=True,  # Include stopped containers
                filters={"label": f"{COMPOSE_PROJECT_LABEL}={service_name}"}
            )
            return containers[0] if containers else None
        except Exception as e:
            logger.error(f"Error finding container for service {service_name}: {e}")
            return None

    def _parse_since(self, since: str) -> Optional[int]:
        """
        Convert since parameter to Unix timestamp.
        Returns None for 'all' (no time filter).
        """
        if since not in SINCE_MAPPING:
            since = "15m"  # Default fallback
        
        seconds = SINCE_MAPPING.get(since)
        if seconds is None:
            return None
        
        return int(time.time()) - seconds

    def get_or_create_stream(
        self, 
        session_id: str, 
        service_name: str, 
        since: str = "15m"
    ) -> Optional[Generator[str, None, None]]:
        """
        Get existing stream for session or create new one.
        If same session switches to different service or since, recreate stream.
        
        Args:
            session_id: Unique client session identifier
            service_name: Docker compose service name
            since: Time filter (5m, 15m, 1h, 6h, all)
        
        Returns:
            Generator yielding log lines, or None on error
        """
        with self._streams_lock:
            existing = self._streams.get(session_id)

            # Check if we can reuse existing stream
            if existing:
                if (existing.get("service") == service_name and 
                    existing.get("since") == since and
                    existing.get("generator")):
                    return existing.get("generator")
                
                # Different params - cleanup old stream
                self._cleanup_stream_entry(existing)

            # Find container
            container = self._get_container_by_service(service_name)
            if container is None:
                logger.warning(f"Container not found for service: {service_name}")
                return None

            # Parse since parameter
            since_timestamp = self._parse_since(since)

            # Create generator
            try:
                generator = self._create_log_generator(
                    container, 
                    since_timestamp,
                    session_id
                )
                
                self._streams[session_id] = {
                    "generator": generator,
                    "service": service_name,
                    "since": since,
                    "container_id": container.id,
                    "created_at": time.time()
                }
                
                logger.debug(f"Started log stream: {session_id} -> {service_name} (since={since})")
                return generator

            except Exception as e:
                logger.error(f"Failed to create log stream: {e}")
                return None

    def _create_log_generator(
        self, 
        container, 
        since_timestamp: Optional[int],
        session_id: str
    ) -> Generator[str, None, None]:
        """
        Create a generator that yields log lines from container.
        Handles timestamps and carriage returns.
        """
        try:
            # Build log parameters
            log_params = {
                "stream": True,
                "follow": True,
                "timestamps": True,
                "tail": 500  # Initial lines limit
            }
            
            if since_timestamp is not None:
                log_params["since"] = since_timestamp

            # Get log stream
            log_stream = container.logs(**log_params)

            for chunk in log_stream:
                # Decode bytes to string
                if isinstance(chunk, bytes):
                    line = chunk.decode('utf-8', errors='replace')
                else:
                    line = str(chunk)

                # Handle carriage returns (progress bars etc.)
                # Only yield the last non-empty part after \r splits
                parts = line.rstrip('\n').split('\r')
                for part in reversed(parts):
                    part = part.strip()
                    if part:
                        yield part
                        break

        except GeneratorExit:
            # Client disconnected - normal
            logger.debug(f"Log stream generator exit: {session_id}")
        except NotFound:
            yield "Error: Container not found"
        except APIError as e:
            logger.error(f"Docker API error: {e}")
            yield f"Error: Docker API error - {e}"
        except Exception as e:
            logger.error(f"Log streaming error: {e}")
            yield f"Error: {e}"

    def stop_stream(self, session_id: str) -> bool:
        """Stop and cleanup stream for session."""
        with self._streams_lock:
            stream = self._streams.pop(session_id, None)
            if stream:
                self._cleanup_stream_entry(stream)
                logger.debug(f"Stopped log stream: {session_id}")
                return True
            return False

    def _cleanup_stream_entry(self, stream_entry: Dict[str, Any]):
        """Cleanup a stream entry (close generator if possible)."""
        generator = stream_entry.get("generator")
        if generator:
            try:
                generator.close()
            except Exception:
                pass

    def cleanup_stale_streams(self) -> int:
        """
        Cleanup old streams (2min+).
        Should be called periodically.
        """
        now = time.time()
        stale_sessions = []

        with self._streams_lock:
            for session_id, stream in self._streams.items():
                created_at = stream.get("created_at", 0)
                if now - created_at > STALE_TIMEOUT:
                    stale_sessions.append(session_id)

            for session_id in stale_sessions:
                stream = self._streams.pop(session_id, None)
                if stream:
                    self._cleanup_stream_entry(stream)

        if stale_sessions:
            logger.info(f"Cleaned up {len(stale_sessions)} stale log streams")

        return len(stale_sessions)

    def get_active_count(self) -> int:
        """Get number of active streams."""
        with self._streams_lock:
            return len(self._streams)

    def shutdown(self):
        """Close all streams and Docker client (graceful shutdown)."""
        with self._streams_lock:
            for session_id, stream in list(self._streams.items()):
                self._cleanup_stream_entry(stream)
            self._streams.clear()
        
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        
        logger.info("All log streams shut down")


# Singleton instance
log_stream_manager = LogStreamManager()

# Backward compatibility alias
log_process_manager = log_stream_manager
