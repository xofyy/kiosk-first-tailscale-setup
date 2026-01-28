"""
Log Stream Manager - Docker API with Non-blocking Threading
Manages container log streams via Docker socket API with proper resource cleanup.
"""

import time
import logging
import threading
import queue
import docker
from typing import Dict, Optional, Any, Generator, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Constants
STALE_TIMEOUT = 300          # 5 minutes - cleanup threshold
HEARTBEAT_INTERVAL = 10      # Heartbeat frequency (seconds) - reduced for faster response
READ_TIMEOUT = 60            # No data timeout (seconds)
MAX_CONCURRENT_STREAMS = 10  # Maximum concurrent streams
QUEUE_MAX_SIZE = 500         # Log buffer queue size - reduced
THREAD_JOIN_TIMEOUT = 0.5    # Thread join timeout (seconds) - very short, don't block


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

    CRITICAL: Lock is only held for dict operations, never during cleanup!
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
        """
        # Step 1: Remove existing stream from dict (with lock)
        # Step 2: Cleanup old stream (WITHOUT lock - this can block!)
        # Step 3: Create new stream (with lock for dict update)

        existing = None
        streams_to_cleanup: List[StreamInfo] = []

        # PHASE 1: Quick lock - just remove from dict
        with self._streams_lock:
            existing = self._streams.pop(session_id, None)
            if existing:
                streams_to_cleanup.append(existing)

            # Check concurrent limit
            if len(self._streams) >= MAX_CONCURRENT_STREAMS:
                oldest_session = min(
                    self._streams.keys(),
                    key=lambda s: self._streams[s].created_at
                )
                oldest = self._streams.pop(oldest_session, None)
                if oldest:
                    streams_to_cleanup.append(oldest)
                    logger.info(f"Evicted oldest stream: {oldest_session}")

        # PHASE 2: Cleanup WITHOUT lock (this can take time)
        for stream_info in streams_to_cleanup:
            self._cleanup_stream_async(stream_info)

        # PHASE 3: Create new stream
        log_stream = None
        try:
            containers = self._docker_client.containers.list(
                filters={'label': f'com.docker.compose.service={service_name}'}
            )

            if not containers:
                logger.warning(f"No container found for service: {service_name}")
                return None

            container = containers[0]

            # Parse since parameter
            since_timestamp = self._parse_since(since) if since else None

            # Create log stream (Generator from Docker API)
            log_stream = container.logs(
                stream=True,
                follow=True,
                tail=int(tail),
                since=since_timestamp,
                timestamps=True
            )

            # Create stream info
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

            # PHASE 4: Quick lock - just add to dict
            with self._streams_lock:
                self._streams[session_id] = stream_info

            logger.debug(f"Started log stream: {session_id} -> {service_name}")

            # Return non-blocking generator
            return self._create_non_blocking_generator(stream_info, session_id)

        except Exception as e:
            if log_stream is not None:
                self._close_generator(log_stream)
            logger.error(f"Failed to start log stream: {e}")
            return None

    def _cleanup_stream_async(self, stream_info: StreamInfo) -> None:
        """
        Cleanup a stream asynchronously - doesn't block.
        First closes generator to unblock the reader thread.
        """
        # 1. Close generator FIRST - this unblocks the reader thread
        self._close_generator(stream_info.generator)

        # 2. Signal thread to stop
        stream_info.stop_event.set()

        # 3. Quick join - don't wait long (thread is daemon, will die with process)
        if stream_info.reader_thread and stream_info.reader_thread.is_alive():
            stream_info.reader_thread.join(timeout=THREAD_JOIN_TIMEOUT)

        # 4. Drain queue
        try:
            while True:
                stream_info.log_queue.get_nowait()
        except queue.Empty:
            pass

    def _reader_thread_func(
        self,
        docker_generator: Generator,
        log_queue: "queue.Queue[Optional[bytes]]",
        stop_event: threading.Event,
        session_id: str
    ) -> None:
        """
        Reader thread - reads from Docker API and writes to queue.
        Will exit when generator is closed or stop_event is set.
        """
        try:
            for log_bytes in docker_generator:
                if stop_event.is_set():
                    break
                try:
                    log_queue.put(log_bytes, timeout=0.5)
                except queue.Full:
                    # Skip if queue full
                    continue
        except GeneratorExit:
            pass
        except Exception as e:
            if not stop_event.is_set():
                logger.debug(f"Reader thread error {session_id}: {e}")
        finally:
            try:
                log_queue.put(None, timeout=0.1)
            except:
                pass

    def _create_non_blocking_generator(
        self, stream_info: StreamInfo, session_id: str
    ) -> Generator[bytes, None, None]:
        """
        Non-blocking generator with heartbeat support.
        """
        last_data_time = time.time()

        while not stream_info.stop_event.is_set():
            try:
                item = stream_info.log_queue.get(timeout=HEARTBEAT_INTERVAL)

                if item is None:
                    break

                last_data_time = time.time()
                yield item

            except queue.Empty:
                # Timeout - check if we should stop
                if time.time() - last_data_time > READ_TIMEOUT:
                    logger.debug(f"Read timeout: {session_id}")
                    break
                # Send heartbeat
                yield b":heartbeat"

    def stop_stream(self, session_id: str) -> bool:
        """Stop and cleanup stream for session."""
        # Quick lock - just remove from dict
        stream_info = None
        with self._streams_lock:
            stream_info = self._streams.pop(session_id, None)

        # Cleanup WITHOUT lock
        if stream_info:
            self._cleanup_stream_async(stream_info)
            logger.debug(f"Stopped log stream: {session_id}")
            return True
        return False

    def cleanup_stale_streams(self) -> int:
        """Cleanup old streams - called periodically."""
        now = time.time()
        stale_streams: List[tuple] = []

        # Quick lock - just identify stale streams
        with self._streams_lock:
            for session_id, stream_info in list(self._streams.items()):
                is_stale = False

                if now - stream_info.created_at > STALE_TIMEOUT:
                    is_stale = True
                else:
                    try:
                        stream_info.container.reload()
                    except:
                        is_stale = True

                if is_stale:
                    self._streams.pop(session_id, None)
                    stale_streams.append((session_id, stream_info))

        # Cleanup WITHOUT lock
        for session_id, stream_info in stale_streams:
            self._cleanup_stream_async(stream_info)

        if stale_streams:
            logger.info(f"Cleaned up {len(stale_streams)} stale streams")

        return len(stale_streams)

    def get_active_count(self) -> int:
        """Get number of active streams."""
        with self._streams_lock:
            return len(self._streams)

    def get_stream_info(self) -> Dict[str, Dict[str, Any]]:
        """Get debug info about active streams."""
        with self._streams_lock:
            return {
                sid: {
                    "service": info.service,
                    "age_seconds": int(time.time() - info.created_at),
                    "queue_size": info.log_queue.qsize(),
                    "thread_alive": info.reader_thread.is_alive() if info.reader_thread else False
                }
                for sid, info in self._streams.items()
            }

    def shutdown(self):
        """Close all streams."""
        streams_to_cleanup = []
        with self._streams_lock:
            streams_to_cleanup = list(self._streams.values())
            self._streams.clear()

        for stream_info in streams_to_cleanup:
            self._cleanup_stream_async(stream_info)

        logger.info("All log streams shut down")

    def _close_generator(self, generator) -> None:
        """Safely close Docker API generator."""
        if generator is None:
            return
        try:
            generator.close()
        except:
            pass

    def _parse_since(self, since: str) -> Optional[datetime]:
        """Convert since parameter to datetime."""
        mappings = {
            '1h': timedelta(hours=1),
            '6h': timedelta(hours=6),
            '24h': timedelta(hours=24),
            '168h': timedelta(hours=168)
        }
        delta = mappings.get(since)
        return datetime.utcnow() - delta if delta else None


# Singleton instance
log_process_manager = LogStreamManager()
