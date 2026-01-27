/**
 * Home Page JavaScript
 * Network interfaces, RVM ID, system controls, component status polling
 */
'use strict';

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
        const data = await api.get('/network/interfaces');

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
    const typeConfig = defaultIpConfigs[iface.type] || defaultIpConfigs.pcie;
    const staticIp = typeConfig.ip;

    // Mode badge configuration - UI labels based on interface type
    // Onboard: network→Network, dhcp→Direct
    // PCIe: direct→Network, dhcp→Direct
    const networkIcon = '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>';
    const directIcon = '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>';

    let mode;
    if (iface.type === 'onboard') {
        if (iface.mode === 'network') {
            mode = { label: 'Network', class: 'mode-network', icon: networkIcon };
        } else if (iface.mode === 'dhcp') {
            mode = { label: 'Direct', class: 'mode-direct', icon: directIcon };
        }
    } else {
        // PCIe
        if (iface.mode === 'direct') {
            mode = { label: 'Network', class: 'mode-network', icon: networkIcon };
        } else if (iface.mode === 'dhcp') {
            mode = { label: 'Direct', class: 'mode-direct', icon: directIcon };
        }
    }
    const modeBadgeHtml = mode ? `
        <div class="interface-mode-badge ${mode.class}">
            <svg class="icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                ${mode.icon}
            </svg>
            <span>${mode.label}</span>
        </div>
    ` : '';

    // Build buttons based on interface type
    let buttonsHtml = '';

    if (iface.type === 'onboard') {
        // Onboard: Network (static IP + gateway), Direct (DHCP/Auto)
        buttonsHtml = `
            <button class="btn btn-sm btn-ip-network" onclick="setInterfaceIP('${iface.name}', '${iface.type}', 'network')">
                <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                </svg>
                <span>Network</span>
                <small>${staticIp} + GW</small>
            </button>
            <button class="btn btn-sm btn-ip-direct" onclick="setInterfaceIP('${iface.name}', '${iface.type}', 'dhcp')">
                <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                </svg>
                <span>Direct</span>
                <small>Auto</small>
            </button>
        `;
    } else {
        // PCIe: Network (static IP, no gateway), Direct (DHCP/Auto)
        buttonsHtml = `
            <button class="btn btn-sm btn-ip-network" onclick="setInterfaceIP('${iface.name}', '${iface.type}', 'direct')">
                <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                </svg>
                <span>Network</span>
                <small>${staticIp}</small>
            </button>
            <button class="btn btn-sm btn-ip-direct" onclick="setInterfaceIP('${iface.name}', '${iface.type}', 'dhcp')">
                <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                </svg>
                <span>Direct</span>
                <small>Auto</small>
            </button>
        `;
    }

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
                ${modeBadgeHtml}
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
                ${buttonsHtml}
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
        const data = await api.post('/network/set-ip', {
            interface: interfaceName,
            interface_type: interfaceType,
            mode: mode
        });

        if (data.success) {
            // Toast message based on UI label (not backend mode)
            // Onboard: network→Network, dhcp→Direct
            // PCIe: direct→Network, dhcp→Direct
            let toastText;
            if (interfaceType === 'onboard') {
                toastText = mode === 'network' ? 'Network IP set' : 'Direct mode set';
            } else {
                toastText = mode === 'direct' ? 'Network IP set' : 'Direct mode set';
            }
            showToast(`${interfaceName}: ${toastText}`, 'success');

            // Update IP display
            if (ipDisplay) {
                if ((mode === 'network' || mode === 'direct') && defaultIpConfigs) {
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
                const data = await api.post('/rvm-id', { rvm_id });

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
                const data = await api.post('/rvm-id', { rvm_id });

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
        const data = await api.post('/system/reboot');

        if (data.success) {
            showToast('System rebooting...', 'success');
        } else {
            showToast(data.error || 'Error occurred', 'error');
        }
    } catch (error) {
        showToast('Connection error', 'error');
    }
}

// =============================================================================
// System Clock & Settings
// =============================================================================

let clockIntervalId = null;
let currentTimezone = null;
let currentKeyboardLayout = null;

// -----------------------------------------------------------------------------
// Live System Clock
// -----------------------------------------------------------------------------

function startClock() {
    updateClockDisplay();
    if (clockIntervalId) clearInterval(clockIntervalId);
    clockIntervalId = setInterval(updateClockDisplay, 1000);
}

function stopClock() {
    if (clockIntervalId) {
        clearInterval(clockIntervalId);
        clockIntervalId = null;
    }
}

function updateClockDisplay() {
    const el = document.getElementById('clock-datetime');
    if (!el) return;

    const now = new Date();
    const options = {
        timeZone: currentTimezone || undefined,
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    };

    try {
        const formatter = new Intl.DateTimeFormat('tr-TR', options);
        const parts = formatter.formatToParts(now);

        let day = '', month = '', year = '', hour = '', minute = '', second = '';
        for (const part of parts) {
            switch (part.type) {
                case 'day': day = part.value; break;
                case 'month': month = part.value; break;
                case 'year': year = part.value; break;
                case 'hour': hour = part.value; break;
                case 'minute': minute = part.value; break;
                case 'second': second = part.value; break;
            }
        }

        el.textContent = `${day}.${month}.${year} ${hour}:${minute}:${second}`;
    } catch (e) {
        const pad = n => String(n).padStart(2, '0');
        el.textContent = `${pad(now.getDate())}.${pad(now.getMonth() + 1)}.${now.getFullYear()} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    }
}

// -----------------------------------------------------------------------------
// Timezone Management
// -----------------------------------------------------------------------------

async function loadTimezoneData() {
    const select = document.getElementById('timezone-select');
    const tzDisplay = document.getElementById('clock-timezone');
    if (!select) return;

    try {
        const data = await api.get('/system/timezone', 10000);

        currentTimezone = data.timezone || 'UTC';

        if (tzDisplay) {
            tzDisplay.textContent = `(${currentTimezone})`;
        }

        // Populate select with optgroups by region
        if (data.timezones && data.timezones.length > 0) {
            const groups = {};
            data.timezones.forEach(tz => {
                const slashIndex = tz.indexOf('/');
                let region, city;
                if (slashIndex !== -1) {
                    region = tz.substring(0, slashIndex);
                    city = tz.substring(slashIndex + 1).replace(/_/g, ' ');
                } else {
                    region = 'Other';
                    city = tz;
                }
                if (!groups[region]) groups[region] = [];
                groups[region].push({ value: tz, label: city });
            });

            select.innerHTML = '';
            const sortedRegions = Object.keys(groups).sort();
            for (const region of sortedRegions) {
                const optgroup = document.createElement('optgroup');
                optgroup.label = region;
                groups[region].forEach(item => {
                    const option = document.createElement('option');
                    option.value = item.value;
                    option.textContent = item.label;
                    if (item.value === currentTimezone) {
                        option.selected = true;
                    }
                    optgroup.appendChild(option);
                });
                select.appendChild(optgroup);
            }
        }

        select.disabled = false;
        startClock();

    } catch (error) {
        console.error('Failed to load timezone data:', error);
        select.innerHTML = '<option value="">Error</option>';
        startClock();
    }
}

async function changeTimezone(timezone) {
    if (!timezone) return;

    const select = document.getElementById('timezone-select');
    const tzDisplay = document.getElementById('clock-timezone');

    if (select) select.disabled = true;

    try {
        const data = await api.post('/system/timezone', { timezone });

        if (data.success) {
            currentTimezone = timezone;
            if (tzDisplay) {
                tzDisplay.textContent = `(${timezone})`;
            }
            showToast(`Timezone: ${timezone}`, 'success');
        } else {
            showToast(data.error || 'Failed to set timezone', 'error');
            if (select) select.value = currentTimezone;
        }
    } catch (error) {
        showToast('Connection error', 'error');
        if (select) select.value = currentTimezone;
    } finally {
        if (select) select.disabled = false;
    }
}

// -----------------------------------------------------------------------------
// Keyboard Layout Management
// -----------------------------------------------------------------------------

const KEYBOARD_LAYOUTS = [
    { value: 'tr', label: 'Turkish (TR)' },
    { value: 'us', label: 'English US (US)' },
    { value: 'gb', label: 'English UK (GB)' },
    { value: 'de', label: 'German (DE)' },
    { value: 'fr', label: 'French (FR)' },
    { value: 'es', label: 'Spanish (ES)' },
    { value: 'it', label: 'Italian (IT)' },
    { value: 'pt', label: 'Portuguese (PT)' },
    { value: 'br', label: 'Portuguese Brazil (BR)' },
    { value: 'ru', label: 'Russian (RU)' },
    { value: 'ar', label: 'Arabic (AR)' },
    { value: 'nl', label: 'Dutch (NL)' },
    { value: 'pl', label: 'Polish (PL)' },
    { value: 'sv', label: 'Swedish (SV)' },
    { value: 'no', label: 'Norwegian (NO)' },
    { value: 'da', label: 'Danish (DA)' },
    { value: 'fi', label: 'Finnish (FI)' },
    { value: 'el', label: 'Greek (EL)' },
    { value: 'hu', label: 'Hungarian (HU)' },
    { value: 'cs', label: 'Czech (CS)' },
    { value: 'ro', label: 'Romanian (RO)' },
    { value: 'bg', label: 'Bulgarian (BG)' },
    { value: 'hr', label: 'Croatian (HR)' },
    { value: 'sk', label: 'Slovak (SK)' },
    { value: 'sl', label: 'Slovenian (SL)' },
    { value: 'uk', label: 'Ukrainian (UK)' },
    { value: 'az', label: 'Azerbaijani (AZ)' },
    { value: 'jp', label: 'Japanese (JP)' },
    { value: 'kr', label: 'Korean (KR)' },
];

async function loadKeyboardData() {
    const select = document.getElementById('keyboard-select');
    if (!select) return;

    try {
        const data = await api.get('/system/keyboard');
        currentKeyboardLayout = data.layout || 'us';

        select.innerHTML = '';
        KEYBOARD_LAYOUTS.forEach(item => {
            const option = document.createElement('option');
            option.value = item.value;
            option.textContent = item.label;
            if (item.value === currentKeyboardLayout) {
                option.selected = true;
            }
            select.appendChild(option);
        });

        select.disabled = false;

    } catch (error) {
        console.error('Failed to load keyboard data:', error);
        select.innerHTML = '<option value="">Error</option>';
    }
}

async function changeKeyboard(layout) {
    if (!layout) return;

    const select = document.getElementById('keyboard-select');
    if (select) select.disabled = true;

    try {
        const data = await api.post('/system/keyboard', { layout });

        if (data.success) {
            currentKeyboardLayout = layout;
            showToast(`Keyboard: ${layout.toUpperCase()}`, 'success');
        } else {
            showToast(data.error || 'Failed to set keyboard', 'error');
            if (select) select.value = currentKeyboardLayout;
        }
    } catch (error) {
        showToast('Connection error', 'error');
        if (select) select.value = currentKeyboardLayout;
    } finally {
        if (select) select.disabled = false;
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
        const data = await api.get('/system/components', 5000);

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
// System Monitor (CPU, Memory, Disk, Temp, Network)
// =============================================================================

let monitorPollingInterval = null;
let historyRefreshInterval = null;

// DOM cache for monitor elements
const monitorCache = {
    cpuValue: null, cpuBar: null, cpuDetail: null,
    memValue: null, memBar: null, memDetail: null,
    diskRootCard: null, diskRootValue: null, diskRootBar: null, diskRootDetail: null,
    diskDataCard: null, diskDataValue: null, diskDataBar: null, diskDataDetail: null,
    gpuCard: null, gpuValue: null, gpuBar: null, gpuDetail: null,
    vramCard: null, vramValue: null, vramBar: null, vramDetail: null,
    cpuTemp: null, gpuTemp: null,
    netRx: null, netTx: null,
    historyChart: null, historyStatus: null,
    _initialized: false
};

function initMonitorCache() {
    if (monitorCache._initialized) return;
    monitorCache.cpuValue = document.getElementById('monitor-cpu-value');
    monitorCache.cpuBar = document.getElementById('monitor-cpu-bar');
    monitorCache.cpuDetail = document.getElementById('monitor-cpu-detail');
    monitorCache.memValue = document.getElementById('monitor-memory-value');
    monitorCache.memBar = document.getElementById('monitor-memory-bar');
    monitorCache.memDetail = document.getElementById('monitor-memory-detail');
    monitorCache.diskRootCard = document.getElementById('monitor-disk-root');
    monitorCache.diskRootValue = document.getElementById('monitor-disk-root-value');
    monitorCache.diskRootBar = document.getElementById('monitor-disk-root-bar');
    monitorCache.diskRootDetail = document.getElementById('monitor-disk-root-detail');
    monitorCache.diskDataCard = document.getElementById('monitor-disk-data');
    monitorCache.diskDataValue = document.getElementById('monitor-disk-data-value');
    monitorCache.diskDataBar = document.getElementById('monitor-disk-data-bar');
    monitorCache.diskDataDetail = document.getElementById('monitor-disk-data-detail');
    monitorCache.gpuCard = document.getElementById('monitor-gpu');
    monitorCache.gpuValue = document.getElementById('monitor-gpu-value');
    monitorCache.gpuBar = document.getElementById('monitor-gpu-bar');
    monitorCache.gpuDetail = document.getElementById('monitor-gpu-detail');
    monitorCache.vramCard = document.getElementById('monitor-vram');
    monitorCache.vramValue = document.getElementById('monitor-vram-value');
    monitorCache.vramBar = document.getElementById('monitor-vram-bar');
    monitorCache.vramDetail = document.getElementById('monitor-vram-detail');
    monitorCache.cpuTemp = document.getElementById('monitor-cpu-temp');
    monitorCache.gpuTemp = document.getElementById('monitor-gpu-temp');
    monitorCache.netRx = document.getElementById('monitor-net-rx');
    monitorCache.netTx = document.getElementById('monitor-net-tx');
    monitorCache.historyChart = document.getElementById('monitor-history-chart');
    monitorCache.historyStatus = document.getElementById('monitor-history-status');
    monitorCache._initialized = true;
}

function getLevel(percent) {
    if (percent >= 85) return 'level-critical';
    if (percent >= 60) return 'level-warning';
    return 'level-ok';
}

function formatSpeed(bytesPerSec) {
    if (bytesPerSec < 1024) return bytesPerSec.toFixed(0) + ' B/s';
    if (bytesPerSec < 1024 * 1024) return (bytesPerSec / 1024).toFixed(1) + ' KB/s';
    return (bytesPerSec / (1024 * 1024)).toFixed(2) + ' MB/s';
}

function updateProgressBar(barEl, valueEl, percent) {
    const level = getLevel(percent);
    if (barEl) {
        barEl.style.width = percent + '%';
        barEl.className = 'progress-fill ' + level;
    }
    if (valueEl) {
        valueEl.textContent = percent + '%';
        valueEl.className = 'monitor-value ' + level;
    }
}

async function updateSystemMonitor() {
    initMonitorCache();

    try {
        const data = await api.get('/system/monitor', 5000);

        // CPU
        if (data.cpu) {
            updateProgressBar(monitorCache.cpuBar, monitorCache.cpuValue, data.cpu.percent);
            if (monitorCache.cpuDetail) {
                monitorCache.cpuDetail.textContent = data.cpu.count + ' cores';
            }
        }

        // Memory
        if (data.memory) {
            updateProgressBar(monitorCache.memBar, monitorCache.memValue, data.memory.percent);
            if (monitorCache.memDetail) {
                monitorCache.memDetail.textContent =
                    data.memory.used_mb + ' / ' + data.memory.total_mb + ' MB';
            }
        }

        // Disk (root)
        if (data.disk && data.disk.root) {
            updateProgressBar(monitorCache.diskRootBar, monitorCache.diskRootValue, data.disk.root.percent);
            if (monitorCache.diskRootDetail) {
                monitorCache.diskRootDetail.textContent =
                    data.disk.root.used_gb + ' / ' + data.disk.root.total_gb + ' GB';
            }
        }

        // Disk (data) - show card only when backend reports /data mount
        if (data.disk && data.disk.data) {
            if (monitorCache.diskDataCard) {
                monitorCache.diskDataCard.style.display = '';
            }
            updateProgressBar(monitorCache.diskDataBar, monitorCache.diskDataValue, data.disk.data.percent);
            if (monitorCache.diskDataDetail) {
                monitorCache.diskDataDetail.textContent =
                    data.disk.data.used_gb + ' / ' + data.disk.data.total_gb + ' GB';
            }
        }

        // GPU + VRAM - show cards only when NVIDIA GPU is available
        if (data.gpu) {
            // GPU utilization card
            if (monitorCache.gpuCard) {
                monitorCache.gpuCard.style.display = '';
            }
            updateProgressBar(monitorCache.gpuBar, monitorCache.gpuValue, data.gpu.utilization);
            if (monitorCache.gpuDetail) {
                monitorCache.gpuDetail.textContent = data.gpu.name || '--';
            }

            // VRAM memory card
            if (monitorCache.vramCard) {
                monitorCache.vramCard.style.display = '';
            }
            updateProgressBar(monitorCache.vramBar, monitorCache.vramValue, data.gpu.memory_percent);
            if (monitorCache.vramDetail) {
                monitorCache.vramDetail.textContent =
                    data.gpu.memory_used_mb + ' / ' + data.gpu.memory_total_mb + ' MB';
            }
        }

        // Temperature
        if (data.temperatures) {
            if (monitorCache.cpuTemp) {
                monitorCache.cpuTemp.textContent = data.temperatures.cpu !== null
                    ? 'CPU: ' + data.temperatures.cpu + '\u00B0C'
                    : 'CPU: N/A';
            }
            if (monitorCache.gpuTemp) {
                monitorCache.gpuTemp.textContent = data.temperatures.gpu !== null
                    ? 'GPU: ' + data.temperatures.gpu + '\u00B0C'
                    : 'GPU: N/A';
            }
        }

        // Network throughput
        if (data.network) {
            if (monitorCache.netRx) {
                monitorCache.netRx.textContent = '\u2193 ' + formatSpeed(data.network.rx_speed);
            }
            if (monitorCache.netTx) {
                monitorCache.netTx.textContent = '\u2191 ' + formatSpeed(data.network.tx_speed);
            }
        }

    } catch (error) {
        console.warn('System monitor update failed:', error.message || error);
    }
}

async function loadNetworkHistory() {
    initMonitorCache();
    if (!monitorCache.historyChart) return;

    try {
        const data = await api.get('/system/network-history?hours=24', 10000);

        if (!data.available || !data.data || data.data.length === 0) {
            monitorCache.historyChart.innerHTML =
                '<div class="monitor-history-placeholder">' +
                (data.error || 'No data available') + '</div>';
            if (monitorCache.historyStatus) {
                monitorCache.historyStatus.textContent = data.error || '';
            }
            return;
        }

        // Aggregate into ~48 buckets (30min each for 24h)
        const bucketCount = 48;
        const points = data.data;
        const timeRange = points[points.length - 1].time - points[0].time;
        const bucketSize = timeRange / bucketCount || 1;

        const buckets = [];
        for (let i = 0; i < bucketCount; i++) {
            buckets.push({ rx: 0, tx: 0, count: 0 });
        }

        for (const point of points) {
            const idx = Math.min(
                Math.floor((point.time - points[0].time) / bucketSize),
                bucketCount - 1
            );
            buckets[idx].rx += (point.rx || 0);
            buckets[idx].tx += (point.tx || 0);
            buckets[idx].count++;
        }

        // Average each bucket
        for (const bucket of buckets) {
            if (bucket.count > 0) {
                bucket.rx /= bucket.count;
                bucket.tx /= bucket.count;
            }
        }

        // Find max for scaling
        const maxVal = Math.max(...buckets.map(b => Math.max(b.rx, b.tx)), 1);
        const chartHeight = 120;

        // Render bars
        let html = '';
        for (const bucket of buckets) {
            const rxHeight = Math.max(Math.round((bucket.rx / maxVal) * chartHeight), 1);
            const txHeight = Math.max(Math.round((bucket.tx / maxVal) * chartHeight), 1);
            html += '<div class="history-bar" style="height:' + rxHeight + 'px" title="RX: ' + formatSpeed(bucket.rx) + '"></div>';
            html += '<div class="history-bar tx" style="height:' + txHeight + 'px" title="TX: ' + formatSpeed(bucket.tx) + '"></div>';
        }

        monitorCache.historyChart.innerHTML = html;
        if (monitorCache.historyStatus) {
            monitorCache.historyStatus.textContent = points.length + ' data points';
        }

    } catch (error) {
        console.warn('Network history load failed:', error.message || error);
        if (monitorCache.historyChart) {
            monitorCache.historyChart.innerHTML =
                '<div class="monitor-history-placeholder">Failed to load</div>';
        }
    }
}

function startMonitorPolling() {
    if (monitorPollingInterval) return;
    monitorPollingInterval = setInterval(() => {
        if (!document.hidden) updateSystemMonitor();
    }, 5000);
}

function stopMonitorPolling() {
    if (monitorPollingInterval) {
        clearInterval(monitorPollingInterval);
        monitorPollingInterval = null;
    }
}

function startHistoryRefresh() {
    if (historyRefreshInterval) return;
    historyRefreshInterval = setInterval(() => {
        if (!document.hidden) loadNetworkHistory();
    }, 300000); // 5 minutes
}

function stopHistoryRefresh() {
    if (historyRefreshInterval) {
        clearInterval(historyRefreshInterval);
        historyRefreshInterval = null;
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

    // System clock, timezone, keyboard
    loadTimezoneData();
    loadKeyboardData();

    // System monitor
    updateSystemMonitor();
    startMonitorPolling();
    loadNetworkHistory();
    startHistoryRefresh();
});

// Handle visibility changes
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopComponentPolling();
        stopInterfacePolling();
        stopClock();
        stopMonitorPolling();
        stopHistoryRefresh();
    } else {
        startComponentPolling();
        startInterfacePolling();
        updateComponentStatuses();
        loadNetworkInterfaces();
        startClock();
        startMonitorPolling();
        updateSystemMonitor();
        startHistoryRefresh();
    }
});
