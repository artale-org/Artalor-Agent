# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

import os
import time

import requests
from datetime import datetime
from openai import OpenAI
from openai import BadRequestError
import json
import base64
import replicate
from modules.tools.utils import load_env, ProgressIndicator, filter_description
try:
    import fal_client
except Exception:
    fal_client = None


def _gpt_gen(prompt: str, model="dall-e-3", ref_image_path=None) -> str:
    client = OpenAI()
    
    if ref_image_path is not None:
        # Enhance prompt for product consistency
        consistency_instruction = (
            " Maintain EXACT product consistency with reference image: "
            "same shape, colors, materials, distinctive features, brand elements. "
            "Do NOT modify the product appearance."
        )
        # Filter sensitive words from prompt
        filtered_prompt = filter_description(prompt + consistency_instruction) + ' based on the reference image'
        print(f"🔍 [image_gen] Original prompt: {prompt[:100]}...")
        print(f"🔍 [image_gen] Filtered prompt: {filtered_prompt[:100]}...")
        print(f"🎯 [image_gen] Enhanced with product consistency instructions")
        if len(ref_image_path) == 1:
            image_data = open(ref_image_path[0], "rb")
        else:
            image_data = [open(image_path, "rb") for image_path in ref_image_path]
        try:
            resp = client.images.edit(
                model=model,
                image=image_data,
                prompt=filtered_prompt,
                n=1,
                size="1024x1024",  # "256x256"/"512x512"/"1024x1024"
            )
            image_url = resp.data[0].url
        except BadRequestError as e:
            print(f"❌ [image_gen] Failed to generate with reference image: {str(e)}")
            if len(ref_image_path) == 1:
                image_data.close()
            else:
                for image_data in image_data:
                    image_data.close()
            return None
        print(f"✅ [image_gen] Successfully generated with reference image")

        if len(ref_image_path) == 1:
            image_data.close()
        else:
            for image_data in image_data:
                image_data.close()
        return image_url
    else:
        try:
            resp = client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
                size="1024x1024",  # "256x256"/"512x512"/"1024x1024"
                response_format="url"
            )
            image_url = resp.data[0].url
            return image_url
        except BadRequestError as e:
            # Handle OpenAI BadRequestError (400) - usually content policy violation
            print(f"⚠️ [image_gen] Content policy violation detected: {str(e)}")
            print(f"⚠️ [image_gen] Error details: {e.response.json() if hasattr(e, 'response') else 'No details'}")
            
            safe_prompt = filter_description(prompt)
            try:
                print(f"🔄 [image_gen] Retrying with safe prompt: {safe_prompt}")
                resp = client.images.generate(
                    model=model,
                    prompt=safe_prompt,
                    n=1,
                    size="1024x1024",
                    response_format="url"
                )
                image_url = resp.data[0].url
                print(f"✅ [image_gen] Successfully generated with safe prompt")
                return image_url
            except Exception as e2:
                print(f"❌ [image_gen] Unexpected error with safe prompt: {str(e2)}")
                return None
        except Exception as e:
            print(f"❌ [image_gen] Unexpected error: {str(e)}")
            return None


def get_base64_data(file_path):
    with open(file_path, "rb") as image_file:
        data = base64.b64encode(image_file.read()).decode('utf-8')
    return data


