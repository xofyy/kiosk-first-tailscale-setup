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
    MAX_LINE_LENGTH: 5000,  // Truncate lines longer than this (5000 for mechatronic_controller)
    UPDATE_INTERVAL: 100,   // Batch update interval (ms)
    TRUNCATE_SUFFIX: '...'  // Suffix for truncated lines
};

// =============================================================================
// Service Icons (Inline SVG - No CDN dependency)
// =============================================================================

const SERVICE_ICONS = {
    'settings': '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    'scan-line': '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
    'printer': '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/>',
    'video': '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
    'smartphone': '<rect width="14" height="20" x="5" y="2" rx="2" ry="2"/><path d="M12 18h.01"/>',
    'cloud': '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
    'search': '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    'key': '<path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4"/><path d="m21 2-9.6 9.6"/><circle cx="7.5" cy="15.5" r="5.5"/>',
    'coins': '<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/><path d="m16.71 13.88.7.71-2.82 2.82"/>',
    'ruler': '<path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z"/><path d="m14.5 12.5 2-2"/><path d="m11.5 9.5 2-2"/><path d="m8.5 6.5 2-2"/><path d="m17.5 15.5 2-2"/>',
    'table-2': '<path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18"/>',
    'database': '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
    'server': '<rect width="20" height="8" x="2" y="2" rx="2" ry="2"/><rect width="20" height="8" x="2" y="14" rx="2" ry="2"/><line x1="6" x2="6.01" y1="6" y2="6"/><line x1="6" x2="6.01" y1="18" y2="18"/>',
    'box': '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'
};

function renderServiceIcons() {
    document.querySelectorAll('.service-icon[data-icon]').forEach(el => {
        const iconName = el.getAttribute('data-icon');
        const iconPath = SERVICE_ICONS[iconName] || SERVICE_ICONS['box'];
        el.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${iconPath}</svg>`;
    });
}

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
let logFilterLines = null;
let logFilterSince = null;

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
    logFilterLines = document.getElementById('log-filter-lines');
    logFilterSince = document.getElementById('log-filter-since');
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

    // Reset filters to defaults
    if (logFilterLines) logFilterLines.value = '300';
    if (logFilterSince) logFilterSince.value = '';

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

    // Build URL with filter parameters
    const filters = getLogFilters();
    const params = new URLSearchParams({
        session_id: PAGE_LOG_SESSION_ID,
        tail: filters.tail
    });
    if (filters.since) {
        params.append('since', filters.since);
    }
    const url = `/api/docker/containers/${serviceName}/logs?${params.toString()}`;
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

/**
 * Get current filter values.
 */
function getLogFilters() {
    return {
        tail: logFilterLines?.value || '300',
        since: logFilterSince?.value || ''
    };
}

/**
 * Handle filter change - restart stream with new params.
 */
function onLogFilterChange() {
    if (!currentLogService) return;

    // Clear existing logs and buffers
    logBuffer = [];
    logLines = [];
    if (logUpdateTimer) {
        clearTimeout(logUpdateTimer);
        logUpdateTimer = null;
    }
    if (logContent) {
        logContent.textContent = '';
    }
    if (logStatus) {
        logStatus.textContent = 'Reloading...';
    }

    // Restart stream with new filters
    startLogStream(currentLogService);
}

/**
 * Setup filter event listeners.
 */
function setupLogFilterListeners() {
    if (logFilterLines) {
        logFilterLines.addEventListener('change', onLogFilterChange);
    }
    if (logFilterSince) {
        logFilterSince.addEventListener('change', onLogFilterChange);
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

document.addEventListener('DOMContentLoaded', () => {
    initElements();
    renderServiceIcons();
    setupLogFilterListeners();
});

// Clean up on page unload - notify server to kill subprocess
window.addEventListener('beforeunload', () => {
    stopLogStream();
    // Send cleanup request (sendBeacon reliable even on page close)
    const blob = new Blob([JSON.stringify({ session_id: PAGE_LOG_SESSION_ID })], {
        type: 'application/json'
    });
    navigator.sendBeacon('/api/docker/containers/logs/stop', blob);
});
