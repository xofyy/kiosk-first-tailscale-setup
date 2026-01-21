/**
 * Services Page JavaScript
 * Service iframe management
 */

// =============================================================================
// Service Frame Management
// =============================================================================

function openService(path, title) {
    const container = document.getElementById('frame-container');
    const frame = document.getElementById('service-frame');
    const titleEl = document.getElementById('frame-title');
    const loading = document.getElementById('frame-loading');

    titleEl.textContent = title;
    loading.classList.add('visible');
    frame.style.opacity = '0';

    frame.onload = function() {
        loading.classList.remove('visible');
        frame.style.opacity = '1';
    };

    frame.src = path;
    container.classList.add('visible');
    document.body.style.overflow = 'hidden';
}

function closeFrame() {
    const container = document.getElementById('frame-container');
    const frame = document.getElementById('service-frame');
    const loading = document.getElementById('frame-loading');

    container.classList.remove('visible');
    loading.classList.remove('visible');
    frame.src = '';
    document.body.style.overflow = '';
}

// =============================================================================
// Keyboard Shortcuts
// =============================================================================

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeFrame();
    }
});
