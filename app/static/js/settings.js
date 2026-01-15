/**
 * Kiosk Setup Panel - Settings JavaScript
 */

// =============================================================================
// Settings Form
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const settingsForm = document.getElementById('settings-form');
    
    if (!settingsForm) return;
    
    settingsForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(settingsForm);
        const data = {};
        
        // Convert form data to nested object
        for (const [key, value] of formData.entries()) {
            // Skip disabled fields
            const input = settingsForm.querySelector(`[name="${key}"]`);
            if (input?.disabled) continue;
            
            // Handle special cases
            if (key === 'network.dns_servers') {
                // Convert comma-separated to array
                data[key] = value.split(',').map(v => v.trim()).filter(v => v);
            } else if (!isNaN(value) && value !== '') {
                // Convert numbers
                data[key] = Number(value);
            } else {
                data[key] = value;
            }
        }
        
        const submitBtn = settingsForm.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner"></span> Kaydediliyor...';
        }
        
        try {
            const result = await api.post('/config', data);
            
            if (result.success) {
                showToast('Ayarlar kaydedildi', 'success');
                
                // Show updated fields
                if (result.updated?.length > 0) {
                    console.log('Updated fields:', result.updated);
                }
            } else {
                // Show errors
                if (result.errors?.length > 0) {
                    showToast(result.errors.join('\n'), 'error');
                } else {
                    showToast('Bazı ayarlar kaydedilemedi', 'warning');
                }
            }
        } catch (error) {
            showToast('Kaydetme hatası', 'error');
            console.error('Settings save error:', error);
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Ayarları Kaydet';
            }
        }
    });
    
    // Password visibility toggle
    const passwordInputs = settingsForm.querySelectorAll('input[type="password"]');
    
    passwordInputs.forEach(input => {
        const wrapper = document.createElement('div');
        wrapper.style.position = 'relative';
        
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);
        
        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.className = 'password-toggle';
        toggleBtn.textContent = '👁';
        toggleBtn.style.cssText = `
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            cursor: pointer;
            font-size: 16px;
            opacity: 0.6;
        `;
        
        toggleBtn.addEventListener('click', () => {
            if (input.type === 'password') {
                input.type = 'text';
                toggleBtn.textContent = '🔒';
            } else {
                input.type = 'password';
                toggleBtn.textContent = '👁';
            }
        });
        
        wrapper.appendChild(toggleBtn);
    });
});

// =============================================================================
// Validation
// =============================================================================

function validateIP(ip) {
    const parts = ip.split('.');
    if (parts.length !== 4) return false;
    
    return parts.every(part => {
        const num = parseInt(part, 10);
        return num >= 0 && num <= 255;
    });
}

function validatePort(port) {
    const num = parseInt(port, 10);
    return num >= 1 && num <= 65535;
}

// Add input validation
document.addEventListener('DOMContentLoaded', () => {
    // Validate ports
    const portInputs = document.querySelectorAll('input[name$=".port"]');
    
    portInputs.forEach(input => {
        input.addEventListener('blur', () => {
            if (input.value && !validatePort(input.value)) {
                input.style.borderColor = 'var(--color-error)';
                showToast('Geçersiz port numarası (1-65535)', 'error');
            } else {
                input.style.borderColor = '';
            }
        });
    });
});
