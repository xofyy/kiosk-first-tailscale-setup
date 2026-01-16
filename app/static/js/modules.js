/**
 * Kiosk Setup Panel - Module Installation JavaScript
 * Async install ve polling sistemi
 */

// =============================================================================
// Module Installation (Async)
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
        // API'yi çağır (async - hemen döner)
        const result = await api.post(`/modules/${moduleName}/install`);
        
        if (result.success) {
            showToast(result.message || 'Kurulum başlatıldı', 'success');
            
            // Log sayfasını yeni tab'da aç (modül filtresiyle)
            window.open(`/logs?module=${moduleName}`, '_blank');
            
            // Polling başlat
            startModulePolling(moduleName);
        } else {
            // Hata durumunda UI'ı güncelle
            handleInstallError(moduleCard, installBtn, statusBadge, result.error);
        }
    } catch (error) {
        handleInstallError(moduleCard, installBtn, statusBadge, 'Bağlantı hatası');
        console.error('Install error:', error);
    }
}

function handleInstallError(moduleCard, installBtn, statusBadge, errorMessage) {
    moduleCard.setAttribute('data-status', 'failed');
    installBtn.className = 'btn btn-primary btn-install';
    installBtn.disabled = false;
    installBtn.textContent = 'Yeniden Dene';
    
    if (statusBadge) {
        statusBadge.className = 'status-badge error';
        statusBadge.textContent = '✗ Hata';
    }
    
    showToast(errorMessage || 'Kurulum başlatılamadı', 'error');
}

// =============================================================================
// Module Status Polling
// =============================================================================

const modulePollingIntervals = {};

function startModulePolling(moduleName) {
    // Önceki polling'i durdur
    stopModulePolling(moduleName);
    
    // 3 saniyede bir status kontrol et
    modulePollingIntervals[moduleName] = setInterval(async () => {
        await checkModuleStatus(moduleName);
    }, 3000);
    
    // İlk kontrolü hemen yap
    checkModuleStatus(moduleName);
}

function stopModulePolling(moduleName) {
    if (modulePollingIntervals[moduleName]) {
        clearInterval(modulePollingIntervals[moduleName]);
        delete modulePollingIntervals[moduleName];
    }
}

async function checkModuleStatus(moduleName) {
    try {
        const data = await api.get(`/modules/${moduleName}/status`);
        const status = data.status;
        
        const moduleCard = document.querySelector(`[data-module="${moduleName}"]`);
        if (!moduleCard) return;
        
        const installBtn = moduleCard.querySelector('.btn-install, .btn-reboot, .btn-secondary');
        const statusBadge = moduleCard.querySelector('.module-status .status-badge');
        
        // Status değişti mi?
        const currentStatus = moduleCard.getAttribute('data-status');
        if (currentStatus === status) return;
        
        // UI güncelle
        updateModuleUI(moduleCard, installBtn, statusBadge, status);
        
        // Polling'i durdur (installing dışındaki durumlar için)
        if (status !== 'installing') {
            stopModulePolling(moduleName);
            updateProgress();
        }
        
    } catch (error) {
        console.error('Status check error:', error);
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
                installBtn.textContent = 'Kuruldu';
                installBtn.onclick = null;
            }
            if (statusBadge) {
                statusBadge.className = 'status-badge success';
                statusBadge.textContent = '✓ Tamamlandı';
            }
            showToast(message || `${moduleName} kurulumu tamamlandı`, 'success');
            break;
            
        case 'installing':
            if (installBtn) {
                installBtn.className = 'btn btn-secondary';
                installBtn.disabled = true;
                installBtn.innerHTML = '<span class="spinner"></span> Kuruluyor';
            }
            if (statusBadge) {
                statusBadge.className = 'status-badge warning';
                statusBadge.textContent = '⟳ Kuruluyor...';
            }
            break;
            
        case 'reboot_required':
            if (installBtn) {
                installBtn.className = 'btn btn-warning btn-reboot';
                installBtn.disabled = false;
                installBtn.textContent = 'Yeniden Başlat';
                installBtn.onclick = () => showRebootPrompt(message);
            }
            if (statusBadge) {
                statusBadge.className = 'status-badge info';
                statusBadge.textContent = '↻ Reboot Gerekli';
            }
            showToast(message || 'Reboot gerekli', 'warning');
            showRebootPrompt(message);
            break;
            
        case 'mok_pending':
            if (installBtn) {
                installBtn.className = 'btn btn-warning btn-reboot';
                installBtn.disabled = false;
                installBtn.textContent = 'MOK Onayı';
                installBtn.onclick = () => showMokInstructions(message);
            }
            if (statusBadge) {
                statusBadge.className = 'status-badge info';
                statusBadge.textContent = '🔐 MOK Onayı';
            }
            showToast(message || 'MOK onayı için reboot gerekli', 'warning');
            showMokInstructions(message);
            break;
            
        case 'failed':
        default:
            if (installBtn) {
                installBtn.className = 'btn btn-primary btn-install';
                installBtn.disabled = false;
                installBtn.textContent = 'Yeniden Dene';
                installBtn.onclick = () => installModule(moduleName);
            }
            if (statusBadge) {
                statusBadge.className = 'status-badge error';
                statusBadge.textContent = '✗ Hata';
            }
            if (status === 'failed') {
                showToast(message || `${moduleName} kurulumu başarısız`, 'error');
            }
            break;
    }
}

