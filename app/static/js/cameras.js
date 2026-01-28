/**
 * NVR Camera Live View
 * WebRTC streaming via go2rtc + ISAPI channel discovery
 */
'use strict';

// =============================================================================
// Utilities
// =============================================================================

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// =============================================================================
// State
// =============================================================================

// Active streams: streamName -> { ws, pc, video, channelName, channelId }
const activeStreams = {};

// DOM cache
let cameraCardsEl = null;
let cameraLoadingEl = null;
let cameraControlsEl = null;
let videoGridEl = null;
let fullscreenOverlayEl = null;
let fullscreenVideoEl = null;
let fullscreenTitleEl = null;
let nvrConfigFormEl = null;
let nvrConfigStatusEl = null;
let nvrConfigConnectedEl = null;

// go2rtc WebSocket base (same host, port 1984)
const GO2RTC_WS_URL = `ws://${window.location.hostname}:1984`;

// =============================================================================
// DOM Init
// =============================================================================

function initCameraElements() {
    cameraCardsEl = document.getElementById('camera-cards');
    cameraLoadingEl = document.getElementById('camera-loading');
    cameraControlsEl = document.getElementById('camera-controls');
    videoGridEl = document.getElementById('video-grid');
    fullscreenOverlayEl = document.getElementById('fullscreen-overlay');
    fullscreenVideoEl = document.getElementById('fullscreen-video');
    fullscreenTitleEl = document.getElementById('fullscreen-title');
    nvrConfigFormEl = document.getElementById('nvr-config-form');
    nvrConfigStatusEl = document.getElementById('nvr-config-status');
    nvrConfigConnectedEl = document.getElementById('nvr-config-connected');
}

// =============================================================================
// NVR Config
// =============================================================================

async function saveNvrConfig() {
    const username = document.getElementById('nvr-username')?.value.trim();
    const password = document.getElementById('nvr-password')?.value.trim();

    if (!username || !password) {
        showToast('Username and password required', 'error');
        return;
    }

    if (nvrConfigStatusEl) nvrConfigStatusEl.textContent = 'Saving...';

    try {
        const result = await api.post('/nvr/config', { username, password });

        if (result.success) {
            showToast('NVR credentials saved', 'success');
            if (nvrConfigStatusEl) nvrConfigStatusEl.textContent = '';
            // Reload to show connected state and discover cameras
            setTimeout(() => location.reload(), 500);
        } else {
            showToast(result.error || 'Save failed', 'error');
            if (nvrConfigStatusEl) nvrConfigStatusEl.textContent = result.error || 'Error';
        }
    } catch (error) {
        showToast('Connection error', 'error');
        if (nvrConfigStatusEl) nvrConfigStatusEl.textContent = 'Connection error';
    }
}

function toggleNvrSettings() {
    if (!nvrConfigFormEl) return;
    nvrConfigFormEl.classList.toggle('hidden');
}

// =============================================================================
// Camera Discovery
// =============================================================================

async function discoverCameras() {
    initCameraElements();
    if (!cameraCardsEl) return;

    // Show loading
    if (cameraLoadingEl) cameraLoadingEl.classList.remove('hidden');

    try {
        const result = await api.get('/nvr/channels', 15000);

        if (cameraLoadingEl) cameraLoadingEl.classList.add('hidden');

        if (!result.success) {
            cameraCardsEl.innerHTML = `<div class="camera-error">${result.error || 'Discovery failed'}</div>`;
            return;
        }

        const channels = result.channels || [];
        if (channels.length === 0) {
            cameraCardsEl.innerHTML = '<div class="camera-error">No cameras found</div>';
            return;
        }

        // Filter main streams (stream_type 1) for card display
        const mainStreams = channels.filter(ch => ch.stream_type === 1 && ch.enabled);

        if (mainStreams.length === 0) {
            cameraCardsEl.innerHTML = '<div class="camera-error">No enabled cameras found</div>';
            return;
        }

        // Build camera cards
        cameraCardsEl.innerHTML = mainStreams.map(ch => createCameraCard(ch)).join('');

    } catch (error) {
        if (cameraLoadingEl) cameraLoadingEl.classList.add('hidden');
        cameraCardsEl.innerHTML = '<div class="camera-error">Cannot connect to NVR</div>';
        console.error('Camera discovery error:', error);
    }
}

function createCameraCard(channel) {
    const streamName = `camera_${channel.id}`;
    const isActive = streamName in activeStreams;
    const video = channel.video || {};
    const resolution = (video.width && video.height) ? `${video.width}x${video.height}` : '';
    const codec = video.codec || '';

    return `
        <div class="camera-card" id="card-${channel.id}" data-channel-id="${channel.id}">
            <div class="camera-card-header">
                <span class="camera-name">${escapeHtml(channel.name || 'Camera ' + channel.channel_no)}</span>
                <span class="camera-badge">CH ${channel.channel_no}</span>
            </div>
            <div class="camera-card-info">
                ${resolution ? `<span class="camera-info-item">${resolution}</span>` : ''}
                ${codec ? `<span class="camera-info-item">${codec}</span>` : ''}
            </div>
            <div class="camera-card-actions">
                <button class="btn-watch ${isActive ? 'active' : ''}"
                        onclick="toggleCameraStream(${channel.id}, '${escapeHtml(channel.name || 'Camera ' + channel.channel_no)}')"
                        id="btn-watch-${channel.id}">
                    ${isActive ? 'Stop' : 'Watch'}
                </button>
            </div>
        </div>
    `;
}

