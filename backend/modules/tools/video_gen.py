# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

import requests
import json
import base64
from modules.tools.utils import load_env, ProgressIndicator
import os
import time
from datetime import datetime
import replicate
try:
    import fal_client
except Exception:
    fal_client = None

load_env()

# Cache for models config
_MODELS_CONFIG_CACHE = None

def _get_model_input_schema(model_name):
    """Retrieve input schema for a model from models_config.json"""
    global _MODELS_CONFIG_CACHE
    if _MODELS_CONFIG_CACHE is None:
        try:
            # Try standard path first
            config_path = os.path.join(os.getcwd(), 'config', 'models_config.json')
            if not os.path.exists(config_path):
                # Fallback: try relative to this file
                current_dir = os.path.dirname(os.path.abspath(__file__))
                config_path = os.path.join(current_dir, '..', '..', 'config', 'models_config.json')
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    _MODELS_CONFIG_CACHE = json.load(f)
            else:
                _MODELS_CONFIG_CACHE = {}
        except Exception as e:
            print(f"⚠️ Warning: Failed to load models_config.json: {e}")
            _MODELS_CONFIG_CACHE = {}
            
    # Look up model in nested structure: models -> category -> model_name
    models_root = _MODELS_CONFIG_CACHE.get('models', {})
    if not models_root:
        return {}

    target_config = None
    
    # 1. Try exact match
    for category, models in models_root.items():
        if isinstance(models, dict) and model_name in models:
            target_config = models[model_name]
            break
    
    # 2. Try without version if exact match failed
    if not target_config:
        base_name = model_name.split(':')[0]
        for category, models in models_root.items():
            if isinstance(models, dict) and base_name in models:
                target_config = models[base_name]
                break
    
    if target_config:
        return target_config.get('input_keys', {})
        
    return {}


def get_base64_data(file_path):
    with open(file_path, "rb") as image_file:
        data = base64.b64encode(image_file.read()).decode('utf-8')
    return data


