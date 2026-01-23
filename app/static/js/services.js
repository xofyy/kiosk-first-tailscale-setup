/**
 * Services Page JavaScript
 * Docker container management and log streaming
 */
'use strict';

// =============================================================================
// Log Buffer Configuration
// =============================================================================

const LOG_CONFIG = {
    MAX_LINES: 1000,        // Maximum lines in DOM
    MAX_LINE_LENGTH: 500,   // Truncate lines longer than this
    UPDATE_INTERVAL: 100,   // Batch update interval (ms)
    TRUNCATE_SUFFIX: '...'  // Suffix for truncated lines
};

// =============================================================================
// DOM Elements (cached for performance)
// =============================================================================

let frameContainer = null;
let serviceFrame = null;
let frameTitle = null;
let frameLoading = null;
let servicesList = null;
let logModal = null;
let logContent = null;
let logStatus = null;
let logAutoScroll = null;

// SSE connection for logs
let logEventSource = null;
let currentLogService = null;

// Log buffer state (for throttled updates)
let logBuffer = [];
let logLines = [];
let logUpdateTimer = null;

// Single session ID per page - server auto-kills old process when same session requests new service
const PAGE_LOG_SESSION_ID = 'log_' + Date.now() + '_' + Math.random().toString(36).substring(2, 11);

function initElements() {
    frameContainer = document.getElementById('frame-container');
    serviceFrame = document.getElementById('service-frame');
    frameTitle = document.getElementById('frame-title');
    frameLoading = document.getElementById('frame-loading');
    servicesList = document.getElementById('services-list');
    logModal = document.getElementById('log-modal');
    logContent = document.getElementById('log-content');
    logStatus = document.getElementById('log-status');
    logAutoScroll = document.getElementById('log-auto-scroll');
}

// =============================================================================
// Container Actions
// =============================================================================

async function containerAction(serviceName, action) {
    const card = document.querySelector(`[data-service="${serviceName}"]`);
    if (card) {
        card.classList.add('loading');
    }

    try {
        const result = await api.post(`/docker/containers/${serviceName}/${action}`);

        if (result.success) {
            showToast(`${action.charAt(0).toUpperCase() + action.slice(1)} successful`, 'success');
            // Refresh page after a short delay to update UI
            setTimeout(() => location.reload(), 1500);
        } else {
            showToast(result.error || 'Action failed', 'error');
            if (card) {
                card.classList.remove('loading');
            }
        }
    } catch (error) {
        showToast('Action failed', 'error');
        console.error('Container action error:', error);
        if (card) {
            card.classList.remove('loading');
        }
    }
}

async function refreshContainerStatus(serviceName) {
    try {
        const data = await api.get(`/docker/containers/${serviceName}/status`);
        if (data.success) {
            updateCardStatus(serviceName, data.status);
        }
    } catch (error) {
        console.error('Status refresh error:', error);
    }
}

function updateCardStatus(serviceName, status) {
    const card = document.querySelector(`[data-service="${serviceName}"]`);
    if (!card) return;

    // Remove old status classes
    card.classList.remove('running', 'stopped', 'restarting', 'exited', 'created', 'paused', 'dead', 'not_found', 'unknown');
    card.classList.add(status);

    // Update badge
    const badge = card.querySelector('.service-badge');
    if (badge) {
        badge.className = `service-badge ${status}`;
        badge.innerHTML = `<span class="dot"></span>${status.charAt(0).toUpperCase() + status.slice(1)}`;
    }
}

// =============================================================================
// Log Viewer (SSE Streaming)
// =============================================================================

/**
 * Process a log line: trim and truncate if too long.
 * Returns null for empty lines.
 */
function processLogLine(line) {
    if (!line || !line.trim()) return null;

    if (line.length > LOG_CONFIG.MAX_LINE_LENGTH) {
        return line.substring(0, LOG_CONFIG.MAX_LINE_LENGTH) + LOG_CONFIG.TRUNCATE_SUFFIX;
    }
    return line;
}

/**
 * Add a line to the buffer and schedule an update.
 */
function addToLogBuffer(line) {
    const processed = processLogLine(line);
    if (processed) {
        logBuffer.push(processed);
        scheduleLogUpdate();
    }
}

/**
 * Schedule a throttled DOM update.
 * Only one timer runs at a time.
 */
function scheduleLogUpdate() {
    if (logUpdateTimer) return;

    logUpdateTimer = setTimeout(() => {
        flushLogBuffer();
        logUpdateTimer = null;
    }, LOG_CONFIG.UPDATE_INTERVAL);
}

/**
 * Flush buffer to DOM with max line limit.
 */
