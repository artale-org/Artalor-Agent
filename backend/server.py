# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

import os
import subprocess
import uuid
import json
import re
import logging
import threading
import signal
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime, UTC
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


app = Flask(__name__, static_folder='../frontend')

# Silence only the noisy polling access logs (keep other logs).
# These lines are emitted by Werkzeug's request logger, not app.logger.
class _WerkzeugPollingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        # Frontend polling endpoints (every 3s) – hide only these.
        if 'GET /api/results/' in msg or 'GET /api/status/' in msg:
            return False
        return True

logging.getLogger('werkzeug').addFilter(_WerkzeugPollingFilter())

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'task_data')
ALLOWED_EXTENSIONS = {
    'images': {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff'},
    'videos': {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv'},
    'audio': {'mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a'}
}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Global workflow tracking
# Format: {task_id: {'thread': thread_obj, 'stop_event': threading.Event(), 'status': 'running'|'stopped'}}
running_workflows = {}

def is_task_complete(task_path):
    """Check if a task is complete by checking for final_complete video in final_videos folder"""
    # Check for completion marker file (legacy)
    completion_file = os.path.join(task_path, '__complete__')
    if os.path.exists(completion_file):
        return True
    
    # Check if final_complete video exists in final_videos folder
    final_videos_folder = os.path.join(task_path, 'final_videos')
    if os.path.exists(final_videos_folder):
        try:
            # Look for any video file starting with 'final_complete'
            for filename in os.listdir(final_videos_folder):
                if filename.startswith('final_complete') and not filename.endswith('.json'):
                    file_path = os.path.join(final_videos_folder, filename)
                    # Check if it's a file (not a directory) and it exists
                    if os.path.isfile(file_path):
                        return True
        except Exception as e:
            print(f"Error checking final video in final_videos folder: {e}")
    
    return False


def detect_workflow_type(task_id: str) -> str:
    """
    Detect whether a task is an ad creation or story video workflow.
    
    Returns:
        'ad' for ad creation workflows
        'story' for story video workflows
        'unknown' if cannot determine
    """
    if 'story_video' in task_id:
        return 'story'
    if 'ad_creation' in task_id:
        return 'ad'
    
    # Fallback: check task directory for clues
    task_path = os.path.join(UPLOAD_FOLDER, task_id)
    if os.path.exists(task_path):
        # Story workflows have story_analysis JSON but no upload folder with images
        if os.path.exists(os.path.join(task_path, 'story_analysis.json')):
            return 'story'
        if os.path.exists(os.path.join(task_path, 'upload')):
            return 'ad'
    
    return 'unknown'


def generate_composite_thumbnail(task_path: str) -> str:
    """
    Generate a composite thumbnail by combining all sub_video image_first images.
    Saves to task_path/thumbnail_composite.jpg
    
    Returns the path to the generated thumbnail, or None if generation fails.
    """
    try:
        from PIL import Image
        import math
        
        THUMB_NAME = 'thumbnail_composite.jpg'
        thumb_path = os.path.join(task_path, THUMB_NAME)
        
        image_exts = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
        images_to_combine = []
        
        # Collect images from sub_video folders
        for i in range(100):  # Reasonable limit
            sub_video_dir = os.path.join(task_path, f'sub_video_{i}')
            if not os.path.exists(sub_video_dir):
                break
            
            # Find image_first (prefer current version, then v1, then any image)
            found_image = None
            for name in ['image_first', 'image_first_v1', 'image']:
                for ext in image_exts:
                    candidate = os.path.join(sub_video_dir, f'{name}{ext}')
                    if os.path.exists(candidate):
                        found_image = candidate
                        break
                if found_image:
                    break
            
            # Fallback to any image in folder
            if not found_image:
                for f in sorted(os.listdir(sub_video_dir)):
                    if f.lower().endswith(image_exts) and not f.startswith('.'):
                        found_image = os.path.join(sub_video_dir, f)
                        break
            
            if found_image:
                images_to_combine.append(found_image)
        
        # Also include upload folder image as first
        upload_dir = os.path.join(task_path, 'upload')
        if os.path.exists(upload_dir):
            for f in sorted(os.listdir(upload_dir)):
                if f.lower().endswith(image_exts) and not f.startswith('.'):
                    images_to_combine.insert(0, os.path.join(upload_dir, f))
                    break
        
        if not images_to_combine:
            return None
        
        # Create composite image
        num_images = len(images_to_combine)
        cols = min(num_images, 3)  # Max 3 columns
        rows = math.ceil(num_images / cols)
        
        # Cell size
        cell_width = 150
        cell_height = 100
        
        # Create composite
        composite_width = cols * cell_width
        composite_height = rows * cell_height
        composite = Image.new('RGB', (composite_width, composite_height), (30, 30, 30))
        
        for idx, img_path in enumerate(images_to_combine):
            try:
                with Image.open(img_path) as img:
                    # Convert to RGB if necessary
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    
                    # Resize to fit cell while maintaining aspect ratio
                    img.thumbnail((cell_width - 4, cell_height - 4), Image.Resampling.LANCZOS)
                    
                    # Calculate position (center in cell)
                    col = idx % cols
                    row = idx // cols
                    x = col * cell_width + (cell_width - img.width) // 2
                    y = row * cell_height + (cell_height - img.height) // 2
                    
                    composite.paste(img, (x, y))
            except Exception as e:
                print(f"Error processing image {img_path}: {e}")
                continue
        
        # Save composite
        composite.save(thumb_path, 'JPEG', quality=85, optimize=True)
        print(f"✅ Generated composite thumbnail: {thumb_path}")
        return thumb_path
        
    except ImportError:
        print("⚠️  Pillow not installed, cannot generate composite thumbnail")
        return None
    except Exception as e:
        print(f"Error generating composite thumbnail: {e}")
        return None


def get_project_thumbnail(task_path: str, task_id: str) -> str:
    """
    Get the project thumbnail URL.
    Returns the composite thumbnail if it exists, otherwise generates it.
    
    Returns relative URL path like '/projects/task_id/thumbnail_composite.jpg'
    or None if no thumbnail available.
    """
    THUMB_NAME = 'thumbnail_composite.jpg'
    thumb_path = os.path.join(task_path, THUMB_NAME)
    
    # If composite thumbnail exists, return it
    if os.path.exists(thumb_path):
        return f'/projects/{task_id}/{THUMB_NAME}'
    
    # Try to generate it
    if generate_composite_thumbnail(task_path):
        return f'/projects/{task_id}/{THUMB_NAME}'
    
    # Fallback: return first available image
    image_exts = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
    
    # Try sub_video_0/image_first
    sub_video_0 = os.path.join(task_path, 'sub_video_0')
    if os.path.exists(sub_video_0):
        for name in ['image_first', 'image_first_v1', 'image']:
            for ext in image_exts:
                candidate = os.path.join(sub_video_0, f'{name}{ext}')
                if os.path.exists(candidate):
                    return f'/projects/{task_id}/sub_video_0/{name}{ext}'
    
    # Try upload folder
    upload_dir = os.path.join(task_path, 'upload')
    if os.path.exists(upload_dir):
        for f in sorted(os.listdir(upload_dir)):
            if f.lower().endswith(image_exts) and not f.startswith('.'):
                return f'/projects/{task_id}/upload/{f}'
    
    return None


def allowed_file(filename):
    if '.' not in filename:
        return False, None
    
    ext = filename.rsplit('.', 1)[1].lower()
    for file_type, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return True, file_type
    return False, None

def get_file_type(filename):
    if '.' not in filename:
        return None
    
    ext = filename.rsplit('.', 1)[1].lower()
    for file_type, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return file_type
    return None

def parse_versioned_asset_path(path: str):
    """
    Parse a potentially versioned asset path.

    - Version suffix format: `_v<digits>` right before the extension.

    Returns:
      (normalized_path, normalized_filename, version_tag_or_none)

    Examples:
      - sub_video_0/image_last_v11.png -> (sub_video_0/image_last.png, image_last.png, "v11")
      - voiceover_v2.mp3 -> (voiceover.mp3, voiceover.mp3, "v2")
      - video.mp4 -> (video.mp4, video.mp4, None)
    """
    try:
        if not path or not isinstance(path, str):
            return path, os.path.basename(path) if isinstance(path, str) else None, None

        d = os.path.dirname(path)
        b = os.path.basename(path)

        # Capture optional `_v<digits>` right before extension
        m = re.match(r'^(?P<stem>.+?)(?:_v(?P<ver>\d+))?(?P<ext>\.[^.]+)$', b)
        if not m:
            # No extension or unexpected form; return as-is
            return path, b, None

        stem = m.group('stem')
        ext = m.group('ext')
        ver_str = m.group('ver')
        ver_tag = f"v{ver_str}" if ver_str is not None else None

        normalized_filename = f"{stem}{ext}"
        normalized_path = os.path.join(d, normalized_filename) if d else normalized_filename
        return normalized_path, normalized_filename, ver_tag
    except Exception:
        # Best-effort fallback
        try:
            return path, os.path.basename(path), None
        except Exception:
            return path, None, None

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/projects/<path:path>')
def serve_project_files(path):
    # Extract task_id (first part of path before /)
    task_id = path.split('/')[0] if '/' in path else path
    
    # First try task_data folder
    task_data_file = os.path.join(app.config['UPLOAD_FOLDER'], path)
    if os.path.exists(task_data_file):
        return send_from_directory(app.config['UPLOAD_FOLDER'], path)
    
    # If not found, try showcase folder
    showcase_folder = os.path.join(os.path.dirname(app.config['UPLOAD_FOLDER']), 'showcase')
    showcase_file = os.path.join(showcase_folder, path)
    if os.path.exists(showcase_file):
        return send_from_directory(showcase_folder, path)
    
    # File not found in either location
    return jsonify({'error': 'File not found'}), 404

@app.route('/generate', methods=['POST'])
def generate_ad():
    if 'product_image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    requirement = request.form.get('requirement')
    file = request.files['product_image']
    
    # Get target duration (default to 30 seconds)
    target_duration = request.form.get('target_duration', '30')
    try:
        target_duration = int(target_duration)
        # Validate duration range (15-120 seconds)
        if target_duration < 15:
            target_duration = 15
        elif target_duration > 120:
            target_duration = 120
    except (ValueError, TypeError):
        target_duration = 30
    
    # Get selected models from form
    # NOTE: browsers may submit empty string; normalize to None
    def _norm(v: str):
        if v is None:
            return None
        v = v.strip()
        return v if v else None

    image_model = _norm(request.form.get('image_model'))
    video_model = _norm(request.form.get('video_model'))
    audio_model = _norm(request.form.get('audio_model'))
    
    # Get user-provided API keys (optional)
    user_openai_api_key = _norm(request.form.get('user_openai_api_key'))
    user_replicate_api_token = _norm(request.form.get('user_replicate_api_token'))

    if not requirement or not file or file.filename == '':
        return jsonify({'error': 'Missing requirement or image file'}), 400

    is_allowed, file_type = allowed_file(file.filename)
    langgraph = True  # Set to True to use LangGraph workflow, otherwise use original workflow
    if file and is_allowed:
        if langgraph:
            prefix = 'ad_creation_langgraph_'
            workflow_script = 'ad_creation_workflow_langgraph.py'
        else:
            prefix = 'ad_creation_'
            workflow_script = 'ad_creation_workflow.py'
        try:
            task_id = prefix + datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
            upload_path = os.path.join(task_path, 'upload')
            os.makedirs(upload_path, exist_ok=True)

            filename = secure_filename(file.filename)
            image_path = os.path.join(upload_path, filename)
            file.save(image_path)

            # Strict model validation: if user provided a model, it MUST exist in models_config.json.
            # No silent fallbacks to unexpected models.
            if image_model or video_model or audio_model:
                config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
                models_config_path = os.path.join(config_dir, 'models_config.json')
                with open(models_config_path, 'r') as f:
                    models_config = json.load(f) or {}

                def _base(m: str) -> str:
                    return m.split(':')[0] if isinstance(m, str) and m else m

                def _is_allowed(model_type: str, model_name: str) -> bool:
                    if not model_name:
                        return True
                    allowed = set((models_config.get('models') or {}).get(model_type, {}).keys())
                    if model_name in allowed:
                        return True
                    # Also allow "model:hash" if base matches a known model key
                    return _base(model_name) in allowed

                if image_model and not _is_allowed('image_generation', image_model):
                    return jsonify({'error': f'Invalid image_model: {image_model}'}), 400
                if video_model and not _is_allowed('video_generation', video_model):
                    return jsonify({'error': f'Invalid video_model: {video_model}'}), 400
                if audio_model and not _is_allowed('tts', audio_model):
                    return jsonify({'error': f'Invalid audio_model: {audio_model}'}), 400

            # Create custom workflow config if models are selected
            config_path = None
            if image_model or video_model or audio_model:
                config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
                template_path = os.path.join(config_dir, 'ad_workflow_config_template.json')
                models_config_path = os.path.join(config_dir, 'models_config.json')
                
                # Load template and models config
                with open(template_path, 'r') as f:
                    config = json.load(f)
                
                with open(models_config_path, 'r') as f:
                    models_config = json.load(f)

                def _base(m: str) -> str:
                    return m.split(':')[0] if isinstance(m, str) and m else m

                def _canonical_with_template_default(selected: str, template_default: str) -> str:
                    """
                    STRICT: never invent a version hash.
                    - If selected includes ':', keep as-is.
                    - If selected is a base name and matches template default base, use template default (may include ':hash').
                    - Otherwise keep selected as-is.
                    """
                    if not selected:
                        return selected
                    if isinstance(selected, str) and ':' in selected:
                        return selected
                    if template_default and isinstance(template_default, str) and _base(template_default) == selected:
                        return template_default
                    return selected
                
                # Helper function to extract default parameters for a model
                def get_model_default_params(model_type, model_name):
                    if 'models' in models_config and model_type in models_config['models']:
                        if model_name in models_config['models'][model_type]:
                            model_def = models_config['models'][model_type][model_name]
                            if 'parameters' in model_def:
                                defaults = {}
                                for param_name, param_def in model_def['parameters'].items():
                                    if 'default' in param_def:
                                        defaults[param_name] = param_def['default']
                                return defaults
                    return {}
                
                # Update models and their parameters if provided
                if image_model:
                    # Preserve original identifier (do NOT drop ':hash' if user ever provides one)
                    config['image_generation']['model'] = image_model
                    default_params = get_model_default_params('image_generation', _base(image_model))
                    if default_params:
                        config['image_generation']['parameters'] = default_params
                
                if video_model:
                    # Preserve original identifier. If user selected base name that matches template default,
                    # use the template default (which may include the required Replicate version hash).
                    template_default_video = config.get('video_generation', {}).get('model', '')
                    canonical_video = _canonical_with_template_default(video_model, template_default_video)
                    config['video_generation']['model'] = canonical_video
                    default_params = get_model_default_params('video_generation', _base(video_model))
                    if default_params:
                        config['video_generation']['parameters'] = default_params
                
                if audio_model:
                    config['tts']['model'] = audio_model
                    default_params = get_model_default_params('tts', _base(audio_model))
                    if default_params:
                        config['tts']['parameters'] = default_params
                
                # Save custom config to task directory
                config_path = os.path.join(task_path, 'workflow_config.json')
                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)

            # Save user API keys to task config for rerun/continue
            api_keys_config = {}
            if user_openai_api_key:
                api_keys_config['openai_api_key'] = user_openai_api_key
            if user_replicate_api_token:
                api_keys_config['replicate_api_token'] = user_replicate_api_token
            
            if api_keys_config:
                api_keys_path = os.path.join(task_path, '.api_keys.json')
                with open(api_keys_path, 'w') as f:
                    json.dump(api_keys_config, f)
                print(f"🔑 Saved API keys config for task rerun")

            # Run the ad creation workflow script as a background process
            workflow_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workflow_applications', 'advertisement', workflow_script)
            
            log_path = os.path.join(task_path, 'logs')
            os.makedirs(log_path, exist_ok=True)
            log_file_path = os.path.join(log_path, 'output.log')

            # Build command with config if provided
            cmd = [
                'python', workflow_script_path,
                '--requirement', requirement,
                '--image', image_path,
                '--task-path', task_path,
                '--target-duration', str(target_duration)  # Add target duration parameter
            ]
            
            if config_path:
                cmd.extend(['--config', config_path])

            # Prepare environment with user API keys (if provided)
            env = os.environ.copy()
            if user_openai_api_key:
                env['OPENAI_API_KEY'] = user_openai_api_key
                print(f"🔑 Using user-provided OpenAI API key")
            if user_replicate_api_token:
                env['REPLICATE_API_TOKEN'] = user_replicate_api_token
                print(f"🔑 Using user-provided Replicate API token")

            with open(log_file_path, 'w') as log_file:
                proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=env)

            # Track this workflow for status monitoring
            running_workflows[task_id] = {
                'process': proc,
                'stop_event': threading.Event(),
                'status': 'running'
            }

            return jsonify({'message': 'Ad creation started successfully', 'task_id': task_id, 'status': 'running'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/generate-story', methods=['POST'])
def generate_story():
    """
    Start a story video workflow.
    
    Expected form data:
    - story: Story text content (required)
    - image_model: Image generation model (optional)
    - video_model: Video generation model (optional)
    - user_openai_api_key: User-provided OpenAI API key (optional)
    - user_replicate_api_token: User-provided Replicate API token (optional)
    """
    story = request.form.get('story')
    if not story or not story.strip():
        return jsonify({'error': 'Story text is required'}), 400

    # Normalize optional model selections
    def _norm(v: str):
        if v is None:
            return None
        v = v.strip()
        return v if v else None

    image_model = _norm(request.form.get('image_model'))
    video_model = _norm(request.form.get('video_model'))

    # Get target duration (default to 30 seconds)
    target_duration = request.form.get('target_duration', '30')
    try:
        target_duration = int(target_duration)
        # Validate duration range (15-120 seconds)
        if target_duration < 15:
            target_duration = 15
        elif target_duration > 120:
            target_duration = 120
    except (ValueError, TypeError):
        target_duration = 30

    # Get user-provided API keys (optional)
    user_openai_api_key = _norm(request.form.get('user_openai_api_key'))
    user_replicate_api_token = _norm(request.form.get('user_replicate_api_token'))

    try:
        task_id = 'story_video_langgraph_' + datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        os.makedirs(task_path, exist_ok=True)

        # Save story text to file inside task directory
        story_file_path = os.path.join(task_path, 'story_input.txt')
        with open(story_file_path, 'w', encoding='utf-8') as f:
            f.write(story)

        # Save user-uploaded character image if provided
        character_image = request.files.get('character_image')
        if character_image and character_image.filename:
            char_ref_dir = os.path.join(task_path, 'character_reference')
            os.makedirs(char_ref_dir, exist_ok=True)
            # Save as character.png (standard name expected by workflow)
            ext = os.path.splitext(character_image.filename)[1] or '.png'
            char_save_path = os.path.join(char_ref_dir, f'character{ext}')
            character_image.save(char_save_path)
            print(f"🎨 User-uploaded character image saved: {char_save_path}")

        # Create custom workflow config if models are selected
        config_path = None
        config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
        template_path = os.path.join(config_dir, 'story_workflow_config_template.json')

        # Load template
        default_cfg = {}
        if os.path.exists(template_path):
            with open(template_path, 'r') as f:
                default_cfg = json.load(f) or {}

        if image_model or video_model:
            models_config_path = os.path.join(config_dir, 'models_config.json')
            models_config = {}
            if os.path.exists(models_config_path):
                with open(models_config_path, 'r') as f:
                    models_config = json.load(f) or {}

            def get_model_default_params(model_type, model_name):
                if 'models' in models_config and model_type in models_config['models']:
                    base = model_name.split(':')[0] if isinstance(model_name, str) else model_name
                    for key in [model_name, base]:
                        if key in models_config['models'][model_type]:
                            model_def = models_config['models'][model_type][key]
                            if 'parameters' in model_def:
                                return {p: d['default'] for p, d in model_def['parameters'].items() if 'default' in d}
                return {}

            def _base(m: str) -> str:
                return m.split(':')[0] if isinstance(m, str) and m else m

            def _canonical_with_template_default(selected: str, template_default: str) -> str:
                """
                If selected is a base name that matches the template default's base,
                use the template default (which may include ':hash').
                """
                if not selected:
                    return selected
                if isinstance(selected, str) and ':' in selected:
                    return selected
                if template_default and isinstance(template_default, str) and _base(template_default) == selected:
                    return template_default
                return selected

            if image_model:
                if 'image_generation' not in default_cfg:
                    default_cfg['image_generation'] = {}
                template_default_image = default_cfg.get('image_generation', {}).get('model', '')
                default_cfg['image_generation']['model'] = _canonical_with_template_default(image_model, template_default_image)
                params = get_model_default_params('image_generation', _base(image_model))
                if params:
                    default_cfg['image_generation']['parameters'] = params

            if video_model:
                if 'video_generation' not in default_cfg:
                    default_cfg['video_generation'] = {}
                template_default_video = default_cfg.get('video_generation', {}).get('model', '')
                default_cfg['video_generation']['model'] = _canonical_with_template_default(video_model, template_default_video)
                params = get_model_default_params('video_generation', _base(video_model))
                if params:
                    default_cfg['video_generation']['parameters'] = params

        # Inject target_duration into workflow config
        if 'global_settings' not in default_cfg:
            default_cfg['global_settings'] = {}
        default_cfg['global_settings']['target_duration'] = target_duration

        # Save workflow config to task directory
        config_path = os.path.join(task_path, 'workflow_config.json')
        with open(config_path, 'w') as f:
            json.dump(default_cfg, f, indent=2)

        # Save user API keys to task config for rerun/continue
        api_keys_config = {}
        if user_openai_api_key:
            api_keys_config['openai_api_key'] = user_openai_api_key
        if user_replicate_api_token:
            api_keys_config['replicate_api_token'] = user_replicate_api_token

        if api_keys_config:
            api_keys_path = os.path.join(task_path, '.api_keys.json')
            with open(api_keys_path, 'w') as f:
                json.dump(api_keys_config, f)
            print(f"🔑 Saved API keys config for story task")

        # Run the story video workflow script as a background process
        workflow_script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'workflow_applications', 'story_to_video',
            'story_video_workflow_langgraph.py'
        )

        log_path = os.path.join(task_path, 'logs')
        os.makedirs(log_path, exist_ok=True)
        log_file_path = os.path.join(log_path, 'output.log')

        cmd = [
            'python', workflow_script_path,
            '--story-file', story_file_path,
            '--task-path', task_path,
            '--config', config_path,
            '--target-duration', str(target_duration)
        ]

        # Prepare environment with user API keys
        env = os.environ.copy()
        if user_openai_api_key:
            env['OPENAI_API_KEY'] = user_openai_api_key
            print(f"🔑 Using user-provided OpenAI API key")
        if user_replicate_api_token:
            env['REPLICATE_API_TOKEN'] = user_replicate_api_token
            print(f"🔑 Using user-provided Replicate API token")

        with open(log_file_path, 'w') as log_file:
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=env)

        # Track this workflow for status monitoring
        running_workflows[task_id] = {
            'process': proc,
            'stop_event': threading.Event(),
            'status': 'running'
        }

        return jsonify({'message': 'Story video creation started successfully', 'task_id': task_id, 'status': 'running'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/upload/<task_id>', methods=['POST'])
def upload_files(task_id):
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files')
    if not files or all(file.filename == '' for file in files):
        return jsonify({'error': 'No files selected'}), 400

    task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
    if not os.path.exists(task_path):
        return jsonify({'error': 'Task not found'}), 404

    uploaded_files = []
    errors = []

    for file in files:
        if file.filename == '':
            continue
            
        is_allowed, file_type = allowed_file(file.filename)
        if not is_allowed:
            errors.append(f'File type not allowed: {file.filename}')
            continue

        try:
            filename = secure_filename(file.filename)
            
            # Create appropriate folder based on file type
            if file_type == 'images':
                folder_path = os.path.join(task_path, 'images')
            elif file_type == 'videos':
                folder_path = os.path.join(task_path, 'videos')
            elif file_type == 'audio':
                folder_path = os.path.join(task_path, 'audios')
            
            os.makedirs(folder_path, exist_ok=True)
            
            # Save file
            file_path = os.path.join(folder_path, filename)
            file.save(file_path)
            
            uploaded_files.append({
                'filename': filename,
                'type': file_type,
                'path': os.path.relpath(file_path, app.config['UPLOAD_FOLDER'])
            })
            
        except Exception as e:
            errors.append(f'Error uploading {file.filename}: {str(e)}')

    response = {'uploaded_files': uploaded_files}
    if errors:
        response['errors'] = errors
        
    return jsonify(response), 200 if uploaded_files else 400

@app.route('/delete/<task_id>', methods=['DELETE'])
def delete_file(task_id):
    data = request.get_json()
    if not data or 'file_path' not in data:
        return jsonify({'error': 'No file path provided'}), 400

    file_path = data['file_path']
    task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
    
    if not os.path.exists(task_path):
        return jsonify({'error': 'Task not found'}), 404

    # Construct full file path
    full_file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_path)
    
    # Security check: ensure the file is within the task directory
    if not full_file_path.startswith(task_path):
        return jsonify({'error': 'Invalid file path'}), 400

    try:
        if os.path.exists(full_file_path):
            os.remove(full_file_path)
            return jsonify({'message': 'File deleted successfully', 'deleted_file': file_path}), 200
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Failed to delete file: {str(e)}'}), 500

@app.route('/api/projects')
def list_projects():
    """List all local projects from task_data/"""
    projects = []
    try:
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            return jsonify({'projects': []})
            
        for item in os.listdir(app.config['UPLOAD_FOLDER']):
            item_path = os.path.join(app.config['UPLOAD_FOLDER'], item)
            
            # Only include directories that look like project folders (ad or story)
            is_ad = os.path.isdir(item_path) and item.startswith('ad_creation')
            is_story = os.path.isdir(item_path) and item.startswith('story_video')
            
            if is_ad or is_story:
                wf_type = 'story' if is_story else 'ad'
                project_info = {
                    'id': item,
                    'name': item,
                    'workflow_type': wf_type,
                    'created': datetime.fromtimestamp(os.path.getctime(item_path)).strftime('%Y-%m-%d %H:%M'),
                    'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M'),
                    'status': 'complete' if is_task_complete(item_path) else 'in_progress'
                }
                
                # Count actual media assets (not JSON metadata)
                asset_count = 0
                
                # Count files in sub_video folders
                for sub_item in os.listdir(item_path):
                    if sub_item.startswith('sub_video_'):
                        sub_folder = os.path.join(item_path, sub_item)
                        if os.path.isdir(sub_folder):
                            files = [f for f in os.listdir(sub_folder)
                                   if not f.startswith('.') and not f.endswith('.json')
                                   and os.path.isfile(os.path.join(sub_folder, f))]
                            asset_count += len(files)
                
                # Count final videos
                final_folder = os.path.join(item_path, 'final_videos')
                if os.path.exists(final_folder):
                    files = [f for f in os.listdir(final_folder)
                           if not f.startswith('.') and not f.endswith('.json')
                           and os.path.isfile(os.path.join(final_folder, f))]
                    asset_count += len(files)
                
                project_info['asset_count'] = asset_count
                
                # Try to get project description
                if is_ad:
                    # Ad workflow: get description from script_writing JSON
                    script_file = os.path.join(item_path, 'script_writing_v1.json')
                    if not os.path.exists(script_file):
                        script_file = os.path.join(item_path, 'script_writing.json')
                    
                    if os.path.exists(script_file):
                        try:
                            with open(script_file, 'r') as f:
                                script_data = json.loads(f.read())
                                if 'hook' in script_data:
                                    project_info['description'] = script_data['hook'][:100] + '...' if len(script_data['hook']) > 100 else script_data['hook']
                        except:
                            pass
                    
                    if 'description' not in project_info:
                        project_info['description'] = 'Ad creation project'
                else:
                    # Story workflow: get description from story_input.txt or story_analysis.json
                    story_input = os.path.join(item_path, 'story_input.txt')
                    if os.path.exists(story_input):
                        try:
                            with open(story_input, 'r', encoding='utf-8') as f:
                                story_text = f.read().strip()
                            project_info['description'] = story_text[:100] + '...' if len(story_text) > 100 else story_text
                        except:
                            pass
                    
                    if 'description' not in project_info:
                        project_info['description'] = 'Story video project'
                
                # Get thumbnail image
                project_info['thumbnail'] = get_project_thumbnail(item_path, item)
                
                projects.append(project_info)
        
        # Sort by modification time (newest first)
        projects.sort(key=lambda x: x['modified'], reverse=True)
        
        # Assign unified sequential project numbers (oldest = 1, newest = highest)
        total = len(projects)
        for idx, proj in enumerate(projects):
            num = total - idx
            proj['name'] = f'Project {num}'
        
        return jsonify({'projects': projects})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/showcase')