def _kling_gen(prompt: str, ref_image_path=None, model='kling-v2') -> bytes:
    from modules.tools.kling_get_api_key import get_kling_image_api_key
    api_key = get_kling_image_api_key()

    # Enhance prompt when using reference images
    enhanced_prompt = prompt
    if ref_image_path and os.path.exists(ref_image_path):
        enhanced_prompt = (
            f"{prompt} "
            "Based on reference image provided, maintain EXACT product appearance: "
            "same shape, colors, materials, distinctive features, and brand elements."
        )
        # Truncate if needed (Kling has 500 char limit)
        if len(enhanced_prompt) > 500:
            # Keep most important part
            enhanced_prompt = enhanced_prompt[:497] + "..."
        print(f"🎯 [kling_gen] Enhanced prompt for product consistency")

    # ------ request ------
    # model = "kling-v2"

    url = "https://api.klingai.com/v1/images/generations"
    data = {
        "model_name": model,  # kling-v1, kling-v1-5, kling-v2
        "prompt": enhanced_prompt,  # max 500

        # "negative_prompt": "",
    }
    
    # Add reference image parameters if provided
    if ref_image_path and os.path.exists(ref_image_path):
        data["image"] = get_base64_data(ref_image_path)
        data["image_reference"] = "subject"  # Use "subject" mode for product consistency
        data["image_fidelity"] = 0.9  # Increase fidelity to 0.9 for stronger consistency
        print(f"🖼️ [kling_gen] Using reference image with high fidelity (0.9): {ref_image_path}")
    
    # "human_fidelity": 0.45,
    # "n": 1,
    # "aspect_ratio": "16:9",

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

    # ------ query ------
    url = f"https://api.klingai.com/v1/images/generations/{task_id}"

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
            print("\r[image_gen]succ...")
            results = {d['index']: d['url'] for d in response_json['data']['task_result']['images']}
            results = sorted(results.items(), key=lambda x: x[0])
            # return [r[1] for r in results]
            return [r[1] for r in results][0]  # single as default
        elif response_json['data']['task_status'] == 'failed':
            print(f"\r[image_gen]failed... {response_json['data']['task_status_msg']}")
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
            print(f"\r[image_gen] {response_json['data']['task_id']} "
                  f"{cost_time}"
                  f" waiting" + '.' * cnt, end='')
            time.sleep(0.5)


