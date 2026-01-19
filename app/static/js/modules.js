/**
 * Kiosk Setup Panel - Module Installation JavaScript
 * Async install and polling system
 */

// =============================================================================
// Module Installation (Async)
// =============================================================================

async function installModule(moduleName) {
    const moduleCard = document.querySelector(`[data-module="${moduleName}"]`);
    const installBtn = moduleCard?.querySelector('.btn-install');

    if (!moduleCard || !installBtn) {
        showToast('Module not found', 'error');
        return;
    }

    // Update UI - installing state
    moduleCard.setAttribute('data-status', 'installing');
    installBtn.disabled = true;
    installBtn.innerHTML = '<span class="spinner"></span> Installing';

    const statusBadge = moduleCard.querySelector('.module-status .status-badge');
    if (statusBadge) {
        statusBadge.className = 'status-badge warning';
        statusBadge.textContent = '⟳ Installing...';
    }

    showToast(`${moduleName} installation started...`, 'info');

    try {
        // Call API (async - returns immediately)
        const result = await api.post(`/modules/${moduleName}/install`);

        if (result.success) {
            showToast(result.message || 'Installation started', 'success');

            // Open log page in new tab (with module filter)
            window.open(`/logs?module=${moduleName}`, '_blank');

            // Start polling
            startModulePolling(moduleName);
        } else {
            // Update UI on error
            handleInstallError(moduleCard, installBtn, statusBadge, result.error);
        }
    } catch (error) {
        handleInstallError(moduleCard, installBtn, statusBadge, 'Connection error');
        console.error('Install error:', error);
    }
}

function handleInstallError(moduleCard, installBtn, statusBadge, errorMessage) {
    moduleCard.setAttribute('data-status', 'failed');
    installBtn.className = 'btn btn-primary btn-install';
    installBtn.disabled = false;
    installBtn.textContent = 'Retry';

    if (statusBadge) {
        statusBadge.className = 'status-badge error';
        statusBadge.textContent = '✗ Error';
    }

    showToast(errorMessage || 'Installation could not start', 'error');
}

// =============================================================================
// Module Status Polling
// =============================================================================

const modulePollingIntervals = {};

function startModulePolling(moduleName) {
    // Stop previous polling
    stopModulePolling(moduleName);

    // Check status every 3 seconds
    modulePollingIntervals[moduleName] = setInterval(async () => {
        await checkModuleStatus(moduleName);
    }, 3000);

    // Do first check immediately
    checkModuleStatus(moduleName);
}

function stopModulePolling(moduleName) {
    if (modulePollingIntervals[moduleName]) {
        clearInterval(modulePollingIntervals[moduleName]);
        delete modulePollingIntervals[moduleName];
    }
}

async function checkModuleStatus(moduleName) {
    // Skip if offline
    if (!navigator.onLine) return;

    try {
        const data = await api.get(`/modules/${moduleName}/status`, 5000);
        const status = data.status;

        const moduleCard = document.querySelector(`[data-module="${moduleName}"]`);
        if (!moduleCard) return;

        const installBtn = moduleCard.querySelector('.btn-install, .btn-reboot, .btn-secondary');
        const statusBadge = moduleCard.querySelector('.module-status .status-badge');

        // Did status change?
        const currentStatus = moduleCard.getAttribute('data-status');
        if (currentStatus === status) return;

        // Update UI
        updateModuleUI(moduleCard, installBtn, statusBadge, status);

        // Stop polling (for states other than installing)
        if (status !== 'installing') {
            stopModulePolling(moduleName);
            updateProgress();
        }

    } catch (error) {
        console.warn('Status check error:', error.message || error);
    }
}

// =============================================================================
// Update Module UI Based on Status
// =============================================================================

function updateModuleUI(moduleCard, installBtn, statusBadge, status, message) {
    const moduleName = moduleCard.getAttribute('data-module');
    moduleCard.setAttribute('data-status', status);

    switch (status) {
        case 'completed':
            if (installBtn) {
                installBtn.className = 'btn btn-secondary';
                installBtn.disabled = true;
                installBtn.textContent = 'Installed';
                installBtn.onclick = null;
            }
            if (statusBadge) {
                statusBadge.className = 'status-badge success';
                statusBadge.textContent = '✓ Completed';
            }
            showToast(message || `${moduleName} installation completed`, 'success');
            break;

        case 'installing':
            if (installBtn) {
                installBtn.className = 'btn btn-secondary';
                installBtn.disabled = true;
                installBtn.innerHTML = '<span class="spinner"></span> Installing';
            }
            if (statusBadge) {
                statusBadge.className = 'status-badge warning';
                statusBadge.textContent = '⟳ Installing...';
            }
            break;

        case 'reboot_required':
            if (installBtn) {
                installBtn.className = 'btn btn-warning btn-reboot';
                installBtn.disabled = false;
                installBtn.textContent = 'Reboot';
                installBtn.onclick = () => showRebootPrompt(message);
            }
            if (statusBadge) {
                statusBadge.className = 'status-badge info';
                statusBadge.textContent = '↻ Reboot Required';
            }
            showToast(message || 'Reboot required', 'warning');
            showRebootPrompt(message);
            break;

        case 'mok_pending':
            if (installBtn) {
                installBtn.className = 'btn btn-warning btn-reboot';
                installBtn.disabled = false;
                installBtn.textContent = 'MOK Pending';
                installBtn.onclick = () => showMokInstructions(message);
            }
            if (statusBadge) {
                statusBadge.className = 'status-badge info';
                statusBadge.textContent = '🔐 MOK Pending';
            }
            showToast(message || 'Reboot required for MOK approval', 'warning');
            showMokInstructions(message);
            break;

        case 'failed':
        default:
            if (installBtn) {
                installBtn.className = 'btn btn-primary btn-install';
                installBtn.disabled = false;
                installBtn.textContent = 'Retry';
                installBtn.onclick = () => installModule(moduleName);
            }
            if (statusBadge) {
                statusBadge.className = 'status-badge error';
                statusBadge.textContent = '✗ Error';
            }
            if (status === 'failed') {
                showToast(message || `${moduleName} installation failed`, 'error');
            }
            break;
    }
}

