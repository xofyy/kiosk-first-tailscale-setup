/**
 * Services Page JavaScript
 * Service iframe management
 */
'use strict';

// =============================================================================
// DOM Elements (cached for performance)
// =============================================================================

let frameContainer = null;
let serviceFrame = null;
let frameTitle = null;
let frameLoading = null;

function getFrameElements() {
    if (!frameContainer) {
        frameContainer = document.getElementById('frame-container');
        serviceFrame = document.getElementById('service-frame');
        frameTitle = document.getElementById('frame-title');
        frameLoading = document.getElementById('frame-loading');
    }
    return { frameContainer, serviceFrame, frameTitle, frameLoading };
}

// =============================================================================
// Service Frame Management
// =============================================================================

function openService(port, title) {
    const { frameContainer, serviceFrame, frameTitle, frameLoading } = getFrameElements();
    if (!frameContainer || !serviceFrame) return;

    if (frameTitle) frameTitle.textContent = title;
    if (frameLoading) frameLoading.classList.add('visible');
    serviceFrame.style.opacity = '0';

    serviceFrame.onload = function() {
        if (frameLoading) frameLoading.classList.remove('visible');
        serviceFrame.style.opacity = '1';
    };

    const directUrl = `http://${window.location.hostname}:${port}/`;
    serviceFrame.src = directUrl;
    frameContainer.classList.add('visible');
    document.body.style.overflow = 'hidden';
}

function closeFrame() {
    const { frameContainer, serviceFrame, frameLoading } = getFrameElements();
    if (!frameContainer) return;

    frameContainer.classList.remove('visible');
    if (frameLoading) frameLoading.classList.remove('visible');
    if (serviceFrame) serviceFrame.src = '';
    document.body.style.overflow = '';
}

// =============================================================================
// Keyboard Shortcuts
// =============================================================================

function handleKeydown(e) {
    if (e.key === 'Escape') {
        closeFrame();
    }
}

document.addEventListener('keydown', handleKeydown);