def _replicate_gen(prompt: str, model="black-forest-labs/flux-1.1-pro", ref_image_path=None, **kwargs) -> str:
    # Enhance prompt when using reference images
    enhanced_prompt = prompt
    if ref_image_path is not None and len(ref_image_path) > 0:
        # Add strong consistency instruction for models that support reference images
        enhanced_prompt = (
            f"{prompt}\n\n"
            "IMPORTANT: Use the reference image(s) provided to maintain EXACT visual consistency. "
            "The product/subject in the generated image MUST match the reference image precisely in terms of: "
            "shape, color, material, distinctive features, brand elements, and overall appearance. "
            "Do NOT modify or reimagine the product - maintain identical visual characteristics."
        )
        print(f"🎯 [replicate_gen] Improved prompt with consistency instructions")
    
    inputs = {
        "prompt": enhanced_prompt,
        **kwargs
    }

    if model == 'openai/gpt-image-1':
        inputs['openai_api_key'] = os.getenv('OPENAI_API_KEY')
    
    # Get model-specific keys from config
    input_keys = _get_model_input_schema(model)
    ref_key = None
    
    if input_keys:
        # Fuzzy match for reference image key
        for key, definition in input_keys.items():
            key_lower = key.lower()
            desc_lower = definition.get('description', '').lower()
            # Check strict reference image keywords
            if any(kw in key_lower or kw in desc_lower for kw in ['reference_image', 'image_input', 'input_image', 'init_image', 'control_image']):
                # Avoid 'image_num' or output related keys
                if 'num' not in key_lower and 'count' not in key_lower:
                    ref_key = key
                    break
        
        # Fallback: check if 'image' exists (common for img2img)
        if not ref_key and 'image' in input_keys:
             ref_key = 'image'
             
    else:
        # Fallback heuristics if config not found
        # Check if reference image key is already in kwargs (from key conversion/overrides)
        for key in ['reference_images', 'reference_image', 'image_input', 'input_images', 'image']:
            if key in kwargs and kwargs[key]:
                ref_key = key
                break
    
    # Inject reference image(s) using the discovered key
    if ref_image_path:
         # If we found a key, or if we force a default one
         if not ref_key: 
             # Default fallback mapping
             img_key_mapping = {
                'openai/gpt-image-1': 'input_images',
                'google/nano-banana': 'reference_images',
            }
             ref_key = img_key_mapping.get(model, 'reference_image')
         
         # Prepare image data (file handle or list of handles)
         # Normalize to list for processing
         if not isinstance(ref_image_path, list):
             paths_to_load = [ref_image_path]
         else:
             paths_to_load = ref_image_path
             
         valid_paths = [p for p in paths_to_load if p and os.path.exists(p)]
         
         if valid_paths:
             # Decide if model wants list or single
             # We can check input_keys schema type if available, or guess
             is_list_type = False
             if input_keys and ref_key in input_keys:
                 type_def = input_keys[ref_key].get('type', '')
                 if 'list' in type_def or 'array' in type_def or ref_key.endswith('s'):
                     is_list_type = True
             elif ref_key.endswith('s') or 'images' in ref_key:
                 is_list_type = True
                 
             if is_list_type:
                 inputs[ref_key] = [open(p, "rb") for p in valid_paths]
             else:
                 # Take first one
                 inputs[ref_key] = open(valid_paths[0], "rb")
             
             print(f"🖼️  [replicate_gen] Using reference image(s) with key: {ref_key}")

    # Cleanup generic keys that might confuse the API
    for generic in ['reference_image', 'reference_images', 'image_input', 'input_images', 'image']:
        if generic in inputs and generic != ref_key:
            val = inputs[generic]
            # Only remove if it holds a path string/list (heuristic)
            # And prevent removing the key we just set
            if isinstance(val, (str, list)):
                 inputs.pop(generic, None)

    prediction = replicate.predictions.create(
        model,
        input=inputs,
    )

    t = time.time()
    pi = ProgressIndicator(f'[image_gen] id:{prediction.id}')
    while True:
        time.sleep(0.5)
        cost_time = time.time() - t
        pi.next_print(f'cost_time:{cost_time:.1f}s status:{prediction.status}')
        if prediction.status == 'succeeded':
            print()
            return prediction.output
        elif prediction.status in ('starting', 'processing'):
            prediction = replicate.predictions.get(prediction.id)
        elif prediction.status == 'failed':
            print()
            error_msg = getattr(prediction, 'error', None) or 'Unknown error'
            print(f"❌ [replicate_gen] Prediction failed: {error_msg}")
            # Try to get more details from logs if available
            if hasattr(prediction, 'logs') and prediction.logs:
                print(f"📋 [replicate_gen] Logs: {prediction.logs[-500:]}")  # Last 500 chars
            return None
        elif prediction.status == 'canceled':
            print()
            print(f"⚠️  [replicate_gen] Prediction was canceled")
            return None
        else:
            print()
            print(f"⚠️  [replicate_gen] Unexpected status: {prediction.status}")
            return None


def _fal_extract_first_url(result) -> str:
    try:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            # images
            if 'images' in result and isinstance(result['images'], list) and len(result['images']) > 0:
                first = result['images'][0]
                if isinstance(first, dict) and 'url' in first:
                    return first['url']
                if isinstance(first, str):
                    return first
            if 'image' in result and isinstance(result['image'], dict) and 'url' in result['image']:
                return result['image']['url']
            # videos
            if 'videos' in result and isinstance(result['videos'], list) and len(result['videos']) > 0:
                v0 = result['videos'][0]
                if isinstance(v0, dict) and 'url' in v0:
                    return v0['url']
                if isinstance(v0, str):
                    return v0
            if 'video' in result and isinstance(result['video'], dict) and 'url' in result['video']:
                return result['video']['url']
        if isinstance(result, list) and len(result) > 0:
            first = result[0]
            if isinstance(first, dict) and 'url' in first:
                return first['url']
            if isinstance(first, str):
                return first
    except Exception:
        pass
    return None


