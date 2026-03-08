# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

import os
import random
import sys
from typing import Dict, List, Optional, Tuple

import requests
import json
import re
import time
try:
    import yaml  # For parsing OpenAPI YAML if needed
except Exception:
    yaml = None
from dotenv import load_dotenv
try:
    import fal_client  # optional, for validation-based param guessing
except Exception:
    fal_client = None


API_BASE = "https://api.replicate.com/v1"

# Load .env early so FAL_KEY / REPLICATE_API_TOKEN are available
load_dotenv()

# ===================== 指定模型列表 =====================
# 在这里指定要拉取的模型，按类别分组
# 使用 --use-specified 参数启用此模式
SPECIFIED_MODELS: Dict[str, List[str]] = {
    "image": [
        "openai/gpt-image-1",
        "google/nano-banana-pro",
        "bytedance/seedream-4.5",
        "black-forest-labs/flux-2-max",
        "qwen/qwen-image-edit-2511",
    ],
    "video": [
        "google/veo-3.1",
        "google/veo-3.1-fast",
        "wan-video/wan-2.6-i2v",
        "openai/sora-2",
        "lucataco/wan-2.2-first-last-frame",
        "kwaivgi/kling-v2.6",
        "bytedance/seedance-1.5-pro",
    ],
    "tts": [
        "minimax/speech-02-hd",
        "minimax/speech-02-turbo",
        "resemble-ai/chatterbox-pro",
        
    ],
    "bgm": [
        "google/lyria-2",
        "minimax/music-1.5",
        "meta/musicgen",
    ],
}


def get_api_token() -> str:
    load_dotenv()
    token = os.environ.get("REPLICATE_API_TOKEN")
    if not token:
        raise RuntimeError(
            "REPLICATE_API_TOKEN 未设置。请在环境变量或 .env 中配置 REPLICATE_API_TOKEN。"
        )
    return token


def http_get(path: str, token: str, params: Optional[Dict] = None, timeout: int = 30) -> Dict:
    url = path if path.startswith("http") else f"{API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _parse_datetime_maybe(value: Optional[str]):
    """Parse ISO8601 datetime/date string into an aware datetime (UTC).

    Accepts:
    - 'YYYY-MM-DD'
    - ISO strings like '2025-01-02T03:04:05Z' / with offset / without tz
    Returns None if parsing fails.
    """
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        import datetime as _dt
        # Handle trailing Z
        if s.endswith("Z"):
            s2 = s[:-1] + "+00:00"
        else:
            s2 = s
        # Date only
        if len(s2) == 10 and s2.count("-") == 2:
            d = _dt.date.fromisoformat(s2)
            return _dt.datetime(d.year, d.month, d.day, tzinfo=_dt.timezone.utc)
        dt = _dt.datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt.astimezone(_dt.timezone.utc)
    except Exception:
        return None


def _pick_model_updated_at(model_info: Dict) -> Optional[str]:
    """Best-effort pick of model 'updated' timestamp (string) from model_info."""
    if not isinstance(model_info, dict):
        return None
    # Replicate commonly exposes updated_at / created_at; be defensive.
    for k in ("updated_at", "last_updated", "modified_at"):
        v = model_info.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _pick_model_created_at(model_info: Dict) -> Optional[str]:
    """Best-effort pick of model 'created' timestamp (string) from model_info."""
    if not isinstance(model_info, dict):
        return None
    for k in ("created_at", "published_at"):
        v = model_info.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _pick_latest_version_info(model_info: Dict) -> Tuple[Optional[str], Optional[str]]:
    """Return (latest_version_id, latest_version_created_at) from model_info if present."""
    if not isinstance(model_info, dict):
        return None, None
    latest = model_info.get("latest_version")
    if not isinstance(latest, dict):
        return None, None
    vid = latest.get("id") if isinstance(latest.get("id"), str) else None
    vcreated = latest.get("created_at") if isinstance(latest.get("created_at"), str) else None
    return vid, vcreated


def _infer_effective_category(
    model_id: str,
    description: str,
    properties: Dict,
    source_category: str,
) -> Tuple[str, str]:
    """Infer effective category for our pipeline from schema keys (preferred) + light heuristics.

    Returns:
        (effective_category, reason)

    Categories are our pipeline buckets:
      - image_generation
      - video_generation
      - tts
      - bgm

    If inference is inconclusive, returns (source_category, "fallback_to_source_category").
    """
    model_id_l = (model_id or "").lower()
    desc_l = (description or "").lower()
    props = properties or {}
    keys = {str(k).lower() for k in props.keys()} if isinstance(props, dict) else set()

    # 1) Strong schema-based signals (highest priority)
    video_first_keys = {"first_frame", "first_frame_image", "start_image", "start_frame", "initial_image", "image_tail"}
    video_last_keys = {"last_frame", "last_frame_image", "end_image", "end_frame", "tail_image", "image_tail"}
    if keys.intersection(video_first_keys) or keys.intersection(video_last_keys):
        return "video_generation", "schema_has_video_frame_keys"

    # TTS signals: text + voice/audio prompt common patterns
    tts_keys = {"text", "input_text", "prompt", "speaker_audio", "voice", "language", "speaker", "voice_id"}
    if ("speaker_audio" in keys) or ("text" in keys and ("voice" in keys or "speaker" in keys)):
        return "tts", "schema_looks_like_tts"

    # BGM/music signals: prompt/text + duration/tempo common patterns
    bgm_keys = {"duration", "duration_seconds", "bpm", "tempo", "seed", "audio_format", "output_format"}
    if ("bpm" in keys) or ("tempo" in keys) or ("music" in desc_l and ("duration" in keys or "prompt" in keys or "text" in keys)):
        return "bgm", "schema_looks_like_music"

    # Image signals: prompt + aspect_ratio/resolution/reference image keys
    image_ref_keys = {
        "reference_image", "reference_images", "input_image", "input_images", "image", "images",
        "init_image", "control_image", "style_image", "image_reference"
    }
    if ("prompt" in keys or "text" in keys) and (keys.intersection(image_ref_keys) or "aspect_ratio" in keys or "resolution" in keys):
        return "image_generation", "schema_looks_like_image"

    # 2) Keyword-based fallback when schema is missing/empty
    if any(w in model_id_l or w in desc_l for w in ["text-to-video", "image-to-video", "video generation", "video-to-video", "i2v", "t2v"]):
        return "video_generation", "keyword_video"
    if any(w in model_id_l or w in desc_l for w in ["text-to-speech", "tts", "speech", "voice cloning", "voice"]):
        return "tts", "keyword_tts"
    if any(w in model_id_l or w in desc_l for w in ["music", "audio generation", "text-to-music", "bgm", "soundtrack"]):
        return "bgm", "keyword_music"
    if any(w in model_id_l or w in desc_l for w in ["text-to-image", "image generation", "image-to-image", "t2i", "img2img"]):
        return "image_generation", "keyword_image"

    return source_category, "fallback_to_source_category"


def list_all_collections(token: str) -> List[Dict]:
    collections: List[Dict] = []
    next_url: Optional[str] = f"{API_BASE}/collections"
    while next_url:
        data = http_get(next_url, token)
        items = data.get("results", []) or data.get("collections", [])
        collections.extend(items)
        next_url = data.get("next")
    return collections


