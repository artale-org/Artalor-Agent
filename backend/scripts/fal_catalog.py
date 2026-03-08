"""
Fal models catalog tool - 拉取 Fal 模型参数

使用方法:
    python fal_catalog.py                    # 拉取指定模型并生成 config
    python fal_catalog.py --fetch-only       # 只拉取数据，不生成 config
    python fal_catalog.py --generate-only    # 只从现有数据生成 config
"""

import os
import sys
import json
from typing import Dict, List, Optional, Tuple

import requests
try:
    import yaml
except Exception:
    yaml = None
from dotenv import load_dotenv

load_dotenv()

# ===================== 指定模型列表 =====================
# 在这里指定要拉取的 Fal 模型，按类别分组
# 格式: "owner/model-name" 或 "owner/model-name/variant"
SPECIFIED_MODELS: Dict[str, List[str]] = {
    "image": [
        "fal-ai/gpt-image-1.5/edit",
        "fal-ai/nano-banana-pro/edit",
        "fal-ai/bytedance/seedream/v4.5/edit",
        "fal-ai/flux-2-max/edit",
        "fal-ai/qwen-image-edit-2511"
    ],
    "video": [
        "fal-ai/veo3.1/first-last-frame-to-video",
        "fal-ai/veo3.1/fast/first-last-frame-to-video",
    ],
    "tts": [
        # "fal-ai/f5-tts",
    ],
    "bgm": [
        # "fal-ai/stable-audio",
    ],
}


def get_fal_key() -> Optional[str]:
    return os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")


def fal_http_get_json(url: str) -> Optional[Dict]:
    """Fetch JSON from fal URL"""
    try:
        headers = {}
        fal_key = get_fal_key()
        if fal_key:
            headers["Authorization"] = f"Key {fal_key}"
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            if yaml is not None:
                try:
                    return yaml.safe_load(resp.text)
                except Exception:
                    return None
            return None
    except Exception as e:
        return None


def extract_properties_from_openapi(doc: Dict) -> Tuple[Dict, List[str]]:
    """Extract properties and required fields from OpenAPI schema"""
    if not isinstance(doc, dict):
        return {}, []
    
    # 1) components.schemas.Input
    input_schema = (
        doc.get("components", {})
        .get("schemas", {})
        .get("Input", {})
    )
    if isinstance(input_schema, dict) and input_schema.get("properties"):
        return input_schema.get("properties", {}), input_schema.get("required", [])
    
    # 2) any object schema with properties inside components.schemas
    schemas = doc.get("components", {}).get("schemas", {})
    if isinstance(schemas, dict):
        for name, schema in schemas.items():
            if isinstance(schema, dict) and schema.get("type") == "object":
                props = schema.get("properties", {})
                if isinstance(props, dict) and props:
                    return props, schema.get("required", [])
    
    # 3) paths -> first POST -> requestBody -> application/json -> schema
    paths = doc.get("paths", {})
    if isinstance(paths, dict):
        for _, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            post = path_item.get("post") or path_item.get("Post")
            if not isinstance(post, dict):
                continue
            rb = post.get("requestBody", {})
            if not isinstance(rb, dict):
                continue
            content = rb.get("content", {})
            app_json = content.get("application/json", {})
            schema = app_json.get("schema", {})
            if isinstance(schema, dict):
                props = schema.get("properties", {})
                if isinstance(props, dict) and props:
                    return props, schema.get("required", [])
    
    return {}, []


def fal_get_input_schema(slug: str, retry: int = 2) -> Tuple[Dict, List[str], Dict]:
    """Get input schema for a fal model
    
    Returns:
        (properties, required, full_schema)
    """
    candidates = [
        f"https://fal.run/{slug}/openapi.json",
        f"https://fal.run/{slug}/openapi",
    ]
    
    for _ in range(retry):
        for url in candidates:
            data = fal_http_get_json(url)
            if not data:
                continue
            props, required = extract_properties_from_openapi(data)
            if props:
                return props, required, data
    
    return {}, [], {}


