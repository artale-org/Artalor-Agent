// -----------------------------------------------------------------------------
// © 2026 Artalor
// Artalor Project — All rights reserved.
// Licensed for personal and educational use only.
// Commercial use or redistribution prohibited.
// See LICENSE.md for full terms.
// -----------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function() {
    // Always start at the top of the home page. Without this, browsers may restore
    // scroll position (e.g. back/forward navigation) and make the Generate area
    // appear "missing" at first glance.
    if ('scrollRestoration' in history) {
        history.scrollRestoration = 'manual';
    }
    window.scrollTo(0, 0);

    const adForm = document.getElementById('ad-form');
    const storyForm = document.getElementById('story-form');
    const productImage = document.getElementById('product_image');
    const fileNameSpan = document.getElementById('file-name');
    const statusDiv = document.getElementById('status');
    const resultDiv = document.getElementById('result');
    const generateBtn = document.getElementById('generate-btn');
    const generateStoryBtn = document.getElementById('generate-story-btn');
    const projectsSection = document.getElementById('projects-section');
    const projectsGrid = document.getElementById('projects-grid');
    const showcaseSection = document.getElementById('showcase-section');
    const showcaseGrid = document.getElementById('showcase-grid');

    // Workflow toggle
    document.querySelectorAll('.workflow-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.workflow-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const wf = tab.dataset.workflow;
            adForm.style.display = wf === 'ad' ? '' : 'none';
            if (storyForm) storyForm.style.display = wf === 'story' ? '' : 'none';
            // Clear status
            statusDiv.textContent = '';
            resultDiv.innerHTML = '';
        });
    });

    // Story file upload handler
    const storyFileUpload = document.getElementById('story-file-upload');
    const storyFileNameSpan = document.getElementById('story-file-name');
    if (storyFileUpload) {
        storyFileUpload.addEventListener('change', function() {
            if (storyFileUpload.files.length > 0) {
                const file = storyFileUpload.files[0];
                storyFileNameSpan.textContent = file.name;
                // Read file content into textarea
                const reader = new FileReader();
                reader.onload = function(e) {
                    document.getElementById('story-text').value = e.target.result;
                };
                reader.readAsText(file);
            } else {
                storyFileNameSpan.textContent = '';
            }
        });
    }

    // Character image upload handler
    const characterImageUpload = document.getElementById('character-image-upload');
    if (characterImageUpload) {
        characterImageUpload.addEventListener('change', function() {
            if (characterImageUpload.files.length > 0) {
                const name = characterImageUpload.files[0].name;
                // Append character image name to the file-name span
                const existing = storyFileNameSpan.textContent;
                storyFileNameSpan.textContent = existing ? `${existing}, ${name}` : name;
            }
        });
    }

    // Load models config on page load
    loadModelsConfig();
    
    // Load showcase (public, no auth needed)
    loadShowcase();
    
    // Load projects
    loadProjects();

    // Track whether user explicitly changed any model dropdown.
    const modelSelectTouched = {
        'image-model': false,
        'video-model': false,
        'audio-model': false
    };
    ['image-model', 'video-model', 'audio-model'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', () => {
                modelSelectTouched[id] = true;
            });
        }
    });

    productImage.addEventListener('change', function() {
        if (productImage.files.length > 0) {
            fileNameSpan.textContent = productImage.files[0].name;
        } else {
            fileNameSpan.textContent = '';
        }
    });

    // Drag and drop functionality for image upload
    const inputArea = document.querySelector('.input-area');
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        inputArea.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        inputArea.addEventListener(eventName, () => {
            inputArea.classList.add('drag-over');
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        inputArea.addEventListener(eventName, () => {
            inputArea.classList.remove('drag-over');
        }, false);
    });
    
    inputArea.addEventListener('drop', function(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            // Check if it's an image file
            const file = files[0];
            if (file.type.startsWith('image/')) {
                // Update the file input
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(file);
                productImage.files = dataTransfer.files;
                
                // Update the file name display
                fileNameSpan.textContent = file.name;
            }
        }
    }, false);

    adForm.addEventListener('submit', async function(event) {
        event.preventDefault();

        // Check if product image is uploaded
        if (!productImage.files || productImage.files.length === 0) {
            statusDiv.textContent = '';
            resultDiv.innerHTML = `<p style="color: #f59e0b;">Please upload a product image to generate your video</p>`;
            return;
        }

        // Check if both API keys are configured
        if (window.apiKeysManager) {
            const apiKeys = window.apiKeysManager.getKeys();
            const hasOpenAI = apiKeys.openai_api_key && apiKeys.openai_api_key.trim() !== '';
            const hasReplicate = apiKeys.replicate_api_token && apiKeys.replicate_api_token.trim() !== '';
            
            if (!hasOpenAI || !hasReplicate) {
                statusDiv.textContent = '';
                resultDiv.innerHTML = `<p style="color: #f59e0b;">⚠️ Please provide your API keys (there will be no additional charge beyond original API costs)</p>`;
                
                // Automatically open the API keys modal
                setTimeout(() => {
                    window.apiKeysManager.showModal();
                }, 100);
                return;
            }
        }
        
        // STRICT MODE:
        // If default model matching failed on load, do not allow submission.
        if (generateBtn.dataset.defaultModelError === 'true') {
            statusDiv.textContent = 'Model config error: default model mismatch.';
            resultDiv.innerHTML = `<p style="color: red;">${generateBtn.dataset.defaultModelErrorMessage || 'Default model mismatch. Please refresh or fix models-config.'}</p>`;
            return;
        }

        const formData = new FormData(adForm);
        
        // Add user API keys if configured
        if (window.apiKeysManager) {
            const apiKeys = window.apiKeysManager.getKeys();
            if (apiKeys.openai_api_key) {
                formData.append('user_openai_api_key', apiKeys.openai_api_key);
            }
            if (apiKeys.replicate_api_token) {
                formData.append('user_replicate_api_token', apiKeys.replicate_api_token);
            }
        }

        generateBtn.disabled = true;
        statusDiv.textContent = 'Starting...';

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Something went wrong');
            }

            const result = await response.json();
            if (result.task_id) {
                window.location.href = `results.html?task_id=${result.task_id}`;
            } else {
                throw new Error('Failed to start generation task.');
            }

        } catch (error) {
            statusDiv.textContent = 'An error occurred.';
            resultDiv.innerHTML = `<p style="color: red;">${error.message}</p>`;
        } finally {
            generateBtn.disabled = false;
        }
    });

    async function loadShowcase() {
        try {
            const response = await fetch('/api/showcase');
            const data = await response.json();
            
            if (data.projects && data.projects.length > 0) {
                displayShowcase(data.projects);
                showcaseSection.style.display = 'block';
            } else {
                showcaseSection.style.display = 'none';
            }
        } catch (error) {
            console.error('Error loading showcase:', error);
            showcaseSection.style.display = 'none';
        }
    }

    async function loadProjects() {
        try {
            const response = await fetch('/api/projects');
            const data = await response.json();
            
            if (data.projects && data.projects.length > 0) {
                displayProjects(data.projects);
                projectsSection.style.display = 'block';
            } else {
                projectsSection.style.display = 'none';
            }
        } catch (error) {
            console.error('Error loading projects:', error);
            projectsSection.style.display = 'none';
        }
    }

    function displayShowcase(projects) {
        if (projects.length === 0) {
            showcaseGrid.innerHTML = `
                <div class="empty-projects">
                    <i class="fas fa-star"></i>
                    <p>No showcase projects available.</p>
                </div>
            `;
            return;
        }

        showcaseGrid.innerHTML = projects.map(project => {
            const isStory = project.workflow_type === 'story';
            const typeIcon = isStory ? 'fa-book-open' : 'fa-bullhorn';
            const typeLabel = isStory ? 'Story' : 'Ad';
            const typeClass = isStory ? 'type-story' : 'type-ad';
            return `
            <div class="project-card showcase-card" onclick="openProject('${project.id}', true)">
                ${project.final_video ? `
                    <div class="showcase-video-container">
                        <video 
                            class="showcase-video" 
                            src="${project.final_video}" 
                            muted 
                            loop 
                            playsinline
                            preload="metadata"
                        ></video>
                        <div class="showcase-video-overlay">
                            <i class="fas fa-play-circle"></i>
                        </div>
                        <span class="project-type-badge ${typeClass}"><i class="fas ${typeIcon}"></i> ${typeLabel}</span>
                    </div>
                ` : `
                    <div class="showcase-video-placeholder">
                        <i class="fas fa-video"></i>
                        <span class="project-type-badge ${typeClass}"><i class="fas ${typeIcon}"></i> ${typeLabel}</span>
                    </div>
                `}
                <div class="project-content">
                    <div class="project-header">
                        <h4 class="project-title">${project.name}</h4>
                        <span class="project-status ${project.status}">${project.status.replace('_', ' ')}</span>
                    </div>
                    <p class="project-description">${project.description}</p>
                    <div class="project-meta">
                        <div class="project-date">
                            <i class="fas fa-clock"></i>
                            ${project.modified}
                        </div>
                        <div class="project-assets">
                            <i class="fas fa-layer-group"></i>
                            ${project.asset_count} assets
                        </div>
                    </div>
                </div>
            </div>
        `}).join('');
        
        // Add hover event listeners for video playback
        showcaseGrid.querySelectorAll('.showcase-card').forEach(card => {
            const video = card.querySelector('.showcase-video');
            const overlay = card.querySelector('.showcase-video-overlay');
            
            if (video) {
                card.addEventListener('mouseenter', () => {
                    video.play().catch(() => {});
                    if (overlay) overlay.style.opacity = '0';
                });
                
                card.addEventListener('mouseleave', () => {
                    video.pause();
                    video.currentTime = 0;
                    if (overlay) overlay.style.opacity = '1';
                });
            }
        });
    }

    function displayProjects(projects) {
        if (projects.length === 0) {
            projectsGrid.innerHTML = `
                <div class="empty-projects">
                    <i class="fas fa-folder-open"></i>
                    <p>No projects yet. Create your first ad!</p>
                </div>
            `;
            return;
        }

        projectsGrid.innerHTML = projects.map(project => {
            const isStory = project.workflow_type === 'story';
            const typeIcon = isStory ? 'fa-book-open' : 'fa-bullhorn';
            const typeLabel = isStory ? 'Story' : 'Ad';
            const typeClass = isStory ? 'type-story' : 'type-ad';
            return `
            <div class="project-card" onclick="openProject('${project.id}')">
                ${project.thumbnail ? `
                    <div class="project-thumbnail">
                        <img src="${project.thumbnail}" alt="${project.name}" loading="lazy" decoding="async" onload="this.classList.add('loaded')">
                        <span class="project-type-badge ${typeClass}"><i class="fas ${typeIcon}"></i> ${typeLabel}</span>
                    </div>
                ` : `
                    <div class="project-thumbnail placeholder">
                        <i class="fas ${isStory ? 'fa-book-open' : 'fa-images'}"></i>
                        <span class="project-type-badge ${typeClass}"><i class="fas ${typeIcon}"></i> ${typeLabel}</span>
                    </div>
                `}
                <div class="project-content">
                    <div class="project-header">
                        <h4 class="project-title">${project.name}</h4>
                        <span class="project-status ${project.status}">${project.status.replace('_', ' ')}</span>
                    </div>
                    <p class="project-description">${project.description}</p>
                    <div class="project-meta">
                        <div class="project-date">
                            <i class="fas fa-clock"></i>
                            ${project.modified}
                        </div>
                        <div class="project-assets">
                            <i class="fas fa-layer-group"></i>
                            ${project.asset_count} assets
                        </div>
                    </div>
                </div>
            </div>
        `}).join('');
    }

    // Story form submission
    if (storyForm) {
        storyForm.addEventListener('submit', async function(event) {
            event.preventDefault();

            const storyText = document.getElementById('story-text').value.trim();
            if (!storyText) {
                statusDiv.textContent = '';
                resultDiv.innerHTML = `<p style="color: #f59e0b;">Please enter or upload a story to generate your video</p>`;
                return;
            }

            // Check API keys
            if (window.apiKeysManager) {
                const apiKeys = window.apiKeysManager.getKeys();
                const hasOpenAI = apiKeys.openai_api_key && apiKeys.openai_api_key.trim() !== '';
                const hasReplicate = apiKeys.replicate_api_token && apiKeys.replicate_api_token.trim() !== '';
                
                if (!hasOpenAI || !hasReplicate) {
                    statusDiv.textContent = '';
                    resultDiv.innerHTML = `<p style="color: #f59e0b;">\u26a0\ufe0f Please provide your API keys (there will be no additional charge beyond original API costs)</p>`;
                    setTimeout(() => { window.apiKeysManager.showModal(); }, 100);
                    return;
                }
            }

            const formData = new FormData();
            formData.append('story', storyText);

            // Add character image if uploaded
            const charImgInput = document.getElementById('character-image-upload');
            if (charImgInput && charImgInput.files.length > 0) {
                formData.append('character_image', charImgInput.files[0]);
            }

            // Add target duration
            const storyTargetDuration = document.getElementById('story-target-duration');
            if (storyTargetDuration && storyTargetDuration.value) formData.append('target_duration', storyTargetDuration.value);

            // Add selected models
            const storyImageModel = document.getElementById('story-image-model');
            const storyVideoModel = document.getElementById('story-video-model');
            if (storyImageModel && storyImageModel.value) formData.append('image_model', storyImageModel.value);
            if (storyVideoModel && storyVideoModel.value) formData.append('video_model', storyVideoModel.value);

            // Add user API keys
            if (window.apiKeysManager) {
                const apiKeys = window.apiKeysManager.getKeys();
                if (apiKeys.openai_api_key) formData.append('user_openai_api_key', apiKeys.openai_api_key);
                if (apiKeys.replicate_api_token) formData.append('user_replicate_api_token', apiKeys.replicate_api_token);
            }

            generateStoryBtn.disabled = true;
            statusDiv.textContent = 'Starting story video generation...';

            try {
                const response = await fetch('/generate-story', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Something went wrong');
                }

                const result = await response.json();
                if (result.task_id) {
                    window.location.href = `results.html?task_id=${result.task_id}`;
                } else {
                    throw new Error('Failed to start story generation task.');
                }

            } catch (error) {
                statusDiv.textContent = 'An error occurred.';
                resultDiv.innerHTML = `<p style="color: red;">${error.message}</p>`;
            } finally {
                generateStoryBtn.disabled = false;
            }
        });
    }

    async function loadModelsConfig() {
        try {
            const response = await fetch('/api/models-config');
            const data = await response.json();
            
            if (data.defaults && data.available) {
                populateModelDropdown('image-model', data.available.image_generation, data.defaults.image_generation);
                populateModelDropdown('video-model', data.available.video_generation, data.defaults.video_generation);
                populateModelDropdown('audio-model', data.available.tts, data.defaults.tts);

                // Also populate story form dropdowns (image + video only) using story-specific defaults
                const storyDefaults = data.story_defaults || data.defaults;
                populateModelDropdown('story-image-model', data.available.image_generation, storyDefaults.image_generation || data.defaults.image_generation);
                populateModelDropdown('story-video-model', data.available.video_generation, storyDefaults.video_generation || data.defaults.video_generation);

                // After populating, strictly validate that provided defaults actually exist in the dropdowns.
                // If not, block Generate and surface a clear error (no silent fallback to "first option").
                const errors = [];
                ['image-model', 'video-model', 'audio-model'].forEach(id => {
                    const sel = document.getElementById(id);
                    if (!sel) return;
                    const expected = sel.dataset.defaultModel || '';
                    const matched = sel.dataset.defaultMatched === 'true';
                    if (expected && !matched) {
                        errors.push(`${id}: default="${expected}" not found in available options`);
                    }
                });

                if (errors.length > 0) {
                    const msg = `Default model mismatch. Refusing to continue.\n${errors.join('\n')}`;
                    console.error(msg);
                    statusDiv.textContent = 'Model config error.';
                    resultDiv.innerHTML = `<p style="color: red; white-space: pre-wrap;">${msg}</p>`;
                    generateBtn.disabled = true;
                    generateBtn.dataset.defaultModelError = 'true';
                    generateBtn.dataset.defaultModelErrorMessage = msg;
                } else {
                    generateBtn.dataset.defaultModelError = 'false';
                    generateBtn.dataset.defaultModelErrorMessage = '';
                }
            }
        } catch (error) {
            console.error('Error loading models config:', error);
            // Set fallback "Loading failed" message
            ['image-model', 'video-model', 'audio-model', 'story-image-model', 'story-video-model'].forEach(id => {
                const select = document.getElementById(id);
                if (select) {
                    select.innerHTML = '<option value="">Loading failed</option>';
                }
            });
        }
    }

    function populateModelDropdown(selectId, models, defaultModel) {
        const select = document.getElementById(selectId);
        if (!select) return;

        // Clear existing options
        select.innerHTML = '';

        // Store expected default for strict validation
        const defaultBase = (defaultModel && typeof defaultModel === 'string')
            ? defaultModel.split(':')[0]
            : (defaultModel || '');
        select.dataset.defaultModel = defaultModel || '';
        select.dataset.defaultBase = defaultBase || '';
        select.dataset.defaultMatched = 'false';

        // Add all model options
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            
            // Create a shorter display name (take last part after /)
            let displayName = model;
            if (model.includes('/')) {
                const parts = model.split('/');
                displayName = parts[parts.length - 1];
                // If there's a version/hash after :, truncate it for display
                if (displayName.includes(':')) {
                    displayName = displayName.split(':')[0];
                }
            }
            
            option.textContent = displayName;
            
            // Mark as default if it matches (base-name match to avoid hash/version mismatches)
            const modelBase = (model && typeof model === 'string') ? model.split(':')[0] : model;
            if (defaultModel && (model === defaultModel || (modelBase && defaultBase && modelBase === defaultBase))) {
                // Show hash in UI if default contains it (e.g., model:003f...)
                const hash = (typeof defaultModel === 'string' && defaultModel.includes(':'))
                    ? defaultModel.split(':')[1]
                    : '';
                const shortHash = hash ? hash.slice(0, 8) : '';
                option.textContent += shortHash ? ` (default @${shortHash})` : ' (default)';
                option.selected = true;
                select.dataset.defaultMatched = 'true';
            }
            
            select.appendChild(option);
        });
    }

    // Make openProject function global so it can be called from onclick
    window.openProject = function(projectId, isShowcase = false) {
        const params = new URLSearchParams({ task_id: projectId });
        if (isShowcase) {
            params.append('source', 'showcase');
        }
        window.location.href = `results.html?${params.toString()}`;
    };
});