def get_collection_models(slug: str, token: str, limit: Optional[int] = None) -> List[Dict]:
    # Fetch all models from collection (no limit by default)
    models: List[Dict] = []
    next_url: Optional[str] = f"{API_BASE}/collections/{slug}"
    while next_url:
        data = http_get(next_url, token)
        items = data.get("models", [])
        models.extend(items)
        next_url = data.get("next")
        if limit and len(models) >= limit:
            break
    return models[:limit] if limit else models


def get_model_latest_version(owner: str, name: str, token: str) -> Optional[str]:
    data = http_get(f"/models/{owner}/{name}", token)
    latest = data.get("latest_version")
    if not latest:
        # Fallback: versions list if available (not all APIs expose here)
        versions_url = data.get("versions_url")
        if versions_url:
            versions = http_get(versions_url, token).get("results", [])
            if versions:
                return versions[0].get("id")
        return None
    return latest.get("id")


def get_version_input_schema(owner: str, name: str, version_id: str, token: str, retry: int = 3) -> Dict:
    for _ in range(retry):
        try:
            data = http_get(f"/models/{owner}/{name}/versions/{version_id}", token)
            schema = data.get("openapi_schema", {})
            properties = (
                schema.get("components", {})
                .get("schemas", {})
                .get("Input", {})
                .get("properties", {})
            )
            return properties
        except Exception as e:
            print(f"Error getting version input schema for {owner}/{name}/{version_id}: {e}")
            continue
    return {}


def get_version_input_schema_full(owner: str, name: str, version_id: str, token: str, retry: int = 3) -> Tuple[Dict, List[str]]:
    """Get full input schema including properties and required fields"""
    for _ in range(retry):
        try:
            data = http_get(f"/models/{owner}/{name}/versions/{version_id}", token)
            schema = data.get("openapi_schema", {})
            input_schema = (
                schema.get("components", {})
                .get("schemas", {})
                .get("Input", {})
            )
            properties = input_schema.get("properties", {}) or {}
            required = input_schema.get("required", []) or []
            return properties, required
        except Exception as e:
            print(f"Error getting full schema for {owner}/{name}/{version_id}: {e}")
            continue
    return {}, []

def resolve_target_collections(
    collections: List[Dict],
) -> Dict[str, List[str]]:
    """Match available collections to our categories and return ALL matching slugs.
    
    Uses whitelist (must contain) + blacklist (must not contain) for precise matching.
    
    Returns:
        Dict mapping category to list of matched collection slugs.
    """
    # Define whitelist keywords and blacklist keywords for each category
    # A collection matches if: (any whitelist keyword matches) AND (no blacklist keyword matches)
    category_rules: Dict[str, Dict[str, List[str]]] = {
        "image": {
            "whitelist": ["text-to-image", "image-to-image", "image-generation", "image-editing"],
            "blacklist": ["super-resolution", "upscale", "restore", "enhance", "ocr", "caption", "segmentation"],
        },
        "video": {
            "whitelist": ["text-to-video", "image-to-video", "video-generation", "video-editing"],
            "blacklist": ["video-to-text", "video-captioning", "video-understanding"],
        },
        "tts": {
            "whitelist": ["text-to-speech", "tts", "voice-cloning", "voice-generation"],
            "blacklist": ["speech-to-text", "transcription", "speech-recognition", "sing"],
        },
        "bgm": {
            "whitelist": ["text-to-music", "music-generation", "text-to-audio"],
            "blacklist": ["speech", "voice", "transcription"],
        },
    }

    result: Dict[str, List[str]] = {k: [] for k in category_rules}
    
    for col in collections:
        slug = col.get("slug", "")
        name = col.get("name", "").lower()
        if not slug:
            continue
        
        slug_lower = slug.lower()
        combined = f"{slug_lower} {name}"  # Combine for matching
        
        # Check which category this collection belongs to
        for cat, rules in category_rules.items():
            whitelist = rules["whitelist"]
            blacklist = rules["blacklist"]
            
            # Must match at least one whitelist keyword
            if not any(kw in combined for kw in whitelist):
                continue
            
            # Must not match any blacklist keyword
            if any(kw in combined for kw in blacklist):
                continue
            
            if slug not in result[cat]:
                result[cat].append(slug)
            break  # Each collection only goes to one category
    
    return result


def pick_sample_models(models: List[Dict], k: int = 2) -> List[Tuple[str, str]]:
    if not models:
        return []
    sample = random.sample(models, k=min(k, len(models)))
    pairs: List[Tuple[str, str]] = []
    for m in sample:
        owner = m.get("owner") or (m.get("repository_owner") or "")
        name = m.get("name") or (m.get("repository_name") or "")
        if owner and name:
            pairs.append((owner, name))
    return pairs


def build_key_mappings(analysis: Dict) -> Dict:
    """Build key mappings from analysis results"""
    video_frame_keys_first = set(analysis["video_frame_keys"]["first"].keys())
    video_frame_keys_last = set(analysis["video_frame_keys"]["last"].keys())
    image_ref_keys_single = {k: "reference_image" for k in analysis["image_ref_keys"]["single"].keys()}
    image_ref_keys_multiple = {k: "reference_images" for k in analysis["image_ref_keys"]["multiple"].keys()}
    
    # Get prompt keys for each category
    prompt_keys_image = set(analysis["prompt_keys"]["image"].keys())
    prompt_keys_video = set(analysis["prompt_keys"]["video"].keys())
    prompt_keys_tts = set(analysis["prompt_keys"]["tts"].keys())
    prompt_keys_bgm = set(analysis["prompt_keys"]["bgm"].keys())
    
    return {
        "video_frame": {
            **{k: 'first_frame' for k in video_frame_keys_first},
            **{k: 'last_frame' for k in video_frame_keys_last}
        },
        "image_ref": {**image_ref_keys_single, **image_ref_keys_multiple},
        "prompt": {
            "image_generation": prompt_keys_image,
            "video_generation": prompt_keys_video,
            "tts": prompt_keys_tts,
            "bgm": prompt_keys_bgm
        }
    }


