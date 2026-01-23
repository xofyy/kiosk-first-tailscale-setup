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
let servicesList = null;

function getFrameElements() {
    if (!frameContainer) {
        frameContainer = document.getElementById('frame-container');
        serviceFrame = document.getElementById('service-frame');
        frameTitle = document.getElementById('frame-title');
        frameLoading = document.getElementById('frame-loading');
        servicesList = document.getElementById('services-list');
    }
    return { frameContainer, serviceFrame, frameTitle, frameLoading, servicesList };
}

// =============================================================================
// Service Frame Management
// =============================================================================

function openService(port, path, title) {
    const { frameContainer, serviceFrame, frameTitle, frameLoading, servicesList } = getFrameElements();
    if (!frameContainer || !serviceFrame) return;

    // Hide services list, show frame
    if (servicesList) servicesList.classList.add('hidden');

    if (frameTitle) frameTitle.textContent = title;
    if (frameLoading) frameLoading.classList.add('visible');
    serviceFrame.style.opacity = '0';

    serviceFrame.onload = function() {
        if (frameLoading) frameLoading.classList.remove('visible');
        serviceFrame.style.opacity = '1';
    };

    const directUrl = `http://${window.location.hostname}:${port}${path}`;
    serviceFrame.src = directUrl;
    frameContainer.classList.add('visible');
}

function closeFrame() {
    const { frameContainer, serviceFrame, frameLoading, servicesList } = getFrameElements();
    if (!frameContainer) return;

    // Hide frame, show services list
    frameContainer.classList.remove('visible');
    if (frameLoading) frameLoading.classList.remove('visible');
    if (serviceFrame) serviceFrame.src = '';

    if (servicesList) servicesList.classList.remove('hidden');
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