def fetch_specified_models_data(
    specified_models: Dict[str, List[str]],
) -> Dict:
    """Fetch models data for specified Fal model IDs"""
    
    category_map = {
        "image": "image_generation",
        "video": "video_generation",
        "tts": "tts",
        "bgm": "bgm"
    }

    result = {
        "fetched_at": __import__("datetime").datetime.now().isoformat(),
        "platform": "fal",
        "mode": "specified_models",
        "models": {
            "image_generation": [],
            "video_generation": [],
            "tts": [],
            "bgm": [],
        }
    }

    total_models = sum(len(models) for models in specified_models.values())
    print(f"指定模式：共 {total_models} 个 Fal 模型待处理\n")

    for cat, model_ids in specified_models.items():
        if not model_ids:
            continue
        
        cat_key = category_map.get(cat, cat)
        print(f"\n处理 {cat} 分类 ({len(model_ids)} 个模型)...")

        for idx, model_id in enumerate(model_ids, 1):
            print(f"  [{idx}/{len(model_ids)}] {model_id}...", end=" ", flush=True)

            # Fetch schema
            properties, required, full_schema = fal_get_input_schema(model_id)
            schema_fetched = bool(properties)

            entry = {
                "model_id": model_id,
                "platform": "fal",
                "source_category": cat_key,
                "effective_category": cat_key,
                "effective_category_reason": "user_specified",
                "has_detailed_schema": schema_fetched,
                "properties": properties,
                "required": required,
                "full_schema": full_schema,
            }

            result["models"][cat_key].append(entry)

            if schema_fetched:
                print(f"✓ [{cat_key}] ({len(properties)} params)")
            else:
                print(f"⚠ no schema [{cat_key}]")

    return result


