/**
 * Install Page JavaScript
 * MOK re-import and initialization
 */

// =============================================================================
// MOK Re-import
// =============================================================================

async function reimportMok() {
    if (!confirm('MOK will be re-imported and system will reboot. Continue?')) {
        return;
    }

    try {
        const response = await fetch('/api/nvidia/mok-reimport', {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            alert(data.message + '\n\nSystem rebooting...');
            // Reboot
            await fetch('/api/system/reboot', { method: 'POST' });
        } else {
            alert('Error: ' + data.message);
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
