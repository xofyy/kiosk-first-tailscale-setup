/**
 * Kiosk Setup Panel - Module Installation JavaScript
 */

// =============================================================================
// Module Installation
// =============================================================================

async function installModule(moduleName) {
    const moduleCard = document.querySelector(`[data-module="${moduleName}"]`);
    const installBtn = moduleCard?.querySelector('.btn-install');
    
    if (!moduleCard || !installBtn) {
        showToast('Modül bulunamadı', 'error');
        return;
    }
    
    // Update UI - installing state
    moduleCard.setAttribute('data-status', 'installing');
    installBtn.disabled = true;
    installBtn.innerHTML = '<span class="spinner"></span> Kuruluyor';
    
    const statusBadge = moduleCard.querySelector('.module-status .status-badge');
    if (statusBadge) {
        statusBadge.className = 'status-badge warning';
        statusBadge.textContent = '⟳ Kuruluyor...';
    }
    
    showToast(`${moduleName} kurulumu başlatıldı...`, 'info');
    
    try {
        const result = await api.post(`/modules/${moduleName}/install`);
        
        if (result.success) {
            // Update UI - completed state
            moduleCard.setAttribute('data-status', 'completed');
            installBtn.className = 'btn btn-secondary';
            installBtn.disabled = true;
            installBtn.textContent = 'Kuruldu';
            
            if (statusBadge) {
                statusBadge.className = 'status-badge success';
                statusBadge.textContent = '✓ Tamamlandı';
            }
            
            showToast(result.message || `${moduleName} kuruldu`, 'success');
            
            // Update progress
            updateProgress();
            
            // Check if needs reboot
            if (result.message?.includes('reboot')) {
                setTimeout(() => {
                    if (confirm('Değişikliklerin uygulanması için yeniden başlatma gerekiyor. Şimdi yeniden başlatılsın mı?')) {
                        rebootSystem();
                    }
                }, 1000);
            }
        } else {
            // Update UI - failed state
            moduleCard.setAttribute('data-status', 'failed');
            installBtn.className = 'btn btn-primary btn-install';
            installBtn.disabled = false;
            installBtn.textContent = 'Yeniden Dene';
            
            if (statusBadge) {
                statusBadge.className = 'status-badge error';
                statusBadge.textContent = '✗ Hata';
            }
            
            showToast(result.error || 'Kurulum başarısız', 'error');
        }
    } catch (error) {
        // Update UI - failed state
        moduleCard.setAttribute('data-status', 'failed');
        installBtn.className = 'btn btn-primary btn-install';
        installBtn.disabled = false;
        installBtn.textContent = 'Yeniden Dene';
        
        if (statusBadge) {
            statusBadge.className = 'status-badge error';
            statusBadge.textContent = '✗ Hata';
        }
        
        showToast('Kurulum hatası', 'error');
        console.error('Install error:', error);
    }
}

// =============================================================================
// Progress Update
// =============================================================================

async function updateProgress() {
    try {
        const data = await api.get('/setup/status');
        
        // Update progress bar
        const progressBar = document.getElementById('overall-progress');
        const progressText = document.getElementById('progress-text');
        
        if (progressBar) {
            progressBar.style.width = `${data.progress}%`;
        }
        
        if (progressText) {
            progressText.textContent = `${data.completed_modules} / ${data.total_modules} modül tamamlandı`;
        }
        
        // Update complete button
        const completeBtn = document.getElementById('btn-complete');
        if (completeBtn) {
            completeBtn.disabled = data.completed_modules < data.total_modules;
        }
        
    } catch (error) {
        console.error('Progress update error:', error);
    }
}

// =============================================================================
// Complete Setup
// =============================================================================

async function completeSetup() {
    if (!confirm('Kurulumu tamamlamak istediğinizden emin misiniz?\n\nSistem kiosk moduna geçecek ve yeniden başlatılacak.')) {
        return;
    }
    
    const btn = document.getElementById('btn-complete');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Tamamlanıyor...';
    }
    
    try {
        const result = await api.post('/setup/complete');
        
        if (result.success) {
            showToast(result.message || 'Kurulum tamamlandı!', 'success');
            
            // Reboot after 3 seconds
            setTimeout(() => {
                rebootSystem();
            }, 3000);
        } else {
            showToast(result.error || 'Kurulum tamamlanamadı', 'error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Kurulumu Tamamla';
            }
        }
    } catch (error) {
        showToast('Kurulum tamamlama hatası', 'error');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Kurulumu Tamamla';
        }
    }
}

// =============================================================================
// Reboot System
// =============================================================================

async function rebootSystem() {
    try {
        await api.post('/system/reboot');
        showToast('Sistem yeniden başlatılıyor...', 'warning');
        
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
                    border-top-color: #58a6ff;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin-bottom: 24px;
                "></div>
                <h2>Sistem Yeniden Başlatılıyor</h2>
                <p style="color: #8b949e; margin-top: 8px;">Lütfen bekleyin...</p>
            </div>
            <style>
                @keyframes spin { to { transform: rotate(360deg); } }
            </style>
        `;
    } catch (error) {
        showToast('Yeniden başlatma hatası', 'error');
    }
}

// =============================================================================
// Module Status Polling
// =============================================================================

let pollingInterval = null;

function startPolling() {
    if (pollingInterval) return;
    
    pollingInterval = setInterval(async () => {
        // Check if any module is installing
        const installingModules = document.querySelectorAll('[data-status="installing"]');
        
        if (installingModules.length === 0) {
            stopPolling();
            return;
        }
        
        // Update progress
        await updateProgress();
        
    }, 5000);
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

// =============================================================================
// Page Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Initial progress update
    updateProgress();
    
    // Start polling if any module is installing
    const installingModules = document.querySelectorAll('[data-status="installing"]');
    if (installingModules.length > 0) {
        startPolling();
    }
});