def list_showcase():
    """
    List showcase projects from the showcase/ folder.
    This endpoint always returns all projects from showcase/ regardless of authentication.
    """
    projects = []
    try:
        # Use showcase folder instead of task_data
        showcase_folder = os.path.join(os.path.dirname(app.config['UPLOAD_FOLDER']), 'showcase')
        
        if not os.path.exists(showcase_folder):
            return jsonify({'projects': []})
            
        for item in os.listdir(showcase_folder):
            item_path = os.path.join(showcase_folder, item)
            
            # Only include directories that look like project folders
            if os.path.isdir(item_path) and (item.startswith('ad_creation') or item.startswith('story_video')):
                is_story = item.startswith('story_video')
                project_info = {
                    'id': item,
                    'name': 'Showcase',
                    'workflow_type': 'story' if is_story else 'ad',
                    'created': datetime.fromtimestamp(os.path.getctime(item_path)).strftime('%Y-%m-%d %H:%M'),
                    'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M'),
                    'status': 'complete' if is_task_complete(item_path) else 'in_progress'
                }
                
                # Count actual media assets (not JSON metadata)
                asset_count = 0
                
                # Count files in sub_video folders
                for sub_item in os.listdir(item_path):
                    if sub_item.startswith('sub_video_'):
                        sub_folder = os.path.join(item_path, sub_item)
                        if os.path.isdir(sub_folder):
                            files = [f for f in os.listdir(sub_folder)
                                   if not f.startswith('.') and not f.endswith('.json')
                                   and os.path.isfile(os.path.join(sub_folder, f))]
                            asset_count += len(files)
                
                # Count final videos
                final_folder = os.path.join(item_path, 'final_videos')
                if os.path.exists(final_folder):
                    files = [f for f in os.listdir(final_folder)
                           if not f.startswith('.') and not f.endswith('.json')
                           and os.path.isfile(os.path.join(final_folder, f))]
                    asset_count += len(files)
                
                project_info['asset_count'] = asset_count
                
                # Try to get project description from script_writing_v1.json
                script_file = os.path.join(item_path, 'script_writing_v1.json')
                if not os.path.exists(script_file):
                    # Fallback to non-versioned name
                    script_file = os.path.join(item_path, 'script_writing.json')
                
                if os.path.exists(script_file):
                    try:
                        with open(script_file, 'r') as f:
                            script_data = json.loads(f.read())
                            if 'hook' in script_data:
                                project_info['description'] = script_data['hook'][:100] + '...' if len(script_data['hook']) > 100 else script_data['hook']
                    except:
                        pass
                
                if 'description' not in project_info:
                    project_info['description'] = 'Story video showcase' if is_story else 'Ad creation showcase'
                
                # Get final video path from data_version.json
                data_version_file = os.path.join(item_path, 'data_version.json')
                if os.path.exists(data_version_file):
                    try:
                        with open(data_version_file, 'r') as f:
                            data_version = json.load(f)
                            if 'final_video' in data_version and 'curr_version' in data_version['final_video']:
                                # Convert absolute path to relative URL
                                full_path = data_version['final_video']['curr_version']
                                # Extract relative path from showcase folder
                                if 'showcase/' in full_path:
                                    rel_path = full_path.split('showcase/')[-1]
                                    project_info['final_video'] = f'/projects/{rel_path}'
                                elif 'task_data/' in full_path:
                                    rel_path = full_path.split('task_data/')[-1]
                                    project_info['final_video'] = f'/projects/{rel_path}'
                    except:
                        pass
                
                # Fallback: try to find final video directly
                if 'final_video' not in project_info:
                    final_folder = os.path.join(item_path, 'final_videos')
                    if os.path.exists(final_folder):
                        for f in os.listdir(final_folder):
                            if f.startswith('final_complete') and f.endswith('.mp4'):
                                project_info['final_video'] = f'/projects/{item}/final_videos/{f}'
                                break
                
                projects.append(project_info)
        
        # Sort by modification time (newest first)
        projects.sort(key=lambda x: x['modified'], reverse=True)
        
        # Assign sequential showcase numbers (Showcase 1, Showcase 2, etc.)
        for idx, proj in enumerate(projects, start=1):
            proj['name'] = f'Showcase {idx}'
        
        return jsonify({'projects': projects})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/<task_id>')
