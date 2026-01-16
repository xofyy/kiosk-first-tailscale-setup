/**
 * Kiosk Setup Panel - Main JavaScript
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

let isCheckingInternet = false; // Çakışmayı önle

async function checkInternetStatus() {
    // Zaten kontrol ediliyorsa veya tarayıcı offline'sa atla
    if (isCheckingInternet || !navigator.onLine) {
        updateOfflineUI();
        return;
    }
    
    isCheckingInternet = true;
    
    try {
        const data = await api.get('/system/internet', 3000); // 3 saniye timeout
        
        // Header status dot güncelle
        const statusDot = document.querySelector('.status-dot');
        const statusText = document.querySelector('.status-text');
        
        if (statusDot && statusText) {
            if (data.connected) {
                statusDot.classList.add('online');
                statusDot.classList.remove('offline');
                statusText.textContent = data.ip || 'Bağlı';
            } else {
                statusDot.classList.add('offline');
                statusDot.classList.remove('online');
                statusText.textContent = 'Bağlantı Yok';
            }
        }
        
        // Connection grid badge'lerini güncelle
        const connInternet = document.getElementById('conn-internet');
        if (connInternet) {
            connInternet.innerHTML = data.connected 
                ? '<span class="status-badge success">Bağlı</span>'
                : '<span class="status-badge error">Bağlı Değil</span>';
        }
        
        const connDns = document.getElementById('conn-dns');
        if (connDns) {
            connDns.innerHTML = data.dns_working 
                ? '<span class="status-badge success">Çalışıyor</span>'
                : '<span class="status-badge error">Hata</span>';
        }
        
        // IP adresi güncelle
        const connIp = document.getElementById('conn-ip');
        if (connIp) {
            connIp.textContent = data.ip || 'N/A';
        }
        
        // Tailscale IP güncelle
        const connTailscale = document.getElementById('conn-tailscale');
        if (connTailscale) {
            connTailscale.textContent = data.tailscale_ip || 'Bağlı Değil';
        }
        
    } catch (error) {
        updateOfflineUI();
        console.warn('Internet check failed:', error.message || error);
    } finally {
        isCheckingInternet = false;
    }
}

function updateOfflineUI() {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    
    if (statusDot && statusText) {
        statusDot.classList.add('offline');
        statusDot.classList.remove('online');
        statusText.textContent = 'Çevrimdışı';
    }
    
    const connInternet = document.getElementById('conn-internet');
    if (connInternet) {
        connInternet.innerHTML = '<span class="status-badge error">Çevrimdışı</span>';
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
// Kiosk ID Form
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const kioskIdForm = document.getElementById('kiosk-id-form');
    
    if (kioskIdForm) {
        kioskIdForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const input = kioskIdForm.querySelector('input[name="kiosk_id"]');
            const kioskId = input.value.toUpperCase().trim();
            
            if (!kioskId) {
                showToast('Kiosk ID gerekli', 'error');
                return;
            }
            
            try {
                const result = await api.post('/kiosk-id', {
                    'kiosk_id': kioskId
                });
                
                if (result.success) {
                    showToast('Kiosk ID kaydedildi: ' + result.kiosk_id, 'success');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast(result.error || 'Hata oluştu', 'error');
                }
            } catch (error) {
                showToast('Kaydetme hatası', 'error');
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
                showToast('IP ve Gateway gerekli', 'error');
                return;
            }
            
            try {
                const result = await api.post('/network/temporary-ip', data);
                
                if (result.success) {
                    showToast('IP ayarlandı', 'success');
                    setTimeout(() => location.reload(), 2000);
                } else {
                    showToast(result.error || 'Hata oluştu', 'error');
                }
            } catch (error) {
                showToast('IP ayarlama hatası', 'error');
            }
        });
    }
});

// =============================================================================
// Page Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Sadece online ise kontrol et
    if (navigator.onLine) {
        checkInternetStatus();
    } else {
        updateOfflineUI();
    }
    
    // Periodic check - sadece online ise çalışır
    setInterval(() => {
        if (navigator.onLine) {
            checkInternetStatus();
        }
    }, 10000);
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