// =============================================================================
// Reboot and MOK Prompts
// =============================================================================

function showRebootPrompt(message) {
    setTimeout(() => {
        if (confirm((message || 'A reboot is required for changes to take effect.') + '\n\nReboot now?')) {
            rebootSystem();
        }
    }, 500);
}

function showMokInstructions(message) {
    const instructions = `
MOK APPROVAL REQUIRED

After system reboots, on the BLUE SCREEN:

1. Select 'Enroll MOK' → Enter
2. Select 'Continue' → Enter
3. Select 'Yes' → Enter
4. Enter the password (not visible on screen)
5. Select 'Reboot' → Enter

${message || ''}

Reboot now?
    `.trim();

    setTimeout(() => {
        if (confirm(instructions)) {
            rebootSystem();
        }
    }, 500);
}

// =============================================================================
// Progress Update
// =============================================================================

async function updateProgress() {
    // Skip if offline
    if (!navigator.onLine) return;

    try {
        const data = await api.get('/setup/status', 5000);

        // Update progress bar
        const progressBar = document.getElementById('overall-progress');
        const progressText = document.getElementById('progress-text');

        if (progressBar) {
            progressBar.style.width = `${data.progress}%`;
        }

        if (progressText) {
            progressText.textContent = `${data.completed_modules} / ${data.total_modules} modules completed`;
        }

        // Update complete button
        const completeBtn = document.getElementById('btn-complete');
        if (completeBtn) {
            if (data.complete) {
                // Setup already completed
                completeBtn.textContent = '✓ Setup Complete';
                completeBtn.disabled = true;
                completeBtn.classList.remove('btn-success');
                completeBtn.classList.add('btn-secondary');
            } else {
                // Enable button if all modules are completed
                completeBtn.disabled = data.completed_modules < data.total_modules;
            }
        }

    } catch (error) {
        console.error('Progress update error:', error);
    }
}

// =============================================================================
// Complete Setup
// =============================================================================

async function completeSetup() {
    if (!confirm('Are you sure you want to complete setup?\n\nSystem will switch to kiosk mode and reboot.')) {
        return;
    }

    const btn = document.getElementById('btn-complete');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Completing...';
    }

    try {
        const result = await api.post('/setup/complete');

        if (result.success) {
            showToast(result.message || 'Setup complete!', 'success');

            // Reboot after 3 seconds
            setTimeout(() => {
                rebootSystem();
            }, 3000);
        } else {
            showToast(result.error || 'Setup could not be completed', 'error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Complete Setup';
            }
        }
    } catch (error) {
        showToast('Setup completion error', 'error');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Complete Setup';
        }
    }
}

// =============================================================================
// Reboot System
// =============================================================================

async function rebootSystem() {
    try {
        await api.post('/system/reboot');
        showToast('System rebooting...', 'warning');

        // Show overlay
        document.body.innerHTML = `
            <div style="
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
                background: #0a0e14;
                color: #e6edf3;
                font-family: monospace;
            ">
                <div class="spinner" style="
                    width: 48px;
                    height: 48px;
                    border: 3px solid transparent;
                    border-top-color: #00ff88;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin-bottom: 24px;
                "></div>
                <h2>System Rebooting</h2>
                <p style="color: #8b949e; margin-top: 8px;">Please wait...</p>
            </div>
            <style>
                @keyframes spin { to { transform: rotate(360deg); } }
            </style>
        `;
    } catch (error) {
        showToast('Reboot error', 'error');
    }
}

// =============================================================================
// Page-wide Polling (for installing modules)
// =============================================================================

let globalPollingInterval = null;

function startGlobalPolling() {
    if (globalPollingInterval) return;

    globalPollingInterval = setInterval(async () => {
        // Check all modules in installing state
        const installingModules = document.querySelectorAll('[data-status="installing"]');

        if (installingModules.length === 0) {
            stopGlobalPolling();
            return;
        }

        for (const moduleCard of installingModules) {
            const moduleName = moduleCard.getAttribute('data-module');
            await checkModuleStatus(moduleName);
        }

        // Update progress
        await updateProgress();

    }, 5000);
}

function stopGlobalPolling() {
    if (globalPollingInterval) {
        clearInterval(globalPollingInterval);
        globalPollingInterval = null;
    }
}

// =============================================================================
// Page Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Initial progress update
    updateProgress();

    // Start polling if there are modules in installing state
    const installingModules = document.querySelectorAll('[data-status="installing"]');
    if (installingModules.length > 0) {
        startGlobalPolling();

        // Also start individual polling for each (for faster updates)
        installingModules.forEach(card => {
            const moduleName = card.getAttribute('data-module');
            startModulePolling(moduleName);
        });
    }
});

// When page visibility changes
document.addEventListener('visibilitychange', () => {
    const installingModules = document.querySelectorAll('[data-status="installing"]');

    if (document.hidden) {
        stopGlobalPolling();
    } else if (installingModules.length > 0) {
        startGlobalPolling();
    }
});