def parse_schema_to_config(properties: Dict, required: List[str], category: str, mappings: Dict) -> Tuple[Dict, Dict]:
    """Parse OpenAPI schema properties into input_keys and parameters"""
    input_keys = {}
    parameters = {}
    
    video_frame_keys = mappings["video_frame"]
    image_ref_keys = mappings["image_ref"]
    prompt_keys = mappings["prompt"].get(category, set())
    
    for key, prop in properties.items():
        prop_type = prop.get("type", "string")
        description = prop.get("description", "").strip()
        default_val = prop.get("default")
        is_required = key in required
        
        # Determine if this is an input_key or parameter
        is_input_key = False
        mapped_key = key
        
        if category == "video_generation":
            # Check prompt first
            if key in prompt_keys or key == "prompt":
                mapped_key = "prompt"
                is_input_key = True
            # Check frame keys
            elif key in video_frame_keys:
                mapped_key = video_frame_keys[key]
                is_input_key = True
        elif category == "image_generation":
            # Check prompt first
            if key in prompt_keys or key == "prompt":
                mapped_key = "prompt"
                is_input_key = True
            # Check reference image keys
            elif key in image_ref_keys:
                mapped_key = image_ref_keys[key]
                is_input_key = True
        elif category == "tts":
            # Check prompt/text keys
            if key in prompt_keys or key in ["text", "prompt"]:
                mapped_key = "text"
                is_input_key = True
            elif key == "speaker_audio":
                mapped_key = "speaker_audio"
                is_input_key = True
        elif category == "bgm":
            # Check prompt keys
            if key in prompt_keys or key in ["prompt", "text"]:
                mapped_key = "prompt"
                is_input_key = True
        
        if is_input_key:
            # IMPORTANT: Save the original API key name for frame/image keys, but use unified key for prompt/text
            # This ensures:
            # 1. API compatibility: frame/image keys match what API expects (start_image, end_image, etc.)
            # 2. Unified interface: prompt/text keys are unified (prompt, text) for consistent usage
            # The mapped_key is used to identify the type of input for classification
            # But for API-specific keys (frames, images), we preserve the original key name
            if mapped_key in ["prompt", "text", "speaker_audio"]:
                # Use unified key for prompt/text (these are standardized)
                save_key = mapped_key
            else:
                # Use original API key for frame/image keys (preserve API compatibility)
                save_key = key
            
            input_keys[save_key] = {
                "type": prop_type if prop_type != "array" else "list[string]",
                "required": is_required,
                "description": description or f"{save_key} input"
            }
        else:
            param_def = {
                "type": prop_type,
                "description": description or f"{key} parameter"
            }
            if default_val is not None:
                param_def["default"] = default_val
            
            # Add range/options if available
            if "enum" in prop:
                param_def["options"] = prop["enum"]
            elif prop_type == "integer" and "minimum" in prop and "maximum" in prop:
                param_def["range"] = [prop["minimum"], prop["maximum"]]
            elif prop_type == "number" and "minimum" in prop and "maximum" in prop:
                param_def["range"] = [prop["minimum"], prop["maximum"]]
            
            parameters[key] = param_def
    
    return input_keys, parameters


def list_all_models(token: str) -> List[Dict]:
    """Try to fetch all models from Replicate API (if endpoint exists)"""
    models: List[Dict] = []
    try:
        # Try /models endpoint (may not exist)
        print("  尝试访问 /models 端点...", end=" ", flush=True)
        next_url: Optional[str] = f"{API_BASE}/models"
        timeout_count = 0
        max_attempts = 1  # Only try once, don't loop
        
        try:
            data = http_get(next_url, token)
            items = data.get("results", []) or data.get("models", [])
            if items:
                models.extend(items)
                print(f"✓ 找到 {len(items)} 个模型")
            else:
                print("⚠️  端点返回空结果")
            # Don't loop through pagination for now - may be too slow
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print("⚠️  /models 端点不存在 (404)")
            elif e.response.status_code == 403:
                print("⚠️  无权限访问 /models 端点 (403)")
            else:
                print(f"⚠️  HTTP 错误: {e.response.status_code}")
        except requests.exceptions.Timeout:
            print("⚠️  请求超时")
        except Exception as e:
            print(f"⚠️  错误: {type(e).__name__}: {str(e)[:100]}")
    except Exception as e:
        print(f"⚠️  无法访问 /models 端点: {type(e).__name__}")
    return models


def fetch_specified_models_data(
    token: str,
    specified_models: Dict[str, List[str]],
    min_created_at: Optional[str] = None,
) -> Dict:
    """Fetch models data for specified model IDs only.
    
    Args:
        token: API token
        specified_models: Dict mapping category to list of model IDs (e.g., {"image": ["owner/name", ...]})
        min_created_at: Optional date filter
    """
    threshold_dt = _parse_datetime_maybe(min_created_at) if min_created_at else None
    if min_created_at and not threshold_dt:
        raise ValueError(
            f"--min-created-at 解析失败: {min_created_at}. 期望 YYYY-MM-DD 或 ISO8601"
        )

    category_map = {
        "image": "image_generation",
        "video": "video_generation",
        "tts": "tts",
        "bgm": "bgm"
    }

    result = {
        "fetched_at": __import__("datetime").datetime.now().isoformat(),
        "min_created_at_filter": min_created_at,
        "mode": "specified_models",
        "models": {
            "image_generation": [],
            "video_generation": [],
            "tts": [],
            "bgm": [],
        }
    }

    total_models = sum(len(models) for models in specified_models.values())
    print(f"指定模式：共 {total_models} 个模型待处理\n")

    for cat, model_ids in specified_models.items():
        if not model_ids:
            continue
        
        cat_key = category_map.get(cat, cat)
        print(f"\n处理 {cat} 分类 ({len(model_ids)} 个模型)...")

        for idx, model_id in enumerate(model_ids, 1):
            if "/" not in model_id:
                print(f"  [{idx}/{len(model_ids)}] {model_id}... ⚠️ 格式错误，跳过")
                continue
            
            owner, name = model_id.split("/", 1)
            print(f"  [{idx}/{len(model_ids)}] {model_id}...", end=" ", flush=True)

            # Fetch model info
            try:
                model_info = http_get(f"/models/{owner}/{name}", token)
            except Exception as e:
                print(f"❌ 获取失败: {e}")
                continue

            updated_at = _pick_model_updated_at(model_info)
            created_at = _pick_model_created_at(model_info)
            version_id, latest_version_created_at = _pick_latest_version_info(model_info)

            # Filter by created_at if threshold is set
            if threshold_dt is not None:
                dt_created = _parse_datetime_maybe(created_at)
                if dt_created is not None and dt_created < threshold_dt:
                    created_str = created_at[:10] if created_at else "unknown"
                    threshold_str = threshold_dt.strftime("%Y-%m-%d")
                    print(f"↷ skip (created={created_str} < threshold={threshold_str})")
                    continue

            # Fetch schema
            properties, required, input_schema = {}, [], {}
            version_created_at = None
            schema_fetched = False

            if not version_id:
                version_id = get_model_latest_version(owner, name, token)
            if version_id:
                try:
                    version_info = http_get(f"/models/{owner}/{name}/versions/{version_id}", token)
                    version_created_at = version_info.get("created_at") if isinstance(version_info.get("created_at"), str) else None
                    schema = version_info.get("openapi_schema", {})
                    input_schema = (
                        schema.get("components", {})
                        .get("schemas", {})
                        .get("Input", {})
                    )
                    properties = input_schema.get("properties", {}) or {}
                    required = input_schema.get("required", []) or []
                    schema_fetched = True
                except Exception as e:
                    print(f"schema获取失败: {e}")

            # 指定模式下不重新分类，直接使用用户指定的类别
            entry = {
                "model_id": model_id,
                "owner": owner,
                "name": name,
                "description": model_info.get("description", ""),
                "source_category": cat_key,
                "source_collection": "specified",
                "effective_category": cat_key,
                "effective_category_reason": "user_specified",
                "updated_at": updated_at,
                "created_at": created_at,
                "latest_version_id": version_id,
                "latest_version_created_at": latest_version_created_at,
                "version_id": version_id,
                "version_created_at": version_created_at,
                "has_detailed_schema": bool(properties),
                "properties": properties,
                "required": required,
                "full_schema": input_schema,
            }

            # 直接使用用户指定的类别
            result["models"][cat_key].append(entry)

            print(f"✓ [{cat_key}]" if schema_fetched else f"⚠ no schema [{cat_key}]")

    return result


