import Uppy from '@uppy/core';
import Dashboard from '@uppy/dashboard';
import XHRUpload from '@uppy/xhr-upload';

import '@uppy/core/dist/style.css';
import '@uppy/dashboard/dist/style.css';

// Prevent browser from opening/playing dropped files
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    document.body.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

// Get CSRF token
function getCsrfToken() {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token ? token.getAttribute('content') : '';
}

// Initialize Uppy when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const uppy = new Uppy({
        debug: true,
        autoProceed: false,
        restrictions: {
            maxNumberOfFiles: 1,
            allowedFileTypes: ['.m4a', '.m4b', '.mp3'],
            maxFileSize: 5 * 1024 * 1024 * 1024, // 5 GB max
        },
    })
    .use(Dashboard, {
        inline: true,
        target: '#uppy-dashboard',
        height: 450,
        width: '100%',
        showProgressDetails: true,
        proudlyDisplayPoweredByUppy: false,
        note: 'Audiobook files only (.m4a, .m4b, .mp3), up to 5 GB',
        theme: 'auto',
        hideUploadButton: false,
        hideCancelButton: false,
        hideRetryButton: false,
        showRemoveButtonAfterComplete: true,
        fileManagerSelectionType: 'files',
        disableLocalFiles: false,
    })
    .use(XHRUpload, {
        endpoint: '/admin/import/upload',
        formData: true,
        fieldName: 'audio_file',
        headers: {
            'x-csrf-token': getCsrfToken(),
        },
        bundle: false,
    });

    // Handle successful upload
    uppy.on('upload-success', (file, response) => {
        console.log('Upload successful:', file.name);
        console.log('Server response:', response.body);

        // Store the redirect URL from the response
        if (response.body && response.body.redirect_url) {
            file.meta.redirectUrl = response.body.redirect_url;
        }
    });

    // Handle complete upload and redirect
    uppy.on('complete', (result) => {
        if (result.successful.length > 0) {
            // Get redirect URL from the successful upload
            const redirectUrl = result.successful[0]?.meta?.redirectUrl || '/library';

            console.log('Upload complete, redirecting to:', redirectUrl);

            // Wait a moment to show the success state, then redirect
            setTimeout(() => {
                window.location.href = redirectUrl;
            }, 1500);
        }

        if (result.failed.length > 0) {
            console.error('Upload failed:', result.failed);
            alert('Upload failed. Please try again.');
        }
    });

    // Handle upload errors
    uppy.on('upload-error', (file, error, response) => {
        console.error('Upload error:', error);
        let errorMessage = 'Upload failed. Please try again.';

        if (response && response.body && response.body.detail) {
            errorMessage = response.body.detail;
        }

        alert(errorMessage);
    });

    // Debug: Log when Uppy is ready
    uppy.on('dashboard:file-added', (file) => {
        console.log('File added to dashboard:', file.name);
    });
});
