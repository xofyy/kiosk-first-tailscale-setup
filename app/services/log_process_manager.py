"""
Log Process Manager - Thread-based Non-blocking
Reader thread reads subprocess, queue transfers to main thread.
Prevents Gunicorn worker blocking.
"""

import os
import queue
import time
import signal
import logging
import threading
import subprocess
from typing import Dict, Optional, Any, List, Generator

logger = logging.getLogger(__name__)

# Constants
COMPOSE_PATH = "/srv/docker"
STALE_TIMEOUT = 300  # 5 minutes
MAX_CONCURRENT_STREAMS = 10
QUEUE_TIMEOUT = 0.2  # Queue read timeout (seconds) - shorter for faster response


class LogProcessManager:
    """
    Singleton subprocess manager with thread-based reading.
    Reader thread handles blocking I/O, main thread stays non-blocking.
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

    def get_or_create_stream(
        self, session_id: str, service_name: str,
        tail: str = '300', since: str = ''
    ) -> Optional[Generator[str, None, None]]:
        """
        Create a new log stream for session.
        Returns a generator that yields log lines (non-blocking).
        """
        streams_to_stop: List[Dict[str, Any]] = []

        # PHASE 1: Quick lock - identify streams to stop
        with self._streams_lock:
            # Remove existing stream for this session
            existing = self._streams.pop(session_id, None)
            if existing:
                streams_to_stop.append(existing)

            # Enforce limit
            if len(self._streams) >= MAX_CONCURRENT_STREAMS:
                oldest_id = min(
                    self._streams.keys(),
                    key=lambda s: self._streams[s].get("created_at", 0)
                )
                oldest = self._streams.pop(oldest_id, None)
                if oldest:
                    streams_to_stop.append(oldest)
                    logger.info(f"Evicted stream: {oldest_id}")

        # PHASE 2: Stop old streams WITHOUT lock
        for stream in streams_to_stop:
            self._stop_stream_internal(stream)

        # PHASE 3: Create new process
        cmd = ['docker', 'compose', 'logs', '--tail', tail]
        if since:
            cmd.extend(['--since', since])
        cmd.extend(['-f', '-t', '--no-color', service_name])

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=COMPOSE_PATH,
                preexec_fn=os.setpgrp if os.name != 'nt' else None
            )

            # Create queue and stop event
            log_queue: queue.Queue = queue.Queue(maxsize=1000)
            stop_event = threading.Event()

            # Start reader thread
            reader_thread = threading.Thread(
                target=self._reader_worker,
                args=(process, log_queue, stop_event),
                daemon=True,
                name=f"log-reader-{session_id[:8]}"
            )
            reader_thread.start()

            # Create generator
            def log_generator() -> Generator[str, None, None]:
                """Non-blocking generator that reads from queue."""
                try:
                    while True:
                        try:
                            item = log_queue.get(timeout=QUEUE_TIMEOUT)
                            if item is None:  # EOF marker
                                break
                            yield item
                        except queue.Empty:
                            # Timeout - check if we should continue
                            if stop_event.is_set():
                                break
                            if process.poll() is not None:
                                # Process dead, drain queue
                                while True:
                                    try:
                                        item = log_queue.get_nowait()
                                        if item is None:
                                            break
                                        yield item
                                    except queue.Empty:
                                        break
                                break
                            # Otherwise continue waiting
                except GeneratorExit:
                    pass

            # PHASE 4: Quick lock - add to dict
            stream_info = {
                "process": process,
                "thread": reader_thread,
                "queue": log_queue,
                "stop_event": stop_event,
                "generator": log_generator,
                "service": service_name,
                "created_at": time.time(),
                "tail": tail,
                "since": since
            }

            with self._streams_lock:
                self._streams[session_id] = stream_info

            logger.debug(f"Started stream: {session_id} -> {service_name}")
            return log_generator()

        except Exception as e:
            logger.error(f"Failed to start stream: {e}")
            return None

    def _reader_worker(
        self,
        process: subprocess.Popen,
        log_queue: queue.Queue,
        stop_event: threading.Event
    ) -> None:
        """
        Reader thread - reads from subprocess stdout.
        Blocking reads are OK here - this is a separate thread.
        """
        try:
            for line in iter(process.stdout.readline, ''):
                if stop_event.is_set():
                    break
                line = line.rstrip('\n\r')
                if line:
                    try:
                        log_queue.put(line, timeout=0.1)
                    except queue.Full:
                        # Queue full, skip line
                        pass
        except Exception as e:
            logger.debug(f"Reader thread error: {e}")
        finally:
            # Signal EOF
            try:
                log_queue.put(None, timeout=0.1)
            except queue.Full:
                pass

    def stop_stream(self, session_id: str) -> bool:
        """Stop stream - non-blocking."""
        stream = None
        with self._streams_lock:
            stream = self._streams.pop(session_id, None)

        if stream:
            self._stop_stream_internal(stream)
            logger.debug(f"Stopped stream: {session_id}")
            return True
        return False

    def _stop_stream_internal(self, stream: Dict[str, Any]) -> None:
        """Stop a stream - signal thread and kill process."""
        # Signal thread to stop
        stop_event = stream.get("stop_event")
        if stop_event:
            stop_event.set()

        # Kill process and close stdout (unblocks readline)
        process = stream.get("process")
        if process:
            self._kill_process(process)

    def _kill_process(self, process: subprocess.Popen) -> None:
        """Kill process and close stdout to unblock readline."""
        if process is None:
            return
        try:
            # First close stdout - this unblocks readline() in reader thread
            try:
                if process.stdout:
                    process.stdout.close()
            except Exception:
                pass

            # Then kill the process
            if process.poll() is None:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    try:
                        process.kill()
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Kill error (ignored): {e}")

    def cleanup_stale_streams(self) -> int:
        """Cleanup old/dead streams."""
        now = time.time()
        stale: List[tuple] = []

        with self._streams_lock:
            for sid, stream in list(self._streams.items()):
                proc = stream.get("process")
                created = stream.get("created_at", 0)

                # Dead or old
                if proc is None or proc.poll() is not None or (now - created > STALE_TIMEOUT):
                    self._streams.pop(sid, None)
                    stale.append((sid, stream))

        # Stop without lock
        for sid, stream in stale:
            self._stop_stream_internal(stream)

        if stale:
            logger.info(f"Cleaned {len(stale)} stale streams")
        return len(stale)

    def get_active_count(self) -> int:
        with self._streams_lock:
            return len(self._streams)

    def get_stream_info(self) -> Dict[str, Any]:
        with self._streams_lock:
            return {
                sid: {
                    "service": s.get("service"),
                    "age": int(time.time() - s.get("created_at", 0)),
                    "alive": s.get("process").poll() is None if s.get("process") else False
                }
                for sid, s in self._streams.items()
            }

    def shutdown(self):
        """Kill all streams."""
        streams = []
        with self._streams_lock:
            streams = list(self._streams.values())
            self._streams.clear()

        for stream in streams:
            self._stop_stream_internal(stream)
        logger.info("All streams shut down")


# Singleton instance
log_process_manager = LogProcessManager()
