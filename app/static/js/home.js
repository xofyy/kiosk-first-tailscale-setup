/**
 * Home Page JavaScript
 * Network interfaces, RVM ID, system controls, component status polling
 */

// =============================================================================
// Network Interfaces Management
// =============================================================================

let interfacesData = null;
let defaultIpConfigs = null;
let interfacePollingInterval = null;

async function loadNetworkInterfaces() {
    const container = document.getElementById('interface-cards');
    if (!container) return;

    try {
        const response = await fetch('/api/network/interfaces');
        const data = await response.json();

        interfacesData = data.interfaces;
        defaultIpConfigs = data.default_ips;

        if (!interfacesData || interfacesData.length === 0) {
            container.innerHTML = '<p class="text-muted">No network interfaces found.</p>';
            return;
        }

        container.innerHTML = interfacesData.map(iface => renderInterfaceCard(iface)).join('');
    } catch (error) {
        console.error('Failed to load interfaces:', error);
        container.innerHTML = '<p class="text-muted">Failed to load network interfaces.</p>';
    }
}

function startInterfacePolling() {
    if (interfacePollingInterval) return;
    interfacePollingInterval = setInterval(() => {
        if (!document.hidden) loadNetworkInterfaces();
    }, 3000);
}

function stopInterfacePolling() {
    if (interfacePollingInterval) {
        clearInterval(interfacePollingInterval);
        interfacePollingInterval = null;
    }
}

function renderInterfaceCard(iface) {
    const typeLabel = iface.type === 'onboard' ? 'Onboard' : 'PCIe Add-on';
    const typeClass = iface.type === 'onboard' ? 'type-onboard' : 'type-pcie';
    const defaultConfig = defaultIpConfigs[iface.type] || defaultIpConfigs.onboard;
    const defaultIpText = `${defaultConfig.ip} / ${defaultConfig.gateway}`;

    return `
        <div class="interface-card ${typeClass}" data-interface="${iface.name}" data-type="${iface.type}">
            <div class="interface-header">
                <span class="interface-icon">
                    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/>
                        <line x1="1" y1="10" x2="23" y2="10"/>
                    </svg>
                </span>
                <div class="interface-info">
                    <span class="interface-name">${iface.name}</span>
                    <span class="interface-type">${typeLabel}</span>
                </div>
            </div>

            <div class="interface-status">
                <div class="interface-ip">
                    <span class="ip-label">Current IP:</span>
                    <span class="ip-value" id="ip-${iface.name}">${iface.ip || 'No IP'}</span>
                </div>
                <div class="interface-state ${iface.state === 'up' ? 'state-up' : 'state-down'}">
                    <span class="state-dot"></span>
                    <span>${iface.state === 'up' ? 'Connected' : 'Disconnected'}</span>
                </div>
            </div>

            <div class="interface-buttons">
                <button class="btn btn-sm btn-ip-default" onclick="setInterfaceIP('${iface.name}', '${iface.type}', 'default')">
                    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                    </svg>
                    <span>Default IP</span>
                    <small>${defaultIpText}</small>
                </button>
                <button class="btn btn-sm btn-ip-dhcp" onclick="setInterfaceIP('${iface.name}', '${iface.type}', 'dhcp')">
                    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                    </svg>
                    <span>DHCP</span>
                    <small>Automatic</small>
                </button>
            </div>
        </div>
    `;
}

async function setInterfaceIP(interfaceName, interfaceType, mode) {
    const card = document.querySelector(`[data-interface="${interfaceName}"]`);
    const buttons = card?.querySelectorAll('button');
    const ipDisplay = document.getElementById(`ip-${interfaceName}`);

    // Disable buttons
    buttons?.forEach(btn => btn.disabled = true);
    if (ipDisplay) ipDisplay.textContent = 'Setting...';

    try {
        const response = await fetch('/api/network/set-ip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                interface: interfaceName,
                interface_type: interfaceType,
                mode: mode
            })
        });

        const data = await response.json();

        if (data.success) {
            const modeText = mode === 'default' ? 'Default IP set' : 'DHCP enabled';
            showToast(`${interfaceName}: ${modeText}`, 'success');

            // Update IP display
            if (ipDisplay) {
                if (mode === 'default' && defaultIpConfigs) {
                    ipDisplay.textContent = defaultIpConfigs[interfaceType]?.ip || 'Set';
                } else {
                    ipDisplay.textContent = 'DHCP...';
                }
            }

            // Refresh interface status after a delay
            setTimeout(loadNetworkInterfaces, 2000);
        } else {
            showToast(data.error || 'Failed to set IP', 'error');
            if (ipDisplay) ipDisplay.textContent = 'Error';
        }
    } catch (error) {
        showToast('Connection error', 'error');
        if (ipDisplay) ipDisplay.textContent = 'Error';
    } finally {
        buttons?.forEach(btn => btn.disabled = false);
    }
}