def fetch_all_models_data(
    token: str,
    include_all_models: bool = True,
    min_created_at: Optional[str] = None,
) -> Dict:
    """Fetch all models data from Replicate API and save to local file
    
    Args:
        token: API token
        include_all_models: If True, try to fetch all models (not just from collections)
    """
    print("获取所有 collections...")
    collections = list_all_collections(token)
    if not collections:
        raise RuntimeError("未获取到任何 collections")
    
    print(f"  共找到 {len(collections)} 个 collections")
    
    targets = resolve_target_collections(collections)
    print("\n目标分类对应的 collections：")
    for cat, slugs in targets.items():
        if slugs:
            print(f"- {cat}: {', '.join(slugs)}")
        else:
            print(f"- {cat}: <未匹配到>")
    
    threshold_dt = _parse_datetime_maybe(min_created_at) if min_created_at else None
    if min_created_at and not threshold_dt:
        raise ValueError(
            f"--min-created-at 解析失败: {min_created_at}. 期望 YYYY-MM-DD 或 ISO8601 (例如 2025-01-01 或 2025-01-01T00:00:00Z)"
        )

    result = {
        "fetched_at": __import__("datetime").datetime.now().isoformat(),
        "min_created_at_filter": min_created_at,
        "collections": targets,
        "models": {
            "image_generation": [],
            "video_generation": [],
            "tts": [],
            "bgm": [],
        }
    }
    
    category_map = {
        "image": "image_generation",
        "video": "video_generation",
        "tts": "tts",
        "bgm": "bgm"
    }
    
    # NOTE: We no longer rely on collection_models mapping; we reclassify by schema into effective_category.

    # If include_all_models is True, try to fetch additional models
    all_models_list = []
    # if include_all_models:
    #     print("\n尝试获取所有模型（不限于 collections）...")
    #     all_models_list = list_all_models(token)
    #     if all_models_list:
    #         print(f"  从 /models 端点找到 {len(all_models_list)} 个模型")
    #     else:
    #         print("  ⚠️  无法从 /models 端点获取模型（可能不支持或需要其他方法）")
    
    # Process models from collections and all_models
    processed_models = set()
    
    for cat, slugs in targets.items():
        cat_key = category_map[cat]
        
        for slug in slugs:
            print(f"\n处理 {cat} 分类 - collection: {slug}...")
            
            try:
                models = get_collection_models(slug, token)
                print(f"  找到 {len(models)} 个模型")
            except Exception as e:
                print(f"  ⚠️  获取 collection {slug} 失败: {e}")
                continue
            
            # We append directly into result["models"][effective_category] to support schema-based reclassification.
            for idx, model in enumerate(models, 1):
                owner = model.get("owner")
                name = model.get("name")
                if not owner or not name:
                    continue
                
                model_id = f"{owner}/{name}"
                if model_id in processed_models:
                    continue
                
                print(f"  [{idx}/{len(models)}] {model_id}...", end=" ", flush=True)
                processed_models.add(model_id)

                # Always fetch model_info once to record timestamps in raw data.
                try:
                    model_info = http_get(f"/models/{owner}/{name}", token)
                except Exception as e:
                    print(f"错误: {e}")
                    continue

                updated_at = _pick_model_updated_at(model_info)
                created_at = _pick_model_created_at(model_info)
                version_id, latest_version_created_at = _pick_latest_version_info(model_info)

                # Filter by model's created_at time - skip old models entirely
                if threshold_dt is not None:
                    dt_created = _parse_datetime_maybe(created_at)
                    if dt_created is not None and dt_created < threshold_dt:
                        # Model is too old, skip entirely
                        created_str = created_at[:10] if created_at else "unknown"
                        threshold_str = threshold_dt.strftime("%Y-%m-%d")
                        print(f"↷ skip (created={created_str} < threshold={threshold_str})")
                        continue

                # Fetch schema for models that pass the date filter
                properties, required, input_schema = {}, [], {}
                version_created_at = None
                schema_fetched = False
                
                # Ensure version_id (fallback to extra API call only when needed)
                if not version_id:
                    version_id = get_model_latest_version(owner, name, token)
                if version_id:
                    try:
                        version_info = http_get(f"/models/{owner}/{name}/versions/{version_id}", token)
                        version_created_at = version_info.get("created_at") if isinstance(version_info.get("created_at"), str) else None
                        schema = version_info.get("openapi_schema", {})
                        input_schema = (
                            schema.get("components", {})
                            .get("schemas", {})
                            .get("Input", {})
                        )
                        properties = input_schema.get("properties", {}) or {}
                        required = input_schema.get("required", []) or []
                        schema_fetched = True
                    except Exception as e:
                        print(f"schema获取失败: {e}")

                # Reclassify by schema/keywords into effective category
                effective_category, category_reason = _infer_effective_category(
                    model_id=model_id,
                    description=model_info.get("description", ""),
                    properties=properties,
                    source_category=cat_key,
                )

                entry = {
                    "model_id": model_id,
                    "owner": owner,
                    "name": name,
                    "description": model_info.get("description", ""),
                    "source_category": cat_key,
                    "source_collection": slug,
                    "effective_category": effective_category,
                    "effective_category_reason": category_reason,
                    "updated_at": updated_at,
                    "created_at": created_at,
                    "latest_version_id": version_id,
                    "latest_version_created_at": latest_version_created_at,
                    "version_id": version_id,
                    "version_created_at": version_created_at,
                    "has_detailed_schema": bool(properties),
                    "properties": properties,
                    "required": required,
                    "full_schema": input_schema,
                }
                # Append into effective bucket (fallback to source if unknown)
                bucket = entry.get("effective_category") or cat_key
                if bucket not in result["models"]:
                    bucket = cat_key
                    entry["effective_category"] = bucket
                    entry["effective_category_reason"] = "fallback_bucket_unknown"
                result["models"][bucket].append(entry)

                print(f"✓ [{bucket}]" if schema_fetched else f"⚠ no schema [{bucket}]")
    
    # Process additional models from /models endpoint (if available)
    if all_models_list:
        print(f"\n处理额外的模型（从 /models 端点，共 {len(all_models_list)} 个）...")
        additional_by_category = {"image_generation": [], "video_generation": [], "tts": [], "bgm": []}
        
        for model in all_models_list:
            owner = model.get("owner")
            name = model.get("name")
            if not owner or not name:
                continue
            
            model_id = f"{owner}/{name}"
            if model_id in processed_models:
                continue  # Already processed from collections
            
            # Try to categorize based on model name/description
            model_desc = model.get("description", "").lower()
            model_name_lower = model_id.lower()
            
            category = None
            if any(keyword in model_desc or keyword in model_name_lower 
                   for keyword in ["image", "text-to-image", "image-to-image", "image generation"]):
                category = "image_generation"
            elif any(keyword in model_desc or keyword in model_name_lower 
                     for keyword in ["video", "text-to-video", "image-to-video", "video generation"]):
                category = "video_generation"
            elif any(keyword in model_desc or keyword in model_name_lower 
                     for keyword in ["speech", "tts", "text-to-speech", "voice"]):
                category = "tts"
            elif any(keyword in model_desc or keyword in model_name_lower 
                     for keyword in ["music", "audio", "text-to-music", "bgm"]):
                category = "bgm"
            
            if category:
                print(f"  处理 {model_id} (分类: {category})...", end=" ", flush=True)
                try:
                    model_info = http_get(f"/models/{owner}/{name}", token)
                    updated_at = _pick_model_updated_at(model_info)
                    created_at = _pick_model_created_at(model_info)
                    version_id, latest_version_created_at = _pick_latest_version_info(model_info)

                    # Filter by model's created_at time - skip old models entirely
                    if threshold_dt is not None:
                        dt_created = _parse_datetime_maybe(created_at)
                        if dt_created is not None and dt_created < threshold_dt:
                            created_str = created_at[:10] if created_at else "unknown"
                            threshold_str = threshold_dt.strftime("%Y-%m-%d")
                            print(f"↷ skip (created={created_str} < threshold={threshold_str})")
                            continue

                    # Fetch schema
                    properties, required, input_schema = {}, [], {}
                    version_created_at = None
                    schema_fetched = False
                    if not version_id:
                        version_id = get_model_latest_version(owner, name, token)
                    if version_id:
                        version_info = http_get(f"/models/{owner}/{name}/versions/{version_id}", token)
                        version_created_at = version_info.get("created_at") if isinstance(version_info.get("created_at"), str) else None
                        schema = version_info.get("openapi_schema", {})
                        input_schema = (
                            schema.get("components", {})
                            .get("schemas", {})
                            .get("Input", {})
                        )
                        properties = input_schema.get("properties", {}) or {}
                        required = input_schema.get("required", []) or []
                        schema_fetched = True

                    # Reclassify additional models too (best-effort)
                    effective_category, category_reason = _infer_effective_category(
                        model_id=model_id,
                        description=model_info.get("description", ""),
                        properties=properties,
                        source_category=category,
                    )

                    additional_by_category[effective_category].append({
                        "model_id": model_id,
                        "owner": owner,
                        "name": name,
                        "description": model_info.get("description", ""),
                        "source_category": category,
                        "source_collection": None,
                        "effective_category": effective_category,
                        "effective_category_reason": category_reason,
                        "updated_at": updated_at,
                        "created_at": created_at,
                        "latest_version_id": version_id,
                        "latest_version_created_at": latest_version_created_at,
                        "version_id": version_id,
                        "version_created_at": version_created_at,
                        "has_detailed_schema": bool(properties),
                        "properties": properties,
                        "required": required,
                        "full_schema": input_schema,
                    })
                    processed_models.add(model_id)
                    print(f"✓ [{effective_category}]" if schema_fetched else f"⚠ no schema [{effective_category}]")
                except Exception as e:
                    print(f"错误: {e}")
        
        # Merge additional models into result
        for cat_key, additional_models in additional_by_category.items():
            if additional_models:
                print(f"\n  在 {cat_key} 中添加了 {len(additional_models)} 个额外模型")
                result["models"][cat_key].extend(additional_models)
    
    return result


