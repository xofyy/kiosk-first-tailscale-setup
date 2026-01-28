/**
 * ACO Maintenance Panel - Main JavaScript
 */
'use strict';

// =============================================================================
// API Helper
// =============================================================================

const api = {
    async get(endpoint, timeout = 5000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        
        try {
            const response = await fetch(`/api${endpoint}`, {
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            if (!response.ok) {
                return { success: false, error: `HTTP ${response.status}` };
            }
            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                console.warn('API GET timeout:', endpoint);
            } else {
                console.error('API GET error:', error);
            }
            throw error;
        }
    },
    
    async post(endpoint, data = {}, timeout = 30000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        
        try {
            const response = await fetch(`/api${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data),
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            if (!response.ok) {
                return { success: false, error: `HTTP ${response.status}` };
            }
            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                console.warn('API POST timeout:', endpoint);
            } else {
                console.error('API POST error:', error);
            }
            throw error;
        }
    }
};

// =============================================================================
// Toast Notifications
// =============================================================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// =============================================================================
// Internet Status Check
// =============================================================================

let isCheckingInternet = false; // Prevent overlap

// Cached DOM elements (populated on first use)
const domCache = {
    connInternet: null,
    connDns: null,
    connTailscale: null,
    _initialized: false
};

function initDomCache() {
    if (domCache._initialized) return;
    domCache.connInternet = document.getElementById('conn-internet');
    domCache.connDns = document.getElementById('conn-dns');
    domCache.connTailscale = document.getElementById('conn-tailscale');
    domCache._initialized = true;
}

async function checkInternetStatus() {
    // Skip if already checking or browser is offline
    if (isCheckingInternet || !navigator.onLine) {
        updateOfflineUI();
        return;
    }

    isCheckingInternet = true;
    initDomCache();

    try {
        const data = await api.get('/system/internet', 3000); // 3 second timeout

        // Update connection grid badges
        if (domCache.connInternet) {
            if (data.connected === null) {
                domCache.connInternet.innerHTML = '<span class="status-badge skeleton">Checking...</span>';
            } else {
                domCache.connInternet.innerHTML = data.connected
                    ? '<span class="status-badge success">Connected</span>'
                    : '<span class="status-badge error">Not Connected</span>';
            }
        }

        if (domCache.connDns) {
            if (data.dns_working === null) {
                domCache.connDns.innerHTML = '<span class="status-badge skeleton">Checking...</span>';
            } else {
                domCache.connDns.innerHTML = data.dns_working
                    ? '<span class="status-badge success">Working</span>'
                    : '<span class="status-badge error">Error</span>';
            }
        }

        // Update Tailscale IP
        if (domCache.connTailscale) {
            if (data.tailscale_ip === null) {
                domCache.connTailscale.textContent = 'Checking...';
            } else {
                domCache.connTailscale.textContent = data.tailscale_ip || 'Not Connected';
            }
        }

    } catch (error) {
        updateOfflineUI();
        console.warn('Internet check failed:', error.message || error);
    } finally {
        isCheckingInternet = false;
    }
}

function updateOfflineUI() {
    initDomCache();

    if (domCache.connInternet) {
        domCache.connInternet.innerHTML = '<span class="status-badge error">Offline</span>';
    }
}

// =============================================================================
// Page Initialization
// =============================================================================

// Internet check interval management
let internetCheckInterval = null;

function startInternetCheck() {
    if (internetCheckInterval) return;
    internetCheckInterval = setInterval(() => {
        if (navigator.onLine) {
            checkInternetStatus();
        }
    }, 3000);
}

function stopInternetCheck() {
    if (internetCheckInterval) {
        clearInterval(internetCheckInterval);
        internetCheckInterval = null;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Only check if online
    if (navigator.onLine) {
        checkInternetStatus();
    } else {
        updateOfflineUI();
    }

    // Start periodic check
    startInternetCheck();
});

// Stop/resume polling based on page visibility
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopInternetCheck();
    } else {
        startInternetCheck();
        if (navigator.onLine) {
            checkInternetStatus();
        }
    }
});

// Online/offline event listeners - anında tepki
window.addEventListener('online', () => {
    checkInternetStatus();
});

window.addEventListener('offline', () => {
    updateOfflineUI();
});

// =============================================================================
// Smart Refresh (iframe support)
// =============================================================================

function handleRefresh() {
    const frameContainer = document.getElementById('frame-container');
    const serviceFrame = document.getElementById('service-frame');

    // If iframe is visible and has content, refresh iframe
    if (frameContainer?.classList.contains('visible') && serviceFrame?.src && serviceFrame.src !== 'about:blank' && serviceFrame.src !== '') {
        serviceFrame.src = serviceFrame.src;
    } else {
        // Otherwise reload page
        location.reload();
    }
}