// =============================================================================
// Stream Management
// =============================================================================

async function toggleCameraStream(channelId, channelName) {
    const streamName = `camera_${channelId}`;

    if (streamName in activeStreams) {
        await stopCameraStream(streamName);
    } else {
        await startCameraStream(channelId, channelName);
    }
}

async function startCameraStream(channelId, channelName) {
    const streamName = `camera_${channelId}`;
    const btn = document.getElementById(`btn-watch-${channelId}`);

    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Connecting...';
    }

    try {
        // Tell server to create stream in go2rtc
        const result = await api.post('/nvr/stream/start', { channel_id: channelId });

        if (!result.success) {
            showToast(result.error || 'Stream start failed', 'error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Watch';
            }
            return;
        }

        // Create video cell in grid
        const videoEl = createVideoCell(streamName, channelName);

        // Connect WebRTC
        const { ws, pc } = await connectWebRTC(streamName, videoEl);

        // Store in active streams
        activeStreams[streamName] = {
            ws, pc, video: videoEl,
            channelName, channelId
        };

        // Update UI
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Stop';
            btn.classList.add('active');
        }

        showGrid();
        updateGridLayout();

    } catch (error) {
        console.error('Stream start error:', error);
        showToast('Stream connection failed', 'error');

        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Watch';
        }

        // Cleanup on failure
        cleanupStream(streamName);
    }
}

async function stopCameraStream(streamName) {
    const stream = activeStreams[streamName];
    if (!stream) return;

    const channelId = stream.channelId;
    const btn = document.getElementById(`btn-watch-${channelId}`);

    // Close WebRTC
    cleanupStream(streamName);

    // Tell server to remove stream
    try {
        await api.post('/nvr/stream/stop', { stream_name: streamName });
    } catch (error) {
        console.error('Stream stop error:', error);
    }

    // Remove from active
    delete activeStreams[streamName];

    // Update UI
    if (btn) {
        btn.textContent = 'Watch';
        btn.classList.remove('active');
    }

    // Remove video cell
    const cell = document.getElementById(`cell-${streamName}`);
    if (cell) cell.remove();

    // Update grid
    updateGridLayout();

    if (Object.keys(activeStreams).length === 0) {
        hideGrid();
    }
}

async function stopAllCameraStreams() {
    const streamNames = Object.keys(activeStreams);

    // Cleanup all local connections
    for (const name of streamNames) {
        cleanupStream(name);
        delete activeStreams[name];

        const cell = document.getElementById(`cell-${name}`);
        if (cell) cell.remove();
    }

    // Tell server to stop all
    try {
        await api.post('/nvr/stream/stop-all');
    } catch (error) {
        console.error('Stop all error:', error);
    }

    // Reset all watch buttons
    document.querySelectorAll('.btn-watch.active').forEach(btn => {
        btn.textContent = 'Watch';
        btn.classList.remove('active');
    });

    hideGrid();
}

function cleanupStream(streamName) {
    const stream = activeStreams[streamName];
    if (!stream) return;

    if (stream.ws) {
        try { stream.ws.close(); } catch (e) { /* ignore */ }
    }
    if (stream.pc) {
        try { stream.pc.close(); } catch (e) { /* ignore */ }
    }
}

// =============================================================================
// WebRTC Connection (go2rtc protocol)
// =============================================================================