def save_raw_data(data: Dict, output_path: str) -> None:
    """Save raw models data to JSON file"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_raw_data(input_path: str) -> Dict:
    """Load raw models data from JSON file"""
    with open(input_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_raw_data(data: Dict) -> Dict:
    """Analyze raw data to understand key patterns for better classification"""
    analysis = {
        "video_frame_keys": {"first": {}, "last": {}},
        "image_ref_keys": {"single": {}, "multiple": {}},
        "prompt_keys": {"image": {}, "video": {}, "tts": {}, "bgm": {}},
        "all_keys_by_category": {}
    }
    
    # Known patterns from actual data
    video_first_frame_patterns = {
        "start_image", "first_frame_image", "first_frame", "image"  # image is first frame when used alone
    }
    video_last_frame_patterns = {
        "end_image", "last_frame_image", "last_image", "last_frame"
    }
    
    image_ref_single_patterns = {
        "image_reference", "character_reference", "style_reference", "subject_reference",
        "input_image", "image_prompt", "init_image",  # image_prompt is a reference image, not a prompt
        "control_image", "style_image"
    }
    image_ref_multiple_patterns = {
        "style_reference_images", "image_input", "reference_images", "input_images"
    }
    
    # Exclude keywords - these are NOT reference images or prompt inputs
    exclude_keywords = {
        "aspect_ratio", "output_format", "resolution", "size", "image_size", 
        "image_width", "image_height", "megapixels", "sizing_strategy",
        "magic_prompt", "style_type", "style_preset", "style", "effect",
        "mask", "num_images", "number_of_images", "max_images",
        "enhance_image", "image_noise_scale", "image_prompt_strength",
        "scheduler", "model_variant", "frames", "num_frames", "max_frames",
        "frame_rate", "frames_per_second", "playback_frames_per_second",
        "click_frames", "output_frame_interval", "frame_interpolation",
        "frame_load_cap", "frame_num", "skip_first_frames", "animation_prompts",
        "prompt_map", "gif_frames_per_second", "smoother_steps",
        "color_theme_style", "lighting_style", "shot_type_style", "vibe_style",
        "lora_weights", "replicate_weights", "extra_lora_weights",
        "sequential_image_generation", "input_file", "controlnet_video",
        "end_video_id", "start_video_id", "subject_image_1", "subject_image_2",
        "subject_image_3", "subject_image_4", "image_1", "image_2", "image_3",
        "image_4", "image_5", "image_6", "image_7", "image_8", "image_9", "image_10",
        "controlnet_1_image", "controlnet_2_image", "controlnet_3_image",
        "negative_prompt"  # Negative prompt is a parameter, not an input_key
    }
    
    # Analyze video models
    video_models = data.get("models", {}).get("video_generation", [])
    for model in video_models:
        props = model.get("properties", {})
        model_id = model.get("model_id", "")
        
        for key, prop in props.items():
            prop_type = prop.get("type", "")
            desc = prop.get("description", "").lower()
            key_lower = key.lower()
            
            # Skip excluded keys
            if key in exclude_keywords or any(exc in key_lower for exc in ["_url", "_weight", "_strength"]):
                continue
            
            # Check for prompt keys
            if key == "prompt" or ("prompt" in key_lower and "text" in desc):
                if key not in analysis["prompt_keys"]["video"]:
                    analysis["prompt_keys"]["video"][key] = []
                analysis["prompt_keys"]["video"][key].append(model_id)
                continue
            
            # Check for frame keys
            is_frame_key = False
            
            # Exact match for known patterns
            if key in video_last_frame_patterns:
                # last_image should be last, not first
                is_frame_key = True
                target = "last"
            elif key in video_first_frame_patterns:
                # image/start_image/first_frame_image can be first frame
                if key != "last_image":  # Exclude last_image from first
                    is_frame_key = True
                    target = "first"
            
            if is_frame_key:
                target_dict = analysis["video_frame_keys"][target]
                if key not in target_dict:
                    target_dict[key] = []
                target_dict[key].append(model_id)
    
    # Analyze image models
    image_models = data.get("models", {}).get("image_generation", [])
    for model in image_models:
        props = model.get("properties", {})
        model_id = model.get("model_id", "")
        
        for key, prop in props.items():
            prop_type = prop.get("type", "")
            desc = prop.get("description", "").lower()
            key_lower = key.lower()
            
            # Skip excluded keys
            if key in exclude_keywords or any(exc in key_lower for exc in ["_url", "_weight", "_strength"]):
                continue
            
            # Check for prompt keys (exclude image_prompt which is actually a reference image)
            if key == "prompt" or (key != "image_prompt" and "prompt" in key_lower and "text" in desc):
                if key not in analysis["prompt_keys"]["image"]:
                    analysis["prompt_keys"]["image"][key] = []
                analysis["prompt_keys"]["image"][key].append(model_id)
                continue
            
            # Check for reference image keys
            is_ref_key = False
            is_multiple = False
            
            # Exact match for known patterns
            if key in image_ref_multiple_patterns:
                is_ref_key = True
                is_multiple = True
            elif key in image_ref_single_patterns:
                is_ref_key = True
                is_multiple = False
            # Pattern matching
            elif prop_type == "array" and ("image" in key_lower or "reference" in key_lower):
                is_ref_key = True
                is_multiple = True
            elif prop_type in ["file", "string"]:
                # Check if it's a reference image by description
                ref_indicators = ["reference", "guide", "use as", "use with", "input", "init", "style", 
                                "character", "subject", "transform", "guide generation", "composition"]
                if any(indicator in desc for indicator in ref_indicators):
                    if "image" in key_lower or "image" in desc:
                        # Exclude inpainting/image editing specific keys
                        if not any(exc in desc for exc in ["inpaint", "mask", "edit", "controlnet", "img2img"]):
                            is_ref_key = True
                            is_multiple = "multiple" in desc or "list" in desc or "array" in desc or prop_type == "array"
                # Special case: key is just "image" - check description carefully
                elif key == "image":
                    # Must explicitly indicate it's a reference, and NOT for inpainting
                    if any(indicator in desc for indicator in ["reference", "guide", "use", "input", "init", "composition"]):
                        if not any(exc in desc for exc in ["inpaint", "mask", "img2img"]):
                            is_ref_key = True
                            is_multiple = False
            
            if is_ref_key:
                target_dict = analysis["image_ref_keys"]["multiple" if is_multiple else "single"]
                if key not in target_dict:
                    target_dict[key] = []
                target_dict[key].append(model_id)
    
    # Analyze TTS models
    tts_models = data.get("models", {}).get("tts", [])
    for model in tts_models:
        props = model.get("properties", {})
        model_id = model.get("model_id", "")
        
        for key, prop in props.items():
            desc = prop.get("description", "").lower()
            key_lower = key.lower()
            
            # Check for prompt/text keys
            if key == "text" or key == "prompt" or ("prompt" in key_lower and "text" in desc):
                if key not in analysis["prompt_keys"]["tts"]:
                    analysis["prompt_keys"]["tts"][key] = []
                analysis["prompt_keys"]["tts"][key].append(model_id)
    
    # Analyze BGM models
    bgm_models = data.get("models", {}).get("bgm", [])
    for model in bgm_models:
        props = model.get("properties", {})
        model_id = model.get("model_id", "")
        
        for key, prop in props.items():
            desc = prop.get("description", "").lower()
            key_lower = key.lower()
            
            # Skip excluded keys (like negative_prompt)
            if key in exclude_keywords:
                continue
            
            # Check for prompt keys
            if key == "prompt" or key == "text" or ("prompt" in key_lower and "text" in desc and "negative" not in key_lower):
                if key not in analysis["prompt_keys"]["bgm"]:
                    analysis["prompt_keys"]["bgm"][key] = []
                analysis["prompt_keys"]["bgm"][key].append(model_id)
    
    # Collect all keys by category for reference
    for cat in ["image_generation", "video_generation", "tts", "bgm"]:
        models = data.get("models", {}).get(cat, [])
        all_keys = set()
        for model in models:
            all_keys.update(model.get("properties", {}).keys())
        analysis["all_keys_by_category"][cat] = sorted(all_keys)
    
    return analysis


def print_analysis_results(analysis: Dict) -> None:
    """Print analysis results for debugging"""
    print("\n=== 分析结果 ===")
    
    print("\n【Prompt Keys】")
    cat_map = {"image": "image_generation", "video": "video_generation", "tts": "tts", "bgm": "bgm"}
    for cat, cat_key in cat_map.items():
        keys = analysis["prompt_keys"].get(cat, {})
        if keys:
            print(f"  {cat_key}: {', '.join(sorted(keys.keys()))}")
    
    print("\n【Video Models - 首帧 Keys】")
    for key, models in sorted(analysis["video_frame_keys"]["first"].items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {key}: {len(models)} 个模型")
    
    print("\n【Video Models - 尾帧 Keys】")
    for key, models in sorted(analysis["video_frame_keys"]["last"].items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {key}: {len(models)} 个模型")
    
    print("\n【Image Models - 单图参考 Keys】")
    for key, models in sorted(analysis["image_ref_keys"]["single"].items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {key}: {len(models)} 个模型")
    
    print("\n【Image Models - 多图参考 Keys】")
    for key, models in sorted(analysis["image_ref_keys"]["multiple"].items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {key}: {len(models)} 个模型")


def generate_models_config_from_raw(raw_data_path: str) -> Dict:
    """Generate models_config.json from raw data file"""
    # Load and analyze
    print(f"加载原始数据: {raw_data_path}")
    data = load_raw_data(raw_data_path)
    
    print("分析原始数据...")
    analysis = analyze_raw_data(data)
    print_analysis_results(analysis)
    
    # Build mappings once
    mappings = build_key_mappings(analysis)
    
    # Generate config
    print("\n生成 models_config.json...")
    result = {
        "description": "Replicate and Fal model configuration definitions - universal configuration, task-independent",
        "version": "1.0",
        "models": {
            "image_generation": {},
            "video_generation": {},
            "tts": {},
            "bgm": {}
        },
        "notes": {
            "purpose": "Define input keys and parameters for all Replicate models",
            "location": "tools/ directory (universal configuration, task-independent)",
            "usage": "Workflow loads this configuration at runtime to understand input/output interface of each model"
        }
    }
    
    for cat_key in ["image_generation", "video_generation", "tts", "bgm"]:
        models = data.get("models", {}).get(cat_key, [])
        print(f"\n处理 {cat_key} ({len(models)} 个模型)...")
        
        for idx, model in enumerate(models, 1):
            model_id = model.get("model_id")
            properties = model.get("properties", {})
            required = model.get("required", [])
            
            print(f"  [{idx}/{len(models)}] {model_id}...", end=" ", flush=True)
            
            if not properties:
                print("跳过（无properties）")
                continue
            
            input_keys, parameters = parse_schema_to_config(properties, required, cat_key, mappings)
            
            result["models"][cat_key][model_id] = {
                "description": model.get("description", f"Replicate {cat_key} model"),
                "input_keys": input_keys,
                "parameters": parameters
            }
            print("✓")
    
    return result


def write_models_config(output_path: str, config: Dict) -> None:
    """Write models_config.json to file"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def print_parameters(title: str, owner: str, name: str, token: str) -> None:
    version_id = get_model_latest_version(owner, name, token)
    print(f"\n[{title}] 模型: {owner}/{name}")
    if not version_id:
        print("  未找到最新版本，跳过参数读取。")
        return
    props = get_version_input_schema(owner, name, version_id, token)
    if not props:
        print("  未找到输入参数定义。")
        return
    for key, meta in props.items():
        t = meta.get("type") or meta.get("anyOf") or meta.get("oneOf") or "unknown"
        default = meta.get("default", "<none>")
        desc = meta.get("description", "").strip()
        if len(desc) > 140:
            desc = desc[:137] + "..."
        print(f"  - {key}: type={t}, default={default}, desc={desc}")


