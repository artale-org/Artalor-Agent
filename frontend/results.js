// -----------------------------------------------------------------------------
// © 2026 Artalor
// Artalor Project — All rights reserved.
// Licensed for personal and educational use only.
// Commercial use or redistribution prohibited.
// See LICENSE.md for full terms.
// -----------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    // Get DOM elements
    const loader = document.getElementById('loader');
    const modal = document.getElementById('fullscreen-modal');
    const modalContent = document.getElementById('modal-content');
    const closeBtn = document.querySelector('.close-btn');
    const projectStatus = document.getElementById('project-status');
    const previewContainer = document.getElementById('preview-container');
    // Version Management Elements
    const versionGrid = document.getElementById('version-grid');
    const applyVersionBtn = document.getElementById('apply-version-btn');
    const versionStatus = document.getElementById('version-status');
    // commandStatus DOM was removed from HTML. Keep a safe fallback so upload/export/delete
    // won't crash at runtime. Prefer a dedicated element if reintroduced; otherwise reuse versionStatus.
    const commandStatus = document.getElementById('command-status') || versionStatus;

    function setCommandStatus(message, color = '', clearAfterMs = 0) {
        if (!commandStatus) return;
        commandStatus.textContent = message || '';
        commandStatus.style.color = color || '';
        if (clearAfterMs && clearAfterMs > 0) {
            setTimeout(() => {
                if (commandStatus) commandStatus.textContent = '';
            }, clearAfterMs);
        }
    }
    
    // Track currently selected version in the grid
    let selectedVersionPath = null;
    
    const playPauseBtn = document.getElementById('play-pause');
    const timelineSlider = document.getElementById('timeline-slider');
    const timeDisplay = document.getElementById('time-display');
    const uploadAssetBtn = document.getElementById('upload-asset');
    const fileUpload = document.getElementById('file-upload');
    const refreshAssetsBtn = document.getElementById('refresh-assets');
    const exportBtn = document.getElementById('export-btn');
    const deleteAssetBtn = document.getElementById('delete-asset');
    const textPreviewPanel = document.getElementById('text-preview-panel');
    const textPreviewContent = document.getElementById('text-preview-content');
    const closeTextPreviewBtn = document.getElementById('close-text-preview');
    const regenerateBtn = document.getElementById('regenerate-btn');
    const rerunBtn = document.getElementById('rerun-btn');
    const stopBtn = document.getElementById('stop-btn');
    const continueBtn = document.getElementById('continue-btn');
    
    let isTextEdited = false;
    let currentEditableFile = null;
    let workflowRunning = false;  // Track if workflow is currently running
    
    // Asset grids container
    const assetCategoriesContainer = document.getElementById('asset-categories-container');
    
    // Counters - removed individual counters as they are now dynamic
    
    const urlParams = new URLSearchParams(window.location.search);
    const taskId = urlParams.get('task_id');
    const source = urlParams.get('source'); // 'showcase' or null
    
    // Create source parameter for API calls
    const sourceParam = source ? `?source=${source}` : '';

    if (!taskId) {
        projectStatus.textContent = 'No task ID provided';
        return;
    }

    // Determine if this is a showcase project from URL parameter
    let isShowcaseProject = (source === 'showcase');
    
    // Disable buttons immediately if it's a showcase project
    if (isShowcaseProject) {
        rerunBtn.disabled = true;
        rerunBtn.classList.remove('active');
        rerunBtn.title = 'Rerun is disabled for showcase projects';
        
        continueBtn.disabled = true;
        continueBtn.title = 'Continue is disabled for showcase projects';
        
        console.log('📌 Showcase project detected from URL - buttons disabled immediately');
    }
    
    console.log('🔍 Loading project:', taskId, source ? `(from ${source})` : '(from task_data)');

    // Global variables
    let displayedFiles = new Set();
    let polling = true;
    let currentPreviewElement = null;
    let selectedAsset = null;
    let currentAssetConfigPath = null; // Path to the currently loaded asset-specific config
    let segmentedMonologueData = null;
    let imageUnderstandingData = null;
    let productAnalysisData = null;
    let workflowConfigData = null;
    let modelsConfigData = null;
    
    // Pending config changes (not saved to JSON until Generate New Version is clicked)
    let pendingConfigChanges = {}; // { model: 'new_model', param1: value1, ... }
    let currentNodeType = null; // Track which node type is being configured
    let originalAssetConfig = null; // Store original config to show what's changed
    
    // Intersection Observer for lazy loading videos
    const videoObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const video = entry.target;
                // Load video metadata (first frame) when it comes into view
                if (video.tagName === 'VIDEO' && video.preload === 'none') {
                    video.preload = 'metadata';
                    observer.unobserve(video); // Stop observing once loaded
                }
            }
        });
    }, {
        rootMargin: '200px 0px' // Start loading when video is 200px away from viewport
    });
    
    // Workflow config panel elements
    const workflowConfigPanel = document.getElementById('workflow-config-panel');
    const workflowConfigContent = document.getElementById('workflow-config-content');
    const panelResizeHandle = document.getElementById('panel-resize-handle');

    // --- Collapsible sections + resize handle logic ---
    const assetDetailsHeader = document.getElementById('asset-details-header');
    const assetDetailsToggle = document.getElementById('asset-details-toggle');
    const workflowConfigToggleHeader = document.getElementById('workflow-config-toggle-header');
    const workflowConfigToggle = document.getElementById('workflow-config-toggle');

    let assetDetailsCollapsed = false;
    let workflowConfigCollapsed = false;

    // Sync resize handle: only visible when both section bodies are actually visible and expanded
    function syncResizeHandle() {
        const configVisible = workflowConfigPanel && workflowConfigPanel.style.display !== 'none';
        const detailsVisible = textPreviewContent && textPreviewContent.style.display !== 'none'
                               && !textPreviewContent.classList.contains('collapsed');
        const configExpanded = !workflowConfigCollapsed;
        if (panelResizeHandle) {
            panelResizeHandle.style.display = (configVisible && detailsVisible && configExpanded) ? 'flex' : 'none';
        }
    }

    // Wrapper: show/hide workflow config panel and always sync handle
    function setWorkflowConfigVisible(visible) {
        workflowConfigPanel.style.display = visible ? 'flex' : 'none';
        syncResizeHandle();
    }

    // Toggle Asset Details collapse
    if (assetDetailsHeader) {
        assetDetailsHeader.addEventListener('click', (e) => {
            if (e.target.closest('#close-text-preview')) return;
            assetDetailsCollapsed = !assetDetailsCollapsed;
            textPreviewContent.classList.toggle('collapsed', assetDetailsCollapsed);
            if (assetDetailsToggle) assetDetailsToggle.classList.toggle('collapsed', assetDetailsCollapsed);
            // Reset flex overrides from drag
            textPreviewContent.style.flex = '';
            workflowConfigPanel.style.flex = '';
            syncResizeHandle();
        });
    }

    // Toggle Workflow Config collapse
    if (workflowConfigToggleHeader) {
        workflowConfigToggleHeader.addEventListener('click', () => {
            workflowConfigCollapsed = !workflowConfigCollapsed;
            workflowConfigContent.classList.toggle('collapsed', workflowConfigCollapsed);
            workflowConfigPanel.classList.toggle('panel-collapsed', workflowConfigCollapsed);
            if (workflowConfigToggle) workflowConfigToggle.classList.toggle('collapsed', workflowConfigCollapsed);
            // Reset flex overrides from drag
            textPreviewContent.style.flex = '';
            workflowConfigPanel.style.flex = '';
            syncResizeHandle();
        });
    }

    // Resize drag logic (only active when both sections expanded)
    if (panelResizeHandle) {
        let isResizing = false;
        let startY = 0;
        let startTopH = 0;
        let startBottomH = 0;
        let totalH = 0;
        const MIN_TOP = 40;
        const MIN_BOTTOM = 60;

        panelResizeHandle.addEventListener('mousedown', (e) => {
            if (assetDetailsCollapsed || workflowConfigCollapsed) return;
            if (textPreviewContent.style.display === 'none') return;
            e.preventDefault();
            isResizing = true;
            startY = e.clientY;
            startTopH = textPreviewContent.getBoundingClientRect().height;
            startBottomH = workflowConfigPanel.getBoundingClientRect().height;
            totalH = startTopH + startBottomH;
            panelResizeHandle.classList.add('dragging');
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            const delta = e.clientY - startY;
            // Clamp so neither panel goes below its minimum
            let newTop = startTopH + delta;
            let newBottom = startBottomH - delta;
            if (newTop < MIN_TOP) { newTop = MIN_TOP; newBottom = totalH - MIN_TOP; }
            if (newBottom < MIN_BOTTOM) { newBottom = MIN_BOTTOM; newTop = totalH - MIN_BOTTOM; }
            textPreviewContent.style.flex = `0 0 ${newTop}px`;
            workflowConfigPanel.style.flex = `0 0 ${newBottom}px`;
        });

        document.addEventListener('mouseup', () => {
            if (!isResizing) return;
            isResizing = false;
            panelResizeHandle.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        });
    }

    // Modal handling
    closeBtn.onclick = () => modal.style.display = 'none';
    window.onclick = (event) => {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    };

    // Start polling for results
    const pollResults = setInterval(async () => {
        if (!polling) return;

        try {
            const resultsRes = await fetch(`/api/results/${taskId}${sourceParam}`);
            const resultsData = await resultsRes.json();
            updateAssets(resultsData);

            const statusRes = await fetch(`/api/status/${taskId}${sourceParam}`);
            const statusData = await statusRes.json();
            
            if (statusData.status === 'complete') {
                polling = false;
                clearInterval(pollResults);
                projectStatus.textContent = 'Complete';
                projectStatus.style.background = 'rgba(34, 197, 94, 0.2)';
                projectStatus.style.color = '#22c55e';
            } else {
                projectStatus.textContent = 'Processing...';
                projectStatus.style.background = 'rgba(251, 191, 36, 0.2)';
                projectStatus.style.color = '#fbbf24';
            }
        } catch (error) {
            console.error('Polling error:', error);
            projectStatus.textContent = 'Error';
            projectStatus.style.background = 'rgba(239, 68, 68, 0.2)';
            projectStatus.style.color = '#ef4444';
        }
    }, 3000);

    // Update assets in the workspace
    // This function handles data from data_version.json structure
    // Each item (image, video, voiceover) should only occupy ONE slot
    // - If curr_version exists: show the actual file
    // - If curr_version is null/empty: show a pending placeholder
    function updateAssets(data) {
        const structure = data.structure || {};
        
        // Debug: Log the is_showcase flag
        console.log('📊 API Response - is_showcase:', data.is_showcase, 'Type:', typeof data.is_showcase);
        
        // Check if this is a showcase project and disable modification buttons
        if (data.is_showcase !== undefined) {
            isShowcaseProject = data.is_showcase;
            
            if (isShowcaseProject) {
                // Disable rerun and continue buttons for showcase projects
                rerunBtn.disabled = true;
                rerunBtn.classList.remove('active');
                rerunBtn.title = 'Rerun is disabled for showcase projects';
                
                continueBtn.disabled = true;
                continueBtn.title = 'Continue is disabled for showcase projects';
                
                console.log('📌 Showcase project detected - modification buttons disabled');
            } else {
                // Enable rerun button for regular projects
                rerunBtn.disabled = false;
                rerunBtn.classList.add('active');
                rerunBtn.title = '';
                
                console.log('✅ Regular project - rerun button enabled');
            }
        }
        
        // Check if we have any files to hide loader
        let hasFiles = false;
        if (Object.keys(structure).length > 0) {
            hasFiles = true;
            loader.style.display = 'none';
            const emptyState = document.getElementById('empty-state');
            if (emptyState) emptyState.remove();
        } else if (data.uploaded_images && data.uploaded_images.length > 0) {
            // Fallback for old API response format
            loader.style.display = 'none';
            const emptyState = document.getElementById('empty-state');
            if (emptyState) emptyState.remove();
        } else {
            // Show empty state if loading is done but no files
            loader.style.display = 'none';
            if (!document.getElementById('empty-state')) {
                 const emptyState = document.createElement('div');
                 emptyState.id = 'empty-state';
                 emptyState.style.padding = '40px 20px';
                 emptyState.style.textAlign = 'center';
                 emptyState.style.color = '#9ca3af';
                 emptyState.innerHTML = '<i class="fas fa-folder-open" style="font-size: 2.5em; margin-bottom: 15px; display: block;"></i><p>No assets found in this task.</p>';
                 assetCategoriesContainer.appendChild(emptyState);
            }
        }

        // --- Stable per-grid sorting (fixed order, never depends on backend return order) ---
        // Desired order for every grid:
        // 1) image_first, 2) image_last, 3) other images, 4) audio, 5) video, 6) others
        const _extractVersionNum = (s) => {
            if (!s || typeof s !== 'string') return -1;
            const m = s.match(/_v(\d+)(?=\.[^.]+$)/i);
            return m ? parseInt(m[1], 10) : -1;
        };

        const _inferExt = (s) => {
            if (!s || typeof s !== 'string') return '';
            const base = s.split('?')[0];
            const idx = base.lastIndexOf('.');
            return idx >= 0 ? base.slice(idx + 1).toLowerCase() : '';
        };

        const _assetRank = (fileObj) => {
            const itemKey = (fileObj && (fileObj.item_key || fileObj.name)) ? String(fileObj.item_key || fileObj.name).toLowerCase() : '';
            const path = (fileObj && fileObj.path) ? String(fileObj.path).toLowerCase() : '';
            const type = (fileObj && fileObj.type) ? String(fileObj.type).toLowerCase() : '';
            const ext = _inferExt(path || itemKey);

            const isImg = type === 'img' || ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'].includes(ext) || itemKey.includes('image_') || path.includes('/image_');
            const isAudio = type === 'audio' || ['mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg'].includes(ext) || itemKey.includes('voiceover') || itemKey.includes('bgm') || path.includes('voiceover') || path.includes('bgm');
            const isVideo = type === 'video' || ['mp4', 'mov', 'webm', 'mkv'].includes(ext) || itemKey.includes('video') || path.includes('/video');

            if (isImg) {
                if (itemKey.includes('image_first') || path.includes('image_first')) return 0;
                if (itemKey.includes('image_last') || path.includes('image_last')) return 1;
                return 2;
            }
            if (isAudio) return 3;
            if (isVideo) return 4;
            return 5;
        };

        const _assetStableKey = (fileObj) => {
            const a = (fileObj && (fileObj.item_key || fileObj.name)) ? String(fileObj.item_key || fileObj.name) : '';
            const b = (fileObj && fileObj.path) ? String(fileObj.path) : '';
            return (a || b).toLowerCase();
        };

        const _assetGridComparator = (a, b) => {
            const ra = _assetRank(a);
            const rb = _assetRank(b);
            if (ra !== rb) return ra - rb;

            // Same group: prefer lower version number first for stability, then name/path
            const va = _extractVersionNum((a && (a.name || a.path)) ? String(a.name || a.path) : '');
            const vb = _extractVersionNum((b && (b.name || b.path)) ? String(b.name || b.path) : '');
            if (va !== vb) return va - vb;

            return _assetStableKey(a).localeCompare(_assetStableKey(b));
        };

        // Process each folder in the structure
        // Sort keys to ensure consistent order (upload/character_reference first, then final_videos, then others)
        const folderNames = Object.keys(structure).sort((a, b) => {
            // specific priority: upload/character_reference first, then final_videos
            if (a === 'upload' || a === 'character_reference') return -1;
            if (b === 'upload' || b === 'character_reference') return 1;
            if (a === 'final_videos') return -1;
            if (b === 'final_videos') return 1;
            return a.localeCompare(b);
        });

        folderNames.forEach(folderName => {
            const files = structure[folderName] || [];
            const sortedFiles = Array.isArray(files) ? [...files].sort(_assetGridComparator) : [];
            
            // Find or create category container
            let categoryId = `category-${folderName.replace(/[^a-zA-Z0-9-_]/g, '-')}`;
            let categoryEl = document.getElementById(categoryId);
            let gridEl;
            let countEl;
            
            if (!categoryEl) {
                // Create new category
                categoryEl = document.createElement('div');
                categoryEl.className = 'asset-category';
                categoryEl.id = categoryId;
                
                // Choose icon based on folder name
                let iconClass = 'fas fa-folder';
                const lowerName = folderName.toLowerCase();
                if (lowerName === 'upload') iconClass = 'fas fa-cloud-upload-alt';
                else if (lowerName === 'character_reference') iconClass = 'fas fa-user';
                else if (lowerName === 'final_videos' || lowerName === 'output') iconClass = 'fas fa-film';
                else if (lowerName.includes('image')) iconClass = 'fas fa-images';
                else if (lowerName.includes('video')) iconClass = 'fas fa-video';
                else if (lowerName.includes('audio')) iconClass = 'fas fa-music';
                
                // Format folder name for display
                let displayName;
                if (lowerName === 'upload') {
                    displayName = 'User Upload';
                } else if (lowerName === 'character_reference') {
                    displayName = 'Character';
                } else {
                    displayName = folderName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                }
                
                categoryEl.innerHTML = `
                    <div class="category-header" data-category="${categoryId}">
                        <div class="category-header-left">
                            <i class="category-toggle fas fa-chevron-down"></i>
                            <i class="${iconClass}"></i>
                            <span>${displayName}</span>
                        </div>
                        <span class="category-count">0</span>
                    </div>
                    <div class="asset-grid" id="grid-${categoryId}"></div>
                `;
                
                assetCategoriesContainer.appendChild(categoryEl);
            }
            
            gridEl = categoryEl.querySelector('.asset-grid');
            countEl = categoryEl.querySelector('.category-count');
            
            // Process files in this folder (in fixed, stable order)
            // Use a unique key based on group_key + item_key to track each slot
            sortedFiles.forEach(fileObj => {
                // Create a unique slot key for this asset (e.g., "sub_video_1_image")
                const slotKey = `${fileObj.group_key || folderName}_${fileObj.item_key || fileObj.name}`;
                const isPlaceholder = fileObj.is_placeholder === true;
                const filePath = fileObj.path;
                
                // Check if we already have an element for this slot
                const existingItem = gridEl.querySelector(`[data-slot-key="${slotKey}"]`);
                
                if (existingItem) {
                    // Slot already exists - check if we need to update it
                    const wasPlaceholder = existingItem.classList.contains('placeholder');
                    
                    if (wasPlaceholder && !isPlaceholder) {
                        // Transition from placeholder to actual file
                        // Remove the old placeholder and create the actual asset
                        displayedFiles.delete(existingItem.dataset.file);
                        existingItem.remove();
                        displayedFiles.add(filePath);
                        const isFinal = folderName === 'final_videos' || folderName === 'final_video';
                        createAssetItem(filePath, fileObj.type, gridEl, isFinal, fileObj, slotKey);
                    } else if (!wasPlaceholder && isPlaceholder) {
                        // Transition from actual file to placeholder (file was deleted)
                        displayedFiles.delete(existingItem.dataset.file);
                        existingItem.remove();
                        displayedFiles.add(filePath);
                        const isFinal = folderName === 'final_videos' || folderName === 'final_video';
                        createAssetItem(filePath, fileObj.type, gridEl, isFinal, fileObj, slotKey);
                    } else if (!wasPlaceholder && !isPlaceholder) {
                        // Both are actual files - check if the path changed (version update)
                        if (existingItem.dataset.file !== filePath) {
                            displayedFiles.delete(existingItem.dataset.file);
                            existingItem.remove();
                            displayedFiles.add(filePath);
                            const isFinal = folderName === 'final_videos' || folderName === 'final_video';
                            createAssetItem(filePath, fileObj.type, gridEl, isFinal, fileObj, slotKey);
                        } else {
                            // Same file, just update fileData in case historical_versions changed
                            existingItem.fileData = fileObj;
                            // Update dirty badge state for existing real items
                            const wasDirty = existingItem.classList.contains('dirty');
                            const isDirtyNow = fileObj.is_dirty === true;
                            if (wasDirty !== isDirtyNow) {
                                if (isDirtyNow) {
                                    existingItem.classList.add('dirty');
                                    if (!existingItem.querySelector('.dirty-badge')) {
                                        const dirtyBadge = document.createElement('div');
                                        dirtyBadge.className = 'dirty-badge';
                                        dirtyBadge.innerHTML = '<i class="fas fa-sync-alt"></i>';
                                        dirtyBadge.title = 'Update available - needs rerun';
                                        existingItem.appendChild(dirtyBadge);
                                    }
                                } else {
                                    existingItem.classList.remove('dirty');
                                    const badge = existingItem.querySelector('.dirty-badge');
                                    if (badge) badge.remove();
                                }
                            }
                        }
                    } else if (wasPlaceholder && isPlaceholder) {
                        // Placeholder -> Placeholder (check dirty status change)
                        existingItem.fileData = fileObj; // Update data
                        
                        const wasDirty = existingItem.classList.contains('dirty');
                        const isDirty = fileObj.is_dirty === true;
                        
                        if (wasDirty !== isDirty) {
                            if (isDirty) {
                                existingItem.classList.add('dirty');
                                if (!existingItem.querySelector('.dirty-badge')) {
                                    const dirtyBadge = document.createElement('div');
                                    dirtyBadge.className = 'dirty-badge';
                                    dirtyBadge.innerHTML = '<i class="fas fa-sync-alt"></i>';
                                    dirtyBadge.title = 'Update available - needs rerun';
                                    existingItem.appendChild(dirtyBadge);
                                }
                            } else {
                                existingItem.classList.remove('dirty');
                                const badge = existingItem.querySelector('.dirty-badge');
                                if (badge) badge.remove();
                            }
                        }
                    }
                    // If both are placeholders and dirty status unchanged, do nothing
                } else {
                    // New slot - create the asset item
                    if (!displayedFiles.has(filePath)) {
                        displayedFiles.add(filePath);
                        const isFinal = folderName === 'final_videos' || folderName === 'final_video';
                        createAssetItem(filePath, fileObj.type, gridEl, isFinal, fileObj, slotKey);
                    }
                }
            });

            // After updates/creates/removals, enforce deterministic DOM order for this grid.
            // This prevents reordering when backend return order changes (e.g. after Apply Selected Version).
            const slotMap = new Map();
            Array.from(gridEl.children).forEach((el) => {
                if (el && el.dataset && el.dataset.slotKey) {
                    slotMap.set(el.dataset.slotKey, el);
                }
            });
            const desiredSlotKeys = sortedFiles.map(f => `${f.group_key || folderName}_${f.item_key || f.name}`);
            desiredSlotKeys.forEach((sk) => {
                const el = slotMap.get(sk);
                if (el) gridEl.appendChild(el);
            });
            
            // Update count - count actual items displayed, not placeholders
            const actualCount = sortedFiles.filter(f => !f.is_placeholder).length;
            const totalCount = sortedFiles.length;
            countEl.textContent = `${actualCount}/${totalCount}`;
        });
    }

    function processAssets(files, mediaType, container, counter, isFinalVideo = false) {
        // Deprecated function kept for compatibility if needed, but updateAssets now handles logic directly
        // Logic moved to updateAssets loop
    }

    function createAssetItem(file, mediaType, container, isFinalVideo = false, fileObj = null, slotKey = null) {
        const item = document.createElement('div');
        item.className = 'asset-item';
        item.dataset.file = file;
        item.dataset.type = mediaType;
        // Store slot key for tracking asset updates
        if (slotKey) {
            item.dataset.slotKey = slotKey;
        }
        // Store full file object for version management
        item.fileData = fileObj;
        
        const isPlaceholder = fileObj && fileObj.is_placeholder;
        const isDirty = !!(fileObj && fileObj.is_dirty === true);
        
        if (isPlaceholder) {
            item.classList.add('placeholder');
            item.style.opacity = '0.6';
            item.style.cursor = 'pointer'; // Make clickable
            item.style.border = '1px dashed #ccc';
            item.style.background = '#f9fafb';
        }
        
        if (isFinalVideo) {
            item.dataset.isFinalVideo = 'true'; // Mark final videos
        }
        // Create filename overlay at bottom
        const filenameOverlay = document.createElement('div');
        filenameOverlay.className = 'asset-filename';
        // Use provided name for placeholders or regular files if available, otherwise parse path
        filenameOverlay.textContent = (fileObj && fileObj.name) ? fileObj.name : getFileName(file);
        item.appendChild(filenameOverlay);

        if (isPlaceholder) {
            // Placeholder content
            const placeholderIcon = document.createElement('div');
            placeholderIcon.style.cssText = 'display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: #9ca3af;';
            
            let iconClass = 'fas fa-file';
            if (mediaType === 'img') iconClass = 'fas fa-image';
            else if (mediaType === 'video') iconClass = 'fas fa-video';
            else if (mediaType === 'audio') iconClass = 'fas fa-music';
            
            // Add dirty badge to placeholder if dirty
            if (isDirty) {
                const dirtyBadge = document.createElement('div');
                dirtyBadge.className = 'dirty-badge';
                dirtyBadge.innerHTML = '<i class="fas fa-sync-alt"></i>';
                dirtyBadge.title = 'Update available - needs rerun';
                item.appendChild(dirtyBadge);
                item.classList.add('dirty');
            }
            
            placeholderIcon.innerHTML = `<i class="${iconClass}" style="font-size: 24px; margin-bottom: 8px;"></i><span style="font-size: 12px;">Pending</span>`;
            item.appendChild(placeholderIcon);
            
            // Add click handler for placeholders to enable config/regeneration
            item.addEventListener('click', () => selectPlaceholder(item, file, mediaType, fileObj));
            
            container.appendChild(item);
            return;
        }

        // Add dirty badge to REAL asset items too (not only placeholders)
        if (isDirty) {
            const dirtyBadge = document.createElement('div');
            dirtyBadge.className = 'dirty-badge';
            dirtyBadge.innerHTML = '<i class="fas fa-sync-alt"></i>';
            dirtyBadge.title = 'Update available - needs rerun';
            item.appendChild(dirtyBadge);
            item.classList.add('dirty');
        }

        // Create thumbnail or preview
        if (mediaType === 'img') {
            const img = document.createElement('img');
            img.src = `../projects/${file}`;
            img.alt = getFileName(file);
            img.loading = 'lazy';
            item.appendChild(img);
        } else if (mediaType === 'video') {
            const video = document.createElement('video');
            video.src = `../projects/${file}`;
            video.muted = true;
            video.preload = 'none'; // Prevent auto-loading video data initially
            
            // Observe the video for lazy loading
            videoObserver.observe(video);
            
            // Add video icon overlay
            const typeIcon = document.createElement('div');
            typeIcon.className = 'asset-type';
            typeIcon.innerHTML = '<i class="fas fa-play"></i>';
            item.appendChild(typeIcon);
            
            // Load on hover for better UX (immediate feedback)
            item.addEventListener('mouseenter', () => {
                if (video.readyState === 0 && video.networkState === 0) { // HAVE_NOTHING and EMPTY
                    video.preload = 'metadata';
                }
            });
            
            item.appendChild(video);
        } else if (mediaType === 'audio') {
            // Audio placeholder with icon
            const audioIcon = document.createElement('div');
            audioIcon.style.cssText = 'display: flex; align-items: center; justify-content: center; height: 100%; font-size: 24px; color: #666;';
            audioIcon.innerHTML = '<i class="fas fa-music"></i>';
            item.appendChild(audioIcon);
            
            const typeIcon = document.createElement('div');
            typeIcon.className = 'asset-type';
            typeIcon.innerHTML = '<i class="fas fa-volume-up"></i>';
            item.appendChild(typeIcon);
        }

        // Add click handler for preview
        item.addEventListener('click', () => selectAsset(item, file, mediaType));
        
        container.appendChild(item);
    }

    async function selectPlaceholder(item, file, mediaType, fileObj) {
        // Remove previous selection
        document.querySelectorAll('.asset-item.selected').forEach(el => {
            el.classList.remove('selected');
        });
        
        // Select current placeholder item
        item.classList.add('selected');
        
        // Construct a real file path from taskId + group_key + item_key
        // Placeholder's file is "placeholder_xxx" which is useless for config loading and regeneration.
        // Build: "{taskId}/{group_key}/{item_key}_v0.{ext}"
        const groupKey = fileObj?.group_key || '';
        const itemKey = fileObj?.item_key || '';
        let ext = 'mp4';
        if (mediaType === 'img') ext = 'png';
        else if (mediaType === 'audio') ext = 'mp3';
        const resolvedFile = `${taskId}/${groupKey}/${itemKey}_v0.${ext}`;
        console.log(`🔍 Placeholder resolved path: ${file} → ${resolvedFile}`);
        
        // Detect if this placeholder is a final video
        const isFinalVideo = item.dataset.isFinalVideo === 'true';
        
        // Keep a stable reference for regeneration
        selectedAsset = {
            file: resolvedFile,
            mediaType,
            isFinalVideo: isFinalVideo,
            fileData: fileObj,
            slotKey: item.dataset.slotKey || null,
            element: item,
            isPlaceholder: true
        };
        
        // Reset panel resize and collapse state (same as selectAsset)
        textPreviewContent.style.flex = '';
        workflowConfigPanel.style.flex = '';
        assetDetailsCollapsed = false;
        workflowConfigCollapsed = false;
        textPreviewContent.classList.remove('collapsed');
        workflowConfigContent.classList.remove('collapsed');
        workflowConfigPanel.classList.remove('panel-collapsed');
        if (assetDetailsToggle) assetDetailsToggle.classList.remove('collapsed');
        if (workflowConfigToggle) workflowConfigToggle.classList.remove('collapsed');
        
        // Clear preview (no content to show for placeholder)
        const placeholderIcon = mediaType === 'video' ? 'fa-video' : 
                               mediaType === 'img' ? 'fa-image' : 'fa-music';
        const placeholderText = mediaType === 'video' ? 'Video' :
                               mediaType === 'img' ? 'Image' : 'Audio';
        previewContainer.innerHTML = `<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: #9ca3af;"><i class="fas ${placeholderIcon}" style="font-size: 48px; margin-bottom: 16px;"></i><p style="font-size: 14px;">${placeholderText} not generated yet</p><p style="font-size: 12px; color: #6b7280;">Configure settings and click "Generate New Version"</p></div>`;
        document.querySelector('.preview-controls').style.display = 'none';
        
        // Show loading state initially
        textPreviewContent.innerHTML = '<div style="padding:20px; text-align:center; color:#666;"><i class="fas fa-spinner fa-spin"></i> Loading details...</div>';
        workflowConfigContent.innerHTML = '<div style="padding:20px; text-align:center; color:#666;"><i class="fas fa-spinner fa-spin"></i> Loading config...</div>';
        textPreviewPanel.style.display = 'flex';
        
        // Update Version Management UI
        updateVersionUI(fileObj);
        
        // Determine node type and load asset details using the resolved path
        let nodeType = null;
        if (isFinalVideo) {
            nodeType = 'edit';
            await showVideoTextPreview(resolvedFile, true);
        } else if (mediaType === 'video') {
            nodeType = 'video_generation';
            await showVideoTextPreview(resolvedFile, false);
        } else if (mediaType === 'img') {
            nodeType = 'image_generation';
            await showImageTextPreview(resolvedFile);
        } else if (mediaType === 'audio') {
            if (itemKey.includes('bgm') || groupKey.includes('audio')) {
                nodeType = 'bgm';
                await showBGMTextPreview(resolvedFile);
            } else {
                nodeType = 'segmented_tts';
                await showAudioTextPreview(resolvedFile);
            }
        }
        
        // For placeholders, always enable "Generate New Version" button
        regenerateBtn.disabled = false;
        regenerateBtn.classList.add('active');
        regenerateBtn.style.display = '';
        
        // If no node type was determined, show fallback message
        if (!nodeType) {
            textPreviewContent.innerHTML = '<div style="padding:20px; text-align:center; color:#666;">No details available for this asset type.</div>';
            workflowConfigContent.innerHTML = '<div style="padding:20px; text-align:center; color:#666;">No configuration available for this asset type.</div>';
        }
    }

    function selectAsset(item, file, mediaType) {
        // Remove previous selection
        document.querySelectorAll('.asset-item.selected').forEach(el => {
            el.classList.remove('selected');
        });
        
        // Select current item
        item.classList.add('selected');
        const isFinalVideo = item.dataset.isFinalVideo === 'true';
        // Keep a stable reference for polling/refresh after regeneration
        selectedAsset = {
            file,
            mediaType,
            isFinalVideo,
            fileData: item.fileData,
            slotKey: item.dataset.slotKey || null,
            element: item
        };
        
        // Reset panel resize and collapse state
        textPreviewContent.style.flex = '';
        workflowConfigPanel.style.flex = '';
        assetDetailsCollapsed = false;
        workflowConfigCollapsed = false;
        textPreviewContent.classList.remove('collapsed');
        workflowConfigContent.classList.remove('collapsed');
        workflowConfigPanel.classList.remove('panel-collapsed');
        if (assetDetailsToggle) assetDetailsToggle.classList.remove('collapsed');
        if (workflowConfigToggle) workflowConfigToggle.classList.remove('collapsed');
        
        // Clear panel content immediately to prevent showing stale data
        textPreviewContent.innerHTML = '<div style="padding:20px; text-align:center; color:#666;"><i class="fas fa-spinner fa-spin"></i> Loading details...</div>';
        workflowConfigContent.innerHTML = '<div style="padding:20px; text-align:center; color:#666;"><i class="fas fa-spinner fa-spin"></i> Loading config...</div>';
        // Ensure panel is visible so loading state is seen (unless it's a type we don't support)
        if (mediaType === 'audio' || mediaType === 'video' || mediaType === 'img') {
            textPreviewPanel.style.display = 'flex';
        }
        
        // Update Version Management UI
        updateVersionUI(item.fileData);
        
        // Update preview
        updatePreview(file, mediaType);
        
        // Show text preview based on media type
        if (mediaType === 'audio') {
            showAudioTextPreview(file);
        } else if (mediaType === 'video') {
            showVideoTextPreview(file, isFinalVideo);
        } else if (mediaType === 'img') {
            // Check if this is an uploaded image (from upload folder) or character reference
            if (file.includes('/upload/') || file.startsWith('upload/')) {
                showUploadedImagePreview(file);
            } else if (file.includes('/character_reference/') || file.startsWith('character_reference/')) {
                showCharacterImagePreview(file);
            } else {
                showImageTextPreview(file);
            }
        } else {
            // Hide text preview for other media types
            textPreviewPanel.style.display = 'none';
        }
    }

    function updatePreview(file, mediaType) {
        // 1. Stop any currently playing media and clear listeners
        if (currentPreviewElement && typeof currentPreviewElement.pause === 'function') {
            currentPreviewElement.pause();
            currentPreviewElement.src = ''; // Detach source
        }

        // 2. Clear the entire preview container and reset state
        previewContainer.innerHTML = '';
        currentPreviewElement = null;
        timelineSlider.value = 0;
        timelineSlider.max = 100;
        timeDisplay.textContent = '00:00 / 00:00';
        playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';

        // 3. Setup the new element
        if (mediaType === 'img') {
            document.querySelector('.preview-controls').style.display = 'none';
            const img = document.createElement('img');
            img.src = `../projects/${file}`;
            img.alt = getFileName(file);
            previewContainer.appendChild(img);
            currentPreviewElement = img;
        } else if (mediaType === 'video' || mediaType === 'audio') {
            // Show controls immediately for playable media
            document.querySelector('.preview-controls').style.display = 'flex';

            const mediaElement = document.createElement(mediaType);
            currentPreviewElement = mediaElement;

            if (mediaType === 'audio') {
                // For audio, create a visual placeholder
                const audioViz = document.createElement('div');
                audioViz.style.cssText = 'display: flex; align-items: center; justify-content: center; height: 200px; font-size: 64px; color: #666;';
                audioViz.innerHTML = '<i class="fas fa-music"></i>';
                previewContainer.appendChild(audioViz);
                mediaElement.style.display = 'none';
            }

            previewContainer.appendChild(mediaElement);

            // Event listeners
            mediaElement.addEventListener('loadedmetadata', () => {
                timelineSlider.max = mediaElement.duration;
                updateTimeDisplay(mediaElement);
                mediaElement.play().catch(e => console.log('Autoplay was prevented.', e));
            });

            mediaElement.addEventListener('timeupdate', () => {
                if (!isSeeking) {
                    timelineSlider.value = mediaElement.currentTime;
                    updateTimeDisplay(mediaElement);
                }
            });

            mediaElement.addEventListener('play', () => {
                playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
            });

            mediaElement.addEventListener('pause', () => {
                playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
            });

            mediaElement.addEventListener('ended', () => {
                playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
                mediaElement.currentTime = 0;
                timelineSlider.value = 0;
                updateTimeDisplay(mediaElement);
            });

            mediaElement.addEventListener('error', (e) => {
                console.error(`${mediaType} Error:`, e);
            });

            // Set source and load
            mediaElement.src = `../projects/${file}`;
            mediaElement.load();
        }
    }

    function updateTimeDisplay(mediaElement) {
        const currentTime = mediaElement.currentTime || 0;
        const duration = mediaElement.duration || 0;
        
        // Handle NaN values
        const current = formatTime(isNaN(currentTime) ? 0 : currentTime);
        const total = formatTime(isNaN(duration) ? 0 : duration);
        
        timeDisplay.textContent = `${current} / ${total}`;
        
        // Debug log for video issues
        if (mediaElement.tagName === 'VIDEO') {
            console.log('Video time update:', { currentTime, duration, current, total });
        }
    }

    function formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    function getFileName(filePath) {
        return filePath.includes('/') ? filePath.split('/').pop() : filePath;
    }

    // Media controls
    playPauseBtn.addEventListener('click', () => {
        if (currentPreviewElement && (currentPreviewElement.tagName === 'VIDEO' || currentPreviewElement.tagName === 'AUDIO')) {
            if (currentPreviewElement.paused) {
                currentPreviewElement.play().then(() => {
                    playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
                }).catch(error => {
                    console.log('Play failed:', error);
                    playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
                });
            } else {
                currentPreviewElement.pause();
                playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
            }
        }
    });

    // Enhanced timeline controls with seeking
    let isSeeking = false;
    
    timelineSlider.addEventListener('mousedown', () => {
        isSeeking = true;
    });
    
    timelineSlider.addEventListener('mouseup', () => {
        isSeeking = false;
    });
    
    timelineSlider.addEventListener('input', () => {
        if (currentPreviewElement && (currentPreviewElement.tagName === 'VIDEO' || currentPreviewElement.tagName === 'AUDIO')) {
            const seekTime = parseFloat(timelineSlider.value);
            currentPreviewElement.currentTime = seekTime;
            updateTimeDisplay(currentPreviewElement);
        }
    });
    
    timelineSlider.addEventListener('change', () => {
        if (currentPreviewElement && (currentPreviewElement.tagName === 'VIDEO' || currentPreviewElement.tagName === 'AUDIO')) {
            const seekTime = parseFloat(timelineSlider.value);
            currentPreviewElement.currentTime = seekTime;
            updateTimeDisplay(currentPreviewElement);
        }
    });

    // Version Management Logic
    async function refreshRightPanelForVersion(versionPath, isCurrentVersion) {
        if (!selectedAsset) return;

        // Always update preview first
        updatePreview(versionPath, selectedAsset.mediaType);

        // Update right-side text/config panels to match the selected version
        try {
            if (selectedAsset.mediaType === 'audio') {
                await showAudioTextPreview(versionPath);
            } else if (selectedAsset.mediaType === 'video') {
                await showVideoTextPreview(versionPath, selectedAsset.isFinalVideo);
            } else if (selectedAsset.mediaType === 'img') {
                await showImageTextPreview(versionPath);
            }
        } finally {
            // Do not show any hint text; keep UI clean.
            setRightPanelReadOnlyMode(!isCurrentVersion);
        }
    }

    function setRightPanelReadOnlyMode(isReadOnly) {
        // Final videos: keep regenerate button visible and enabled, just clear status.
        if (selectedAsset && selectedAsset.isFinalVideo) {
            versionStatus.textContent = '';
            // Ensure regenerate button stays visible and enabled for final videos
            regenerateBtn.style.display = '';
            regenerateBtn.disabled = false;
            regenerateBtn.classList.add('active');
            return;
        }

        // Keep status area blank unless there's a real error (e.g., apply version failed).
        versionStatus.textContent = '';
        versionStatus.style.color = '';
    }

    function updateVersionUI(fileData) {
        // Clear existing grid
        versionGrid.innerHTML = '';
        versionStatus.textContent = '';
        applyVersionBtn.disabled = true;
        selectedVersionPath = null; // Reset local selection state
        
        if (!fileData || !fileData.historical_versions || fileData.historical_versions.length === 0) {
            versionGrid.innerHTML = '<div class="version-placeholder" style="grid-column: 1 / -1; text-align: center; color: #9ca3af; padding: 10px; font-style: italic;">No versions available</div>';
            return;
        }
        
        // Add historical versions as buttons
        fileData.historical_versions.forEach((verPath, index) => {
            const btn = document.createElement('button');
            btn.className = 'version-btn';
            
            // Extract filename for better display
            const filename = verPath.split('/').pop();
            const isCurrent = verPath === fileData.path;
            const isLastRun = !!(fileData.last_run_version && verPath === fileData.last_run_version);
            
            // 从文件名中提取真实版本号 (例如 image_v5.png -> V5)，而不是按顺序生成索引
            const versionMatch = filename.match(/_v(\d+)\./);
            const labelText = versionMatch ? `V${versionMatch[1]}` : `V${index + 1}`;
            
            // Use different icon based on state
            const iconClass = isCurrent ? 'fas fa-check-circle' : 'fas fa-history';
            
            btn.innerHTML = `<i class="${iconClass}"></i> ${labelText}`;
            btn.title = isCurrent ? `Current Version: ${filename}` : `History: ${filename}`;

            if (isLastRun) {
                btn.classList.add('last-run-version');
                btn.title = `${btn.title}\nLast workflow run`;
            }
            
            // Highlight current version initially if no selection made yet, or if it matches selection
            // But strict logic: active-version marks the "Current" one in backend.
            // selected-version marks the one user clicked to preview.
            
            if (isCurrent) {
                btn.classList.add('active-version');
            }
            
            // If this button matches the currently selected preview path, mark it as selected
            if (selectedVersionPath === verPath) {
                btn.classList.add('selected-version');
            } else if (!selectedVersionPath && isCurrent) {
                // Initial state: current version is selected
                btn.classList.add('selected-version');
                selectedVersionPath = verPath;
            }
            
            // Click handler
            btn.addEventListener('click', async () => {
                // Update UI selection
                document.querySelectorAll('.version-btn').forEach(b => {
                    b.classList.remove('selected-version');
                });
                
                // Style clicked button as selected
                btn.classList.add('selected-version');
                
                selectedVersionPath = verPath;
                
                // Update preview + right-side content immediately (must match selected version)
                if (selectedAsset) {
                    await refreshRightPanelForVersion(verPath, isCurrent);
                }
                
                // Enable apply button
                applyVersionBtn.disabled = false;
            });
            
            versionGrid.appendChild(btn);
        });
    }

    // Apply Version Handler
    applyVersionBtn.addEventListener('click', async () => {
        if (!selectedAsset || !selectedAsset.fileData || !selectedVersionPath) return;
        
        // Save current selection keys to restore after refresh
        const currentGroupKey = selectedAsset.fileData.group_key;
        const currentItemKey = selectedAsset.fileData.item_key;
        const currentType = selectedAsset.mediaType;
        const targetVersionPath = selectedVersionPath; // Keep this to potentially force update UI
        
        const fileData = selectedAsset.fileData;
        const newVersionPath = selectedVersionPath;
        
        applyVersionBtn.disabled = true;
        applyVersionBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Applying...';
        
        try {
            const response = await fetch(`/api/set_version/${taskId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    group_key: fileData.group_key,
                    item_key: fileData.item_key,
                    version_path: newVersionPath
                })
            });
            
            const result = await response.json();
            
            if (response.ok) {
                // Success: do NOT show any success text (user requested no success indicator)
                versionStatus.textContent = '';
                
                // Refresh assets AND restore selection
                // We need to wait for refresh to complete before selecting
                
                // 0. Clear existing assets to force full re-render
                displayedFiles.clear();
                assetCategoriesContainer.innerHTML = '';

                // 1. Perform fetch and update with cache busting
                const resultsRes = await fetch(`/api/results/${taskId}${sourceParam}${sourceParam ? '&' : '?'}t=${Date.now()}`);
                const resultsData = await resultsRes.json();
                
                // 2. Update DOM
                updateAssets(resultsData);
                
                // 3. Find the previously selected item in the new DOM and re-select it
                setTimeout(() => {
                    const assetItems = document.querySelectorAll('.asset-item');
                    let targetItem = null;
                    
                    for (const item of assetItems) {
                        if (item.fileData && 
                            item.fileData.group_key === currentGroupKey && 
                            item.fileData.item_key === currentItemKey) {
                            targetItem = item;
                            break;
                        }
                    }
                    
                    if (targetItem) {
                        // Re-select to update UI
                        const isFinal = targetItem.dataset.isFinalVideo === 'true';
                        
                        // Crucial: update selectedAsset with the NEW fileData which has the updated 'path' (current version)
                        // The selectAsset function will then call updateVersionUI with this new data
                        selectAsset(targetItem, targetItem.dataset.file, currentType);
                    }
                    
                    versionStatus.textContent = '';
                    applyVersionBtn.innerHTML = '<i class="fas fa-check"></i> Apply Selected Version';
                    // Disable button since we just applied it
                    applyVersionBtn.disabled = true; 
                    
                }, 100); // Small delay to ensure DOM is ready
                
            } else {
                throw new Error(result.error || 'Failed to update version');
            }
        } catch (error) {
            console.error('Version update error:', error);
            versionStatus.textContent = 'Error updating version';
            versionStatus.style.color = '#ef4444';
            applyVersionBtn.innerHTML = '<i class="fas fa-check"></i> Apply Selected Version';
            applyVersionBtn.disabled = false;
        }
    });

    // File upload
    uploadAssetBtn.addEventListener('click', () => {
        fileUpload.click();
    });

    fileUpload.addEventListener('change', (e) => {
        const files = Array.from(e.target.files);
        if (files.length > 0) {
            uploadFiles(files);
        }
        // Reset the input so the same file can be uploaded again if needed
        e.target.value = '';
    });

    // Export selected asset
    exportBtn.addEventListener('click', () => {
        if (selectedAsset) {
            exportAsset(selectedAsset.file, selectedAsset.mediaType);
        } else {
            showButtonMessage(exportBtn, '<i class="fas fa-exclamation-triangle"></i> Select Asset', 'rgba(239, 68, 68, 0.8)');
        }
    });

    // Delete selected asset
    deleteAssetBtn.addEventListener('click', () => {
        if (selectedAsset) {
            deleteAsset(selectedAsset.file, selectedAsset.mediaType);
        } else {
            showButtonMessage(deleteAssetBtn, '<i class="fas fa-exclamation-triangle"></i> Select Asset', 'rgba(239, 68, 68, 0.8)');
        }
    });

    // Refresh assets
    refreshAssetsBtn.addEventListener('click', () => {
        displayedFiles.clear();
        assetCategoriesContainer.innerHTML = '';
        
        // Trigger a refresh
        fetch(`/api/results/${taskId}${sourceParam}`)
            .then(res => res.json())
            .then(data => updateAssets(data))
            .catch(err => console.error('Refresh error:', err));
    });

    async function uploadFiles(files) {
        setCommandStatus(`Uploading ${files.length} file(s)...`, '#fbbf24');
        
        try {
            const formData = new FormData();
            files.forEach(file => {
                formData.append('files', file);
            });
            
            const response = await fetch(`/upload/${taskId}`, {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (response.ok) {
                const uploadedCount = result.uploaded_files.length;
                setCommandStatus(`Successfully uploaded ${uploadedCount} file(s)`, '#22c55e');
                
                // Show any errors if some files failed
                if (result.errors && result.errors.length > 0) {
                    console.warn('Upload errors:', result.errors);
                    setCommandStatus(`Successfully uploaded ${uploadedCount} file(s) (${result.errors.length} failed)`, '#22c55e');
                }
                
                // Refresh the assets to show newly uploaded files
                setTimeout(() => {
                    refreshAssetsBtn.click();
                }, 1000);
                
            } else {
                throw new Error(result.error || 'Upload failed');
            }
            
            setCommandStatus(commandStatus ? commandStatus.textContent : '', commandStatus ? commandStatus.style.color : '', 5000);
            
        } catch (error) {
            console.error('Upload error:', error);
            setCommandStatus(`Upload failed: ${error.message}`, '#ef4444', 5000);
        }
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === ' ' && currentPreviewElement) {
            // Don't trigger play/pause if user is editing text
            const isEditingText = document.activeElement.contentEditable === 'true' || 
                                  document.activeElement.isContentEditable ||
                                  document.activeElement.tagName === 'INPUT' ||
                                  document.activeElement.tagName === 'TEXTAREA';
            
            if (!isEditingText) {
                e.preventDefault();
                playPauseBtn.click();
            }
        }
    });

    function exportAsset(file, mediaType) {
        try {
            // Create a temporary link element to trigger download
            const link = document.createElement('a');
            link.href = `../projects/${file}`;
            link.download = getFileName(file);
            
            // Append to body, click, and remove
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            // Show success message
            setCommandStatus(`Downloading ${getFileName(file)}...`, '#22c55e', 3000);
            
        } catch (error) {
            console.error('Export error:', error);
            setCommandStatus('Export failed', '#ef4444', 3000);
        }
    }

    async function deleteAsset(file, mediaType) {
        const filename = getFileName(file);
        
        // Show confirmation dialog
        const confirmed = confirm(`Are you sure you want to delete "${filename}"?\n\nThis action cannot be undone.`);
        
        if (!confirmed) {
            return;
        }
        
        try {
            setCommandStatus(`Deleting ${filename}...`, '#fbbf24');
            
            const response = await fetch(`/delete/${taskId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_path: file
                })
            });
            
            const result = await response.json();
            
            if (response.ok) {
                setCommandStatus(`Successfully deleted ${filename}`, '#22c55e');
                
                // Clear selection since the asset is deleted
                selectedAsset = null;
                
                // Clear preview
                previewContainer.innerHTML = '<div class="preview-placeholder"><i class="fas fa-play-circle"></i><p>Select an asset to preview</p></div>';
                document.querySelector('.preview-controls').style.display = 'none';
                
                // Refresh assets to update the UI
                setTimeout(() => {
                    refreshAssetsBtn.click();
                }, 500);
                
            } else {
                throw new Error(result.error || 'Delete failed');
            }
            
            setCommandStatus(commandStatus ? commandStatus.textContent : '', commandStatus ? commandStatus.style.color : '', 3000);
            
        } catch (error) {
            console.error('Delete error:', error);
            setCommandStatus(`Failed to delete ${filename}: ${error.message}`, '#ef4444', 5000);
        }
    }

    function showButtonMessage(button, message, backgroundColor) {
        const originalText = button.innerHTML;
        const originalBackground = button.style.background;
        
        button.innerHTML = message;
        button.style.background = backgroundColor;
        
        setTimeout(() => {
            button.innerHTML = originalText;
            button.style.background = originalBackground;
        }, 2000);
    }

    // Text Preview functionality
    async function loadSegmentedMonologueData(forceRefresh = false) {
        if (segmentedMonologueData && !forceRefresh) return segmentedMonologueData;
        
        try {
            const jsonPath = `${taskId}/segmented_monologue_design.json`;
            const jsonResponse = await fetch(`../projects/${jsonPath}?nocache=${Date.now()}`);
            
            if (jsonResponse.ok) {
                segmentedMonologueData = await jsonResponse.json();
                return segmentedMonologueData;
            }
        } catch (error) {
            console.error('Error loading segmented monologue data:', error);
        }
        return null;
    }
    
    async function loadImageUnderstandingData(forceRefresh = false) {
        if (imageUnderstandingData && !forceRefresh) return imageUnderstandingData;
        
        try {
            const jsonPath = `${taskId}/image_understanding.json`;
            const jsonResponse = await fetch(`../projects/${jsonPath}?nocache=${Date.now()}`);
            
            if (jsonResponse.ok) {
                imageUnderstandingData = await jsonResponse.json();
                return imageUnderstandingData;
            }
        } catch (error) {
            console.error('Error loading image understanding data:', error);
        }
        return null;
    }
    
    let userInputData = null;
    
    async function loadUserInputData(forceRefresh = false) {
        if (userInputData && !forceRefresh) return userInputData;
        
        try {
            const jsonPath = `${taskId}/user_input.json`;
            const jsonResponse = await fetch(`../projects/${jsonPath}?nocache=${Date.now()}`);
            
            if (jsonResponse.ok) {
                userInputData = await jsonResponse.json();
                return userInputData;
            }
        } catch (error) {
            console.error('Error loading user input data:', error);
        }
        return null;
    }
    
    async function loadProductAnalysisData(forceRefresh = false) {
        if (productAnalysisData && !forceRefresh) return productAnalysisData;
        
        try {
            const jsonPath = `${taskId}/product_analysis.json`;
            const jsonResponse = await fetch(`../projects/${jsonPath}?nocache=${Date.now()}`);
            
            if (jsonResponse.ok) {
                productAnalysisData = await jsonResponse.json();
                return productAnalysisData;
            }
        } catch (error) {
            console.error('Error loading product analysis data:', error);
        }
        return null;
    }
    
    async function loadWorkflowConfigData(forceRefresh = false) {
        if (workflowConfigData && !forceRefresh) return workflowConfigData;
        
        try {
            const jsonPath = `${taskId}/workflow_config.json`;
            const jsonResponse = await fetch(`../projects/${jsonPath}?nocache=${Date.now()}`);
            
            if (jsonResponse.ok) {
                workflowConfigData = await jsonResponse.json();
                return workflowConfigData;
            }
        } catch (error) {
            console.error('Error loading workflow config data:', error);
        }
        return null;
    }
    
    async function loadModelsConfigData(forceRefresh = false) {
        if (modelsConfigData && !forceRefresh) return modelsConfigData;
        
        try {
            const jsonResponse = await fetch(`/config/models_config.json?nocache=${Date.now()}`);
            
            if (jsonResponse.ok) {
                modelsConfigData = await jsonResponse.json();
                return modelsConfigData;
            }
        } catch (error) {
            console.error('Error loading models config data:', error);
        }
        return null;
    }
    
    // Helper function to clear cached JSON data after regeneration
    function clearCachedJsonData() {
        segmentedMonologueData = null;
        imageUnderstandingData = null;
        userInputData = null;
        productAnalysisData = null;
        workflowConfigData = null;
        console.log('🔄 Cleared cached JSON data');
    }
    
    async function showAudioTextPreview(audioFile) {
        const filename = getFileName(audioFile);
        
        // Check if it's a BGM file
        if (filename.toLowerCase().includes('bgm')) {
            await showBGMTextPreview(audioFile);
            return;
        }
        
        // 1. Load config first (for editable text)
        const config = await loadAndShowConfig(audioFile, 'segmented_tts');
        let text = '';
        
        if (config && config.segment_text) {
            text = config.segment_text;
        } else {
            text = "No text available in asset config.";
        }

        // 2. Try to get metadata from monologue design
        let timingInfo = '';
        let segmentIndex = null;
        
        // Try old pattern first: segment_0.mp3
        const oldMatch = filename.match(/segment_(\d+)/i);
        if (oldMatch) {
            segmentIndex = parseInt(oldMatch[1]);
        } else {
            // Robust parsing for sub_video folder structure
            const subVideoMatch = audioFile.match(/sub_video_(\d+)/i);
            const isVoiceover = /voiceover/i.test(audioFile);
            
            if (subVideoMatch && isVoiceover) {
                segmentIndex = parseInt(subVideoMatch[1]);
            }
        }
        
        if (segmentIndex !== null) {
            const data = await loadSegmentedMonologueData(true);
            if (data && data.segments) {
                const segment = data.segments.find(s => s.segment_index === segmentIndex);
                if (segment && segment.timing_notes) {
                    timingInfo = `<div class="text-preview-segment-timing">⏱ ${segment.timing_notes}</div>`;
                }
            }
        }
        
        // 3. Display
        textPreviewContent.innerHTML = `
            <div class="text-preview-segment">
                <div class="text-preview-segment-label">${filename}</div>
                <div class="text-preview-segment-text">${text}</div>
                ${timingInfo}
            </div>
        `;
        
        currentEditableFile = audioFile;
        isTextEdited = false;
        regenerateBtn.disabled = true;
        regenerateBtn.classList.remove('active');
        regenerateBtn.style.display = ''; // Reset display
        textPreviewContent.style.display = ''; // Reset display
        textPreviewPanel.style.display = 'flex';
        syncResizeHandle();
        makeTextEditable();
    }
    
    async function showBGMTextPreview(audioFile) {
        const filename = getFileName(audioFile);
        
        // 1. Load config first (primary source for prompt)
        const config = await loadAndShowConfig(audioFile, 'bgm');
        let prompt = '';
        
        if (config && config.prompt) {
            prompt = config.prompt;
        } else {
            prompt = "No prompt available in asset config.";
        }
        
        // 2. Load product analysis data (supplementary source for mood keywords)
        const data = await loadProductAnalysisData(true);
        let moodInfo = '';
        
        if (data && data.mood_keywords) {
            const moodKeywords = Array.isArray(data.mood_keywords) ? data.mood_keywords.join(', ') : data.mood_keywords;
            moodInfo = `
                <div class="text-preview-mood-label">🎵 Mood Keywords (Reference)</div>
                <div class="text-preview-segment-text" style="font-size: 0.9em; color: #aaa;">${moodKeywords}</div>
                ${data.color_palette ? `<div class="text-preview-field"><strong>🎨 Color Palette:</strong> ${data.color_palette.join(', ')}</div>` : ''}
                ${data.product_category ? `<div class="text-preview-field"><strong>📦 Category:</strong> ${data.product_category}</div>` : ''}
                ${data.visual_style ? `<div class="text-preview-field"><strong>✨ Visual Style:</strong> ${data.visual_style}</div>` : ''}
            `;
        } else {
            moodInfo = '<div class="text-preview-mood-label" style="color: #666;">(No mood analysis data available)</div>';
        }
        
        // 3. Display Combined Content
        textPreviewContent.innerHTML = `
            <div class="text-preview-segment">
                <div class="text-preview-segment-label">${filename}</div>
                <div class="text-preview-image-type">Background Music</div>
                <div class="text-preview-segment-text">${prompt}</div>
                ${moodInfo}
            </div>
        `;
        
        currentEditableFile = audioFile; // Enable editing for BGM files
        isTextEdited = false;
        regenerateBtn.disabled = true;
        regenerateBtn.classList.remove('active');
        regenerateBtn.style.display = ''; // Reset display
        textPreviewContent.style.display = ''; // Reset display
        textPreviewPanel.style.display = 'flex';
        syncResizeHandle();
        makeTextEditable();
    }
    
    async function showVideoTextPreview(videoFile, isFinalVideo = false) {
        const filename = getFileName(videoFile);
        
        // For final videos, hide text content but show edit config and regenerate button
        if (isFinalVideo) {
            // Show the panel but hide text content
            textPreviewPanel.style.display = 'flex';
            textPreviewContent.style.display = 'none';
            // Show regenerate button (always enabled for final videos)
            regenerateBtn.style.display = '';
            regenerateBtn.disabled = false;
            regenerateBtn.classList.add('active');
            // Set currentEditableFile so the click handler can work
            currentEditableFile = videoFile;
            // Show edit node configuration
            await loadAndShowConfig(videoFile, 'edit');
            syncResizeHandle();
            return;
        }
        
        // 1. Load config first (for prompt)
        const config = await loadAndShowConfig(videoFile, 'video_generation');
        let description = '';
        
        if (config && (config.original_prompt || config.prompt)) {
            description = config.original_prompt || config.prompt;
        } else {
            description = "No description available in asset config.";
        }

        // 2. Display
        textPreviewContent.innerHTML = `
            <div class="text-preview-segment">
                <div class="text-preview-segment-label">${filename}</div>
                <div class="text-preview-segment-text">${description}</div>
            </div>
        `;
        
        currentEditableFile = videoFile;
        isTextEdited = false;
        regenerateBtn.disabled = true;
        regenerateBtn.classList.remove('active');
        regenerateBtn.style.display = ''; // Reset display
        textPreviewContent.style.display = ''; // Reset display
        textPreviewPanel.style.display = 'flex';
        syncResizeHandle();
        makeTextEditable();
    }
    
    async function showImageTextPreview(imageFile) {
        const filename = getFileName(imageFile);
        
        // 1. Load config first (for prompt)
        const config = await loadAndShowConfig(imageFile, 'image_generation');
        let description = '';
        
        if (config && (config.original_prompt || config.prompt)) {
            description = config.original_prompt || config.prompt;
        } else {
            description = "No description available in asset config.";
        }

        // 2. Display
        textPreviewContent.innerHTML = `
            <div class="text-preview-segment">
                <div class="text-preview-segment-label">${filename}</div>
                <div class="text-preview-segment-text">${description}</div>
            </div>
        `;
        
        currentEditableFile = imageFile;
        isTextEdited = false;
        regenerateBtn.disabled = true;
        regenerateBtn.classList.remove('active');
        regenerateBtn.style.display = ''; // Reset display
        textPreviewContent.style.display = ''; // Reset display
        textPreviewPanel.style.display = 'flex';
        syncResizeHandle();
        makeTextEditable();
    }
    
    async function showUploadedImagePreview(imageFile) {
        const filename = getFileName(imageFile);
        
        // Load user input data (contains ad_requirement and reference_images info)
        const userData = await loadUserInputData(true);
        
        if (!userData) {
            // Fallback to old behavior if user_input.json doesn't exist
            const data = await loadImageUnderstandingData(true);
            if (!data || !data.descriptions || data.descriptions.length === 0) {
                textPreviewPanel.style.display = 'none';
                return;
            }
            
            // Use old display logic
            const description = data.descriptions[0];
            displayImageDescription(filename, description, null);
            return;
        }
        
        // Find the matching reference image by filename
        let matchingImage = null;
        if (userData.reference_images && userData.reference_images.length > 0) {
            // Try to match by filename
            for (const refImg of userData.reference_images) {
                if (refImg.path && refImg.path.includes(filename)) {
                    matchingImage = refImg;
                    break;
                }
            }
            
            // If no match found, use the first image
            if (!matchingImage) {
                matchingImage = userData.reference_images[0];
            }
        }
        
        if (!matchingImage || !matchingImage.description) {
            textPreviewPanel.style.display = 'none';
            return;
        }
        
        // Display with user requirement
        displayImageDescription(filename, matchingImage.description, userData.ad_requirement);
    }
    
    async function showCharacterImagePreview(imageFile) {
        const filename = getFileName(imageFile);
        
        // 1. Load config (for prompt and workflow config panel) — same as regular images
        const config = await loadAndShowConfig(imageFile, 'image_generation');
        let description = '';
        
        if (config && config.prompt) {
            description = config.prompt;
        } else {
            // Fallback: try loading metadata JSON directly
            try {
                const metaFile = imageFile.replace(/\.[^.]+$/, '.json');
                const metaResponse = await fetch(`../projects/${metaFile}?nocache=${Date.now()}`);
                if (metaResponse.ok) {
                    const metadata = await metaResponse.json();
                    if (metadata && metadata.prompt) {
                        description = metadata.prompt;
                    }
                }
            } catch (e) {
                console.log('Could not load character image metadata:', e);
            }
        }
        
        // Check if this is a user-uploaded image (no metadata at all)
        if (!description) {
            // User-uploaded image — read-only, no regenerate
            textPreviewContent.innerHTML = `
                <div class="text-preview-segment">
                    <div class="text-preview-segment-label">${filename}</div>
                    <div class="text-preview-segment-sublabel">User-uploaded character image</div>
                </div>
            `;
            currentEditableFile = null;
            isTextEdited = false;
            regenerateBtn.disabled = true;
            regenerateBtn.classList.remove('active');
            regenerateBtn.style.display = 'none';
            textPreviewContent.style.display = '';
            textPreviewPanel.style.display = 'flex';
            return;
        }
        
        // 2. Display editable prompt — same as showImageTextPreview
        textPreviewContent.innerHTML = `
            <div class="text-preview-segment">
                <div class="text-preview-segment-label">${filename}</div>
                <div class="text-preview-segment-text">${description}</div>
            </div>
        `;
        
        currentEditableFile = imageFile;
        isTextEdited = false;
        regenerateBtn.disabled = true;
        regenerateBtn.classList.remove('active');
        regenerateBtn.style.display = ''; // Reset display
        textPreviewContent.style.display = ''; // Reset display
        textPreviewPanel.style.display = 'flex';
        makeTextEditable();
    }
    
    function displayImageDescription(filename, description, userRequirement = null) {
        // Build content sections
        let contentSections = '';
        
        // Section 1: User Requirement (if available)
        if (userRequirement) {
            contentSections += `
                <div class="text-preview-segment">
                    <div class="text-preview-segment-label">User Requirement</div>
                    <div class="text-preview-segment-text">${userRequirement}</div>
                </div>
            `;
        }
        
        // Section 2: Image Description (summary only)
        if (description && description.summary) {
            contentSections += `
                <div class="text-preview-segment">
                    <div class="text-preview-segment-label">Image Description</div>
                    <div class="text-preview-segment-text">${description.summary}</div>
                </div>
            `;
        }
        
        textPreviewContent.innerHTML = contentSections;
        currentEditableFile = null; // No editing for uploaded images
        isTextEdited = false;
        regenerateBtn.disabled = true;
        regenerateBtn.classList.remove('active');
        regenerateBtn.style.display = 'none'; // Hide regenerate button for uploaded images
        textPreviewContent.style.display = ''; // Reset display
        textPreviewPanel.style.display = 'flex';
        syncResizeHandle();
        // Do NOT call makeTextEditable() - uploaded images should not be editable
        
        // Hide workflow config panel for uploaded images (no config needed)
        setWorkflowConfigVisible(false);
    }
    
    // Helper function to make text editable and track changes
    function makeTextEditable() {
        const editableElements = textPreviewContent.querySelectorAll('.text-preview-segment-text');
        
        editableElements.forEach(element => {
            element.contentEditable = 'true';
            element.classList.add('editable');
            
            element.addEventListener('input', () => {
                if (!isTextEdited) {
                    isTextEdited = true;
                    regenerateBtn.disabled = false;
                    regenerateBtn.classList.add('active');
                }
            });
            
            // Add visual feedback on focus
            element.addEventListener('focus', () => {
                element.classList.add('editing');
            });
            
            element.addEventListener('blur', () => {
                element.classList.remove('editing');
            });
        });
    }
    
    // Get parameter filter keywords based on node type
    function getParamFilterKeywords(nodeType) {
        const filters = {
            'image_generation': ['aspect_ratio', 'style', 'format'],
            'video_generation': ['aspect_ratio', 'duration', 'effect', 'style', 'resolution', 'motion', 'generate_audio', 'seconds'],
            'segmented_tts': ['bitrate', 'emotion', 'sample_rate', 'speed', 'voice', 'volume', 'channel', 'language'],
            'bgm': ['duration', 'format', 'rate']
        };
        return filters[nodeType] || [];
    }
    
    // Check if parameter key matches any filter keyword
    function matchesFilter(paramKey, filterKeywords) {
        if (filterKeywords.length === 0) return true;
        const lowerKey = paramKey.toLowerCase();
        return filterKeywords.some(keyword => lowerKey.includes(keyword.toLowerCase()));
    }
    
    // Display workflow config for any node type (image_generation, video_generation, segmented_tts, bgm)
    async function showWorkflowConfig(nodeType, assetConfig = null, assetFilePath = null) {
        const workflowConfig = await loadWorkflowConfigData(true);
        const modelsConfig = await loadModelsConfigData();
        
        if (!workflowConfig || !modelsConfig) {
            setWorkflowConfigVisible(false);
            return;
        }
        
        // Determine effective configuration
        let currentModelName = null;
        let currentParams = {};
        
        // 1. Start with global config
        // Map nodeType to workflow_config.json key (some keys differ)
        const configKeyMap = {
            'edit': 'video_editor',
            'segmented_tts': 'tts'
        };
        const configKey = configKeyMap[nodeType] || nodeType;
        const nodeConfig = workflowConfig[configKey];
        if (nodeConfig) {
            currentModelName = nodeConfig.model;
            currentParams = { ...(nodeConfig.parameters || {}) };
        }
        
        // 2. Overlay asset specific config if available
        if (assetConfig) {
            if (assetConfig.model) {
                currentModelName = assetConfig.model;
            }
            // Asset config is flat, so merge all keys as parameters
            // This might include 'model' as a parameter, but that's usually harmless for display if filtered correctly
            currentParams = { ...currentParams, ...assetConfig };
        }
        
        // 3. Overlay pending changes (UI-only, not saved yet)
        if (Object.keys(pendingConfigChanges).length > 0) {
            if (pendingConfigChanges.model) {
                currentModelName = pendingConfigChanges.model;
            }
            // Merge pending parameter changes
            currentParams = { ...currentParams, ...pendingConfigChanges };
        }
        
        const currentModelBaseName = currentModelName ? currentModelName.split(':')[0] : null;
        
        // Prepare Header HTML
        let configHTML = '';
        if (assetFilePath) {
            const fileName = getFileName(assetFilePath);
            configHTML += `<div class="config-header-info" style="background:#eff6ff; color:#1d4ed8; padding: 8px; border-radius: 4px; margin-bottom: 10px; font-size: 0.9em; border: 1px solid #bfdbfe;"><i class="fas fa-file-alt"></i> <strong>Asset Config:</strong> ${fileName}</div>`;
        } else {
            configHTML += `<div class="config-header-info" style="background:#f3f4f6; color:#374151; padding: 8px; border-radius: 4px; margin-bottom: 10px; font-size: 0.9em; border: 1px solid #e5e7eb;"><i class="fas fa-globe"></i> <strong>Global Config:</strong> ${formatParamLabel(nodeType)}</div>`;
        }
        
        // Handle nodes without models (e.g., 'edit' node) or missing model
        if (nodeType === 'edit' || !currentModelName) {
             // Logic for param-only nodes
             // For edit node, always show config even if empty (we'll use defaults)
             if (nodeType === 'edit' || Object.keys(currentParams).length > 0) {
                 // For edit node, ensure we have default parameters if none exist
                 if (nodeType === 'edit' && Object.keys(currentParams).length === 0) {
                     currentParams = {
                         video_volume: 0.35,
                         narration_volume: 0.60,
                         bgm_volume: 0.90,
                         normalize: true,
                         fade_duration: 0.5
                     };
                 }
                 
                 // Check if we need to render video_volumes (need async operation)
                 const needsVideoVolumes = nodeType === 'edit' && ('video_volumes' in currentParams || Object.keys(currentParams).some(k => k === 'video_volume'));
                 
                 if (needsVideoVolumes) {
                     // Render asynchronously with video segment count
                     renderEditNodeConfig(currentParams, configHTML, assetFilePath, nodeType);
                     return;
                 }
                 
                 // Synchronous rendering for other params
                 for (const [paramKey, paramValue] of Object.entries(currentParams)) {
                    if (paramKey === 'model') continue; // Skip model key in params list
                    
                    const valueType = typeof paramValue;
                    if (valueType === 'number') {
                        const step = Number.isInteger(paramValue) ? '1' : '0.01';
                        configHTML += `
                            <div class="config-param">
                                <label class="config-param-label">${formatParamLabel(paramKey)}</label>
                                <input type="number" class="config-param-input" data-param="${paramKey}" 
                                       value="${paramValue}" step="${step}">
                            </div>
                        `;
                    } else if (valueType === 'boolean') {
                        configHTML += `
                            <div class="config-param">
                                <label class="config-param-label">${formatParamLabel(paramKey)}</label>
                                <select class="config-param-select" data-param="${paramKey}">
                                    <option value="true" ${paramValue === true ? 'selected' : ''}>true</option>
                                    <option value="false" ${paramValue === false ? 'selected' : ''}>false</option>
                                </select>
                            </div>
                        `;
                    } else if (valueType === 'string') {
                        configHTML += `
                            <div class="config-param">
                                <label class="config-param-label">${formatParamLabel(paramKey)}</label>
                                <input type="text" class="config-param-input" data-param="${paramKey}" 
                                       value="${paramValue}">
                            </div>
                        `;
                    }
                }
                
                workflowConfigContent.innerHTML = configHTML;
                setWorkflowConfigVisible(true);
                addConfigChangeListeners(nodeType);
                return;
             }
             if (nodeType !== 'edit') {
                 // If it's a generative node but no model selected
                 // Fall through to model selector
             } else {
                 setWorkflowConfigVisible(false);
                 return;
             }
        }
        
        // Determine which model category to look in based on node type
        let modelCategory = nodeType;
        if (nodeType === 'segmented_tts') {
            modelCategory = 'tts';
        }
        // Note: 'bgm' node type maps directly to 'bgm' category in models_config.json
        
        // Get all available models for this category
        const availableModels = modelsConfig.models?.[modelCategory];
        if (!availableModels || Object.keys(availableModels).length === 0) {
            setWorkflowConfigVisible(false);
            console.error('No models found for category:', modelCategory);
            return;
        }
        
        // Build the config UI starting with model selector
        configHTML += `
            <div class="config-param">
                <label class="config-param-label">Model</label>
                <select class="config-model-select" data-node="${nodeType}">
                    ${Object.keys(availableModels).map(modelKey => `
                        <option value="${modelKey}" ${modelKey === currentModelBaseName ? 'selected' : ''}>
                            ${modelKey.split('/').pop()}
                        </option>
                    `).join('')}
                </select>
            </div>
        `;
        
        // If no model is selected/found
        if (!currentModelBaseName) {
            configHTML += `<div class="config-model-info">Please select a model</div>`;
            workflowConfigContent.innerHTML = configHTML;
            setWorkflowConfigVisible(true);
            addModelChangeListener(nodeType);
            return;
        }
        
        // Look up model definition using base name
        const currentModelDef = availableModels[currentModelBaseName];
        if (!currentModelDef) {
            // If model not found in config (maybe removed), keep dropdown but show error or fallback
            // For now just return to avoid crash
             setWorkflowConfigVisible(false);
             return;
        }
        
        // Get filter keywords for this node type
        const filterKeywords = getParamFilterKeywords(nodeType);
        
        // Display filtered parameters
        if (currentModelDef.parameters) {
            for (const [paramKey, paramDef] of Object.entries(currentModelDef.parameters)) {
                // Apply filter - only show parameters matching keywords
                if (!matchesFilter(paramKey, filterKeywords)) {
                    continue;
                }
                
                // Get current value from currentParams (which includes asset overlay) or default
                const currentValue = currentParams[paramKey] ?? paramDef.default;
                
                if (paramDef.options && paramDef.options.length > 0) {
                    // Dropdown for parameters with options
                    configHTML += `
                        <div class="config-param">
                            <label class="config-param-label">${formatParamLabel(paramKey)}</label>
                            <select class="config-param-select" data-param="${paramKey}">
                                ${paramDef.options.map(option => `
                                    <option value="${option}" ${option === currentValue ? 'selected' : ''}>
                                        ${option}
                                    </option>
                                `).join('')}
                            </select>
                        </div>
                    `;
                } else if (paramDef.type === 'number' || paramDef.type === 'integer') {
                    // Number input for numeric parameters
                    const step = paramDef.type === 'integer' ? '1' : '0.01';
                    configHTML += `
                        <div class="config-param">
                            <label class="config-param-label">${formatParamLabel(paramKey)}</label>
                            <input type="number" class="config-param-input" data-param="${paramKey}" 
                                   value="${currentValue}" step="${step}">
                        </div>
                    `;
                } else if (paramDef.type === 'boolean') {
                    // Boolean dropdown
                    configHTML += `
                        <div class="config-param">
                            <label class="config-param-label">${formatParamLabel(paramKey)}</label>
                            <select class="config-param-select" data-param="${paramKey}">
                                <option value="true" ${currentValue === true ? 'selected' : ''}>true</option>
                                <option value="false" ${currentValue === false ? 'selected' : ''}>false</option>
                            </select>
                        </div>
                    `;
                }
            }
        }
        
        workflowConfigContent.innerHTML = configHTML;
        setWorkflowConfigVisible(true);
        
        // Add change listeners for both model and parameters
        addModelChangeListener(nodeType);
        addConfigChangeListeners(nodeType);
    }
    
    // Render edit node config with video volumes support
    async function renderEditNodeConfig(currentParams, headerHTML, assetFilePath, nodeType) {
        const numSegments = await getVideoSegmentCount();
        let configHTML = headerHTML;
        
        // Initialize video_volumes if not present
        if (!currentParams.video_volumes) {
            const defaultVolume = currentParams.video_volume || 0.35;
            currentParams.video_volumes = Array(numSegments).fill(defaultVolume);
        }
        
        for (const [paramKey, paramValue] of Object.entries(currentParams)) {
            if (paramKey === 'model') continue;
            
            // Special handling for video_volumes
            if (paramKey === 'video_volumes') {
                let volumesArray = paramValue;
                if (!volumesArray || !Array.isArray(volumesArray)) {
                    const defaultVolume = currentParams.video_volume || 0.35;
                    volumesArray = Array(numSegments).fill(defaultVolume);
                } else if (volumesArray.length < numSegments) {
                    const defaultVolume = currentParams.video_volume || 0.35;
                    while (volumesArray.length < numSegments) {
                        volumesArray.push(defaultVolume);
                    }
                }
                
                configHTML += `<div class="config-param-group" style="margin-bottom: 16px;">`;
                configHTML += `<div class="config-param-label" style="margin-bottom: 8px; font-weight: 600;">Video Segment Volumes</div>`;
                
                for (let i = 0; i < numSegments; i++) {
                    const volume = volumesArray[i] || 0.35;
                    configHTML += `
                        <div class="config-param" style="margin-bottom: 10px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                                <label class="config-param-label" style="font-size: 0.9em; margin: 0;">Segment ${i + 1}</label>
                                <span class="volume-value" data-index="${i}" style="font-size: 0.85em; color: #6b7280; font-weight: 500;">${volume.toFixed(2)}</span>
                            </div>
                            <input type="range" class="config-volume-slider" 
                                   data-param="video_volumes" 
                                   data-index="${i}"
                                   min="0" max="2" step="0.05" value="${volume}"
                                   style="width: 100%; cursor: pointer;">
                        </div>
                    `;
                }
                
                configHTML += `</div>`;
                continue;
            }
            
            // Skip video_volume if not rendering as regular param
            if (paramKey === 'video_volume') {
                continue; // Hide it when video_volumes is used
            }
            
            const valueType = typeof paramValue;
            
            // Special rendering for volume-related parameters (use sliders)
            if ((paramKey === 'narration_volume' || paramKey === 'bgm_volume') && valueType === 'number') {
                const volume = paramValue || 0.0;
                const label = formatParamLabel(paramKey);
                configHTML += `
                    <div class="config-param" style="margin-bottom: 12px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                            <label class="config-param-label" style="margin: 0;">${label}</label>
                            <span class="single-volume-value" data-param="${paramKey}" style="font-size: 0.85em; color: #6b7280; font-weight: 500;">${volume.toFixed(2)}</span>
                        </div>
                        <input type="range" class="config-single-volume-slider" 
                               data-param="${paramKey}"
                               min="0" max="2" step="0.05" value="${volume}"
                               style="width: 100%; cursor: pointer;">
                    </div>
                `;
                continue;
            }
            
            if (valueType === 'number') {
                const step = Number.isInteger(paramValue) ? '1' : '0.01';
                configHTML += `
                    <div class="config-param">
                        <label class="config-param-label">${formatParamLabel(paramKey)}</label>
                        <input type="number" class="config-param-input" data-param="${paramKey}" 
                               value="${paramValue}" step="${step}">
                    </div>
                `;
            } else if (valueType === 'boolean') {
                configHTML += `
                    <div class="config-param">
                        <label class="config-param-label">${formatParamLabel(paramKey)}</label>
                        <select class="config-param-select" data-param="${paramKey}">
                            <option value="true" ${paramValue === true ? 'selected' : ''}>true</option>
                            <option value="false" ${paramValue === false ? 'selected' : ''}>false</option>
                        </select>
                    </div>
                `;
            } else if (valueType === 'string') {
                configHTML += `
                    <div class="config-param">
                        <label class="config-param-label">${formatParamLabel(paramKey)}</label>
                        <input type="text" class="config-param-input" data-param="${paramKey}" 
                               value="${paramValue}">
                    </div>
                `;
            }
        }
        
        workflowConfigContent.innerHTML = configHTML;
        setWorkflowConfigVisible(true);
        addConfigChangeListeners(nodeType);
        addVolumeSliderListeners();
    }
    
    // Helper to get number of video segments for current task
    async function getVideoSegmentCount() {
        try {
            const res = await fetch(`/api/results/${taskId}${sourceParam}`);
            const data = await res.json();
            
            // Count sub_video_* folders
            let count = 0;
            for (const category of Object.values(data)) {
                if (Array.isArray(category)) {
                    for (const item of category) {
                        if (item.file && item.file.includes('/sub_video_')) {
                            const match = item.file.match(/sub_video_(\d+)/);
                            if (match) {
                                const index = parseInt(match[1]);
                                count = Math.max(count, index + 1);
                            }
                        }
                    }
                }
            }
            
            // If no segments found, default to 4
            return count || 4;
        } catch (error) {
            console.error('Failed to get video segment count:', error);
            return 4; // Default fallback
        }
    }
    
    // Helper to load asset specific config or fallback to global
    async function loadAndShowConfig(file, nodeType) {
        // Reset pending changes when loading a new asset
        pendingConfigChanges = {};
        currentNodeType = nodeType;
        currentAssetConfigPath = null;
        originalAssetConfig = null;
                
        let jsonPath;
        
        // For placeholders, try _v1.json (the config from a previous generation if any)
        // For normal assets, replace extension with .json (e.g. image_first_v1.png -> image_first_v1.json)
        if (selectedAsset && selectedAsset.isPlaceholder) {
            jsonPath = file.replace(/_v0\.[^/.]+$/, "_v1.json");
            console.log(`🔍 Looking for placeholder config: ${file} → ${jsonPath}`);
        } else {
            jsonPath = file.replace(/\.[^/.]+$/, ".json");
        }

        // For edit node (final video), don't load asset metadata - use workflow config instead
        if (nodeType === 'edit') {
            console.log(`🌐 Using workflow config for edit node (final video)`);
            await showWorkflowConfig(nodeType, null, null);
            return null;
        }
        
        try {
            const res = await fetch(`../projects/${jsonPath}?nocache=${Date.now()}`);
            if (res.ok) {
                const assetConfig = await res.json();
                // Set global variable so update knows where to save
                // Note: file here is relative path like 'task_id/sub_folder/file.png'
                currentAssetConfigPath = file;
                originalAssetConfig = { ...assetConfig }; // Store a copy of the original
                console.log(`📄 Loaded asset config for ${file}`);
                await showWorkflowConfig(nodeType, assetConfig, file);
                return assetConfig;
            } else {
                console.log(`🌐 Using global config for ${nodeType} (No asset config found at ${jsonPath})`);
                await showWorkflowConfig(nodeType, null, null);
                return null;
            }
        } catch (e) {
            console.error(`Error loading asset config from ${jsonPath}:`, e);
            await showWorkflowConfig(nodeType, null, null);
            return null;
        }
    }
    
    // Add listener for model selection changes
    function addModelChangeListener(nodeType) {
        const modelSelect = workflowConfigContent.querySelector('.config-model-select');
        if (modelSelect) {
            modelSelect.addEventListener('change', async (e) => {
                const newModel = e.target.value;
                
                // Store change in memory (don't save to JSON yet)
                pendingConfigChanges.model = newModel;
                console.log(`📝 Model change pending: ${newModel} (not saved yet)`);
                
                // Enable regenerate button since there are pending changes
                regenerateBtn.disabled = false;
                regenerateBtn.classList.add('active');
                
                // Refresh the UI to show the new model's parameters
                // Pass original assetConfig so it merges correctly with pending changes
                await showWorkflowConfig(nodeType, originalAssetConfig, currentAssetConfigPath);
            });
        }
    }
    
    // Helper function to add change listeners to config controls
    // Add event listeners for volume sliders (for video_volumes array parameter)
    function addVolumeSliderListeners() {
        const sliders = workflowConfigContent.querySelectorAll('.config-volume-slider');
        
        sliders.forEach((slider) => {
            const index = parseInt(slider.dataset.index);
            const valueDisplay = workflowConfigContent.querySelector(`.volume-value[data-index="${index}"]`);
            
            // Update display value as user drags
            slider.addEventListener('input', (e) => {
                if (valueDisplay) {
                    valueDisplay.textContent = parseFloat(e.target.value).toFixed(2);
                }
            });
            
            // Save change when user releases slider
            slider.addEventListener('change', (e) => {
                updateVideoVolume(index, parseFloat(e.target.value));
            });
        });
        
        // Add listeners for single volume sliders (narration_volume, bgm_volume)
        const singleSliders = workflowConfigContent.querySelectorAll('.config-single-volume-slider');
        singleSliders.forEach((slider) => {
            const paramKey = slider.dataset.param;
            const valueDisplay = workflowConfigContent.querySelector(`.single-volume-value[data-param="${paramKey}"]`);
            
            // Update display value as user drags
            slider.addEventListener('input', (e) => {
                if (valueDisplay) {
                    valueDisplay.textContent = parseFloat(e.target.value).toFixed(2);
                }
            });
            
            // Save change when user releases slider
            slider.addEventListener('change', (e) => {
                const newValue = parseFloat(e.target.value);
                pendingConfigChanges[paramKey] = newValue;
                console.log(`📝 Parameter change pending: ${paramKey} = ${newValue} (not saved yet)`);
                
                // Enable regenerate button
                regenerateBtn.disabled = false;
                regenerateBtn.classList.add('active');
            });
        });
    }
    
    function updateVideoVolume(index, value) {
        // Get or initialize video_volumes array
        if (!pendingConfigChanges.video_volumes) {
            // Initialize from current config or default
            const currentConfig = originalAssetConfig || {};
            const numSegments = workflowConfigContent.querySelectorAll('.config-volume-slider').length;
            const defaultVolume = currentConfig.video_volume || 0.35;
            pendingConfigChanges.video_volumes = Array(numSegments).fill(defaultVolume);
        }
        
        // Update specific index
        if (Array.isArray(pendingConfigChanges.video_volumes)) {
            pendingConfigChanges.video_volumes[index] = value;
            console.log(`📝 Volume change pending for segment ${index}: ${value} (not saved yet)`);
            
            // Enable regenerate button
            regenerateBtn.disabled = false;
            regenerateBtn.classList.add('active');
        }
    }
    
    function addConfigChangeListeners(nodeType) {
        const selects = workflowConfigContent.querySelectorAll('.config-param-select');
        selects.forEach(select => {
            select.addEventListener('change', async (e) => {
                const paramKey = e.target.dataset.param;
                let newValue = e.target.value;
                
                // Convert boolean strings to actual booleans
                if (newValue === 'true') newValue = true;
                if (newValue === 'false') newValue = false;
                
                // Store change in memory (don't save to JSON yet)
                pendingConfigChanges[paramKey] = newValue;
                console.log(`📝 Parameter change pending: ${paramKey} = ${newValue} (not saved yet)`);
                
                // Enable regenerate button since there are pending changes
                regenerateBtn.disabled = false;
                regenerateBtn.classList.add('active');
            });
        });
        
        const inputs = workflowConfigContent.querySelectorAll('.config-param-input');
        inputs.forEach(input => {
            input.addEventListener('change', async (e) => {
                const paramKey = e.target.dataset.param;
                let newValue;
                
                // Check input type to determine how to parse the value
                if (input.type === 'number') {
                    newValue = parseFloat(e.target.value);
                } else {
                    newValue = e.target.value; // Keep as string
                }
                
                // Store change in memory (don't save to JSON yet)
                pendingConfigChanges[paramKey] = newValue;
                console.log(`📝 Parameter change pending: ${paramKey} = ${newValue} (not saved yet)`);
                
                // Enable regenerate button since there are pending changes
                regenerateBtn.disabled = false;
                regenerateBtn.classList.add('active');
            });
        });
    }
    
    // Helper function to format parameter labels
    function formatParamLabel(key) {
        return key
            .split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
    }
    
    // Helper function to enable rerun button
    function enableRerunButton() {
        if (rerunBtn.disabled) {
            rerunBtn.disabled = false;
            rerunBtn.classList.add('active');
            console.log('✅ Rerun button enabled due to config changes');
        }
    }
    
    // Update workflow config on server
    async function updateWorkflowConfig(nodeType, paramKey, newValue) {
        try {
            let url, body;
            
            // Map nodeType to workflow_config.json key
            const configKeyMap = {
                'edit': 'video_editor',
                'segmented_tts': 'tts'
            };
            const configNodeKey = configKeyMap[nodeType] || nodeType;
            
            if (currentAssetConfigPath) {
                // Update specific asset config
                url = `/api/asset-config/${taskId}`;
                body = {
                    file_path: currentAssetConfigPath,
                    parameter: paramKey,
                    value: newValue
                };
                console.log(`🔄 Updating ASSET config for ${currentAssetConfigPath}: ${paramKey}=${newValue}`);
            } else {
                // Update global workflow config
                url = `/api/workflow-config/${taskId}`;
                body = {
                    node: configNodeKey,
                    parameter: paramKey,
                    value: newValue
                };
                console.log(`🔄 Updating GLOBAL config: ${configNodeKey}.${paramKey}=${newValue}`);
            }
            
            const response = await fetch(url, {
                method: currentAssetConfigPath ? 'POST' : 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            });
            
            if (response.ok) {
                console.log(`✅ Update successful`);
                // Clear cache to force reload on next access if it's global config
                if (!currentAssetConfigPath) {
                    workflowConfigData = null;
                }
                return true;
            } else {
                console.error('Failed to update config');
                return false;
            }
        } catch (error) {
            console.error('Error updating config:', error);
            return false;
        }
    }
    
    // Generate New Version button handler
    regenerateBtn.addEventListener('click', async () => {
        const editedText = textPreviewContent.querySelector('.text-preview-segment-text')?.innerText || '';
        
        if (currentEditableFile) {
            // Store info for auto-refresh after regeneration
            // IMPORTANT:
            // - currentEditableFile may point to a historical version path (when user previews V1/V2...)
            // - But the "slot current path" shown in results is selectedAsset.file (active current)
            // For polling readiness, we must compare against the slot's current path, otherwise we'd
            // immediately detect "changed" (because current != historical) and stop polling wrongly.
            const fileToRegenerate = (selectedAsset && selectedAsset.file) ? selectedAsset.file : currentEditableFile;
            // Capture slotKey at click time; file path will change after new version is generated
            const slotKeyToRegenerate = (selectedAsset && selectedAsset.slotKey) ? selectedAsset.slotKey : null;
            const mediaTypeToRegenerate = selectedAsset?.mediaType || 'img';
            const editedTextToStore = editedText;
            
            // Determine file type from the current asset
            const isFinal = selectedAsset && selectedAsset.isFinalVideo;
            let fileType = isFinal ? 'final_video' : mediaTypeToRegenerate;
            // Map 'img' to 'images' for backend compatibility
            if (fileType === 'img') {
                fileType = 'images';
            }
            
            // Show feedback
            regenerateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving changes...';
            regenerateBtn.disabled = true;
            regenerateBtn.classList.add('active');
            
            // Save pending config changes to JSON file if any
            if (Object.keys(pendingConfigChanges).length > 0 && currentAssetConfigPath) {
                console.log('💾 Saving pending config changes:', pendingConfigChanges);
                
                // Save each pending change
                for (const [key, value] of Object.entries(pendingConfigChanges)) {
                    const success = await updateWorkflowConfig(currentNodeType, key, value);
                    if (!success) {
                        console.error(`❌ Failed to save ${key}`);
                        regenerateBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Save Failed';
                        setTimeout(() => {
                        regenerateBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Generate New Version';
                            regenerateBtn.disabled = false;
                        }, 2000);
                        return; // Abort regeneration if config save fails
                    }
                }
                
                // Clear pending changes after successful save
                // Update originalAssetConfig to reflect the saved changes
                if (originalAssetConfig) {
                    originalAssetConfig = { ...originalAssetConfig, ...pendingConfigChanges };
                }
                pendingConfigChanges = {};
                console.log('✅ Config changes saved successfully');
            }
            
            // Update feedback for regeneration
            regenerateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating new version...';
            
            try {
                // Call backend API to regenerate
                console.log('🔄 Generate new version request:', { file: currentEditableFile, fileType, editedText: editedText.substring(0, 50) + '...' });
                const response = await fetch(`/api/regenerate/${taskId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        file: currentEditableFile,
                        edited_text: editedText,
                        file_type: fileType
                    })
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    // Success - start polling for the new asset
                    regenerateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Waiting for new version...';
                    console.log('✅ Regeneration started:', result);
                    
                    // Poll for the regenerated asset
                    let pollCount = 0;
                    const maxPolls = 30; // Poll for up to 30 seconds (30 * 1 second)
                    
                    const checkAssetReady = async () => {
                        pollCount++;
                        
                        try {
                            // Fetch latest results
                            const resultsRes = await fetch(`/api/results/${taskId}${sourceParam}${sourceParam ? '&' : '?'}t=${Date.now()}`);
                            const resultsData = await resultsRes.json();
                            const structure = resultsData.structure || {};
                            
                            // 关键修复：不再探测文件 HEAD，而是检查 slotKey 的路径是否变了
                            const targetSlotKey = slotKeyToRegenerate;
                            const oldPath = fileToRegenerate;
                            let newPathFound = null;
                            
                            // 在新结构中寻找同一个 slotKey 对应的新路径
                            for (const category in structure) {
                                for (const asset of structure[category]) {
                                    const currentSlotKey = `${asset.group_key || category}_${asset.item_key || asset.name}`;
                                    if (currentSlotKey === targetSlotKey) {
                                        if (asset.path !== oldPath) {
                                            newPathFound = asset.path;
                                        }
                                        break;
                                    }
                                }
                                if (newPathFound) break;
                            }
                            
                            if (newPathFound) {
                                // 路径变了，说明新版本已就绪！
                                clearInterval(pollInterval);
                                
                                clearCachedJsonData();
                                updateAssets(resultsData);
                                
                                setTimeout(() => {
                                    const assetItems = document.querySelectorAll('.asset-item');
                                    let targetItem = null;
                                    
                                    for (const item of assetItems) {
                                        if (targetSlotKey && item.dataset.slotKey === targetSlotKey) {
                                            targetItem = item;
                                            break;
                                        }
                                    }
                                    
                                    if (targetItem) {
                                        selectAsset(targetItem, newPathFound, mediaTypeToRegenerate);
                                        console.log('✅ Auto-refreshed to NEW version:', newPathFound);
                                    }
                                    
                                    regenerateBtn.innerHTML = '<i class="fas fa-check"></i> Complete!';
                                    setTimeout(() => {
                                        regenerateBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Generate New Version';
                                        isTextEdited = false;
                                        // Keep button always enabled for final videos
                                        const isFinal = selectedAsset && selectedAsset.isFinalVideo;
                                        if (isFinal) {
                                            regenerateBtn.disabled = false;
                                            regenerateBtn.classList.add('active');
                                        } else {
                                            regenerateBtn.disabled = true;
                                            regenerateBtn.classList.remove('active');
                                        }
                                    }, 2000);
                                }, 500);
                            } else if (pollCount >= maxPolls) {
                                // Timeout - stop trying
                                clearInterval(pollInterval);
                                console.warn('⚠️ Polling timeout - regeneration may still be processing');
                                regenerateBtn.innerHTML = '<i class="fas fa-clock"></i> Timeout';
                                setTimeout(() => {
                                    regenerateBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Generate New Version';
                                    // Keep button always enabled for final videos
                                    const isFinal = selectedAsset && selectedAsset.isFinalVideo;
                                    if (isFinal) {
                                        regenerateBtn.disabled = false;
                                        regenerateBtn.classList.add('active');
                                    } else {
                                        regenerateBtn.disabled = true;
                                        regenerateBtn.classList.remove('active');
                                    }
                                }, 3000);
                            } else {
                                // Continue polling
                                console.log(`⏳ Polling attempt ${pollCount}/${maxPolls} - waiting for asset...`);
                            }
                        } catch (pollError) {
                            // Continue polling even if there's an error
                            console.log(`⏳ Polling attempt ${pollCount}/${maxPolls} - asset not ready yet`);
                        }
                    };
                    
                    // Start polling every 1 second
                    const pollInterval = setInterval(checkAssetReady, 1000);
                    // Also check immediately
                    checkAssetReady();
                    
                } else {
                    // Error from backend (non-2xx response)
                    console.error('Regeneration error:', result.error || result);
                    regenerateBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Failed';
                    setTimeout(() => {
                        regenerateBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Generate New Version';
                        regenerateBtn.disabled = false;
                        if (isFinal) {
                            regenerateBtn.classList.add('active');
                        } else {
                            regenerateBtn.classList.remove('active');
                        }
                    }, 2000);
                }
            } catch (error) {
                console.error('Regeneration request failed:', error);
                regenerateBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
                setTimeout(() => {
                    regenerateBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Generate New Version';
                    regenerateBtn.disabled = false;
                    if (isFinal) {
                        regenerateBtn.classList.add('active');
                    } else {
                        regenerateBtn.classList.remove('active');
                    }
                }, 2000);
            }
        }
    });
    
    // Rerun button handler - Triggers incremental workflow re-execution based on dirty flags
    rerunBtn.addEventListener('click', async () => {
        // Prevent rerun for showcase projects
        if (isShowcaseProject) {
            console.log('❌ Rerun blocked - showcase projects are read-only');
            return;
        }
        
        console.log('🔄 Rerun workflow clicked - triggering incremental re-execution');
        
        // Show loading state
        rerunBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Rerunning Workflow...';
        rerunBtn.disabled = true;
        rerunBtn.classList.add('active');
        
        // Set workflow state
        workflowRunning = true;
        stopBtn.disabled = false;
        continueBtn.disabled = true;
        
        try {
            // Call backend to re-run workflow based on dirty flags
            const response = await fetch(`/api/rerun/${taskId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (response.ok) {
                // Success
                console.log('✅ Workflow re-execution completed:', result);
                rerunBtn.innerHTML = '<i class="fas fa-check"></i> Workflow Complete!';
                
                // Update workflow state
                workflowRunning = false;
                stopBtn.disabled = true;
                
                // Start polling for updated results
                polling = true;
                const rerunPollResults = setInterval(async () => {
                    if (!polling) {
                        clearInterval(rerunPollResults);
                        return;
                    }
                    
                    try {
                        const resultsRes = await fetch(`/api/results/${taskId}${sourceParam}`);
                        const resultsData = await resultsRes.json();
                        updateAssets(resultsData);
                    } catch (error) {
                        console.error('Error polling results:', error);
                    }
                }, 3000);
            
            // Reset button after a short delay
            setTimeout(() => {
                rerunBtn.innerHTML = '<i class="fas fa-redo"></i> Rerun';
                rerunBtn.disabled = false;  // Keep enabled for subsequent reruns
                rerunBtn.classList.remove('active');
            }, 3000);
        } else {
            // Error
            console.error('Workflow re-execution failed:', result.error);
            rerunBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Rerun Failed';
            
            // Reset workflow state
            workflowRunning = false;
            stopBtn.disabled = true;
            
            setTimeout(() => {
                rerunBtn.innerHTML = '<i class="fas fa-redo"></i> Rerun';
                rerunBtn.disabled = false;
                rerunBtn.classList.remove('active');
            }, 3000);
        }
    } catch (error) {
        console.error('Rerun request failed:', error);
        rerunBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
        
        // Reset workflow state
        workflowRunning = false;
        stopBtn.disabled = true;
        
        setTimeout(() => {
            rerunBtn.innerHTML = '<i class="fas fa-redo"></i> Rerun';
            rerunBtn.disabled = false;
            rerunBtn.classList.remove('active');
        }, 3000);
    }
});

// Stop button handler - Stops the currently running workflow
stopBtn.addEventListener('click', async () => {
    console.log('🛑 Stop workflow clicked');
    
    if (!workflowRunning) {
        console.log('⚠️  No workflow is currently running');
        return;
    }
    
    // Show loading state
    stopBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Stopping...';
    stopBtn.disabled = true;
    
    try {
        const response = await fetch(`/api/stop/${taskId}${sourceParam}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (response.ok) {
            console.log('✅ Workflow stopped:', result);
            stopBtn.innerHTML = '<i class="fas fa-check"></i> Stopped';
            workflowRunning = false;
            
            setTimeout(() => {
                stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop';
                stopBtn.disabled = false;
            }, 2000);
        } else {
            console.error('Failed to stop workflow:', result.error);
            stopBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Failed';
            
            setTimeout(() => {
                stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop';
                stopBtn.disabled = false;
            }, 2000);
        }
    } catch (error) {
        console.error('Stop request failed:', error);
        stopBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
        
        setTimeout(() => {
            stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop';
            stopBtn.disabled = false;
        }, 2000);
    }
});

// Continue button handler - Continues workflow from checkpoint
continueBtn.addEventListener('click', async () => {
    // Prevent continue for showcase projects
    if (isShowcaseProject) {
        console.log('❌ Continue blocked - showcase projects are read-only');
        return;
    }
    
    console.log('▶️ Continue workflow clicked');
    
    // Show loading state
    continueBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Continuing...';
    continueBtn.disabled = true;
    
    try {
        const response = await fetch(`/api/continue/${taskId}${sourceParam}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (response.ok) {
            console.log('✅ Workflow continued:', result);
            continueBtn.innerHTML = '<i class="fas fa-check"></i> Continuing';
            workflowRunning = true;
            stopBtn.disabled = false;
            
            // Start polling for results
            polling = true;
            const continuePollResults = setInterval(async () => {
                if (!polling) {
                    clearInterval(continuePollResults);
                    return;
                }
                
                try {
                    const resultsRes = await fetch(`/api/results/${taskId}${sourceParam}`);
                    const resultsData = await resultsRes.json();
                    updateAssets(resultsData);
                } catch (error) {
                    console.error('Error polling results:', error);
                }
            }, 3000);
            
            setTimeout(() => {
                continueBtn.innerHTML = '<i class="fas fa-play"></i> Continue';
                continueBtn.disabled = true;
            }, 2000);
        } else {
            console.error('Failed to continue workflow:', result.error);
            continueBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Failed';
            
            setTimeout(() => {
                continueBtn.innerHTML = '<i class="fas fa-play"></i> Continue';
                continueBtn.disabled = false;
            }, 2000);
        }
    } catch (error) {
        console.error('Continue request failed:', error);
        continueBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
        
        setTimeout(() => {
            continueBtn.innerHTML = '<i class="fas fa-play"></i> Continue';
            continueBtn.disabled = false;
        }, 2000);
    }
});
    
    // Close text preview
    closeTextPreviewBtn.addEventListener('click', () => {
        textPreviewPanel.style.display = 'none';
        isTextEdited = false;
        regenerateBtn.disabled = true;
        regenerateBtn.classList.remove('active');
        // Note: rerunBtn remains enabled - it should always be clickable
    });
    
    // Toggle asset category collapse/expand
    assetCategoriesContainer.addEventListener('click', (e) => {
        // Check if click is on category header or its children
        const header = e.target.closest('.category-header');
        if (!header) return;
        
        const categoryId = header.dataset.category;
        const categoryEl = document.getElementById(categoryId);
        if (!categoryEl) return;
        
        const gridEl = categoryEl.querySelector('.asset-grid');
        const toggleIcon = categoryEl.querySelector('.category-toggle');
        
        // Toggle collapsed state
        categoryEl.classList.toggle('collapsed');
        
        // Update icon
        if (categoryEl.classList.contains('collapsed')) {
            toggleIcon.classList.remove('fa-chevron-down');
            toggleIcon.classList.add('fa-chevron-right');
            gridEl.style.maxHeight = '0';
        } else {
            toggleIcon.classList.remove('fa-chevron-right');
            toggleIcon.classList.add('fa-chevron-down');
            gridEl.style.maxHeight = gridEl.scrollHeight + 'px';
            // Reset to auto after animation for dynamic content
            setTimeout(() => {
                if (!categoryEl.classList.contains('collapsed')) {
                    gridEl.style.maxHeight = 'none';
                }
            }, 300);
        }
    });

    // Workflow status bar element
    const workflowStatusBar = document.getElementById('workflow-status-bar');
    let lastWorkflowStatus = null;
    let statusBarAutoHideTimer = null;
    let statusBarUserDismissed = false;  // Track if user manually dismissed the status bar
    
    // Update workflow status bar UI
    function updateWorkflowStatusBar(status) {
        if (!workflowStatusBar) return;
        
        const statusIcon = workflowStatusBar.querySelector('.status-icon i');
        const statusLabel = workflowStatusBar.querySelector('.status-label');
        const statusDetail = workflowStatusBar.querySelector('.status-detail');
        
        // Clear any existing auto-hide timer
        if (statusBarAutoHideTimer) {
            clearTimeout(statusBarAutoHideTimer);
            statusBarAutoHideTimer = null;
        }
        
        // Remove all state classes
        workflowStatusBar.classList.remove('running', 'success', 'error', 'stopped');
        
        if (status.running) {
            // Running state - always show and reset dismiss flag
            statusBarUserDismissed = false;
            workflowStatusBar.style.display = 'block';
            workflowStatusBar.classList.add('running');
            statusIcon.className = 'fas fa-spinner';
            statusLabel.textContent = 'Processing';
            statusDetail.textContent = 'Generating assets...';
        } else if (status.status === 'completed') {
            // Completed state - only show if not previously dismissed
            if (!statusBarUserDismissed) {
                workflowStatusBar.style.display = 'block';
                workflowStatusBar.classList.add('success');
                statusIcon.className = 'fas fa-check';
                statusLabel.textContent = 'Completed';
                statusDetail.textContent = 'All assets generated successfully';
                
                // Auto-hide after 5 seconds (only once)
                statusBarAutoHideTimer = setTimeout(() => {
                    if (workflowStatusBar.classList.contains('success')) {
                        workflowStatusBar.style.display = 'none';
                        statusBarUserDismissed = true;  // Mark as dismissed
                    }
                }, 5000);
            }
        } else if (status.status === 'error') {
            // Error state - always show (don't auto-hide errors)
            statusBarUserDismissed = false;
            workflowStatusBar.style.display = 'block';
            workflowStatusBar.classList.add('error');
            statusIcon.className = 'fas fa-exclamation-triangle';
            statusLabel.textContent = 'Error';
            statusDetail.textContent = 'Workflow failed - check logs for details';
        } else if (status.status === 'stopped') {
            // Stopped state - only show if not previously dismissed
            if (!statusBarUserDismissed) {
                workflowStatusBar.style.display = 'block';
                workflowStatusBar.classList.add('stopped');
                statusIcon.className = 'fas fa-pause';
                statusLabel.textContent = 'Stopped';
                statusDetail.textContent = 'Workflow paused - click Continue to resume';
                
                // Auto-hide after 5 seconds (only once)
                statusBarAutoHideTimer = setTimeout(() => {
                    if (workflowStatusBar.classList.contains('stopped')) {
                        workflowStatusBar.style.display = 'none';
                        statusBarUserDismissed = true;  // Mark as dismissed
                    }
                }, 5000);
            }
        } else {
            // Idle state - clear any pending auto-hide and hide status bar
            if (statusBarAutoHideTimer) {
                clearTimeout(statusBarAutoHideTimer);
                statusBarAutoHideTimer = null;
            }
            workflowStatusBar.style.display = 'none';
            statusBarUserDismissed = false;
        }
    }
    
    // Poll workflow status to check if Continue button should be enabled
    async function pollWorkflowStatus() {
        try {
            const response = await fetch(`/api/workflow-status/${taskId}${sourceParam}`);
            if (response.ok) {
                const status = await response.json();
                
                // Skip button updates for showcase projects (they should always be disabled)
                if (!isShowcaseProject) {
                    // Update button states based on workflow status
                    stopBtn.disabled = !status.can_stop;
                    continueBtn.disabled = !status.can_continue;
                }
                
                // Update workflow state tracking
                workflowRunning = status.running;
                
                // Update status bar UI
                updateWorkflowStatusBar(status);
                
                // Track status changes for auto-refresh
                if (lastWorkflowStatus !== status.status) {
                    console.log(`📊 Workflow status changed: ${lastWorkflowStatus} → ${status.status}`);
                    lastWorkflowStatus = status.status;
                }
                
                console.log('📊 Workflow status:', status);
            }
        } catch (error) {
            console.error('Failed to poll workflow status:', error);
        }
    }
    
    // Poll workflow status every 3 seconds
    setInterval(pollWorkflowStatus, 3000);
    
    // Initial status check
    pollWorkflowStatus();

    // Initialize
    projectStatus.textContent = 'Loading...';
});