// Backward compatibility for updateIpModeIndicator (called from main.js)
function updateIpModeIndicator() {
    // No longer needed with new interface cards, but keep for compatibility
}

// =============================================================================
// RVM ID Management
// =============================================================================

function initRvmIdForm() {
    const rvmIdForm = document.getElementById('rvm-id-form');
    if (rvmIdForm) {
        rvmIdForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const input = rvmIdForm.querySelector('input[name="rvm_id"]');
            const rvm_id = input.value.toUpperCase().trim();

            if (!rvm_id) {
                showToast('RVM ID required', 'error');
                return;
            }

            try {
                const response = await fetch('/api/rvm-id', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ rvm_id })
                });

                const data = await response.json();

                if (data.success) {
                    showToast('RVM ID saved', 'success');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast(data.error || 'Error occurred', 'error');
                }
            } catch (error) {
                showToast('Connection error', 'error');
            }
        });
    }
}

function toggleRvmIdEdit(show) {
    const displayEl = document.getElementById('rvm-id-display');
    const editEl = document.getElementById('rvm-id-edit');
    if (!displayEl || !editEl) return;

    if (show) {
        displayEl.style.display = 'none';
        editEl.style.display = 'block';
        editEl.querySelector('input').focus();
    } else {
        displayEl.style.display = 'flex';
        editEl.style.display = 'none';
    }
}

function initRvmIdEditForm() {
    const rvmIdEditForm = document.getElementById('rvm-id-edit-form');
    if (rvmIdEditForm) {
        rvmIdEditForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const input = rvmIdEditForm.querySelector('input[name="rvm_id"]');
            const rvm_id = input.value.toUpperCase().trim();

            if (!rvm_id) {
                showToast('RVM ID required', 'error');
                return;
            }

            const btn = rvmIdEditForm.querySelector('button[type="submit"]');
            btn.disabled = true;
            btn.textContent = 'Saving...';

            try {
                const response = await fetch('/api/rvm-id', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ rvm_id })
                });

                const data = await response.json();

                if (data.success) {
                    showToast('RVM ID updated', 'success');
                    document.getElementById('rvm-id-value').textContent = rvm_id;
                    toggleRvmIdEdit(false);
                } else {
                    showToast(data.error || 'Error occurred', 'error');
                }
            } catch (error) {
                showToast('Connection error', 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Save';
            }
        });
    }
}

// =============================================================================
// System Controls
// =============================================================================

async function systemReboot() {
    if (!confirm('Are you sure you want to reboot the system?')) {
        return;
    }

    try {
        const response = await fetch('/api/system/reboot', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            showToast('System rebooting...', 'success');
        } else {
            showToast(data.error || 'Error occurred', 'error');
        }
    } catch (error) {
        showToast('Connection error', 'error');
    }
}

async function systemShutdown() {
    if (!confirm('Are you sure you want to shutdown the system?')) {
        return;
    }

    try {
        const response = await fetch('/api/system/shutdown', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            showToast('System shutting down...', 'success');
        } else {
            showToast(data.error || 'Error occurred', 'error');
        }
    } catch (error) {
        showToast('Connection error', 'error');
    }
}

// =============================================================================
// System Components Auto-Update (with DOM caching)
// =============================================================================

let componentPollingInterval = null;

// Cached component DOM elements
const componentCache = {
    docker: { card: null, status: null, detail: null },
    mongodb: { card: null, status: null, detail: null },
    tailscale: { card: null, status: null, detail: null },
    nvidia: { card: null, status: null, detail: null },
    _initialized: false
};