# ===================== FAL support =====================
def fal_http_get_json(url: str) -> Optional[Dict]:
    try:
        headers = {}
        fal_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
        if fal_key:
            headers["Authorization"] = f"Key {fal_key}"
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        # Try JSON first
        try:
            return resp.json()
        except Exception:
            # Try YAML if available
            if yaml is not None:
                try:
                    return yaml.safe_load(resp.text)
                except Exception:
                    return None
            return None
    except Exception:
        return None


def _extract_properties_from_openapi(doc: Dict) -> Dict:
    if not isinstance(doc, dict):
        return {}
    # 1) components.schemas.Input.properties
    props = (
        doc.get("components", {})
        .get("schemas", {})
        .get("Input", {})
        .get("properties", {})
    )
    if isinstance(props, dict) and props:
        return props
    # 2) any object schema with properties inside components.schemas
    schemas = doc.get("components", {}).get("schemas", {})
    if isinstance(schemas, dict):
        for _, schema in schemas.items():
            if isinstance(schema, dict) and schema.get("type") == "object":
                p = schema.get("properties", {})
                if isinstance(p, dict) and p:
                    return p
    # 3) paths -> first POST -> requestBody -> application/json -> schema -> properties
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
                p = schema.get("properties", {})
                if isinstance(p, dict) and p:
                    return p
    return {}