def _fal_gen(prompt: str, model: str, ref_image_path=None, **kwargs) -> str:
    if fal_client is None:
        print("⚠️ [image_gen] fal-client not installed; please add 'fal-client' to requirements and install.")
        return None
    arguments = {
        'prompt': prompt,
        **kwargs
    }
    # Attach reference images if provided (best-effort; many Fal models accept image_url/images)
    try:
        if ref_image_path is not None and len(ref_image_path) > 0:
            # Encode first image as data URI; if multiple, pass list
            def _to_data_uri(p):
                mime = 'image/png'
                try:
                    import mimetypes, base64
                    m, _ = mimetypes.guess_type(p)
                    if m:
                        mime = m
                    with open(p, 'rb') as f:
                        b64 = base64.b64encode(f.read()).decode('utf-8')
                    return f"data:{mime};base64,{b64}"
                except Exception:
                    return None
            data_uris = [u for u in (_to_data_uri(p) for p in ref_image_path) if u]
            if len(data_uris) == 1:
                arguments['image_url'] = data_uris[0]
            elif len(data_uris) > 1:
                arguments['images'] = data_uris
    except Exception:
        pass

    def _on_update(update):
        try:
            if hasattr(update, 'logs'):
                for log in update.logs:
                    msg = log.get('message') if isinstance(log, dict) else None
                    if msg:
                        print(f"[fal:image] {msg}")
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
        print(f"❌ [image_gen] Fal generation failed: {str(e)}")
        return None

def generate_image(prompt: str, model='kling-v2', file_path=None, ref_image_path=None, **kwargs) -> str:
    print(f"🎨 [generate_image] Starting image generation with model: {model}")
    print(f"🎨 [generate_image] Prompt: {prompt[:100]}...")
    
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        if model.startswith('dall-e') or model.startswith('gpt'):
            url = _gpt_gen(prompt, model, ref_image_path)
        elif model.startswith('kling'):
            url = _kling_gen(prompt, ref_image_path, model)
        elif model.startswith('fal-ai/'):
            url = _fal_gen(prompt=prompt, model=model, ref_image_path=ref_image_path, **kwargs)
        else:
            url = _replicate_gen(prompt=prompt, model=model, ref_image_path=ref_image_path, **kwargs)

        if url is not None:
            # Handle case where URL is a list (some models return list of URLs)
            if isinstance(url, list):
                if len(url) > 0:
                    url = url[0]  # Take first URL from list
                    print(f"📝 [generate_image] Model returned list of URLs, using first one")
                else:
                    print(f"❌ [generate_image] URL list is empty")
                    return None
            
            # Ensure url is a string
            if not isinstance(url, str):
                print(f"❌ [generate_image] Invalid URL type: {type(url)}, value: {url}")
                return None
            
            if file_path is None:
                path = '.'
                path = os.path.join(path, 'images')
                os.makedirs(path, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                filename = f"image_{ts}.png"
                file_path = os.path.join(path, filename)

            try:
                data = requests.get(url).content
                with open(file_path, "wb") as f:
                    f.write(data)
                
                print(f"✅ [generate_image] Successfully saved image to: {file_path}")
                return file_path
            except Exception as e:
                print(f"❌ [generate_image] Failed to download/save image: {str(e)}")
                raise e 
        else:
            print(f"❌ [generate_image] Failed to generate image URL for prompt: {prompt[:50]}...")
            raise RuntimeError(f"Failed to generate image URL for prompt: {prompt[:50]}...")
    except Exception as e:
        print(f"❌ [generate_image] Unexpected error: {str(e)}")
        return None


if __name__ == "__main__":
    # name = generate_image("A serene mountain landscape at sunrise")
    import os
    import sys
    
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..',))

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

    curr_path = os.path.dirname(os.path.abspath(__file__))
    assets_image_path = os.path.join(curr_path, '..', '..', 'assets', 'ad_examples',)
    ref_image_path = [os.path.join(assets_image_path, 'iphone.png')]
    gen_path = generate_image('A successful, fashion-forward individual striking a cool model pose while holding the latest smartphone in their hand.', 
                              ref_image_path=ref_image_path,
                              model='openai/gpt-image-1',
                              file_path=os.path.join(curr_path, '..', '..', 'images', 'test_iphone_gen.png')
                              )
    # name = generate_image("A black skin male in a black jacket walks out of a closed house and observes the empty New York streets.")
    print(f"image saved: {gen_path}")