// =============================================================================
// Reboot and MOK Prompts
// =============================================================================

function showRebootPrompt(message) {
    setTimeout(() => {
        if (confirm((message || 'Değişikliklerin uygulanması için yeniden başlatma gerekiyor.') + '\n\nŞimdi yeniden başlatılsın mı?')) {
            rebootSystem();
        }
    }, 500);
}

function showMokInstructions(message) {
    const instructions = `
MOK ONAYI GEREKLİ

Sistem yeniden başlatıldıktan sonra MAVİ EKRANDA:

1. 'Enroll MOK' seçin → Enter
2. 'Continue' seçin → Enter  
3. 'Yes' seçin → Enter
4. Şifreyi girin (ekranda görünmez)
5. 'Reboot' seçin → Enter

${message || ''}

Şimdi yeniden başlatılsın mı?
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
            if (data.complete) {
                // Setup zaten tamamlanmış
                completeBtn.textContent = '✓ Kurulum Tamamlandı';
                completeBtn.disabled = true;
                completeBtn.classList.remove('btn-success');
                completeBtn.classList.add('btn-secondary');
            } else {
                // Tüm modüller tamamlandıysa butonu aktif et
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
                    border-top-color: #00ff88;
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
// Page-wide Polling (for installing modules)
// =============================================================================

let globalPollingInterval = null;

function startGlobalPolling() {
    if (globalPollingInterval) return;
    
    globalPollingInterval = setInterval(async () => {
        // Installing durumundaki tüm modülleri kontrol et
        const installingModules = document.querySelectorAll('[data-status="installing"]');
        
        if (installingModules.length === 0) {
            stopGlobalPolling();
            return;
        }
        
        for (const moduleCard of installingModules) {
            const moduleName = moduleCard.getAttribute('data-module');
            await checkModuleStatus(moduleName);
        }
        
        // Progress'i güncelle
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
    
    // Installing durumundaki modüller varsa polling başlat
    const installingModules = document.querySelectorAll('[data-status="installing"]');
    if (installingModules.length > 0) {
        startGlobalPolling();
        
        // Her biri için ayrı polling da başlat (daha hızlı güncelleme için)
        installingModules.forEach(card => {
            const moduleName = card.getAttribute('data-module');
            startModulePolling(moduleName);
        });
    }
});

// Sayfa görünürlük değişince
document.addEventListener('visibilitychange', () => {
    const installingModules = document.querySelectorAll('[data-status="installing"]');
    
    if (document.hidden) {
        stopGlobalPolling();
    } else if (installingModules.length > 0) {
        startGlobalPolling();
    }
});