def get_status(task_id):
    # Check if source parameter indicates this is from showcase
    source = request.args.get('source', '')
    
    is_showcase = False
    task_path = None
    
    # If explicitly from showcase, check showcase folder first
    if source == 'showcase':
        showcase_folder = os.path.join(os.path.dirname(app.config['UPLOAD_FOLDER']), 'showcase')
        showcase_path = os.path.join(showcase_folder, task_id)
        
        if os.path.isdir(showcase_path):
            task_path = showcase_path
            is_showcase = True
        else:
            # Fall back to task_data if not found in showcase
            task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
    else:
        # Normal flow: check task_data first, then showcase
        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        
        if not os.path.isdir(task_path):
            showcase_folder = os.path.join(os.path.dirname(app.config['UPLOAD_FOLDER']), 'showcase')
            task_path = os.path.join(showcase_folder, task_id)
            is_showcase = True
    
    is_complete = is_task_complete(task_path)
    
    if is_complete:
        return jsonify({'status': 'complete'})
    return jsonify({'status': 'pending'}), 202

@app.route('/api/results/<task_id>')
def get_results(task_id):
    # Check if source parameter indicates this is from showcase
    source = request.args.get('source', '')
    
    is_showcase = False
    base_folder = app.config['UPLOAD_FOLDER']
    task_path = None
    
    # If explicitly from showcase, check showcase folder first
    if source == 'showcase':
        showcase_folder = os.path.join(os.path.dirname(app.config['UPLOAD_FOLDER']), 'showcase')
        showcase_path = os.path.join(showcase_folder, task_id)
        
        if os.path.isdir(showcase_path):
            task_path = showcase_path
            is_showcase = True
            base_folder = showcase_folder
            print(f"📌 Showcase project detected: {task_id}")
        else:
            # Fall back to task_data if not found in showcase
            task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
    else:
        # Normal flow: check task_data first, then showcase
        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        
        if not os.path.isdir(task_path):
            showcase_folder = os.path.join(os.path.dirname(app.config['UPLOAD_FOLDER']), 'showcase')
            task_path = os.path.join(showcase_folder, task_id)
            is_showcase = True
            base_folder = showcase_folder
    
    if not os.path.isdir(task_path):
        return jsonify({'error': 'Task not found'}), 404

    folder_structure = {}

    def _safe_load_json(path: str) -> dict:
        try:
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f) or {}
        except Exception:
            return {}
        return {}

    # Load dirty flags (optional). Used for incremental workflow rerun, but UI should avoid blanket propagation.
    dirty_flags = _safe_load_json(os.path.join(task_path, 'dirty_flags.json'))

    # Manual/UI dirty + last-run baseline live in workflow module (isolated; no propagation).
    try:
        import sys
        workflow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workflow_applications', 'advertisement')
        if workflow_path not in sys.path:
            sys.path.insert(0, workflow_path)
        from manual_dirty_flags import is_manual_dirty as _is_manual_dirty
        from last_run_assets import load_last_run_assets as _load_last_run_assets
    except Exception:
        def _is_manual_dirty(_task_path: str, _group_key: str, _item_key: str) -> bool:  # type: ignore
            return False
        def _load_last_run_assets(_task_path: str) -> dict:  # type: ignore
            return {}

    last_run_assets = _load_last_run_assets(task_path) or {}

    def _slot_key(group_key: str, item_key: str) -> str:
        return f"{group_key}::{item_key}"

    def _abs_to_rel(p: str) -> str:
        if not p or not isinstance(p, str):
            return ""
        for folder_name in ('task_data/', 'showcase/'):
            if folder_name in p:
                parts = p.split(folder_name)
                if len(parts) > 1:
                    return parts[-1]
        return p

    def _is_item_dirty(group_key: str, item_key: str, data_version: dict) -> bool:
        """
        UI dirty badge semantics (new):
        - Dirty means: this slot's CURRENT version != the version used by LAST successful workflow run.
        - Plus: manual dirty override (set on Apply Selected Version when mismatched).
        - Critically: do NOT mark dependent video dirty just because upstream images changed.
        """
        # Manual/UI-only dirty has the highest priority and never propagates.
        if _is_manual_dirty(task_path, group_key, item_key):
            return True
        try:
            # Compare current data_version curr_version against last_run_assets snapshot
            g = (data_version or {}).get(group_key, {})
            curr_abs = None
            if isinstance(g, dict) and item_key == group_key and 'curr_version' in g:
                curr_abs = g.get('curr_version')
            elif isinstance(g, dict) and item_key in g and isinstance(g.get(item_key), dict):
                curr_abs = g[item_key].get('curr_version')
            if not curr_abs:
                return False
            last_abs = last_run_assets.get(_slot_key(group_key, item_key))
            if not last_abs:
                return False
            return os.path.abspath(str(curr_abs)) != os.path.abspath(str(last_abs))
        except Exception:
            return False

    # Try to read from data_version.json first
    data_version_path = os.path.join(task_path, 'data_version.json')
    if os.path.exists(data_version_path):
        try:
            with open(data_version_path, 'r') as f:
                data_version = json.load(f)

            for group_key, group_value in data_version.items():
                group_files = []

                # Check if group_value itself is a file entry (has curr_version directly)
                # or if it's a container of file entries

                # Normalize to a list of items to process
                items_to_process = []
                if isinstance(group_value, dict) and 'curr_version' in group_value:
                    # It's a single file entry at top level (e.g. bgm)
                    items_to_process.append((group_key, group_value))
                elif isinstance(group_value, dict):
                    # It's a container (e.g. sub_video_0)
                    for k, v in group_value.items():
                        if isinstance(v, dict) and 'curr_version' in v:
                            items_to_process.append((k, v))

                default_version = 'v0'
                for item_key, item_value in items_to_process:
                    curr_version = item_value.get('curr_version')
                    historical_versions_abs = item_value.get('historical_version', [])

                    # Determine type
                    f_type = 'file'
                    lower_key = item_key.lower()
                    if 'image' in lower_key: f_type = 'img'
                    elif 'video' in lower_key: f_type = 'video'
                    elif 'voice' in lower_key or 'audio' in lower_key or 'bgm' in lower_key: f_type = 'audio'
                    default_f_postfix = ''
                    if f_type == 'img': default_f_postfix = '.png'
                    elif f_type == 'video': default_f_postfix = '.mp4'
                    elif f_type == 'audio': default_f_postfix = '.mp3'

                    file_obj = {
                        'type': f_type,
                        'group_key': group_key,
                        'item_key': item_key,
                        'historical_versions': [],
                        'is_manual_dirty': _is_manual_dirty(task_path, group_key, item_key),
                        'is_dirty': _is_item_dirty(group_key, item_key, data_version),
                        'last_run_version': _abs_to_rel(last_run_assets.get(_slot_key(group_key, item_key), "")) or None
                    }

                    # Process historical versions
                    for hist_ver in historical_versions_abs:
                        extracted = False
                        if hist_ver:
                            for folder_name in ('task_data/', 'showcase/'):
                                if folder_name in hist_ver:
                                    parts = hist_ver.split(folder_name)
                                    if len(parts) > 1:
                                        file_obj['historical_versions'].append(parts[-1])
                                        extracted = True
                                        break
                        if not extracted:
                            file_obj['historical_versions'].append(hist_ver)

                    # Convert absolute path to relative path
                    # Backend serves /projects/<path> which checks both task_data/ and showcase/
                    rel_path = None
                    if curr_version:
                        for folder_name in ('task_data/', 'showcase/'):
                            if folder_name in curr_version:
                                parts = curr_version.split(folder_name)
                                if len(parts) > 1:
                                    rel_path = parts[-1]
                                    break
                    
                    # Check if file exists: try original absolute path first,
                    # then resolve relative path under actual base_folder (handles
                    # data_version.json created on a different machine)
                    file_exists = False
                    if curr_version:
                        if os.path.exists(curr_version):
                            file_exists = True
                        elif rel_path:
                            resolved = os.path.join(base_folder, rel_path)
                            if os.path.exists(resolved):
                                file_exists = True
                    
                    if curr_version and file_exists and rel_path:
                        file_obj['path'] = rel_path
                        file_obj['name'] = os.path.basename(curr_version)
                    elif curr_version and file_exists:
                        file_obj['path'] = curr_version
                        file_obj['name'] = os.path.basename(curr_version)
                    else:
                        # Placeholder
                        # Create a dummy path that matches the actual file structure
                        # e.g., "task_id/sub_video_2/video_v0.mp4" (same as real file but without extension)
                        task_id = os.path.basename(task_path)
                        file_obj['path'] = f"{task_id}/{group_key}/{item_key}_{default_version}{default_f_postfix}"
                        file_obj['is_placeholder'] = True
                        file_obj['name'] = item_key # Display simple name like "image", "voiceover"
                        # Placeholders: keep existing behavior (any workflow dirty_flags can show pending rerun),
                        # but ALSO respect manual dirty for this slot.
                        file_obj['is_manual_dirty'] = _is_manual_dirty(task_path, group_key, item_key)
                        file_obj['is_dirty'] = bool(file_obj['is_manual_dirty'] or bool(dirty_flags))
                        file_obj['last_run_version'] = _abs_to_rel(last_run_assets.get(_slot_key(group_key, item_key), "")) or None

                    group_files.append(file_obj)

                if group_files:
                    # Map group_key if necessary (e.g. final_video -> final_videos for sorting)
                    final_key = group_key
                    if group_key == 'final_video':
                        final_key = 'final_videos'

                    folder_structure[final_key] = group_files

            # Always check for upload folder (not tracked in data_version.json)
            upload_folder = os.path.join(task_path, 'upload')
            if os.path.exists(upload_folder) and os.path.isdir(upload_folder):
                upload_files = []
                try:
                    for file in os.listdir(upload_folder):
                        if file.startswith('.'):
                            continue
                        
                        file_path = os.path.join(upload_folder, file)
                        if not os.path.isfile(file_path):
                            continue
                        
                        # Determine file type
                        ext = file.split('.')[-1].lower() if '.' in file else ''
                        file_type = 'file'
                        
                        img_exts = ALLOWED_EXTENSIONS['images']
                        video_exts = ALLOWED_EXTENSIONS['videos']
                        audio_exts = ALLOWED_EXTENSIONS['audio']
                        
                        if ext in img_exts:
                            file_type = 'img'
                        elif ext in video_exts:
                            file_type = 'video'
                        elif ext in audio_exts:
                            file_type = 'audio'
                        
                        # Get relative path from base folder
                        rel_path = os.path.relpath(file_path, base_folder)
                        upload_files.append({
                            'path': rel_path,
                            'type': file_type,
                            'name': file,
                            'group_key': 'upload',
                            'item_key': file
                        })
                    
                    if upload_files:
                        folder_structure['upload'] = upload_files
                except Exception as e:
                    print(f"Error scanning upload folder: {e}")

            # Check for character_reference folder (story workflow)
            char_ref_folder = os.path.join(task_path, 'character_reference')
            if os.path.exists(char_ref_folder) and os.path.isdir(char_ref_folder):
                char_files = []
                try:
                    for file in os.listdir(char_ref_folder):
                        if file.startswith('.'):
                            continue
                        
                        file_path = os.path.join(char_ref_folder, file)
                        if not os.path.isfile(file_path):
                            continue
                        
                        ext = file.split('.')[-1].lower() if '.' in file else ''
                        file_type = 'file'
                        
                        if ext in ALLOWED_EXTENSIONS['images']:
                            file_type = 'img'
                        elif ext in ALLOWED_EXTENSIONS['videos']:
                            file_type = 'video'
                        
                        if file_type != 'file':
                            rel_path = os.path.relpath(file_path, base_folder)
                            char_files.append({
                                'path': rel_path,
                                'type': file_type,
                                'name': file,
                                'group_key': 'character_reference',
                                'item_key': file
                            })
                    
                    if char_files:
                        folder_structure['character_reference'] = char_files
                except Exception as e:
                    print(f"Error scanning character_reference folder: {e}")

            return jsonify({
                'structure': folder_structure,
                'is_showcase': is_showcase
            })

        except Exception as e:
            print(f"Error reading data_version.json: {e}")
            # Fall back to directory scanning if JSON parsing fails
            pass

    try:
        # Get all immediate subdirectories
        items = sorted(os.listdir(task_path))

        # Define allowed extensions flat list for check
        img_exts = ALLOWED_EXTENSIONS['images']
        video_exts = ALLOWED_EXTENSIONS['videos']
        audio_exts = ALLOWED_EXTENSIONS['audio']

        for item in items:
            item_path = os.path.join(task_path, item)

            # Only process directories that are not hidden
            if os.path.isdir(item_path) and not item.startswith('.') and item != '__pycache__':
                files_in_folder = []

                # Walk through the subdirectory to find all assets
                for root, _, files in os.walk(item_path):
                    for file in files:
                        if file.startswith('.'):
                            continue

                        # Determine file type
                        ext = file.split('.')[-1].lower() if '.' in file else ''
                        file_type = None

                        if ext in img_exts:
                            file_type = 'img'
                        elif ext in video_exts:
                            file_type = 'video'
                        elif ext in audio_exts:
                            file_type = 'audio'

                        if file_type:
                            # Get relative path from base folder for frontend URL
                            rel_path = os.path.relpath(os.path.join(root, file), base_folder)
                            files_in_folder.append({
                                'path': rel_path,
                                'type': file_type,
                                'name': file,
                                # Use modified time for stable sorting if needed, or just name
                                'mtime': os.path.getmtime(os.path.join(root, file))
                            })

                # Add to structure if folder has assets
                if files_in_folder:
                    # Sort by name by default
                    folder_structure[item] = sorted(files_in_folder, key=lambda x: x['name'])

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

    return jsonify({
        'structure': folder_structure,
        'is_showcase': is_showcase
    })

