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

function toggleClockSettings() {
    const controls = document.querySelector('.system-controls');
    if (controls) {
        controls.classList.toggle('open');
    }
}

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
            tzDisplay.textContent = currentTimezone;
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
                tzDisplay.textContent = timezone;
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
    historyChart: null, historyStatus: null, historyTitle: null,
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
    monitorCache.historyTitle = document.getElementById('monitor-history-title');
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

function formatBytes(bytes) {
    if (bytes < 1024) return bytes.toFixed(0) + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
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

        // Update title with actual time range
        if (monitorCache.historyTitle) {
            if (points.length > 1 && timeRange > 60) {
                const hours = Math.floor(timeRange / 3600);
                const minutes = Math.floor((timeRange % 3600) / 60);
                let rangeStr = '';
                if (hours > 0) rangeStr += hours + 'H ';
                if (minutes > 0 || hours === 0) rangeStr += minutes + 'M';
                monitorCache.historyTitle.textContent = 'Network History (' + rangeStr.trim() + ')';
            } else {
                monitorCache.historyTitle.textContent = 'Network History';
            }
        }

        const buckets = [];
        for (let i = 0; i < bucketCount; i++) {
            buckets.push({ rx: 0, tx: 0 });
        }

        for (const point of points) {
            const idx = Math.min(
                Math.floor((point.time - points[0].time) / bucketSize),
                bucketCount - 1
            );
            buckets[idx].rx += (point.rx || 0);
            buckets[idx].tx += (point.tx || 0);
        }

        // Calculate 24h totals
        let totalRx = 0;
        let totalTx = 0;
        for (const point of points) {
            totalRx += (point.rx || 0);
            totalTx += (point.tx || 0);
        }

        // Find max for scaling
        const maxVal = Math.max(...buckets.map(b => Math.max(b.rx, b.tx)), 1);
        const chartHeight = 180;

        // Render bars
        let html = '';
        for (const bucket of buckets) {
            const rxHeight = Math.max(Math.round((bucket.rx / maxVal) * chartHeight), 1);
            const txHeight = Math.max(Math.round((bucket.tx / maxVal) * chartHeight), 1);
            html += '<div class="history-bar" style="height:' + rxHeight + 'px" title="Download: ' + formatBytes(bucket.rx) + '"></div>';
            html += '<div class="history-bar tx" style="height:' + txHeight + 'px" title="Upload: ' + formatBytes(bucket.tx) + '"></div>';
        }

        // Legend (inline format for header)
        const legendHtml =
            '<span class="legend-dot legend-rx"></span>' +
            '<span class="legend-label">Download</span>' +
            '<span class="legend-dot legend-tx"></span>' +
            '<span class="legend-label">Upload</span>';

        // Y-axis scale labels
        const scaleSteps = 4;
        let scaleHtml = '<div class="history-scale">';
        for (let i = scaleSteps; i >= 0; i--) {
            const value = (maxVal / scaleSteps) * i;
            const label = formatBytes(value);
            scaleHtml += '<div class="history-scale-label">' + label + '</div>';
        }
        scaleHtml += '</div>';

        // Grid lines (background)
        let gridHtml = '<div class="history-grid">';
        for (let i = 1; i <= scaleSteps; i++) {
            const position = (100 / scaleSteps) * i;
            gridHtml += '<div class="history-grid-line" style="bottom:' + position + '%"></div>';
        }
        gridHtml += '</div>';

        // Bars
        const barsHtml = '<div class="history-bars">' + html + '</div>';

        // Chart container with scale, grid and bars
        const chartHtml = '<div class="history-chart-wrapper">' + scaleHtml +
            '<div class="history-bars-container">' + gridHtml + barsHtml + '</div>' +
            '</div>';

        // Render chart only (no summary stats)
        monitorCache.historyChart.innerHTML = chartHtml;

        // Update status with legend and totals
        if (monitorCache.historyStatus) {
            monitorCache.historyStatus.innerHTML =
                '<span class="history-legend-inline">' + legendHtml + '</span>' +
                '<span class="history-stats-inline">' +
                    points.length + ' points · ' +
                    formatBytes(totalRx) + ' ↓ · ' +
                    formatBytes(totalTx) + ' ↑ · ' +
                    formatBytes(totalRx + totalTx) + ' total' +
                '</span>';
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
// Monitor Detail Modal
// =============================================================================

let monitorDetailModal = null;
let monitorDetailBody = null;
let monitorDetailStatus = null;
let monitorDetailTitle = null;
let monitorDetailInterval = null;
let currentMonitorType = null;

function initMonitorDetailModal() {
    if (!monitorDetailModal) {
        monitorDetailModal = document.getElementById('monitor-detail-modal');
        monitorDetailBody = document.getElementById('monitor-modal-body');
        monitorDetailStatus = document.getElementById('monitor-modal-status');
        monitorDetailTitle = document.getElementById('monitor-modal-title');
    }
}

function openMonitorDetail(type) {
    initMonitorDetailModal();
    if (!monitorDetailModal) return;

    currentMonitorType = type;

    // Set title based on type
    const titles = {
        'cpu': 'CPU Details',
        'memory': 'Memory Details',
        'gpu': 'GPU Details',
        'vram': 'VRAM Details'
    };
    if (monitorDetailTitle) {
        monitorDetailTitle.textContent = titles[type] || 'Details';
    }

    // Show loading state
    if (monitorDetailBody) {
        monitorDetailBody.innerHTML = '<div class="monitor-modal-loading">Loading...</div>';
    }

    // Show modal
    monitorDetailModal.classList.add('visible');

    // Load content immediately
    loadDetailContent(type);

    // Start auto-refresh (5 seconds)
    if (monitorDetailInterval) clearInterval(monitorDetailInterval);
    monitorDetailInterval = setInterval(() => {
        if (!document.hidden && currentMonitorType) {
            loadDetailContent(currentMonitorType);
        }
    }, 5000);
}

function closeMonitorDetail() {
    // Stop auto-refresh
    if (monitorDetailInterval) {
        clearInterval(monitorDetailInterval);
        monitorDetailInterval = null;
    }

    currentMonitorType = null;

    // Hide modal
    if (monitorDetailModal) {
        monitorDetailModal.classList.remove('visible');
    }
}

async function loadDetailContent(type) {
    try {
        const data = await api.get(`/system/monitor/${type}/details`, 5000);

        // Update status with timestamp
        if (monitorDetailStatus) {
            const now = new Date();
            monitorDetailStatus.textContent = 'Updated: ' + now.toLocaleTimeString();
        }

        // Render based on type
        switch (type) {
            case 'cpu':
                renderCpuDetails(data);
                break;
            case 'memory':
                renderMemoryDetails(data);
                break;
            case 'gpu':
                renderGpuDetails(data);
                break;
            case 'vram':
                renderVramDetails(data);
                break;
        }
    } catch (error) {
        console.error('Failed to load monitor details:', error);
        if (monitorDetailBody) {
            monitorDetailBody.innerHTML = '<div class="monitor-modal-error"><span>Failed to load data</span></div>';
        }
    }
}

function renderCpuDetails(data) {
    if (!monitorDetailBody || data.error) {
        if (monitorDetailBody) {
            monitorDetailBody.innerHTML = '<div class="monitor-modal-error"><span>' + (data.error || 'Error loading data') + '</span></div>';
        }
        return;
    }

    // Per-core progress bars
    const coreHtml = data.per_cpu.map((percent, i) => `
        <div class="detail-core-item">
            <span class="detail-core-label">Core ${i}</span>
            <div class="progress-bar progress-bar-sm">
                <div class="progress-fill ${getLevel(percent)}" style="width: ${percent}%"></div>
            </div>
            <span class="detail-core-value ${getLevel(percent)}">${percent}%</span>
        </div>
    `).join('');

    // Process list
    const processHtml = data.top_processes.length > 0 ? data.top_processes.map(proc => `
        <div class="detail-process-item">
            <span class="detail-process-name" title="${proc.name}">${proc.name}</span>
            <span class="detail-process-pid">PID: ${proc.pid}</span>
            <div class="progress-bar progress-bar-sm">
                <div class="progress-fill ${getLevel(proc.cpu_percent)}" style="width: ${Math.min(proc.cpu_percent, 100)}%"></div>
            </div>
            <span class="detail-process-value">${proc.cpu_percent}%</span>
        </div>
    `).join('') : '<div class="detail-empty">No active processes</div>';

    monitorDetailBody.innerHTML = `
        <div class="detail-section">
            <div class="detail-summary">
                <div class="detail-summary-item">
                    <span class="detail-summary-label">Overall Usage</span>
                    <span class="detail-summary-value ${getLevel(data.overall_percent)}">${data.overall_percent}%</span>
                </div>
                <div class="detail-summary-item">
                    <span class="detail-summary-label">Cores</span>
                    <span class="detail-summary-value">${data.physical_cores} Physical / ${data.core_count} Logical</span>
                </div>
                ${data.frequency && data.frequency.current ? `
                <div class="detail-summary-item">
                    <span class="detail-summary-label">Frequency</span>
                    <span class="detail-summary-value">${data.frequency.current} MHz</span>
                </div>
                ` : ''}
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">Load Average</h4>
            <div class="detail-load-avg">
                <span>1m: <strong>${data.load_avg['1min']}</strong></span>
                <span>5m: <strong>${data.load_avg['5min']}</strong></span>
                <span>15m: <strong>${data.load_avg['15min']}</strong></span>
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">Per-Core Usage</h4>
            <div class="detail-cores-grid">
                ${coreHtml}
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">Top 5 Processes</h4>
            <div class="detail-process-list">
                ${processHtml}
            </div>
        </div>
    `;
}

function renderMemoryDetails(data) {
    if (!monitorDetailBody || data.error) {
        if (monitorDetailBody) {
            monitorDetailBody.innerHTML = '<div class="monitor-modal-error"><span>' + (data.error || 'Error loading data') + '</span></div>';
        }
        return;
    }

    // Process list
    const processHtml = data.top_processes.length > 0 ? data.top_processes.map(proc => `
        <div class="detail-process-item">
            <span class="detail-process-name" title="${proc.name}">${proc.name}</span>
            <span class="detail-process-pid">PID: ${proc.pid}</span>
            <div class="progress-bar progress-bar-sm">
                <div class="progress-fill ${getLevel(proc.memory_percent)}" style="width: ${proc.memory_percent}%"></div>
            </div>
            <span class="detail-process-value">${proc.memory_mb} MB</span>
        </div>
    `).join('') : '<div class="detail-empty">No active processes</div>';

    monitorDetailBody.innerHTML = `
        <div class="detail-section">
            <div class="detail-summary">
                <div class="detail-summary-item">
                    <span class="detail-summary-label">Total</span>
                    <span class="detail-summary-value">${data.total_mb} MB</span>
                </div>
                <div class="detail-summary-item">
                    <span class="detail-summary-label">Used</span>
                    <span class="detail-summary-value ${getLevel(data.percent)}">${data.used_mb} MB (${data.percent}%)</span>
                </div>
                <div class="detail-summary-item">
                    <span class="detail-summary-label">Available</span>
                    <span class="detail-summary-value">${data.available_mb} MB</span>
                </div>
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">Memory Breakdown</h4>
            <div class="detail-memory-breakdown">
                <div class="detail-breakdown-item">
                    <span>Buffers:</span>
                    <strong>${data.buffers_mb} MB</strong>
                </div>
                <div class="detail-breakdown-item">
                    <span>Cached:</span>
                    <strong>${data.cached_mb} MB</strong>
                </div>
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">Swap</h4>
            <div class="detail-swap">
                <div class="progress-bar">
                    <div class="progress-fill ${getLevel(data.swap.percent)}" style="width: ${data.swap.percent}%"></div>
                </div>
                <span class="detail-swap-info">${data.swap.used_mb} / ${data.swap.total_mb} MB (${data.swap.percent}%)</span>
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">Top 5 Processes</h4>
            <div class="detail-process-list">
                ${processHtml}
            </div>
        </div>
    `;
}

function renderGpuDetails(data) {
    if (!monitorDetailBody) return;

    if (!data.available) {
        monitorDetailBody.innerHTML = `
            <div class="detail-not-available">
                <span>NVIDIA GPU not available</span>
                <small>${data.error || ''}</small>
            </div>
        `;
        return;
    }

    // Process list
    const processHtml = data.top_processes.length > 0 ? data.top_processes.map(proc => `
        <div class="detail-process-item">
            <span class="detail-process-name" title="${proc.name}">${proc.name}</span>
            <span class="detail-process-pid">PID: ${proc.pid}</span>
            <span class="detail-process-value">${proc.gpu_memory_mb} MB</span>
        </div>
    `).join('') : '<div class="detail-empty">No GPU processes</div>';

    monitorDetailBody.innerHTML = `
        <div class="detail-section">
            <div class="detail-summary">
                <div class="detail-summary-item">
                    <span class="detail-summary-label">GPU</span>
                    <span class="detail-summary-value">${data.name}</span>
                </div>
                <div class="detail-summary-item">
                    <span class="detail-summary-label">Driver</span>
                    <span class="detail-summary-value">${data.driver_version}</span>
                </div>
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">GPU Utilization</h4>
            <div class="detail-gpu-metrics">
                <div class="detail-metric-item">
                    <span class="detail-metric-label">Compute</span>
                    <div class="progress-bar">
                        <div class="progress-fill ${getLevel(data.utilization)}" style="width: ${data.utilization}%"></div>
                    </div>
                    <span class="detail-metric-value ${getLevel(data.utilization)}">${data.utilization}%</span>
                </div>
                <div class="detail-metric-item">
                    <span class="detail-metric-label">Memory I/O</span>
                    <div class="progress-bar">
                        <div class="progress-fill ${getLevel(data.memory_utilization)}" style="width: ${data.memory_utilization}%"></div>
                    </div>
                    <span class="detail-metric-value">${data.memory_utilization}%</span>
                </div>
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">Status</h4>
            <div class="detail-status-grid">
                <div class="detail-status-item">
                    <span>Temperature</span>
                    <strong class="${data.temperature >= 80 ? 'level-critical' : data.temperature >= 70 ? 'level-warning' : ''}">${data.temperature}°C</strong>
                </div>
                ${data.power_draw ? `
                <div class="detail-status-item">
                    <span>Power Draw</span>
                    <strong>${data.power_draw} W</strong>
                </div>
                ` : ''}
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">GPU Processes</h4>
            <div class="detail-process-list">
                ${processHtml}
            </div>
        </div>
    `;
}

function renderVramDetails(data) {
    if (!monitorDetailBody) return;

    if (!data.available) {
        monitorDetailBody.innerHTML = `
            <div class="detail-not-available">
                <span>NVIDIA GPU not available</span>
                <small>${data.error || ''}</small>
            </div>
        `;
        return;
    }

    // Process list with VRAM usage
    const processHtml = data.top_processes.length > 0 ? data.top_processes.map(proc => `
        <div class="detail-process-item">
            <span class="detail-process-name" title="${proc.name}">${proc.name}</span>
            <span class="detail-process-pid">PID: ${proc.pid}</span>
            <div class="progress-bar progress-bar-sm">
                <div class="progress-fill ${getLevel(proc.memory_percent)}" style="width: ${proc.memory_percent}%"></div>
            </div>
            <span class="detail-process-value">${proc.memory_mb} MB</span>
        </div>
    `).join('') : '<div class="detail-empty">No GPU processes</div>';

    monitorDetailBody.innerHTML = `
        <div class="detail-section">
            <div class="detail-summary">
                <div class="detail-summary-item">
                    <span class="detail-summary-label">GPU</span>
                    <span class="detail-summary-value">${data.gpu_name}</span>
                </div>
                <div class="detail-summary-item">
                    <span class="detail-summary-label">Total VRAM</span>
                    <span class="detail-summary-value">${data.total_mb} MB</span>
                </div>
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">VRAM Usage</h4>
            <div class="detail-vram-usage">
                <div class="progress-bar progress-bar-lg">
                    <div class="progress-fill ${getLevel(data.percent)}" style="width: ${data.percent}%"></div>
                </div>
                <div class="detail-vram-info">
                    <span>Used: <strong>${data.used_mb} MB</strong></span>
                    <span>Free: <strong>${data.free_mb} MB</strong></span>
                    <span class="${getLevel(data.percent)}">${data.percent}%</span>
                </div>
            </div>
        </div>

        <div class="detail-section">
            <h4 class="detail-section-title">Per-Process VRAM</h4>
            <div class="detail-process-list">
                ${processHtml}
            </div>
        </div>
    `;
}

// Add click handlers to monitor cards
function initMonitorCardClickHandlers() {
    const clickableCards = [
        { id: 'monitor-cpu', type: 'cpu' },
        { id: 'monitor-memory', type: 'memory' },
        { id: 'monitor-gpu', type: 'gpu' },
        { id: 'monitor-vram', type: 'vram' }
    ];

    clickableCards.forEach(({ id, type }) => {
        const card = document.getElementById(id);
        if (card) {
            card.classList.add('monitor-card-clickable');
            card.onclick = () => openMonitorDetail(type);
        }
    });
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && monitorDetailModal && monitorDetailModal.classList.contains('visible')) {
        closeMonitorDetail();
    }
});

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

    // Monitor detail modal click handlers
    initMonitorCardClickHandlers();
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