function initComponentCache() {
    if (componentCache._initialized) return;
    ['docker', 'mongodb', 'tailscale', 'nvidia'].forEach(name => {
        componentCache[name].card = document.getElementById(`component-${name}`);
        componentCache[name].status = document.getElementById(`component-${name}-status`);
        componentCache[name].detail = document.getElementById(`component-${name}-detail`);
    });
    componentCache._initialized = true;
}

// State definitions (constant - defined once)
const COMPONENT_STATES = {
    tailscale: {
        'connected': { dot: 'ok', text: 'Connected', cardClass: 'component-ok' },
        'disconnected': { dot: 'error', text: 'Disconnected', cardClass: 'component-error' },
        'not_enrolled': { dot: 'pending', text: 'Not Enrolled', cardClass: 'component-pending' },
        'not_installed': { dot: 'pending', text: 'Not Installed', cardClass: 'component-pending' }
    },
    nvidia: {
        'working': { dot: 'ok', text: 'Working', cardClass: 'component-ok' },
        'not_working': { dot: 'error', text: 'Not Working', cardClass: 'component-error' },
        'mok_pending': { dot: 'warning', text: 'MOK Pending', cardClass: 'component-warning' },
        'reboot_required': { dot: 'warning', text: 'Reboot Required', cardClass: 'component-warning' },
        'not_installed': { dot: 'pending', text: 'Not Installed', cardClass: 'component-pending' }
    }
};

async function updateComponentStatuses() {
    if (!navigator.onLine) return;
    initComponentCache();

    try {
        const response = await fetch('/api/system/components', { signal: AbortSignal.timeout(5000) });
        const data = await response.json();

        // Update Docker & MongoDB (simple ok/error states)
        updateSimpleComponent('docker', data.docker, data.docker.version ? `v${data.docker.version}` : '');
        updateSimpleComponent('mongodb', data.mongodb, data.mongodb.info || '');

        // Update Tailscale (multiple states)
        const tsState = COMPONENT_STATES.tailscale[data.tailscale.status] || COMPONENT_STATES.tailscale['not_enrolled'];
        updateComplexComponent('tailscale', tsState, data.tailscale.ip || '');

        // Update NVIDIA (multiple states)
        const nvState = COMPONENT_STATES.nvidia[data.nvidia.status] || COMPONENT_STATES.nvidia['not_installed'];
        updateComplexComponent('nvidia', nvState, data.nvidia.version ? `Driver ${data.nvidia.version}` : '');

    } catch (error) {
        console.warn('Component status update failed:', error.message || error);
    }
}

function updateSimpleComponent(name, data, detail) {
    const { card, status, detail: detailEl } = componentCache[name];
    if (!card || !status) return;

    const isOk = data.ok;
    const newCardClass = isOk ? 'component-ok' : 'component-error';

    // Use classList for minimal reflow
    card.classList.remove('component-ok', 'component-error', 'component-warning', 'component-pending');
    card.classList.add(newCardClass);

    status.innerHTML = `<span class="component-status-dot ${isOk ? 'ok' : 'error'}"></span><span>${isOk ? 'Running' : 'Stopped'}</span>`;
    if (detailEl) detailEl.textContent = detail;
}

function updateComplexComponent(name, state, detail) {
    const { card, status, detail: detailEl } = componentCache[name];
    if (!card || !status) return;

    // Use classList for minimal reflow
    card.classList.remove('component-ok', 'component-error', 'component-warning', 'component-pending');
    card.classList.add(state.cardClass);

    status.innerHTML = `<span class="component-status-dot ${state.dot}"></span><span>${state.text}</span>`;
    if (detailEl) detailEl.textContent = detail;
}

function startComponentPolling() {
    if (componentPollingInterval) return;
    componentPollingInterval = setInterval(() => {
        if (!document.hidden) updateComponentStatuses();
    }, 10000);
}

function stopComponentPolling() {
    if (componentPollingInterval) {
        clearInterval(componentPollingInterval);
        componentPollingInterval = null;
    }
}

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Network interfaces
    loadNetworkInterfaces();
    startInterfacePolling();

    // RVM ID forms
    initRvmIdForm();
    initRvmIdEditForm();

    // Component status polling
    startComponentPolling();
});

// Handle visibility changes
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopComponentPolling();
        stopInterfacePolling();
    } else {
        startComponentPolling();
        startInterfacePolling();
        updateComponentStatuses();
        loadNetworkInterfaces();
    }
});
