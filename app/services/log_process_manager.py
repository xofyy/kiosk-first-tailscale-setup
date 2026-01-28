"""
Log Process Manager - Subprocess Based (No Threading)
Simple and reliable subprocess management for log streaming.
"""

import os
import time
import signal
import logging
import threading
import subprocess
from typing import Dict, Optional, Any, List

logger = logging.getLogger(__name__)

# Constants
COMPOSE_PATH = "/srv/docker"
STALE_TIMEOUT = 300  # 5 minutes
MAX_CONCURRENT_STREAMS = 10


class LogProcessManager:
    """
    Singleton subprocess manager.
    Uses subprocess instead of Docker SDK for better control.
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
    ) -> Optional[subprocess.Popen]:
        """
        Create a new subprocess stream for session.
        """
        processes_to_kill: List[subprocess.Popen] = []

        # PHASE 1: Quick lock - identify processes to kill
        with self._streams_lock:
            # Remove existing stream for this session
            existing = self._streams.pop(session_id, None)
            if existing and existing.get("process"):
                processes_to_kill.append(existing["process"])

            # Enforce limit
            if len(self._streams) >= MAX_CONCURRENT_STREAMS:
                oldest_id = min(self._streams.keys(), key=lambda s: self._streams[s].get("created_at", 0))
                oldest = self._streams.pop(oldest_id, None)
                if oldest and oldest.get("process"):
                    processes_to_kill.append(oldest["process"])
                    logger.info(f"Evicted stream: {oldest_id}")

        # PHASE 2: Kill processes WITHOUT lock (fire and forget)
        for proc in processes_to_kill:
            self._kill_process_async(proc)

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
                # Don't create process group - allows clean kill
                preexec_fn=os.setpgrp if os.name != 'nt' else None
            )

            # PHASE 4: Quick lock - add to dict
            with self._streams_lock:
                self._streams[session_id] = {
                    "process": process,
                    "service": service_name,
                    "created_at": time.time(),
                    "tail": tail,
                    "since": since
                }

            logger.debug(f"Started stream: {session_id} -> {service_name}")
            return process

        except Exception as e:
            logger.error(f"Failed to start stream: {e}")
            return None

    def stop_stream(self, session_id: str) -> bool:
        """Stop stream - non-blocking."""
        process = None
        with self._streams_lock:
            stream = self._streams.pop(session_id, None)
            if stream:
                process = stream.get("process")

        if process:
            self._kill_process_async(process)
            logger.debug(f"Stopped stream: {session_id}")
            return True
        return False

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
                    stale.append((sid, proc))

        # Kill without lock
        for sid, proc in stale:
            if proc:
                self._kill_process_async(proc)

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
        procs = []
        with self._streams_lock:
            for s in self._streams.values():
                if s.get("process"):
                    procs.append(s["process"])
            self._streams.clear()

        for p in procs:
            self._kill_process_async(p)
        logger.info("All streams shut down")

    def _kill_process_async(self, process: subprocess.Popen) -> None:
        """
        Kill process immediately - no waiting.
        Uses SIGKILL for immediate termination.
        """
        if process is None:
            return
        try:
            if process.poll() is None:
                # Try to kill the process group (kills all children too)
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    # Fallback to just killing the process
                    process.kill()
        except Exception as e:
            logger.debug(f"Kill error (ignored): {e}")


# Singleton instance
log_process_manager = LogProcessManager()
