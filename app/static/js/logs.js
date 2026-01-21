/**
 * Logs Page JavaScript
 * Log viewing, auto-refresh, and module status polling
 */
'use strict';

// =============================================================================
// DOM Elements & Configuration
// =============================================================================

const container = document.getElementById('logs-container');
const logsContent = document.getElementById('logs-content');
const autoScroll = document.getElementById('auto-scroll');
const autoRefresh = document.getElementById('auto-refresh');
const logStatus = document.getElementById('log-status');
const lastUpdate = document.getElementById('last-update');

// Read configuration from data attributes
let currentModule = container?.dataset.module || '';
const fromInstall = container?.dataset.fromInstall === 'true';

// =============================================================================
// Log Display
// =============================================================================

// Scroll on page load
if (autoScroll?.checked && container) {
    container.scrollTop = container.scrollHeight;
}

// Change module
function changeModule(moduleName) {
    currentModule = moduleName;
    const url = moduleName ? `/logs?module=${moduleName}` : '/logs';
    window.location.href = url;
}

// Refresh logs (AJAX)
async function refreshLogs() {
    try {
        const url = currentModule
            ? `/api/modules/${currentModule}/logs?lines=200`
            : '/logs';

        if (currentModule) {
            // Get from API (JSON)
            const data = await api.get(`/modules/${currentModule}/logs?lines=200`);

            if (data.logs) {
                logsContent.textContent = data.logs.join('\n');
                logStatus.textContent = `${data.logs.length} lines shown`;
            }
        } else {
            // Get from HTML page
            const response = await fetch(url);
            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const newContent = doc.querySelector('.logs-content');

            if (newContent) {
                logsContent.textContent = newContent.textContent;
            }
        }

        // Scroll
        if (autoScroll?.checked && container) {
            container.scrollTop = container.scrollHeight;
        }

        // Update time
        const now = new Date();
        if (lastUpdate) {
            lastUpdate.textContent = `Last update: ${now.toLocaleTimeString('en-US')}`;
        }

    } catch (error) {
        console.error('Log refresh error:', error);
    }
}

// =============================================================================
// Auto Refresh
// =============================================================================

let refreshInterval = null;

function startAutoRefresh() {
    if (refreshInterval) return;
    refreshInterval = setInterval(() => {
        if (document.hidden) return;
        if (!autoRefresh?.checked) return;
        refreshLogs();
    }, 3000);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Checkbox event listener
autoRefresh?.addEventListener('change', (e) => {
    if (e.target.checked) {
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
});

// =============================================================================
// Module Status Polling (redirect when installation completes)
// =============================================================================

let statusInterval = null;

async function checkModuleStatus() {
    // Only check if viewing a specific module AND came from install page
    if (!currentModule || !fromInstall) return;

    try {
        const data = await api.get(`/modules/${currentModule}/status`);

        // If status is not 'installing', redirect to install page
        if (data.status && data.status !== 'installing') {
            // Stop polling
            stopStatusPolling();
            stopAutoRefresh();

            // Show toast if available
            if (typeof showToast === 'function') {
                const messages = {
                    'completed': `${currentModule} installation completed`,
                    'failed': `${currentModule} installation failed`,
                    'reboot_required': 'Reboot required',
                    'mok_pending': 'MOK enrollment required'
                };
                showToast(messages[data.status] || 'Installation finished',
                          data.status === 'completed' ? 'success' : 'warning');
            }

            // Redirect to install page after a short delay
            setTimeout(() => {
                window.location.href = '/install';
            }, 1500);
        }
    } catch (error) {
        console.warn('Status check error:', error);
    }
}

function startStatusPolling() {
    // Only poll if came from install page
    if (statusInterval || !currentModule || !fromInstall) return;
    statusInterval = setInterval(() => {
        if (document.hidden) return;
        checkModuleStatus();
    }, 3000);
    // Check immediately
    checkModuleStatus();
}

function stopStatusPolling() {
    if (statusInterval) {
        clearInterval(statusInterval);
        statusInterval = null;
    }
}

// =============================================================================
// Visibility Change Handlers
// =============================================================================

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
        stopStatusPolling();
    } else {
        if (autoRefresh?.checked) {
            startAutoRefresh();
            refreshLogs(); // Refresh immediately
        }
        if (currentModule && fromInstall) {
            startStatusPolling();
        }
    }
});

// =============================================================================
// Initialization
// =============================================================================

// Start auto refresh if checked
if (autoRefresh?.checked) {
    startAutoRefresh();
}

// Start status polling ONLY if redirected from install page
if (currentModule && fromInstall) {
    startStatusPolling();
}
