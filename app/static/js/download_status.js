/**
 * Download Status SSE Client
 *
 * Provides real-time updates for download queue status using Server-Sent Events.
 * Reusable across book detail pages and queue pages.
 */

class DownloadStatusClient {
    constructor(url, callbacks) {
        this.url = url;
        this.callbacks = callbacks || {};
        this.eventSource = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
    }

    /**
     * Connect to SSE stream
     */
    connect() {
        console.log(`[SSE] Connecting to ${this.url}`);

        this.eventSource = new EventSource(this.url);

        this.eventSource.addEventListener('queue_status', (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('[SSE] Queue status update:', data);

                if (this.callbacks.onStatusUpdate) {
                    this.callbacks.onStatusUpdate(data);
                }

                // Reset reconnect delay on successful message
                this.reconnectDelay = 1000;
            } catch (error) {
                console.error('[SSE] Error parsing queue status:', error);
            }
        });

        this.eventSource.addEventListener('error', (event) => {
            console.error('[SSE] Connection error:', event);

            if (this.callbacks.onError) {
                this.callbacks.onError(event);
            }

            // Close and attempt reconnection with exponential backoff
            this.eventSource.close();
            this.scheduleReconnect();
        });

        this.eventSource.onopen = () => {
            console.log('[SSE] Connection opened');
            if (this.callbacks.onConnect) {
                this.callbacks.onConnect();
            }
        };
    }

    /**
     * Disconnect from SSE stream
     */
    disconnect() {
        if (this.eventSource) {
            console.log('[SSE] Disconnecting');
            this.eventSource.close();
            this.eventSource = null;
        }
    }

    /**
     * Schedule reconnection with exponential backoff
     */
    scheduleReconnect() {
        console.log(`[SSE] Reconnecting in ${this.reconnectDelay}ms`);

        setTimeout(() => {
            this.connect();
        }, this.reconnectDelay);

        // Increase delay for next reconnect (exponential backoff)
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
    }
}

/**
 * Update UI elements with download status
 *
 * @param {Array} statusData - Array of queue entry status objects
 * @param {Object} options - Configuration options
 */
function updateDownloadStatus(statusData, options = {}) {
    const { bookId, containerSelector } = options;

    // Filter for specific book if bookId provided
    const relevantStatuses = bookId
        ? statusData.filter(item => item.book_id === bookId)
        : statusData;

    // If filtering for specific book and no status found, book is not in queue
    if (bookId && relevantStatuses.length === 0) {
        updateStatusDisplay(containerSelector, null);
        return;
    }

    // Update each status
    relevantStatuses.forEach(item => {
        const selector = bookId ? containerSelector : `[data-queue-id="${item.queue_id}"]`;
        updateStatusDisplay(selector, item);
    });
}

/**
 * Update status display for a single item
 *
 * @param {string} selector - CSS selector for status container
 * @param {Object} status - Status object (null if not in queue)
 */
function updateStatusDisplay(selector, status) {
    const container = document.querySelector(selector);
    if (!container) return;

    if (!status) {
        // Not in queue
        container.innerHTML = '<span class="text-muted">Not queued</span>';
        return;
    }

    // Status badge with appropriate styling
    const statusBadges = {
        'pending': '<span class="badge bg-secondary">Pending</span>',
        'downloading': '<span class="badge bg-primary">Downloading...</span>',
        'decrypting': '<span class="badge bg-info">Decrypting...</span>',
        'completed': '<span class="badge bg-success">Completed</span>',
        'failed': '<span class="badge bg-danger">Failed</span>',
    };

    let html = statusBadges[status.status] || `<span class="badge bg-secondary">${status.status}</span>`;

    // Add progress indicator for active downloads
    if (status.status === 'downloading' || status.status === 'decrypting') {
        html += `
            <div class="progress mt-2" style="height: 5px;">
                <div class="progress-bar progress-bar-striped progress-bar-animated"
                     role="progressbar" style="width: 100%"></div>
            </div>
        `;
    }

    // Add error message if failed
    if (status.status === 'failed' && status.error_message) {
        html += `
            <div class="text-danger small mt-1">
                ${escapeHtml(status.error_message)}
            </div>
        `;
    }

    // Add attempt count
    if (status.attempts > 0) {
        html += `<small class="text-muted ms-2">(Attempt ${status.attempts})</small>`;
    }

    container.innerHTML = html;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Initialize SSE client for book detail page
 *
 * @param {number} bookId - Book ID to monitor
 * @param {string} containerSelector - CSS selector for status container
 */
function initBookStatusMonitor(bookId, containerSelector = '#download-status') {
    const client = new DownloadStatusClient(`/api/queue/stream/${bookId}`, {
        onStatusUpdate: (statusData) => {
            updateDownloadStatus(statusData, { bookId, containerSelector });
        },
        onConnect: () => {
            console.log(`[Book ${bookId}] Status monitor connected`);
        },
        onError: (error) => {
            console.error(`[Book ${bookId}] Status monitor error:`, error);
        }
    });

    client.connect();

    // Clean up on page unload
    window.addEventListener('beforeunload', () => {
        client.disconnect();
    });

    return client;
}

/**
 * Initialize SSE client for queue page
 *
 * @param {string} containerSelector - CSS selector for queue container
 */
function initQueueStatusMonitor(containerSelector = '#queue-container') {
    const client = new DownloadStatusClient('/api/queue/stream', {
        onStatusUpdate: (statusData) => {
            updateDownloadStatus(statusData, { containerSelector });
        },
        onConnect: () => {
            console.log('[Queue] Status monitor connected');
        },
        onError: (error) => {
            console.error('[Queue] Status monitor error:', error);
        }
    });

    client.connect();

    // Clean up on page unload
    window.addEventListener('beforeunload', () => {
        client.disconnect();
    });

    return client;
}