function flushLogBuffer() {
    if (!logContent || logBuffer.length === 0) return;

    // Add buffered lines
    logLines.push(...logBuffer);
    logBuffer = [];

    // Enforce max line limit (keep recent lines)
    if (logLines.length > LOG_CONFIG.MAX_LINES) {
        logLines = logLines.slice(-LOG_CONFIG.MAX_LINES);
    }

    // Single DOM update
    logContent.textContent = logLines.join('\n');

    // Auto-scroll if enabled
    if (logAutoScroll?.checked) {
        const modalBody = logContent.parentElement;
        if (modalBody) {
            modalBody.scrollTop = modalBody.scrollHeight;
        }
    }
}

function openLogs(serviceName, displayName) {
    initElements();
    if (!logModal || !logContent) return;

    currentLogService = serviceName;

    // Update title
    const titleEl = document.getElementById('log-modal-title');
    if (titleEl) {
        titleEl.textContent = `${displayName || serviceName} Logs`;
    }

    // Reset buffers and clear previous content
    logBuffer = [];
    logLines = [];
    if (logUpdateTimer) {
        clearTimeout(logUpdateTimer);
        logUpdateTimer = null;
    }
    logContent.textContent = '';
    if (logStatus) logStatus.textContent = 'Connecting...';

    // Show modal
    logModal.classList.add('visible');

    // Start SSE connection
    startLogStream(serviceName);
}

function closeLogs() {
    initElements();

    // Stop SSE connection
    stopLogStream();

    // Cleanup timer and buffers
    if (logUpdateTimer) {
        clearTimeout(logUpdateTimer);
        logUpdateTimer = null;
    }
    logBuffer = [];
    logLines = [];

    // Hide modal
    if (logModal) {
        logModal.classList.remove('visible');
    }

    currentLogService = null;
}

function startLogStream(serviceName) {
    // Close existing connection if any
    stopLogStream();

    // Use single session ID - server auto-kills old process for same session
    const url = `/api/docker/containers/${serviceName}/logs?session_id=${PAGE_LOG_SESSION_ID}&tail=200`;
    logEventSource = new EventSource(url);

    logEventSource.onopen = () => {
        if (logStatus) logStatus.textContent = 'Connected - Streaming';
    };

    logEventSource.onmessage = (event) => {
        if (!logContent) return;
        addToLogBuffer(event.data);
    };

    logEventSource.onerror = (error) => {
        if (logStatus) logStatus.textContent = 'Connection error - Retrying...';
        console.error('SSE error:', error);
    };
}

function stopLogStream() {
    if (logEventSource) {
        logEventSource.close();
        logEventSource = null;
    }
}

// =============================================================================
// Service Frame (iframe) Management
// =============================================================================

function getFrameElements() {
    if (!frameContainer) {
        initElements();
    }
    return { frameContainer, serviceFrame, frameTitle, frameLoading, servicesList };
}

function openService(port, path, title) {
    const { frameContainer, serviceFrame, frameTitle, frameLoading, servicesList } = getFrameElements();
    if (!frameContainer || !serviceFrame) return;

    // Hide services list, show frame
    if (servicesList) servicesList.classList.add('hidden');

    if (frameTitle) frameTitle.textContent = title;
    if (frameLoading) frameLoading.classList.add('visible');
    serviceFrame.style.opacity = '0';

    serviceFrame.onload = function() {
        if (frameLoading) frameLoading.classList.remove('visible');
        serviceFrame.style.opacity = '1';
    };

    const directUrl = `http://${window.location.hostname}:${port}${path}`;
    serviceFrame.src = directUrl;
    frameContainer.classList.add('visible');
}

function closeFrame() {
    const { frameContainer, serviceFrame, frameLoading, servicesList } = getFrameElements();
    if (!frameContainer) return;

    // Hide frame, show services list
    frameContainer.classList.remove('visible');
    if (frameLoading) frameLoading.classList.remove('visible');
    if (serviceFrame) serviceFrame.src = '';

    if (servicesList) servicesList.classList.remove('hidden');
}

// =============================================================================
// Keyboard Shortcuts
// =============================================================================

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        // Close log modal if open
        if (logModal?.classList.contains('visible')) {
            closeLogs();
        }
        // Close iframe if open
        else if (frameContainer?.classList.contains('visible')) {
            closeFrame();
        }
    }
});

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', initElements);

// Clean up on page unload - notify server to kill subprocess
window.addEventListener('beforeunload', () => {
    stopLogStream();
    // Send cleanup request (sendBeacon reliable even on page close)
    const blob = new Blob([JSON.stringify({ session_id: PAGE_LOG_SESSION_ID })], {
        type: 'application/json'
    });
    navigator.sendBeacon('/api/docker/containers/logs/stop', blob);
});
