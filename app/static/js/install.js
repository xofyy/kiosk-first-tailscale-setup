/**
 * Install Page JavaScript
 * MOK re-import and initialization
 */
'use strict';

// =============================================================================
// MOK Re-import
// =============================================================================

async function reimportMok() {
    if (!confirm('MOK will be re-imported and system will reboot. Continue?')) {
        return;
    }

    try {
        const data = await api.post('/nvidia/mok-reimport');

        if (data.success) {
            alert(data.message + '\n\nSystem rebooting...');
            await api.post('/system/reboot');
        } else {
            alert('Error: ' + (data.message || data.error || 'Unknown error'));
        }
    } catch (error) {
        alert('MOK import error: ' + error);
    }
}

// =============================================================================
// Initialization
// =============================================================================

// Update progress on page load
if (typeof updateProgress === 'function') {
    updateProgress();
}