def save_raw_data(data: Dict, output_path: str) -> None:
    """Save raw models data to JSON file"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_raw_data(input_path: str) -> Dict:
    """Load raw models data from JSON file"""
    with open(input_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def parse_schema_to_config(properties: Dict, required: List[str], category: str) -> Tuple[Dict, Dict]:
    """Parse OpenAPI schema properties into input_keys and parameters
    
    简化版本：根据类别和常见模式识别 input_keys
    """
    input_keys = {}
    parameters = {}
    
    # 常见的 input key 模式
    prompt_keys = {"prompt", "text", "input_text"}
    image_keys = {"image", "image_url", "input_image", "first_frame", "last_frame", 
                  "first_frame_image", "last_frame_image", "start_image", "end_image",
                  "reference_image", "style_image", "control_image"}
    audio_keys = {"audio", "audio_url", "speaker_audio", "voice_audio"}
    
    for key, prop in properties.items():
        prop_type = prop.get("type", "string")
        description = prop.get("description", "").strip()
        default_val = prop.get("default")
        is_required = key in required
        key_lower = key.lower()
        
        # 判断是否为 input_key
        is_input_key = False
        
        if key_lower in prompt_keys:
            is_input_key = True
        elif key_lower in image_keys or "image" in key_lower and ("frame" in key_lower or "input" in key_lower or "reference" in key_lower):
            is_input_key = True
        elif key_lower in audio_keys:
            is_input_key = True
        elif category == "tts" and key_lower in {"text", "prompt"}:
            is_input_key = True
        elif category == "bgm" and key_lower in {"prompt", "text"}:
            is_input_key = True
        
        if is_input_key:
            input_keys[key] = {
                "type": prop_type if prop_type != "array" else "list[string]",
                "required": is_required,
                "description": description or f"{key} input"
            }
        else:
            param_def = {
                "type": prop_type,
                "description": description or f"{key} parameter"
            }
            if default_val is not None:
                param_def["default"] = default_val
            
            if "enum" in prop:
                param_def["options"] = prop["enum"]
            elif prop_type == "integer" and "minimum" in prop and "maximum" in prop:
                param_def["range"] = [prop["minimum"], prop["maximum"]]
            elif prop_type == "number" and "minimum" in prop and "maximum" in prop:
                param_def["range"] = [prop["minimum"], prop["maximum"]]
            
            parameters[key] = param_def
    
    return input_keys, parameters


def generate_models_config_from_raw(raw_data_path: str) -> Dict:
    """Generate models_config.json from raw data file"""
    print(f"加载原始数据: {raw_data_path}")
    data = load_raw_data(raw_data_path)
    
    print("\n生成 fal models config...")
    result = {
        "description": "Fal model configuration definitions",
        "version": "1.0",
        "platform": "fal",
        "models": {
            "image_generation": {},
            "video_generation": {},
            "tts": {},
            "bgm": {}
        },
    }
    
    for cat_key in ["image_generation", "video_generation", "tts", "bgm"]:
        models = data.get("models", {}).get(cat_key, [])
        if not models:
            continue
        print(f"\n处理 {cat_key} ({len(models)} 个模型)...")
        
        for idx, model in enumerate(models, 1):
            model_id = model.get("model_id")
            properties = model.get("properties", {})
            required = model.get("required", [])
            
            print(f"  [{idx}/{len(models)}] {model_id}...", end=" ", flush=True)
            
            if not properties:
                print("跳过（无 properties）")
                continue
            
            input_keys, parameters = parse_schema_to_config(properties, required, cat_key)
            
            result["models"][cat_key][model_id] = {
                "description": f"Fal {cat_key} model",
                "input_keys": input_keys,
                "parameters": parameters
            }
            print("✓")
    
    return result


def write_models_config(output_path: str, config: Dict) -> None:
    """Write models_config.json to file"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def print_summary(config: Dict) -> None:
    """Print summary statistics"""
    total_models = sum(len(models) for models in config["models"].values())
    print(f"\n完成！共生成 {total_models} 个模型的配置")
    for cat, models in config["models"].items():
        if models:
            print(f"  {cat}: {len(models)} 个模型")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Fal models catalog tool")
    parser.add_argument("--fetch-only", action="store_true", help="Only fetch raw data, don't generate config")
    parser.add_argument("--generate-only", action="store_true", help="Only generate config from existing raw data")
    args = parser.parse_args()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    raw_data_path = os.path.join(script_dir, "fal_raw_data.json")
    config_path = os.path.join(script_dir, '..', 'config', 'fal_models_config.json')
    config_path = os.path.abspath(config_path)
    
    # Step 1: Fetch raw data (if not generate-only)
    if not args.generate_only:
        total = sum(len(v) for v in SPECIFIED_MODELS.values())
        if total == 0:
            print("错误：SPECIFIED_MODELS 为空，请先在代码中添加要拉取的模型")
            print("位置：fal_catalog.py 文件顶部的 SPECIFIED_MODELS 字典")
            sys.exit(1)
        
        print(f"输出路径: {raw_data_path}\n")
        
        data = fetch_specified_models_data(SPECIFIED_MODELS)
        save_raw_data(data, raw_data_path)
        
        print(f"\n原始数据已保存到: {raw_data_path}")
        print(f"共拉取 {sum(len(models) for models in data['models'].values())} 个模型的数据")
        
        if args.fetch_only:
            print("\n（仅拉取模式，未生成 config）")
            print("运行 --generate-only 来生成 fal_models_config.json")
            return
    
    # Step 2: Generate config from raw data
    if not args.fetch_only:
        if not os.path.exists(raw_data_path):
            print(f"错误：原始数据文件不存在: {raw_data_path}")
            print("请先运行（不带 --generate-only）拉取数据")
            sys.exit(1)
        
        config = generate_models_config_from_raw(raw_data_path)
        write_models_config(config_path, config)
        print_summary(config)
        print(f"\n配置已保存到: {config_path}")


if __name__ == "__main__":
    main()