def serialize_for_json(data):
    """Helper function to serialize data for JSON, handling Pydantic models"""
    if hasattr(data, 'model_dump'):
        # Pydantic v2 model
        return data.model_dump()
    elif hasattr(data, 'dict'):
        # Pydantic v1 model
        return data.dict()
    elif isinstance(data, dict):
        return {k: serialize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_for_json(item) for item in data]
    else:
        return data

@app.route('/api/regenerate/<task_id>', methods=['POST'])
def regenerate_asset(task_id):
    """
    Regenerate an asset (image/video/audio) with updated text description.
    
    Expected JSON body:
    {
        "file": "path/to/file.mp4",
        "edited_text": "Updated description text",
        "file_type": "video" | "audio" | "image"
    }
    """
    import copy
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        file_path = data.get('file')
        edited_text = data.get('edited_text')
        file_type = data.get('file_type')
        text_edited = bool(data.get('text_edited', False))
        
        if not file_path or not file_type:
            return jsonify({'error': 'Missing required fields: file, file_type'}), 400
        
        # edited_text is required for non-final-video types
        if file_type != 'final_video' and not edited_text:
            return jsonify({'error': 'Missing required field: edited_text'}), 400
        
        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        if not os.path.exists(task_path):
            return jsonify({'error': 'Task not found'}), 404
        
        # Detect workflow type and import the correct module
        wf_type = detect_workflow_type(task_id)
        import sys
        if wf_type == 'story':
            workflow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workflow_applications', 'story_to_video')
            if workflow_path not in sys.path:
                sys.path.insert(0, workflow_path)
            from story_video_workflow_langgraph import get_task_state, edit_state, execute_single_node
        else:
            workflow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workflow_applications', 'advertisement')
            if workflow_path not in sys.path:
                sys.path.insert(0, workflow_path)
            from ad_creation_workflow_langgraph import get_task_state, edit_state, execute_single_node
        
        # Get current task state
        app_instance, config, state, _, _ = get_task_state(task_path)
        
        # Debug: Print state keys
        print(f"🔍 State values keys (wf_type={wf_type}): {list(state.values.keys())}")
        
        # Determine which node to regenerate and what to update based on file type
        normalized_file_path, normalized_filename, _version = parse_versioned_asset_path(file_path)
        filename = os.path.basename(file_path)
        node_to_execute = None
        field_updates = {}
        
        if file_type == 'audio':
            # Check if it's a BGM file
            if 'bgm' in normalized_filename.lower():
                # BGM file: update mood_keywords in product_analysis
                # Parse the edited text (comma-separated mood keywords)
                mood_keywords = [keyword.strip() for keyword in edited_text.split(',')]
                
                # Update product_analysis field
                product_analysis = state.values.get('product_analysis', {})
                product_analysis_copy = copy.deepcopy(product_analysis) if product_analysis else {}
                product_analysis_copy['mood_keywords'] = mood_keywords
                field_updates['product_analysis'] = product_analysis_copy
                print(f"📝 Updated mood_keywords: {mood_keywords}")
                
                # Delete existing BGM file to force regeneration
                bgm_path = state.values.get('bgm_path') or state.values.get('bgm_generation', {}).get('bgm_path')
                if bgm_path and isinstance(bgm_path, str) and os.path.exists(bgm_path):
                    try:
                        os.remove(bgm_path)
                        print(f"🗑️  Removed old BGM file to trigger regeneration: {bgm_path}")
                    except Exception as e:
                        print(f"⚠️  Failed to remove old BGM: {e}")
                
                node_to_execute = 'bgm'  # Will regenerate BGM
            elif wf_type == 'story' and re.search(r'(^|/)audios/voiceover\.(mp3|wav|ogg|aac|flac|m4a)$', normalized_file_path):
                # Story workflow full-track voiceover:
                # - if user edited the text, synthesize from that exact text
                # - otherwise regenerate narration text from story context first
                if text_edited and edited_text and edited_text.strip():
                    field_updates['monologue_text'] = edited_text.strip()
                    field_updates['_use_existing_monologue_text'] = True
                    print(f"📝 Regenerating full story voiceover from user-edited text ({len(edited_text.split())} words)")
                else:
                    print("📝 Regenerating full story narration and voiceover from story context")
                node_to_execute = 'story_tts'
            # Audio file: segment_X.mp3 (old) or sub_video_X/voiceover.mp3 (new)
            # Use fine-grained regeneration: modify segment + delete old file
            else:
                segment_index = None
                
                # Try old pattern first: segment_0.mp3
                old_match = re.match(r'segment_(\d+)', normalized_filename)
                if old_match:
                    segment_index = int(old_match.group(1))
                else:
                    # Try new pattern: extract from path like "sub_video_0/voiceover.mp3"
                    # Note: file_path still contains the original filename, but here we parse based on structure
                    # For audio in sub_video_X, we expect "voiceover.mp3" (version suffix normalized out)
                    new_match = re.search(r'sub_video_(\d+)/voiceover\.(mp3|wav|ogg|aac|flac|m4a)', normalized_file_path)
                    if new_match:
                        segment_index = int(new_match.group(1))
                
                if segment_index is not None:
                    segmented_monologue = state.values.get('segmented_monologue_design', {})
                    segments = segmented_monologue.get('segments', [])
                    
                    # Fallback: Check if segments exists as a top-level field
                    if not segments:
                        segments = state.values.get('segments', [])
                    
                    if segment_index < len(segments):
                        # Step 1: Update segment text using edit_state
                        # Check if segments are nested in segmented_monologue_design or top-level
                        if segmented_monologue and isinstance(segmented_monologue, dict) and 'segments' in segmented_monologue:
                            # Nested case: segments inside segmented_monologue_design
                            segmented_monologue_copy = copy.deepcopy(segmented_monologue)
                            segments_copy = segmented_monologue_copy.get('segments', [])
                            segments_copy[segment_index]['segment_text'] = edited_text
                            field_updates['segmented_monologue_design'] = segmented_monologue_copy
                        else:
                            # Top-level case: segments as separate field
                            segments_copy = copy.deepcopy(segments)
                            segments_copy[segment_index]['segment_text'] = edited_text
                            field_updates['segments'] = segments_copy
                        
                        # Step 2: Mark segment with dirty flag for fine-grained TTS regeneration
                        # (Same pattern as image/video regeneration - SegmentedVoiceoverNode checks dirty flags)
                        top_level_segments = state.values.get('segments', [])
                        if top_level_segments and segment_index < len(top_level_segments):
                            top_segments_copy = copy.deepcopy(top_level_segments)
                            top_segments_copy[segment_index]['segment_text'] = edited_text
                            top_segments_copy[segment_index]['_dirty'] = True
                            top_segments_copy[segment_index]['_dirty_fields'] = ['segment_text']
                            field_updates['segments'] = top_segments_copy
                            print(f"✅ Marked segments[{segment_index}] field 'segment_text' as dirty")
                        elif segmented_monologue and isinstance(segmented_monologue, dict) and 'segments' in segmented_monologue:
                            # If segments are nested, mark inside segmented_monologue_design
                            if 'segmented_monologue_design' not in field_updates:
                                segmented_monologue_copy = copy.deepcopy(segmented_monologue)
                                field_updates['segmented_monologue_design'] = segmented_monologue_copy
                            nested_segs = field_updates['segmented_monologue_design'].get('segments', [])
                            if segment_index < len(nested_segs):
                                nested_segs[segment_index]['_dirty'] = True
                                nested_segs[segment_index]['_dirty_fields'] = ['segment_text']
                                print(f"✅ Marked nested segments[{segment_index}] field 'segment_text' as dirty")
                        
                        node_to_execute = 'segmented_tts'  # Will regenerate ONLY the dirty segment
                    else:
                        return jsonify({
                            'error': f'Segment index {segment_index} not found',
                            'available_segments': len(segments),
                            'segments_structure': 'top-level' if not (segmented_monologue and isinstance(segmented_monologue, dict) and 'segments' in segmented_monologue) else 'nested'
                        }), 404
                else:
                    print(f"❌ Invalid audio filename format: {filename}")
                    return jsonify({'error': 'Invalid audio filename format'}), 400
                
        elif file_type == 'video':
            # Video file: video_X.mp4 (old) or sub_video_X/video.mp4 (new)
            # Use fine-grained regeneration: modify storyboard + delete old file
            video_index = None
            
            # Try old pattern first: video_0.mp4
            old_match = re.match(r'video_(\d+)', normalized_filename)
            if old_match:
                video_index = int(old_match.group(1))
            else:
                # Try new pattern: extract from path like "sub_video_0/video.mp4" (version suffix normalized out)
                new_match = re.search(r'sub_video_(\d+)/video\.(mp4|mov|avi|webm|mkv)', normalized_file_path)
                if new_match:
                    video_index = int(new_match.group(1))
            
            if video_index is not None:
                # Ad workflow uses 'ad_storyboard', story workflow uses 'storyboard'
                ad_storyboard = state.values.get('ad_storyboard', [])
                storyboard = state.values.get('storyboard', [])
                primary_sb = ad_storyboard if ad_storyboard else storyboard
                primary_sb_field = 'ad_storyboard' if ad_storyboard else 'storyboard'
                
                print(f"🔍 Looking for video_index: {video_index} (field: {primary_sb_field})")
                print(f"🔍 Available frames: {len(primary_sb)}")
                
                if video_index < len(primary_sb):
                    # Step 1: Update video_description using edit_state
                    primary_sb_copy = copy.deepcopy(primary_sb)
                    primary_sb_copy[video_index]['video_description'] = edited_text
                    field_updates[primary_sb_field] = primary_sb_copy
                    print(f"📝 Updated video_description for frame {video_index} in {primary_sb_field}")
                    
                    # Step 2: Mark storyboard with dirty flag for fine-grained video regeneration
                    # For ad workflow, also update the separate 'storyboard' field
                    # For story workflow, primary_sb IS storyboard, so mark dirty on it
                    if primary_sb_field == 'ad_storyboard' and video_index < len(storyboard):
                        storyboard_copy = copy.deepcopy(storyboard)
                        storyboard_copy[video_index]['video_description'] = edited_text
                        storyboard_copy[video_index]['_dirty'] = True
                        storyboard_copy[video_index]['_dirty_fields'] = ['video_description']
                        field_updates['storyboard'] = storyboard_copy
                        print(f"✅ Marked storyboard[{video_index}] field 'video_description' as dirty")
                    elif primary_sb_field == 'storyboard':
                        # Story workflow: mark dirty directly on the primary storyboard
                        field_updates['storyboard'][video_index]['_dirty'] = True
                        field_updates['storyboard'][video_index]['_dirty_fields'] = ['video_description']
                        print(f"✅ Marked storyboard[{video_index}] field 'video_description' as dirty (story workflow)")
                    
                    node_to_execute = 'video_generation'  # Will regenerate ONLY the dirty video
                else:
                    return jsonify({
                        'error': f'Video frame at index {video_index} not found',
                        'available_frames': len(primary_sb)
                    }), 404
            else:
                print(f"❌ Invalid video filename format: {filename}")
                return jsonify({'error': 'Invalid video filename format'}), 400
                
        elif file_type == 'final_video':
            # Final video: re-composite the final video by executing the 'edit' node
            # No state field updates needed - just re-execute with current (possibly updated) config
            print(f"🎬 Final video regeneration requested for: {file_path}")
            node_to_execute = 'edit'
                
        elif file_type in ['images', 'image']:
            # Simplified image regeneration logic - NO edit_list_item, NO first/last distinction waste
            image_index = None
            image_type = None
            
            # Try new pattern: extract from path like "sub_video_0/image_first.png" or "sub_video_0/image_first_v1.png"
            new_match = re.search(r'sub_video_(\d+)/image_(first|last)\.(png|jpg|jpeg|gif|bmp|webp|tiff)', normalized_file_path)
            if new_match:
                image_index = int(new_match.group(1))
                image_type = new_match.group(2)  # 'first' or 'last'
            else:
                # Try old pattern: image_0_first.png
                old_match = re.match(r'image_(\d+)_(first|last)', normalized_filename)
                if old_match:
                    image_index = int(old_match.group(1))
                    image_type = old_match.group(2)  # 'first' or 'last'
            
            if image_index is not None and image_type is not None:
                # Ad workflow uses 'ad_storyboard', story workflow uses 'storyboard'
                ad_storyboard = state.values.get('ad_storyboard', [])
                storyboard = state.values.get('storyboard', [])
                primary_sb = ad_storyboard if ad_storyboard else storyboard
                primary_sb_field = 'ad_storyboard' if ad_storyboard else 'storyboard'
                
                print(f"🔍 Looking for image_index: {image_index}, type: {image_type} (field: {primary_sb_field})")
                
                if image_index < len(primary_sb):
                    field_name = f"{image_type}_image_description"
                    
                    # Manual state update instead of edit_list_item
                    primary_sb_copy = copy.deepcopy(primary_sb)
                    primary_sb_copy[image_index][field_name] = edited_text
                    field_updates[primary_sb_field] = primary_sb_copy
                    
                    # For ad workflow, also update the separate 'storyboard' field
                    # For story workflow, primary_sb IS storyboard, so mark dirty on it
                    if primary_sb_field == 'ad_storyboard' and image_index < len(storyboard):
                        storyboard_copy = copy.deepcopy(storyboard)
                        storyboard_copy[image_index][field_name] = edited_text
                        storyboard_copy[image_index]['_dirty'] = True
                        storyboard_copy[image_index]['_dirty_fields'] = [field_name]
                        field_updates['storyboard'] = storyboard_copy
                        print(f"✅ Marked storyboard[{image_index}] field '{field_name}' as dirty")
                    elif primary_sb_field == 'storyboard':
                        # Story workflow: mark dirty directly on the primary storyboard
                        field_updates['storyboard'][image_index]['_dirty'] = True
                        field_updates['storyboard'][image_index]['_dirty_fields'] = [field_name]
                        print(f"✅ Marked storyboard[{image_index}] field '{field_name}' as dirty (story workflow)")
                    
                    node_to_execute = 'image_generation'
                else:
                    return jsonify({'error': f'Image index {image_index} out of range'}), 404
            else:
                print(f"❌ Invalid image filename format: {filename}")
                return jsonify({'error': 'Invalid image filename format'}), 400
        else:
            return jsonify({'error': f'Unsupported file type: {file_type}'}), 400
        
        # Apply the state updates
        if node_to_execute:
            if field_updates:
                edit_state(app_instance, config, task_path, **field_updates)
                print(f"✅ State updated with fields: {list(field_updates.keys())}")
                
                # CRITICAL: Save the updated state to JSON files so frontend can read the modified text
                # Get the updated state after edit_state
                updated_state = app_instance.get_state(config)
                
                # Save the corresponding JSON file based on what was updated
                if 'segmented_monologue_design' in field_updates:
                    json_path = os.path.join(task_path, 'segmented_monologue_design.json')
                    serialized_data = serialize_for_json(field_updates['segmented_monologue_design'])
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(serialized_data, f, ensure_ascii=False, indent=2)
                    print(f"💾 Saved updated segmented_monologue_design.json")
                
                if 'segments' in field_updates:
                    # Top-level segments case
                    json_path = os.path.join(task_path, 'segmented_monologue_design.json')
                    # Load existing JSON and update just the segments field
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                        existing_data['segments'] = serialize_for_json(field_updates['segments'])
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(existing_data, f, ensure_ascii=False, indent=2)
                        print(f"💾 Saved updated segmented_monologue_design.json (top-level segments)")
                    except FileNotFoundError:
                        # Create new file with just segments
                        serialized_segments = serialize_for_json(field_updates['segments'])
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump({'segments': serialized_segments}, f, ensure_ascii=False, indent=2)
                        print(f"💾 Created segmented_monologue_design.json")
                
                if 'product_analysis' in field_updates:
                    json_path = os.path.join(task_path, 'product_analysis.json')
                    # Load existing product analysis and update just the mood_keywords
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                        # Update with all fields from product_analysis
                        for key, value in field_updates['product_analysis'].items():
                            existing_data[key] = serialize_for_json(value)
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(existing_data, f, ensure_ascii=False, indent=2)
                        print(f"💾 Saved updated product_analysis.json")
                    except FileNotFoundError:
                        # Create new file
                        serialized_analysis = serialize_for_json(field_updates['product_analysis'])
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(serialized_analysis, f, ensure_ascii=False, indent=2)
                        print(f"💾 Created product_analysis.json")
            
            # Execute the single node
            print(f"🚀 Executing node: {node_to_execute}")
            execute_single_node(app_instance, config, node_to_execute, task_path, mark_dirty=True)
            
            # 2. 执行完成后强制同步状态并刷新磁盘文件
            final_app, final_config, final_state, _, _ = get_task_state(task_path)
            
            # 确保关键 JSON 文件被同步，这样前端轮询到的就是最新不带脏标记的数据
            json_sync_map = {
                'segmented_tts': ('segmented_monologue_design.json', 'segments'),
                'bgm': ('product_analysis.json', 'product_analysis'),
                'story_tts': ('story_tts_text.json', 'monologue_text')
            }
            
            if node_to_execute in json_sync_map:
                json_filename, state_field = json_sync_map[node_to_execute]
                json_path = os.path.join(task_path, json_filename)
                try:
                    existing_data = {}
                    if os.path.exists(json_path):
                        with open(json_path, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)

                    if node_to_execute == 'story_tts':
                        for key in ['language', 'voice_style', 'pacing', 'monologue_text']:
                            if key in final_state.values:
                                existing_data[key] = serialize_for_json(final_state.values[key])
                    elif state_field in final_state.values:
                        existing_data[state_field] = serialize_for_json(final_state.values[state_field])

                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(existing_data, f, ensure_ascii=False, indent=2)
                    print(f"💾 Synchronized {state_field} to {json_filename}")
                except Exception as e:
                    print(f"⚠️ Failed to sync {json_filename}: {e}")

            # 3. 获取最新结构并返回
            # 注意：不要直接调用 get_results 视图函数，手动实现逻辑以避免上下文冲突
            latest_structure = {}
            try:
                data_version_path = os.path.join(task_path, 'data_version.json')
                if os.path.exists(data_version_path):
                    with open(data_version_path, 'r', encoding='utf-8') as f:
                        dv_data = json.load(f)
                    
                    # 极简版结构提取逻辑，仅供前端定位新路径
                    for g_key, g_val in dv_data.items():
                        latest_structure[g_key] = []
                        if isinstance(g_val, dict) and 'curr_version' in g_val:
                            latest_structure[g_key].append({'item_key': g_key, 'path': g_val['curr_version']})
                        elif isinstance(g_val, dict):
                            for i_key, i_val in g_val.items():
                                if isinstance(i_val, dict) and 'curr_version' in i_val:
                                    latest_structure[g_key].append({'item_key': i_key, 'path': i_val['curr_version']})
            except Exception as e:
                print(f"⚠️ Failed to assemble latest structure: {e}")

            return jsonify({
                'message': 'Asset regeneration started successfully',
                'node': node_to_execute,
                'updated_fields': list(field_updates.keys()),
                'latest_structure': latest_structure
            })
        else:
            return jsonify({'error': 'Could not determine what to regenerate'}), 400
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Regeneration failed: {str(e)}'}), 500

