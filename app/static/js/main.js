/**
 * ACO Maintenance Panel - Main JavaScript
 */

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
    statusDot: null,
    statusText: null,
    connInternet: null,
    connDns: null,
    connIp: null,
    connTailscale: null,
    _initialized: false
};

function initDomCache() {
    if (domCache._initialized) return;
    domCache.statusDot = document.querySelector('.status-dot');
    domCache.statusText = document.querySelector('.status-text');
    domCache.connInternet = document.getElementById('conn-internet');
    domCache.connDns = document.getElementById('conn-dns');
    domCache.connIp = document.getElementById('conn-ip');
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

        // Update header status dot
        if (domCache.statusDot && domCache.statusText) {
            if (data.connected === null) {
                // Cache not yet populated - updating in background
                domCache.statusDot.classList.remove('online', 'offline');
                domCache.statusText.textContent = 'Checking...';
            } else if (data.connected) {
                domCache.statusDot.classList.add('online');
                domCache.statusDot.classList.remove('offline');
                domCache.statusText.textContent = data.ip || 'Connected';
            } else {
                domCache.statusDot.classList.add('offline');
                domCache.statusDot.classList.remove('online');
                domCache.statusText.textContent = 'No Connection';
            }
        }

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

        // Update IP address
        if (domCache.connIp) {
            if (data.ip === null) {
                domCache.connIp.textContent = 'Checking...';
            } else {
                domCache.connIp.textContent = data.ip || 'N/A';
            }
            // Update IP mode indicator if function exists (defined in home.html)
            if (typeof updateIpModeIndicator === 'function') {
                updateIpModeIndicator();
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

    if (domCache.statusDot && domCache.statusText) {
        domCache.statusDot.classList.add('offline');
        domCache.statusDot.classList.remove('online');
        domCache.statusText.textContent = 'Offline';
    }

    if (domCache.connInternet) {
        domCache.connInternet.innerHTML = '<span class="status-badge error">Offline</span>';
    }
}

// =============================================================================
// Form Helpers
// =============================================================================

function getFormData(form) {
    const formData = new FormData(form);
    const data = {};
    
    for (const [key, value] of formData.entries()) {
        // Handle array values (comma-separated)
        if (value.includes(',')) {
            data[key] = value.split(',').map(v => v.trim());
        } else {
            // Convert numbers
            if (!isNaN(value) && value !== '') {
                data[key] = Number(value);
            } else {
                data[key] = value;
            }
        }
    }
    
    return data;
}

// =============================================================================
// RVM ID Form
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const rvmIdForm = document.getElementById('rvm-id-form');

    if (rvmIdForm) {
        rvmIdForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const input = rvmIdForm.querySelector('input[name="rvm_id"]');
            const rvmId = input.value.toUpperCase().trim();

            if (!rvmId) {
                showToast('RVM ID required', 'error');
                return;
            }

            try {
                const result = await api.post('/rvm-id', {
                    'rvm_id': rvmId
                });

                if (result.success) {
                    showToast('RVM ID saved: ' + result.rvm_id, 'success');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast(result.error || 'Error occurred', 'error');
                }
            } catch (error) {
                showToast('Save error', 'error');
            }
        });
    }
});

// =============================================================================
// Temporary IP Form
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const tempIpForm = document.getElementById('temp-ip-form');

    if (tempIpForm) {
        tempIpForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const data = getFormData(tempIpForm);

            if (!data.ip || !data.gateway) {
                showToast('IP and Gateway required', 'error');
                return;
            }

            try {
                const result = await api.post('/network/temporary-ip', data);

                if (result.success) {
                    showToast('IP set', 'success');
                    setTimeout(() => location.reload(), 2000);
                } else {
                    showToast(result.error || 'Error occurred', 'error');
                }
            } catch (error) {
                showToast('IP setting error', 'error');
            }
        });
    }

    // DHCP Reset Button Handler
    const dhcpResetBtn = document.getElementById('dhcp-reset-btn');
    if (dhcpResetBtn) {
        dhcpResetBtn.addEventListener('click', async () => {
            const interfaceSelect = document.querySelector('#temp-ip-form select[name="interface"]');
            const iface = interfaceSelect ? interfaceSelect.value : 'eth0';

            if (!confirm('Are you sure you want to reset to DHCP?\n\nThis will remove current IP settings and get a new IP from DHCP.')) {
                return;
            }

            dhcpResetBtn.disabled = true;
            dhcpResetBtn.textContent = 'Waiting...';

            try {
                const result = await api.post('/network/reset-dhcp', { interface: iface });

                if (result.success) {
                    showToast('DHCP enabled, page refreshing...', 'success');
                    setTimeout(() => location.reload(), 3000);
                } else {
                    showToast(result.error || 'DHCP error', 'error');
                    dhcpResetBtn.disabled = false;
                    dhcpResetBtn.textContent = 'Reset to DHCP';
                }
            } catch (error) {
                showToast('DHCP error', 'error');
                dhcpResetBtn.disabled = false;
                dhcpResetBtn.textContent = 'Reset to DHCP';
            }
        });
    }
});

// =============================================================================
// Page Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Only check if online
    if (navigator.onLine) {
        checkInternetStatus();
    } else {
        updateOfflineUI();
    }

    // Periodic check - only runs when online (every 3 seconds)
    setInterval(() => {
        if (navigator.onLine) {
            checkInternetStatus();
        }
    }, 3000);
});

// Online/offline event listeners - anında tepki
window.addEventListener('online', () => {
    console.log('Network: Online');
    checkInternetStatus();
});

window.addEventListener('offline', () => {
    console.log('Network: Offline');
    updateOfflineUI();
});