def fal_slug_exists(slug: str) -> bool:
    try:
        headers = {}
        fal_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
        if fal_key:
            headers["Authorization"] = f"Key {fal_key}"
        # Prefer HEAD, fallback to GET
        url = f"https://fal.run/{slug}"
        resp = requests.head(url, headers=headers, timeout=15, allow_redirects=True)
        if resp.status_code in (200, 204):
            return True
        if resp.status_code == 405:
            # Method Not Allowed -> likely requires POST; consider exists
            return True
        if resp.status_code == 401:
            # Requires auth; consider exists but inaccessible
            return True
        if resp.status_code == 404:
            return False
        # Other 3xx/5xx -> try GET once
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code in (200, 204, 405, 401):
            return True
        return False
    except Exception:
        return False


def fal_guess_params_by_validation(slug: str) -> List[str]:
    if fal_client is None:
        return []
    try:
        client = fal_client.SyncClient()
        # Intentionally send empty arguments to get validation error without running compute
        try:
            client.run(slug, {})
            return []  # If it succeeded with empty input, then no required params
        except Exception as e:
            # Try to parse common validation error shapes
            msg = str(e)
            # Heuristics: extract 'field required' markers or JSON-like keys
            import re as _re
            fields = set()
            for m in _re.finditer(r"'([a-zA-Z0-9_\-]+)'\s*(field required|is required)", msg):
                fields.add(m.group(1))
            for m in _re.finditer(r"\b([a-zA-Z0-9_\-]+)\b.*(required|missing)", msg):
                if len(m.group(1)) > 1 and len(m.group(1)) < 64:
                    fields.add(m.group(1))
            return sorted(fields)
    except Exception:
        return []


def fal_get_input_schema(slug: str, retry: int = 2) -> Dict:
    # Try to fetch OpenAPI schema exposed for fal functions
    # e.g. https://fal.run/fal-ai/flux-1.1-pro/openapi.json or /openapi
    candidates = [
        f"https://fal.run/{slug}/openapi.json",
        f"https://fal.run/{slug}/openapi",
    ]
    for _ in range(retry):
        for url in candidates:
            data = fal_http_get_json(url)
            if not data:
                continue
            props = _extract_properties_from_openapi(data)
            if props:
                return props
    return {}


def _fal_try_api_endpoints_for_query(query: str) -> List[str]:
    # Try several potential JSON endpoints used by fal site
    endpoints = [
        f"https://fal.run/api/search?q={requests.utils.quote(query)}",
        f"https://fal.run/api/functions?query={requests.utils.quote(query)}",
        f"https://fal.run/api/explore?query={requests.utils.quote(query)}",
    ]
    slugs: List[str] = []
    for url in endpoints:
        data = fal_http_get_json(url)
        if not data:
            continue
        # Try common shapes
        candidates = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            for key in ["results", "functions", "items", "models"]:
                if isinstance(data.get(key), list):
                    candidates = data.get(key)
                    break
        for item in candidates:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug") or item.get("path") or item.get("id")
            if not slug:
                owner = item.get("owner") or item.get("namespace")
                name = item.get("name")
                if owner and name:
                    slug = f"{owner}/{name}"
            if isinstance(slug, str) and "/" in slug:
                slugs.append(slug.strip("/"))
    return list(dict.fromkeys(slugs))  # dedupe, preserve order


def _fal_try_html_for_query(query: str) -> List[str]:
    # Fallback: scrape explore/search page to extract /owner/name links
    urls = [
        f"https://fal.run/explore?search={requests.utils.quote(query)}",
        f"https://fal.run/?search={requests.utils.quote(query)}",
    ]
    slugs: List[str] = []
    pattern = re.compile(r"href=\"/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)\"")
    for url in urls:
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200:
                continue
            for m in pattern.finditer(resp.text):
                slug = f"{m.group(1)}/{m.group(2)}"
                slugs.append(slug)
        except Exception:
            continue
    return list(dict.fromkeys(slugs))


def _fal_query_to_slugs(query: str, limit: int = 30) -> List[str]:
    slugs = _fal_try_api_endpoints_for_query(query)
    if not slugs:
        slugs = _fal_try_html_for_query(query)
    return slugs[:limit]


def fal_get_collections() -> Dict[str, List[str]]:
    # Dynamic discovery via fal site APIs with HTML fallback
    queries_by_cat = {
        "image": ["image", "text to image", "t2i", "img2img", "sd", "flux"],
        "video": ["video", "text to video", "t2v", "i2v", "animate"],
        "tts": ["tts", "text to speech", "speech", "voice"],
        "bgm": ["music", "audio", "music generation", "bgm"],
    }
    results: Dict[str, List[str]] = {"image": [], "video": [], "tts": [], "bgm": []}
    # 1) dynamic discovery
    try:
        for cat, queries in queries_by_cat.items():
            collected: List[str] = []
            for q in queries:
                slugs = _fal_query_to_slugs(q, limit=30)
                for s in slugs:
                    if s not in collected:
                        collected.append(s)
                if len(collected) >= 30:
                    break
            results[cat] = collected[:30]
    except Exception:
        pass

    # 2) config fallback
    if all(len(v) == 0 for v in results.values()):
        cfg_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'fal_collections.json')
        cfg_path = os.path.abspath(cfg_path)
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for k in results.keys():
                    if isinstance(data.get(k), list) and data.get(k):
                        results[k] = data.get(k)
        except Exception:
            # minimal built-in fallback
            results = {
                "image": [
                    "fal-ai/flux-1.1-pro",
                    "fal-ai/flux-dev",
                ],
                "video": [
                    "fal-ai/animate-diff",
                ],
                "tts": [
                    "fal-ai/minimax-speech-01",
                ],
                "bgm": [
                    "fal-ai/stable-audio",
                ],
            }
    # 3) existence filter based on current credentials
    filtered: Dict[str, List[str]] = {"image": [], "video": [], "tts": [], "bgm": []}
    for cat, slugs in results.items():
        for slug in slugs:
            if fal_slug_exists(slug):
                filtered[cat].append(slug)
    return filtered