def _kling_video_gen(prompt, start_image_path, end_image_path, model='kling-v1-5'):
    from modules.tools.kling_get_api_key import get_kling_image_api_key
    api_key = get_kling_image_api_key()

    # Validate and fill missing images
    valid_start = start_image_path if start_image_path and os.path.exists(start_image_path) else None
    valid_end = end_image_path if end_image_path and os.path.exists(end_image_path) else None
    
    if valid_start is None and valid_end is None:
        print(f"❌ [kling_video_gen] No valid images provided")
        return None
    
    # Fill missing image with the available one
    if valid_start is None:
        print(f"⚠️  [kling_video_gen] start_image missing, using end_image as fallback")
        valid_start = valid_end
    elif valid_end is None:
        print(f"⚠️  [kling_video_gen] end_image missing, using start_image as fallback")
        valid_end = valid_start

    # ------ request ------
    # model = "kling-v2"

    url = "https://api.klingai.com/v1/videos/image2video"
    data = {
        "model_name": model,  # kling-v1, kling-v1-5, kling-v1-6
        "prompt": prompt,  # max 2500
        # "negative_prompt": "",
        'mode': 'pro',
        'cfg_scale': 0.5,
        'duration': 5,
        "image": get_base64_data(valid_start),
        "image_tail": get_base64_data(valid_end),
        # todo: dynamic_masks, camera_control
    }
    # print(data['prompt'])
    payload = json.dumps(data)
    headers = {
        'Authorization': 'Bearer ' + api_key,
        'Content-Type': 'application/json',
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    print(response.text)
    if 'data' in response.json():
        task_id = response.json()['data']['task_id']
        print("request succ, task id:" + task_id)
    else:
        print('request failed', response.text)
        return

    # query
    url = f"https://api.klingai.com/v1/videos/image2video/{task_id}"

    headers = {
        'Authorization': 'Bearer ' + api_key,
        'Content-Type': 'application/json'
    }

    cnt = 0
    while True:
        response = requests.request("GET", url, headers=headers)
        # print(response.text)
        response_json = response.json()
        status = response_json['message']
        if response_json['data']['task_status'] == 'succeed':
            print(f"\r[video_gen] {response_json['data']['task_id']} succ...")
            results = {d['id']: d['url'] for d in response_json['data']['task_result']['videos']}
            results = sorted(results.items(), key=lambda x: x[0])
            # return [r[1] for r in results]
            return [r[1] for r in results][0]  # single as default
        elif response_json['data']['task_status'] == 'failed':
            print(f"\r[video_gen]failed... {response_json['data']['task_status_msg']}")
            return
        else:
            cnt = cnt % 3 + 1
            td = time.time() - response_json['data']['created_at'] / 1000
            cost_time = ''
            if td > 3600:
                cost_time += f'{int(td // 3600):2d}h'
                td %= 3600
            if td > 60:
                cost_time += f'{int(td // 60):2d}m'
                td %= 60
            cost_time += f'{int(td):2d}s'
            print(f"\r[video_gen] {response_json['data']['task_id']} "
                  f"{cost_time}"
                  f" waiting" + '.' * cnt, end='')
            time.sleep(0.5)


def _replicate_gen(prompt, start_image_path, end_image_path, model, **kwargs):
    inputs = {'prompt': prompt, **kwargs}  # Include model parameters from kwargs

    # Get model-specific keys from config
    input_keys = _get_model_input_schema(model)
    
    start_key = None
    end_key = None
    
    if input_keys:
        # Strategy 1: Fuzzy match from config
        # First frame keywords (check both underscore and space versions)
        for key, definition in input_keys.items():
            key_lower = key.lower()
            desc_lower = definition.get('description', '').lower()
            # Check strict first frame keywords with both underscore and space versions
            keywords = ['first_frame', 'first frame', 'start_image', 'start image', 'start_frame', 'start frame', 'initial_image', 'initial image']
            if any(kw in key_lower or kw in desc_lower for kw in keywords):
                start_key = key
                break
        
        # If no strict match, try generic 'image' if it looks like a single-image-input model
        if not start_key:
            # Check specific known keys like 'image' or 'input_image'
            for key in ['input_image', 'image', 'source_image']:
                if key in input_keys:
                    start_key = key
                    break
            
        # Last frame keywords (check both underscore and space versions)
        for key, definition in input_keys.items():
            key_lower = key.lower()
            desc_lower = definition.get('description', '').lower()
            keywords = ['last_frame', 'last frame', 'end_image', 'end image', 'end_frame', 'end frame', 'tail_image', 'tail image']
            if any(kw in key_lower or kw in desc_lower for kw in keywords):
                end_key = key
                break
    else:
        # Strategy 2: Fallback heuristics (if config not found)
        # Just default to unified keys and hope the model (or API wrapper) understands
        start_key = 'first_frame'
        end_key = 'last_frame'

    # Inject images using the discovered keys
    if start_image_path and os.path.exists(start_image_path):
        if start_key:
            inputs[start_key] = f"data:application/octet-stream;base64,{get_base64_data(start_image_path)}"
            # print(f"   Start image mapped to key: {start_key}")

    if end_image_path and os.path.exists(end_image_path):
        if end_key:
            inputs[end_key] = f"data:application/octet-stream;base64,{get_base64_data(end_image_path)}"
            # print(f"   End image mapped to key: {end_key}")
        
    # Cleanup generic keys that might confuse the API
    # Only remove them if they are NOT the keys we just decided to use
    # Also avoid removing keys that are not file paths (e.g. booleans/ints)
    for generic in ['first_frame', 'last_frame', 'start_image', 'end_image', 'image', 'input_image']:
        if generic in inputs and generic != start_key and generic != end_key:
            val = inputs[generic]
            # Only remove if it holds a path string (heuristic to avoid deleting valid params)
            if isinstance(val, str) and (val.endswith('.png') or val.endswith('.jpg') or '/' in val):
                 inputs.pop(generic, None)

    prediction = replicate.predictions.create(
        model,
        input=inputs,
    )
    t = time.time()
    pi = ProgressIndicator(f'[video_gen] id:{prediction.id}')
    while True:
        time.sleep(0.5)
        cost_time = time.time() - t
        pi.next_print(f'cost_time:{cost_time:.1f}s status:{prediction.status}')
        if prediction.status == 'succeeded':
            print()
            return prediction.output
        elif prediction.status in ('starting', 'processing'):
            prediction = replicate.predictions.get(prediction.id)
        else:
            break


def _fal_extract_first_url(result) -> str:
    try:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            if 'video' in result and isinstance(result['video'], dict) and 'url' in result['video']:
                return result['video']['url']
            if 'videos' in result and isinstance(result['videos'], list) and len(result['videos']) > 0:
                v0 = result['videos'][0]
                if isinstance(v0, dict) and 'url' in v0:
                    return v0['url']
                if isinstance(v0, str):
                    return v0
    except Exception:
        pass
    return None


def _fal_gen(prompt, start_image_path, end_image_path, model):
    if fal_client is None:
        print("⚠️ [video_gen] fal-client not installed; please add 'fal-client' to requirements and install.")
        return None
    arguments = {
        'prompt': prompt,
    }
    # Attach images as data URIs if present
    try:
        import mimetypes, base64
        def _to_data_uri(p):
            if not p or not os.path.exists(p):
                return None
            mime, _ = mimetypes.guess_type(p)
            if not mime:
                mime = 'image/png'
            with open(p, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
            return f"data:{mime};base64,{b64}"
        start_uri = _to_data_uri(start_image_path)
        end_uri = _to_data_uri(end_image_path)
        if start_uri and end_uri:
            arguments['images'] = [start_uri, end_uri]
        elif start_uri:
            arguments['image_url'] = start_uri
        elif end_uri:
            arguments['image_url'] = end_uri
    except Exception:
        pass

    def _on_update(update):
        try:
            if hasattr(update, 'logs'):
                for log in update.logs:
                    msg = log.get('message') if isinstance(log, dict) else None
                    if msg:
                        print(f"[fal:video] {msg}")
        except Exception:
            pass

    try:
        result = fal_client.subscribe(
            model,
            arguments=arguments,
            with_logs=True,
            on_queue_update=_on_update,
        )
        return _fal_extract_first_url(result)
    except Exception as e:
        print(f"❌ [video_gen] Fal generation failed: {str(e)}")
        return None

def generate_video(prompt, start_image_path, end_image_path, model='kwaivgi/kling-v1.6-pro', file_path=None, **kwargs):
    # Check if converted keys are in kwargs (from key conversion)
    # If so, we don't need start_image_path/end_image_path parameters
    start_frame_keys = ['first_frame', 'start_image', 'image', 'first_frame_image']
    end_frame_keys = ['last_frame', 'end_image', 'last_frame_image', 'end_frame_image']
    has_converted_start = any(k in kwargs for k in start_frame_keys)
    has_converted_end = any(k in kwargs for k in end_frame_keys)
    
    # Validate that we have at least one image (either as parameters or in kwargs)
    if not start_image_path and not end_image_path and not has_converted_start and not has_converted_end:
        raise ValueError("At least one image (start_image_path or end_image_path) is required")
    
    # For models that only support single image, ensure we have at least one valid image
    if model == 'wavespeedai/wan-2.1-i2v-480p':
        # Use the available image (prefer start_image if both exist)
        # Prioritize kwargs if present (handled by _replicate_gen later, but we check here for validation)
        
        # Check if we have start image in kwargs
        has_start_in_kwargs = False
        for k in start_frame_keys:
            if k in kwargs and kwargs[k]:
                has_start_in_kwargs = True
                break
        
        # Check if we have end image in kwargs
        has_end_in_kwargs = False
        for k in end_frame_keys:
            if k in kwargs and kwargs[k]:
                has_end_in_kwargs = True
                break
                
        # Validation logic: check paths OR kwargs
        has_start = (start_image_path and os.path.exists(start_image_path)) or has_start_in_kwargs
        has_end = (end_image_path and os.path.exists(end_image_path)) or has_end_in_kwargs
        
        if has_start:
            pass # start image available
        elif has_end:
            # Only end image available, use it as start image if start_image_path is not set
            if not start_image_path and not has_start_in_kwargs:
                # If we have end_image_path but no start_image_path, swap
                # Note: If end image is in kwargs, _replicate_gen needs to handle it.
                # Here we just handle the positional arg case for simple calls.
                if end_image_path and os.path.exists(end_image_path):
                    start_image_path = end_image_path
        else:
            raise ValueError("No valid image file found for video generation")
    
    if model.startswith('kling'):
        url = _kling_video_gen(prompt, start_image_path, end_image_path, model)
    elif model.startswith('fal-ai/'):
        url = _fal_gen(prompt, start_image_path, end_image_path, model)
    else:
        url = _replicate_gen(prompt, start_image_path, end_image_path, model, **kwargs)

    if url is not None:
        if file_path is None:
            path = '.'
            path = os.path.join(path, 'videos')
            os.makedirs(path, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            filename = f"video_{ts}.mp4"
            file_path = os.path.join(path, filename)

        data = requests.get(url).content
        with open(file_path, "wb") as f:
            f.write(data)

        return file_path


if __name__ == '__main__':
    pass
