"""
Log Stream Manager - Docker API with Non-blocking Threading
Manages container log streams via Docker socket API with proper resource cleanup.
"""

import time
import logging
import threading
import queue
import docker
from typing import Dict, Optional, Any, Generator
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Constants
STALE_TIMEOUT = 300          # 5 minutes - cleanup threshold
HEARTBEAT_INTERVAL = 15      # Heartbeat frequency (seconds)
READ_TIMEOUT = 60            # No data timeout (seconds)
MAX_CONCURRENT_STREAMS = 10  # Maximum concurrent streams
QUEUE_MAX_SIZE = 1000        # Log buffer queue size
THREAD_JOIN_TIMEOUT = 2      # Thread join timeout (seconds)


@dataclass
class StreamInfo:
    """Container for stream-related objects and metadata."""
    generator: Any
    container: Any
    container_id: str
    service: str
    created_at: float
    tail: str
    since: str
    stop_event: threading.Event
    reader_thread: Optional[threading.Thread]
    log_queue: "queue.Queue[Optional[bytes]]" = field(default_factory=lambda: queue.Queue(maxsize=QUEUE_MAX_SIZE))


class LogStreamManager:
    """
    Singleton pattern for single instance.
    Thread-safe log stream management via Docker API with non-blocking I/O.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._docker_client = docker.from_env()
                    cls._instance._streams: Dict[str, StreamInfo] = {}
                    cls._instance._streams_lock = threading.Lock()
        return cls._instance

    def get_or_create_stream(
        self, session_id: str, service_name: str,
        tail: str = '300', since: str = ''
    ) -> Optional[Generator]:
        """
        Create a new non-blocking stream for session.
        Uses threading to prevent blocking on Docker API reads.

        Args:
            session_id: Unique client session identifier
            service_name: Docker compose service name
            tail: Number of historical lines (default: 300)
            since: Time filter (e.g., '1h', '6h', '24h', '168h')

        Returns:
            Generator yielding log bytes or heartbeat markers
        """
        with self._streams_lock:
            # Always cleanup existing stream first (no reuse)
            existing = self._streams.pop(session_id, None)
            if existing:
                self._stop_stream_internal(existing)
                logger.debug(f"Cleaned up existing stream for session: {session_id}")

            # Enforce concurrent stream limit
            if len(self._streams) >= MAX_CONCURRENT_STREAMS:
                oldest_session = min(
                    self._streams.keys(),
                    key=lambda s: self._streams[s].created_at
                )
                oldest = self._streams.pop(oldest_session, None)
                if oldest:
                    self._stop_stream_internal(oldest)
                    logger.info(f"Evicted oldest stream due to limit: {oldest_session}")

            # Find container by service label
            log_stream = None
            try:
                containers = self._docker_client.containers.list(
                    filters={'label': f'com.docker.compose.service={service_name}'}
                )

                if not containers:
                    logger.warning(f"No container found for service: {service_name}")
                    return None

                container = containers[0]

                # Parse since parameter (convert '1h' -> datetime)
                since_timestamp = None
                if since:
                    since_timestamp = self._parse_since(since)

                # Create log stream (Generator from Docker API)
                log_stream = container.logs(
                    stream=True,
                    follow=True,
                    tail=int(tail),
                    since=since_timestamp,
                    timestamps=True
                )

                # Create stream info with threading components
                stop_event = threading.Event()
                log_queue: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=QUEUE_MAX_SIZE)

                stream_info = StreamInfo(
                    generator=log_stream,
                    container=container,
                    container_id=container.id,
                    service=service_name,
                    created_at=time.time(),
                    tail=tail,
                    since=since,
                    stop_event=stop_event,
                    reader_thread=None,
                    log_queue=log_queue
                )

                # Start reader thread
                reader_thread = threading.Thread(
                    target=self._reader_thread_func,
                    args=(log_stream, log_queue, stop_event, session_id),
                    daemon=True,
                    name=f"LogReader-{session_id[:8]}"
                )
                stream_info.reader_thread = reader_thread
                reader_thread.start()

                # Track stream
                self._streams[session_id] = stream_info

                logger.debug(f"Started log stream: {session_id} -> {service_name} (tail={tail}, since={since or 'all'})")

                # Return non-blocking generator
                return self._create_non_blocking_generator(stream_info, session_id)

            except Exception as e:
                # If generator was created but not tracked, close it
                if log_stream is not None:
                    self._close_generator(log_stream)
                logger.error(f"Failed to start log stream: {e}")
                return None

    def _reader_thread_func(
        self,
        docker_generator: Generator,
        log_queue: "queue.Queue[Optional[bytes]]",
        stop_event: threading.Event,
        session_id: str
    ) -> None:
        """
        Reader thread function that reads from Docker API and writes to queue.
        Runs in separate thread to prevent blocking the main generator.
        """
        try:
            for log_bytes in docker_generator:
                if stop_event.is_set():
                    break
                try:
                    # Non-blocking put with timeout to check stop_event periodically
                    log_queue.put(log_bytes, timeout=1)
                except queue.Full:
                    # Queue full, skip this log line (client too slow)
                    logger.warning(f"Log queue full for {session_id}, dropping log line")
                    continue
        except Exception as e:
            if not stop_event.is_set():
                logger.debug(f"Reader thread exception for {session_id}: {e}")
        finally:
            # Signal end of stream
            try:
                log_queue.put(None, timeout=1)
            except queue.Full:
                pass
            logger.debug(f"Reader thread finished: {session_id}")

    def _create_non_blocking_generator(
        self, stream_info: StreamInfo, session_id: str
    ) -> Generator[bytes, None, None]:
        """
        Create a non-blocking generator that reads from queue with heartbeat support.
        """
        last_data_time = time.time()

        while not stream_info.stop_event.is_set():
            try:
                # Wait for data with heartbeat interval timeout
                item = stream_info.log_queue.get(timeout=HEARTBEAT_INTERVAL)

                if item is None:
                    # End of stream signal
                    break

                last_data_time = time.time()
                yield item

            except queue.Empty:
                # No data within heartbeat interval
                current_time = time.time()

                # Check for read timeout (no data for too long)
                if current_time - last_data_time > READ_TIMEOUT:
                    logger.debug(f"Read timeout for session {session_id}, closing stream")
                    break

                # Send heartbeat
                yield b":heartbeat"

    def stop_stream(self, session_id: str) -> bool:
        """Stop and cleanup stream for session."""
        with self._streams_lock:
            stream_info = self._streams.pop(session_id, None)
            if stream_info:
                self._stop_stream_internal(stream_info)
                logger.debug(f"Stopped log stream: {session_id}")
                return True
            return False

    def _stop_stream_internal(self, stream_info: StreamInfo) -> None:
        """
        Internal method to stop a stream (without lock).
        Signals thread to stop, waits for completion, closes resources.
        """
        # Signal thread to stop
        stream_info.stop_event.set()

        # Wait for thread to finish
        if stream_info.reader_thread and stream_info.reader_thread.is_alive():
            stream_info.reader_thread.join(timeout=THREAD_JOIN_TIMEOUT)
            if stream_info.reader_thread.is_alive():
                logger.warning(f"Reader thread did not stop in time for {stream_info.service}")

        # Close Docker API generator
        self._close_generator(stream_info.generator)

        # Drain and clear queue
        try:
            while True:
                stream_info.log_queue.get_nowait()
        except queue.Empty:
            pass

    def cleanup_stale_streams(self) -> int:
        """
        Cleanup old (5min+) streams and detect dead containers.
        Should be called periodically.
        """
        now = time.time()
        stale_sessions = []

        with self._streams_lock:
            for session_id, stream_info in self._streams.items():
                # Check age
                if now - stream_info.created_at > STALE_TIMEOUT:
                    stale_sessions.append(session_id)
                    continue

                # Check if container still exists
                try:
                    stream_info.container.reload()
                except Exception:
                    # Container gone or not accessible
                    stale_sessions.append(session_id)

            for session_id in stale_sessions:
                stream_info = self._streams.pop(session_id, None)
                if stream_info:
                    self._stop_stream_internal(stream_info)

        if stale_sessions:
            logger.info(f"Cleaned up {len(stale_sessions)} stale log streams")

        return len(stale_sessions)

    def get_active_count(self) -> int:
        """Get number of active streams."""
        with self._streams_lock:
            return len(self._streams)

    def get_stream_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all active streams (for debugging)."""
        with self._streams_lock:
            return {
                session_id: {
                    "service": info.service,
                    "created_at": info.created_at,
                    "age_seconds": time.time() - info.created_at,
                    "queue_size": info.log_queue.qsize(),
                    "thread_alive": info.reader_thread.is_alive() if info.reader_thread else False
                }
                for session_id, info in self._streams.items()
            }

    def shutdown(self):
        """Close all streams (graceful shutdown)."""
        with self._streams_lock:
            for session_id, stream_info in list(self._streams.items()):
                self._stop_stream_internal(stream_info)
            self._streams.clear()
        logger.info("All log streams shut down")

    def _close_generator(self, generator) -> None:
        """
        Safely close Docker API generator and release connection.

        Docker API generators maintain an open socket connection.
        Must be explicitly closed to prevent resource leaks.
        """
        if generator is None:
            return

        try:
            generator.close()
            logger.debug("Docker API generator closed, socket released")
        except Exception as e:
            # Generator may already be closed or invalid
            logger.warning(f"Error closing generator: {e}")

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