function connectWebRTC(streamName, videoEl) {
    return new Promise((resolve, reject) => {
        const wsUrl = `${GO2RTC_WS_URL}/api/ws?src=${streamName}`;
        const ws = new WebSocket(wsUrl);
        const pc = new RTCPeerConnection({
            iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
        });

        // Receive remote tracks
        pc.ontrack = (event) => {
            if (videoEl.srcObject !== event.streams[0]) {
                videoEl.srcObject = event.streams[0];
            }
        };

        // Send ICE candidates to go2rtc
        pc.onicecandidate = (event) => {
            if (event.candidate && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'webrtc/candidate',
                    value: event.candidate.candidate
                }));
            }
        };

        ws.onopen = async () => {
            try {
                // Add receive-only transceivers
                pc.addTransceiver('video', { direction: 'recvonly' });
                pc.addTransceiver('audio', { direction: 'recvonly' });

                // Create and send offer
                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);

                ws.send(JSON.stringify({
                    type: 'webrtc/offer',
                    value: offer.sdp
                }));
            } catch (error) {
                reject(error);
            }
        };

        ws.onmessage = async (event) => {
            const msg = JSON.parse(event.data);

            if (msg.type === 'webrtc/answer') {
                try {
                    await pc.setRemoteDescription(new RTCSessionDescription({
                        type: 'answer',
                        sdp: msg.value
                    }));
                    resolve({ ws, pc });
                } catch (error) {
                    reject(error);
                }
            } else if (msg.type === 'webrtc/candidate') {
                try {
                    await pc.addIceCandidate(new RTCIceCandidate({
                        candidate: msg.value,
                        sdpMid: '0'
                    }));
                } catch (error) {
                    console.warn('ICE candidate error:', error);
                }
            }
        };

        ws.onerror = () => {
            reject(new Error('WebSocket connection failed'));
        };

        ws.onclose = () => {
            // Connection lost - could add reconnect logic here
        };

        // Timeout for connection
        setTimeout(() => {
            if (pc.connectionState !== 'connected' && pc.connectionState !== 'connecting') {
                reject(new Error('WebRTC connection timeout'));
            }
        }, 10000);
    });
}

// =============================================================================
// Video Grid
// =============================================================================

function createVideoCell(streamName, channelName) {
    initCameraElements();

    const cell = document.createElement('div');
    cell.className = 'video-cell';
    cell.id = `cell-${streamName}`;

    const video = document.createElement('video');
    video.autoplay = true;
    video.playsInline = true;
    video.muted = true;

    const overlay = document.createElement('div');
    overlay.className = 'video-cell-overlay';
    overlay.innerHTML = `
        <span class="video-cell-name">${escapeHtml(channelName)}</span>
        <div class="video-cell-controls">
            <button class="btn-fullscreen" onclick="openFullscreenCamera('${streamName}')" title="Fullscreen">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
                </svg>
            </button>
            <button class="btn-cell-stop" onclick="stopCameraStream('${streamName}')" title="Stop">
                <svg viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="6" width="12" height="12" rx="1"/>
                </svg>
            </button>
        </div>
    `;

    cell.appendChild(video);
    cell.appendChild(overlay);

    // Double-click for fullscreen
    cell.addEventListener('dblclick', () => openFullscreenCamera(streamName));

    if (videoGridEl) videoGridEl.appendChild(cell);

    return video;
}

function updateGridLayout() {
    if (!videoGridEl) return;

    const count = Object.keys(activeStreams).length;

    // Remove old grid classes
    videoGridEl.className = 'video-grid';

    if (count === 1) {
        videoGridEl.classList.add('grid-1');
    } else if (count === 2) {
        videoGridEl.classList.add('grid-2');
    } else if (count <= 4) {
        videoGridEl.classList.add('grid-4');
    } else {
        videoGridEl.classList.add('grid-9');
    }

    // Show/hide controls
    if (cameraControlsEl) {
        if (count > 0) {
            cameraControlsEl.classList.remove('hidden');
        } else {
            cameraControlsEl.classList.add('hidden');
        }
    }
}

function showGrid() {
    if (videoGridEl) videoGridEl.classList.remove('hidden');
}

function hideGrid() {
    if (videoGridEl) videoGridEl.classList.add('hidden');
    if (cameraControlsEl) cameraControlsEl.classList.add('hidden');
}

// =============================================================================
// Fullscreen
// =============================================================================

function openFullscreenCamera(streamName) {
    initCameraElements();
    const stream = activeStreams[streamName];
    if (!stream || !fullscreenOverlayEl || !fullscreenVideoEl) return;

    // Clone video stream to fullscreen
    if (stream.video.srcObject) {
        fullscreenVideoEl.srcObject = stream.video.srcObject;
    }

    if (fullscreenTitleEl) {
        fullscreenTitleEl.textContent = stream.channelName;
    }

    fullscreenOverlayEl.classList.remove('hidden');
}

function closeFullscreenCamera() {
    initCameraElements();
    if (!fullscreenOverlayEl || !fullscreenVideoEl) return;

    fullscreenOverlayEl.classList.add('hidden');
    fullscreenVideoEl.srcObject = null;
}

// =============================================================================
// Keyboard Shortcuts
// =============================================================================

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (fullscreenOverlayEl && !fullscreenOverlayEl.classList.contains('hidden')) {
            closeFullscreenCamera();
        }
    }
});

// =============================================================================
// Cleanup
// =============================================================================

window.addEventListener('beforeunload', () => {
    // Close all WebRTC connections
    for (const name of Object.keys(activeStreams)) {
        cleanupStream(name);
    }

    // Tell server to cleanup all streams
    navigator.sendBeacon('/api/nvr/stream/stop-all', '');
});

// =============================================================================
// Init
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initCameraElements();

    // Auto-discover cameras if config exists
    const configConnected = document.getElementById('nvr-config-connected');
    if (configConnected) {
        discoverCameras();
    }
});