@app.route('/api/rerun/<task_id>', methods=['POST'])
def rerun_workflow(task_id):
    """
    Re-run the workflow based on dirty flags (after regenerating assets).
    
    This endpoint triggers workflow re-execution in incremental mode,
    where only nodes affected by dirty flags will be re-executed.
    """
    try:
        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        if not os.path.exists(task_path):
            return jsonify({'error': 'Task not found'}), 404
        
        # Check if workflow is already running
        if task_id in running_workflows and running_workflows[task_id]['status'] == 'running':
            return jsonify({'error': 'Workflow is already running for this task'}), 400
        
        # Detect workflow type and import the correct module
        wf_type = detect_workflow_type(task_id)
        import sys
        if wf_type == 'story':
            workflow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workflow_applications', 'story_to_video')
            if workflow_path not in sys.path:
                sys.path.insert(0, workflow_path)
            from story_video_workflow_langgraph import run_workflow
        else:
            workflow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workflow_applications', 'advertisement')
            if workflow_path not in sys.path:
                sys.path.insert(0, workflow_path)
            from ad_creation_workflow_langgraph import run_workflow
        
        print(f"🔄 Re-running workflow for task: {task_id} (type: {wf_type})")
        print(f"   Task path: {task_path}")
        print(f"   Mode: Incremental (based on dirty flags)")
        
        # Load user API keys if saved
        api_keys_path = os.path.join(task_path, '.api_keys.json')
        user_api_keys = {}
        if os.path.exists(api_keys_path):
            try:
                with open(api_keys_path, 'r') as f:
                    user_api_keys = json.load(f)
                print(f"🔑 Loaded user API keys from task config")
            except Exception as e:
                print(f"⚠️  Could not load API keys: {e}")
        
        # Create stop event for this workflow
        stop_event = threading.Event()
        
        # Run workflow in a separate thread
        def run_workflow_thread():
            try:
                # Apply user API keys to environment
                original_env = {}
                for key, env_var in [('openai_api_key', 'OPENAI_API_KEY'), 
                                      ('replicate_api_token', 'REPLICATE_API_TOKEN')]:
                    if key in user_api_keys and user_api_keys[key]:
                        original_env[env_var] = os.environ.get(env_var)
                        os.environ[env_var] = user_api_keys[key]
                        print(f"🔑 Using user-provided {env_var}")
                
                # Check for stop signal before starting
                stop_marker = os.path.join(task_path, '__stop_requested__')
                if os.path.exists(stop_marker):
                    os.remove(stop_marker)
                
                # Run workflow in rerun mode (incremental execution based on dirty flags)
                final_state = run_workflow(
                    task_path=task_path,
                    rerun=True  # Key: enables incremental execution
                )
                
                # Mark as completed if not stopped
                if task_id in running_workflows:
                    if running_workflows[task_id]['status'] != 'stopped':
                        running_workflows[task_id]['status'] = 'completed'
                
                print(f"✅ Workflow re-execution completed successfully")
                
            except KeyboardInterrupt:
                # Graceful stop
                print(f"🛑 Workflow interrupted gracefully")
                if task_id in running_workflows:
                    running_workflows[task_id]['status'] = 'stopped'
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"❌ Workflow re-execution failed: {str(e)}")
                
                if task_id in running_workflows:
                    running_workflows[task_id]['status'] = 'error'
            finally:
                # Restore original environment variables
                for env_var, original_value in original_env.items():
                    if original_value is None:
                        os.environ.pop(env_var, None)
                    else:
                        os.environ[env_var] = original_value
        
        # Start workflow thread
        workflow_thread = threading.Thread(target=run_workflow_thread, daemon=True)
        workflow_thread.start()
        
        # Track this workflow
        running_workflows[task_id] = {
            'thread': workflow_thread,
            'stop_event': stop_event,
            'status': 'running'
        }
        
        return jsonify({
            'message': 'Workflow re-execution started',
            'status': 'running'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Workflow re-execution failed: {str(e)}'}), 500

@app.route('/api/stop/<task_id>', methods=['POST'])
def stop_workflow(task_id):
    """
    Stop a currently running workflow.
    
    This endpoint sets a stop flag that the workflow should check periodically.
    The workflow will be interrupted and can be continued later from its last checkpoint.
    """
    try:
        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        if not os.path.exists(task_path):
            return jsonify({'error': 'Task not found'}), 404
        
        # Check if workflow is running
        if task_id not in running_workflows:
            return jsonify({'error': 'No running workflow found for this task'}), 400
        
        workflow_info = running_workflows[task_id]
        
        # Set stop event
        workflow_info['stop_event'].set()
        
        print(f"🛑 Stop requested for workflow: {task_id}")
        print(f"   Task path: {task_path}")
        
        # Create a stop marker file for the workflow to check
        stop_marker = os.path.join(task_path, '__stop_requested__')
        with open(stop_marker, 'w') as f:
            f.write(str(datetime.now(UTC)))
        
        # Attempt to signal running process if present
        proc = workflow_info.get('process')
        if proc and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
        
        # Mark as stopped immediately (don't wait for thread)
        # The checkpoint system will save state automatically
        workflow_info['status'] = 'stopped'
        
        print(f"✅ Workflow stop signal sent")
        print(f"   Note: LangGraph will checkpoint at next node boundary")
        
        return jsonify({
            'message': 'Workflow stop signal sent. The workflow will checkpoint at the next node boundary.',
            'status': 'stopped'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to stop workflow: {str(e)}'}), 500

@app.route('/api/continue/<task_id>', methods=['POST'])
def continue_workflow(task_id):
    """
    Continue a workflow from its last checkpoint.
    
    This endpoint resumes workflow execution from where it was interrupted.
    Can be used anytime a checkpoint file exists.
    """
    try:
        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        if not os.path.exists(task_path):
            return jsonify({'error': 'Task not found'}), 404
        
        # Check if there's a checkpoint to resume from (support root and subfolder paths)
        checkpoint_file_root = os.path.join(task_path, 'checkpoints.sqlite')
        checkpoint_file_alt = os.path.join(task_path, 'checkpoints', 'checkpoints.sqlite')
        if not (os.path.exists(checkpoint_file_root) or os.path.exists(checkpoint_file_alt)):
            return jsonify({'error': 'No checkpoint found to continue from'}), 400
        
        # Check if workflow is already running
        if task_id in running_workflows and running_workflows[task_id]['status'] == 'running':
            return jsonify({'error': 'Workflow is already running for this task'}), 400
        
        # Remove stop marker if it exists
        stop_marker = os.path.join(task_path, '__stop_requested__')
        if os.path.exists(stop_marker):
            os.remove(stop_marker)
        
        # Detect workflow type and import the correct module
        wf_type = detect_workflow_type(task_id)
        import sys
        if wf_type == 'story':
            workflow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workflow_applications', 'story_to_video')
            if workflow_path not in sys.path:
                sys.path.insert(0, workflow_path)
            from story_video_workflow_langgraph import run_workflow
        else:
            workflow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workflow_applications', 'advertisement')
            if workflow_path not in sys.path:
                sys.path.insert(0, workflow_path)
            from ad_creation_workflow_langgraph import run_workflow
        
        print(f"▶️ Continuing workflow for task: {task_id} (type: {wf_type})")
        print(f"   Task path: {task_path}")
        print(f"   Mode: Resume from checkpoint")
        
        # Load user API keys if saved
        api_keys_path = os.path.join(task_path, '.api_keys.json')
        user_api_keys = {}
        if os.path.exists(api_keys_path):
            try:
                with open(api_keys_path, 'r') as f:
                    user_api_keys = json.load(f)
                print(f"🔑 Loaded user API keys from task config")
            except Exception as e:
                print(f"⚠️  Could not load API keys: {e}")
        
        # Create stop event for this workflow
        stop_event = threading.Event()
        
        # Run workflow in a separate thread
        def run_workflow_thread():
            try:
                # Apply user API keys to environment
                original_env = {}
                for key, env_var in [('openai_api_key', 'OPENAI_API_KEY'), 
                                      ('replicate_api_token', 'REPLICATE_API_TOKEN')]:
                    if key in user_api_keys and user_api_keys[key]:
                        original_env[env_var] = os.environ.get(env_var)
                        os.environ[env_var] = user_api_keys[key]
                        print(f"🔑 Using user-provided {env_var}")
                
                # Check for stop signal before starting
                stop_marker = os.path.join(task_path, '__stop_requested__')
                if os.path.exists(stop_marker):
                    os.remove(stop_marker)
                
                # Run workflow - it will automatically resume from checkpoint
                final_state = run_workflow(
                    task_path=task_path,
                    rerun=True  # Use rerun mode to continue from checkpoint
                )
                
                # Mark as completed if not stopped
                if task_id in running_workflows:
                    if running_workflows[task_id]['status'] != 'stopped':
                        running_workflows[task_id]['status'] = 'completed'
                    
                print(f"✅ Workflow continued and completed successfully")
                
            except KeyboardInterrupt:
                # Graceful stop
                print(f"🛑 Workflow interrupted gracefully")
                if task_id in running_workflows:
                    running_workflows[task_id]['status'] = 'stopped'
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"❌ Workflow continuation failed: {str(e)}")
                
                if task_id in running_workflows:
                    running_workflows[task_id]['status'] = 'error'
            finally:
                # Restore original environment variables
                for env_var, original_value in original_env.items():
                    if original_value is None:
                        os.environ.pop(env_var, None)
                    else:
                        os.environ[env_var] = original_value
        
        # Start workflow thread
        workflow_thread = threading.Thread(target=run_workflow_thread, daemon=True)
        workflow_thread.start()
        
        # Track this workflow
        running_workflows[task_id] = {
            'thread': workflow_thread,
            'stop_event': stop_event,
            'status': 'running'
        }
        
        return jsonify({
            'message': 'Workflow continuation started',
            'status': 'running'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to continue workflow: {str(e)}'}), 500

@app.route('/api/workflow-status/<task_id>', methods=['GET'])
def get_workflow_status(task_id):
    """
    Get the status of a workflow including whether it can be continued.
    
    Returns:
    - running: whether workflow is currently running
    - has_checkpoint: whether checkpoint file exists
    - can_continue: whether continue button should be enabled
    - can_stop: whether stop button should be enabled
    """
    try:
        source = request.args.get('source', '')
        
        task_path = None
        if source == 'showcase':
            showcase_folder = os.path.join(os.path.dirname(app.config['UPLOAD_FOLDER']), 'showcase')
            showcase_path = os.path.join(showcase_folder, task_id)
            if os.path.isdir(showcase_path):
                task_path = showcase_path
            else:
                task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        else:
            task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
            if not os.path.isdir(task_path):
                showcase_folder = os.path.join(os.path.dirname(app.config['UPLOAD_FOLDER']), 'showcase')
                showcase_path = os.path.join(showcase_folder, task_id)
                if os.path.isdir(showcase_path):
                    task_path = showcase_path
        
        if not os.path.exists(task_path):
            return jsonify({'error': 'Task not found'}), 404
        
        # Check checkpoint existence (support root and subfolder paths)
        checkpoint_file_root = os.path.join(task_path, 'checkpoints.sqlite')
        checkpoint_file_alt = os.path.join(task_path, 'checkpoints', 'checkpoints.sqlite')
        has_checkpoint = os.path.exists(checkpoint_file_root) or os.path.exists(checkpoint_file_alt)
        
        # Refresh running status from tracked process if available
        if task_id in running_workflows:
            info = running_workflows[task_id]
            proc = info.get('process')
            if proc is not None:
                if proc.poll() is None:
                    info['status'] = 'running'
                else:
                    if info.get('status') == 'running':
                        info['status'] = 'completed'
        
        # Check if workflow is running
        is_running = task_id in running_workflows and running_workflows[task_id]['status'] == 'running'
        
        # Determine button states
        can_continue = has_checkpoint and not is_running
        can_stop = is_running
        
        return jsonify({
            'running': is_running,
            'has_checkpoint': has_checkpoint,
            'can_continue': can_continue,
            'can_stop': can_stop,
            'status': running_workflows.get(task_id, {}).get('status', 'idle')
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to get workflow status: {str(e)}'}), 500

@app.route('/api/workflow-config/<task_id>', methods=['PUT'])
def update_workflow_config(task_id):
    """
    Update workflow configuration parameters.

    Request body:
    {
        "node": "image_generation",  // which node config to update
        "parameter": "aspect_ratio",  // which parameter to update
        "value": "16:9"              // new value
    }
    """
    try:
        data = request.get_json()
        if not data or 'node' not in data or 'parameter' not in data or 'value' not in data:
            return jsonify({'error': 'Missing required fields: node, parameter, value'}), 400

        node = data['node']
        parameter = data['parameter']
        value = data['value']

        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        config_file = os.path.join(task_path, 'workflow_config.json')

        if not os.path.exists(config_file):
            return jsonify({'error': 'Workflow config file not found'}), 404

        # Load existing config
        with open(config_file, 'r') as f:
            config = json.load(f)

        # Update the parameter
        if node not in config:
            return jsonify({'error': f'Node "{node}" not found in config'}), 404

        # Special handling for 'model' parameter - update at node level, not in parameters
        if parameter == 'model':
            config[node]['model'] = value
            print(f"✅ Updated workflow config: {node}.model = {value}")
        else:
            # Regular parameters go in the 'parameters' dict
            if 'parameters' not in config[node]:
                config[node]['parameters'] = {}

            config[node]['parameters'][parameter] = value
            print(f"✅ Updated workflow config: {node}.parameters.{parameter} = {value}")

        # Save updated config
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        return jsonify({
            'message': 'Workflow config updated successfully',
            'node': node,
            'parameter': parameter,
            'value': value
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to update workflow config: {str(e)}'}), 500

@app.route('/api/asset-config/<task_id>', methods=['POST'])
def update_asset_config(task_id):
    """
    Update configuration for a specific asset.
    """
    try:
        data = request.get_json()
        if not data or 'file_path' not in data or 'parameter' not in data or 'value' not in data:
            return jsonify({'error': 'Missing required fields'}), 400

        file_path = data['file_path']
        parameter = data['parameter']
        value = data['value']

        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)

        # Construct full file path for validation
        full_file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_path)

        # Security check
        if not os.path.abspath(full_file_path).startswith(os.path.abspath(task_path)):
             return jsonify({'error': 'Invalid file path'}), 403

        # Construct JSON config path: replace extension with .json
        base_name = os.path.splitext(full_file_path)[0]
        json_path = base_name + '.json'

        config = {}
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError:
                    pass

        # Update value (flat structure)
        config[parameter] = value

        with open(json_path, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"✅ Updated asset config: {os.path.basename(json_path)} | {parameter} = {value}")

        return jsonify({'message': 'Asset config updated successfully'})

    except Exception as e:
        print(f"Error updating asset config: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/set_version/<task_id>', methods=['POST'])
def set_version(task_id):
    """
    Set the current version of an asset in data_version.json
    """
    try:
        data = request.get_json()
        if not data or 'group_key' not in data or 'item_key' not in data or 'version_path' not in data:
            return jsonify({'error': 'Missing required fields'}), 400

        group_key = data['group_key']
        item_key = data['item_key']
        version_path = data['version_path'] # Relative path from frontend

        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        data_version_path = os.path.join(task_path, 'data_version.json')

        if not os.path.exists(data_version_path):
            return jsonify({'error': 'data_version.json not found'}), 404

        with open(data_version_path, 'r') as f:
            data_version = json.load(f)

        # Reconstruct absolute path
        # version_path is like "task_id/..."
        # UPLOAD_FOLDER is ".../task_data"
        # We need to find the full path.
        # However, we should probably just use the path as constructed if it exists.
        # But data_version.json stores ABSOLUTE paths.
        # So we need to convert the relative path back to absolute.

        # Check if version_path is already absolute (unlikely from frontend but possible)
        if os.path.isabs(version_path):
            abs_path = version_path
        else:
            abs_path = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], version_path))

        # Update data_version
        if group_key in data_version:
            target = data_version[group_key]
            # Check if target is the item itself or a container
            if isinstance(target, dict):
                if item_key == group_key and 'curr_version' in target:
                     # Top level item where group_key was used as item identifier
                     target['curr_version'] = abs_path
                elif item_key in target and isinstance(target[item_key], dict):
                     target[item_key]['curr_version'] = abs_path
                elif 'curr_version' in target:
                     # Fallback for flat structure if keys match differently
                     target['curr_version'] = abs_path
                else:
                     # Try to find item_key in target
                     if item_key in target:
                         target[item_key]['curr_version'] = abs_path

            with open(data_version_path, 'w') as f:
                json.dump(data_version, f, indent=2)

            # Auto manual-dirty for THIS slot based on last successful workflow run baseline.
            # If selected version != last run used version, mark only this slot dirty (UI-only, no propagation).
            try:
                import sys
                workflow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workflow_applications', 'advertisement')
                if workflow_path not in sys.path:
                    sys.path.insert(0, workflow_path)
                from last_run_assets import get_last_run_asset
                from manual_dirty_flags import set_manual_dirty

                last_abs = get_last_run_asset(task_path, group_key, item_key)
                if last_abs and os.path.abspath(str(last_abs)) == os.path.abspath(str(abs_path)):
                    # Matches baseline -> clear manual dirty for this slot
                    set_manual_dirty(task_path, group_key, item_key, False)
                else:
                    # Mismatch baseline -> mark manual dirty
                    set_manual_dirty(task_path, group_key, item_key, True)
            except Exception as e:
                print(f"⚠️ Failed to auto manual-dirty (set_version): {e}")

            # Mark downstream as dirty so UI can show badge and user can rerun
            try:
                dirty_path = os.path.join(task_path, 'dirty_flags.json')
                dirty_flags = {}
                if os.path.exists(dirty_path):
                    with open(dirty_path, 'r', encoding='utf-8') as f:
                        dirty_flags = json.load(f) or {}

                gk = (group_key or "").lower()
                ik = (item_key or "").lower()

                # Applying an upstream version should dirty downstream nodes
                if gk.startswith('sub_video_') and 'image' in ik:
                    dirty_flags['generated_images'] = True
                elif gk.startswith('sub_video_') and 'video' in ik:
                    dirty_flags['generated_videos'] = True
                elif gk.startswith('sub_video_') and ('voice' in ik or 'audio' in ik):
                    dirty_flags['segmented_voiceover_paths'] = True
                elif gk == 'bgm' or 'bgm' in ik:
                    dirty_flags['bgm_path'] = True

                # Persist if any flags
                if dirty_flags:
                    with open(dirty_path, 'w', encoding='utf-8') as f:
                        json.dump(dirty_flags, f, indent=2, ensure_ascii=False)
                    print(f"💾 Saved dirty flags to: {os.path.basename(dirty_path)} (set_version)")
            except Exception as e:
                print(f"⚠️ Failed to update dirty flags in set_version: {e}")

            # Regenerate composite thumbnail if an image version was changed
            ik_lower = (item_key or "").lower()
            if 'image' in ik_lower:
                try:
                    generate_composite_thumbnail(task_path)
                    print(f"🖼️ Regenerated composite thumbnail after version change")
                except Exception as thumb_err:
                    print(f"⚠️ Failed to regenerate thumbnail: {thumb_err}")

            return jsonify({'message': 'Version updated successfully'})

        return jsonify({'error': 'Group key not found'}), 404

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/update-thumbnail/<task_id>', methods=['POST'])
def update_thumbnail(task_id):
    """
    Force regenerate the composite thumbnail for a project.
    Called when user wants to manually refresh the thumbnail.
    """
    try:
        task_path = os.path.join(app.config['UPLOAD_FOLDER'], task_id)
        if not os.path.exists(task_path):
            return jsonify({'error': 'Task not found'}), 404
        
        thumb_path = generate_composite_thumbnail(task_path)
        if thumb_path:
            return jsonify({
                'message': 'Thumbnail regenerated successfully',
                'thumbnail': f'/projects/{task_id}/thumbnail_composite.jpg'
            })
        else:
            return jsonify({'error': 'Failed to generate thumbnail'}), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


## NOTE:
## Manual dirty is now driven automatically by /api/set_version via last_run_assets.json baseline.
## No direct "mark dirty" endpoint is exposed to the UI.

@app.route('/config/<path:path>')
def serve_config_files(path):
    """Serve config files from backend/config directory"""
    config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
    return send_from_directory(config_dir, path)

@app.route('/api/models-config')
def get_models_config():
    """
    Return default models and all available models organized by type.
    Returns:
    {
        "defaults": {
            "image_generation": "google/nano-banana-pro",
            "video_generation": "lucataco/wan-2.2-first-last-frame:...",
            "tts": "minimax/speech-02-hd"
        },
        "available": {
            "image_generation": ["model1", "model2", ...],
            "video_generation": ["model1", "model2", ...],
            "tts": ["model1", "model2", ...]
        }
    }
    """
    try:
        config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
        
        # Load default models from ad template
        template_path = os.path.join(config_dir, 'ad_workflow_config_template.json')
        with open(template_path, 'r') as f:
            template = json.load(f)
        
        # Load default models from story template
        story_template_path = os.path.join(config_dir, 'story_workflow_config_template.json')
        story_template = {}
        if os.path.exists(story_template_path):
            with open(story_template_path, 'r') as f:
                story_template = json.load(f)
        
        # Load all available models
        models_path = os.path.join(config_dir, 'models_config.json')
        with open(models_path, 'r') as f:
            models_config = json.load(f)
        
        # Extract defaults for ad workflow (keep original identifier; may include ":version_hash")
        defaults = {
            'image_generation': template.get('image_generation', {}).get('model', ''),
            'video_generation': template.get('video_generation', {}).get('model', ''),
            'tts': template.get('tts', {}).get('model', '')
        }
        
        # Extract defaults for story workflow
        story_defaults = {
            'image_generation': story_template.get('image_generation', {}).get('model', ''),
            'video_generation': story_template.get('video_generation', {}).get('model', ''),
        }
        
        # Extract available models by type
        available = {}
        if 'models' in models_config:
            for model_type in ['image_generation', 'video_generation', 'tts']:
                if model_type in models_config['models']:
                    available[model_type] = list(models_config['models'][model_type].keys())
        
        return jsonify({
            'defaults': defaults,
            'story_defaults': story_defaults,
            'available': available
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to load models config: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
