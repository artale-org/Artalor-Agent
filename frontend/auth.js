// -----------------------------------------------------------------------------
// © 2026 Artalor
// Artalor Project — All rights reserved.
// Licensed for personal and educational use only.
// Commercial use or redistribution prohibited.
// See LICENSE.md for full terms.
// -----------------------------------------------------------------------------

// ============================================================================
// API Keys Manager (local storage only)
// ============================================================================
class ApiKeysManager {
    constructor() {
        this.STORAGE_KEY = 'artalor_api_keys';
        this.cachedKeys = {};
        this.init();
    }

    init() {
        this.setupEventListeners();
        // Load from localStorage first (fast)
        this.cachedKeys = this.getKeysFromLocal();
        this.loadKeysToForm();
        this.updateIndicator();
    }

    setupEventListeners() {
        // API Keys button in dropdown
        const apiKeysBtn = document.getElementById('api-keys-btn');
        if (apiKeysBtn) {
            apiKeysBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.showModal();
            });
        }

        // Close modal buttons
        const modal = document.getElementById('api-keys-modal');
        if (modal) {
            const closeBtn = modal.querySelector('.auth-modal-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => this.hideModal());
            }

            // Click outside to close
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hideModal();
                }
            });
        }

        // Toggle visibility buttons
        document.querySelectorAll('.toggle-visibility').forEach(btn => {
            btn.addEventListener('click', () => {
                const targetId = btn.dataset.target;
                const input = document.getElementById(targetId);
                const icon = btn.querySelector('i');
                
                if (input.type === 'password') {
                    input.type = 'text';
                    icon.classList.remove('fa-eye');
                    icon.classList.add('fa-eye-slash');
                } else {
                    input.type = 'password';
                    icon.classList.remove('fa-eye-slash');
                    icon.classList.add('fa-eye');
                }
            });
        });

        // Form submission
        const form = document.getElementById('api-keys-form');
        if (form) {
            form.addEventListener('submit', (e) => this.handleSave(e));
        }

        // Clear button
        const clearBtn = document.getElementById('clear-api-keys');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.handleClear());
        }
    }

    showModal() {
        const modal = document.getElementById('api-keys-modal');
        if (modal) {
            // Load current keys into form
            this.loadKeysToForm();
            modal.style.display = 'flex';
        }
    }

    hideModal() {
        const modal = document.getElementById('api-keys-modal');
        if (modal) {
            modal.style.display = 'none';
            this.hideStatus();
        }
    }

    loadKeysToForm() {
        const openaiInput = document.getElementById('openai-api-key');
        const replicateInput = document.getElementById('replicate-api-token');
        
        if (openaiInput) openaiInput.value = this.cachedKeys.openai_api_key || '';
        if (replicateInput) replicateInput.value = this.cachedKeys.replicate_api_token || '';
    }

    // Get keys from localStorage (sync, fast)
    getKeysFromLocal() {
        try {
            const stored = localStorage.getItem(this.STORAGE_KEY);
            return stored ? JSON.parse(stored) : {};
        } catch (e) {
            console.error('Error loading API keys from localStorage:', e);
            return {};
        }
    }

    // Save keys to localStorage (sync)
    saveKeysToLocal(keys) {
        try {
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(keys));
            return true;
        } catch (e) {
            console.error('Error saving API keys to localStorage:', e);
            return false;
        }
    }

    // Public method to get keys (sync, returns cached)
    getKeys() {
        return this.cachedKeys;
    }

    handleSave(e) {
        e.preventDefault();
        
        const openaiKey = document.getElementById('openai-api-key').value.trim();
        const replicateToken = document.getElementById('replicate-api-token').value.trim();
        
        const keys = {};
        if (openaiKey) keys.openai_api_key = openaiKey;
        if (replicateToken) keys.replicate_api_token = replicateToken;
        
        this.saveKeysToLocal(keys);
        this.cachedKeys = keys;
        
        this.showStatus('success', 'API keys saved locally.');
        this.updateIndicator();
        
        // Close modal after a short delay
        setTimeout(() => {
            this.hideModal();
        }, 2000);
    }

    handleClear() {
        if (confirm('Are you sure you want to clear all API keys?')) {
            localStorage.removeItem(this.STORAGE_KEY);
            this.cachedKeys = {};
            
            this.loadKeysToForm();
            this.showStatus('success', 'All API keys have been cleared.');
            this.updateIndicator();
        }
    }

    showStatus(type, message) {
        const statusEl = document.getElementById('api-keys-status');
        if (statusEl) {
            statusEl.textContent = message;
            statusEl.className = 'api-keys-status ' + type;
        }
    }

    hideStatus() {
        const statusEl = document.getElementById('api-keys-status');
        if (statusEl) {
            statusEl.className = 'api-keys-status';
            statusEl.textContent = '';
        }
    }

    updateIndicator() {
        const hasKeys = this.cachedKeys.openai_api_key || this.cachedKeys.replicate_api_token;
        
        // Update the indicator in the dropdown menu
        const apiKeysBtn = document.getElementById('api-keys-btn');
        if (apiKeysBtn) {
            // Remove existing indicator
            const existingIndicator = apiKeysBtn.querySelector('.api-key-indicator');
            if (existingIndicator) {
                existingIndicator.remove();
            }
            
            // Add new indicator
            const indicator = document.createElement('span');
            indicator.className = 'api-key-indicator ' + (hasKeys ? 'configured' : 'not-configured');
            apiKeysBtn.appendChild(indicator);
        }
    }

    // Check if user has configured any API keys
    hasConfiguredKeys() {
        return !!(this.cachedKeys.openai_api_key || this.cachedKeys.replicate_api_token);
    }
}

// Initialize API Keys Manager when DOM is ready
let apiKeysManager;

document.addEventListener('DOMContentLoaded', () => {
    console.log('🔑 Initializing API Keys Manager...');
    apiKeysManager = new ApiKeysManager();
    window.apiKeysManager = apiKeysManager;
});