def print_fal_parameters(title: str, slug: str) -> None:
    owner, name = slug.split("/", 1) if "/" in slug else ("", slug)
    print(f"\n[{title}] 模型: {owner}/{name}")
    props = fal_get_input_schema(slug)
    if not props:
        # Try validation-based guessing as a fallback
        guessed = fal_guess_params_by_validation(slug)
        if guessed:
            print("  未找到输入参数定义。以下为推测的必填字段：")
            for k in guessed:
                print(f"  - {k}")
        else:
            print("  未找到输入参数定义。")
        return
    for key, meta in props.items():
        t = meta.get("type") or meta.get("anyOf") or meta.get("oneOf") or "unknown"
        default = meta.get("default", "<none>")
        desc = (meta.get("description", "") or "").strip()
        if len(desc) > 140:
            desc = desc[:137] + "..."
        print(f"  - {key}: type={t}, default={default}, desc={desc}")

def print_summary(config: Dict) -> None:
    """Print summary statistics"""
    total_models = sum(len(models) for models in config["models"].values())
    print(f"\n完成！共生成 {total_models} 个模型的配置")
    for cat, models in config["models"].items():
        print(f"  {cat}: {len(models)} 个模型")


def fetch_single_model(owner: str, name: str, token: str, category: str) -> Optional[Dict]:
    """Fetch a single model's data and return formatted entry"""
    try:
        print(f"获取模型 {owner}/{name} 的信息...")
        
        # Get model info
        model_info = http_get(f"/models/{owner}/{name}", token)
        version_id = get_model_latest_version(owner, name, token)
        
        if not version_id:
            print(f"  ⚠️  无法获取版本信息")
            return None
        
        # Get version schema
        version_info = http_get(f"/models/{owner}/{name}/versions/{version_id}", token)
        schema = version_info.get("openapi_schema", {})
        input_schema = (
            schema.get("components", {})
            .get("schemas", {})
            .get("Input", {})
        )
        properties = input_schema.get("properties", {}) or {}
        required = input_schema.get("required", []) or []
        
        return {
            "model_id": f"{owner}/{name}",
            "owner": owner,
            "name": name,
            "description": model_info.get("description", ""),
            "version_id": version_id,
            "properties": properties,
            "required": required,
            "full_schema": input_schema
        }
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return None


def update_single_model_in_config(model_owner: str, model_name: str, category: str) -> None:
    """Fetch a single model and update models_config.json"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, '..', 'config', 'models_config.json')
    config_path = os.path.abspath(config_path)
    
    try:
        token = get_api_token()
    except Exception as e:
        print(f"错误：{str(e)}")
        return
    
    # Fetch model data
    model_data = fetch_single_model(model_owner, model_name, token, category)
    if not model_data:
        print("无法获取模型数据")
        return
    
    # Load existing config
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Need to analyze raw data to build mappings - create a minimal analysis
    # For single model update, we'll use basic mappings
    # Note: build_key_mappings expects dict format where values are lists of model_ids
    minimal_analysis = {
        "prompt_keys": {
            "image": {"prompt": [], "text": [], "input_text": []},
            "video": {"prompt": [], "text": []},
            "tts": {"text": [], "input_text": []},
            "bgm": {"prompt": [], "text": []}
        },
        "video_frame_keys": {
            "first": {"first_frame": [], "start_image": [], "image": []},
            "last": {"last_frame": [], "end_image": []}
        },
        "image_ref_keys": {
            "single": {"reference_image": [], "input_image": []},
            "multiple": {"reference_images": [], "input_images": []}
        }
    }
    
    # Build mappings
    mappings = build_key_mappings(minimal_analysis)
    
    # Parse schema to config format
    input_keys, parameters = parse_schema_to_config(
        model_data["properties"],
        model_data["required"],
        category,
        mappings
    )
    
    # Update config
    model_id = f"{model_owner}/{model_name}"
    config["models"][category][model_id] = {
        "description": model_data["description"],
        "input_keys": input_keys,
        "parameters": parameters
    }
    
    # Save config
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 已更新 {model_id} 到 {config_path}")
    print(f"   Input keys: {list(input_keys.keys())}")
    print(f"   Parameters: {list(parameters.keys())}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Replicate models catalog tool")
    parser.add_argument("--fetch-only", action="store_true", help="Only fetch raw data, don't generate config")
    parser.add_argument("--generate-only", action="store_true", help="Only generate config from existing raw data")
    parser.add_argument("--update-model", type=str, help="Update a single model: owner/name:category (e.g., lucataco/wan-2.2-first-last-frame:video_generation)")
    parser.add_argument("--use-specified", action="store_true", help="Use SPECIFIED_MODELS dict instead of fetching from collections")
    parser.add_argument(
        "--min-created-at",
        type=str,
        default=None,
        help="Only fetch models created at/after this time. "
             "Format: YYYY-MM-DD or ISO8601 (e.g., 2025-01-01 or 2025-01-01T00:00:00Z).",
    )
    args = parser.parse_args()
    
    # Handle single model update
    if args.update_model:
        parts = args.update_model.split(":")
        if len(parts) != 2:
            print("错误：格式应为 owner/name:category")
            print("例如：lucataco/wan-2.2-first-last-frame:video_generation")
            sys.exit(1)
        model_id, category = parts
        if "/" not in model_id:
            print("错误：模型名称格式应为 owner/name")
            sys.exit(1)
        owner, name = model_id.split("/", 1)
        update_single_model_in_config(owner, name, category)
        return
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    raw_data_path = os.path.join(script_dir, "replicate_raw_data.json")
    config_path = os.path.join(script_dir, '..', 'config', 'models_config.json')
    config_path = os.path.abspath(config_path)
    
    # Step 1: Fetch raw data (if not generate-only)
    if not args.generate_only:
        try:
            token = get_api_token()
        except Exception as e:
            print(f"错误：{str(e)}")
            sys.exit(1)
        
        print(f"输出路径: {raw_data_path}\n")
        
        if args.use_specified:
            # 使用指定模型模式
            total = sum(len(v) for v in SPECIFIED_MODELS.values())
            if total == 0:
                print("错误：SPECIFIED_MODELS 为空，请先在代码中添加要拉取的模型")
                print("位置：replicate_catalog.py 文件顶部的 SPECIFIED_MODELS 字典")
                sys.exit(1)
            print(f"使用指定模型模式，共 {total} 个模型")
            data = fetch_specified_models_data(token, SPECIFIED_MODELS, min_created_at=args.min_created_at)
        else:
            # 从 collections 拉取
            print(f"拉取所有 Replicate 模型数据（从 collections）...")
            data = fetch_all_models_data(token, include_all_models=True, min_created_at=args.min_created_at)
        
        save_raw_data(data, raw_data_path)
        
        print(f"\n原始数据已保存到: {raw_data_path}")
        print(f"共拉取 {sum(len(models) for models in data['models'].values())} 个模型的数据")
        
        if args.fetch_only:
            print("\n（仅拉取模式，未生成 config）")
            print("运行 --generate-only 来生成 models_config.json")
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

if __name__ == "__main__":
    main()


