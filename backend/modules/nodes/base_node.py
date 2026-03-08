# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

# refactored_architecture/1_infrastructure/nodes/base_node.py
import os
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from modules.utils.data_version_manager import DataVersionManager

class BaseNode(ABC):
    """Base class for all nodes in the workflow system
    
    Provides unified support for:
    - force_execute: Ignore cache and regenerate
    - create_new_version: Create versioned output files
    - data_version_management: Automatically track file versions
    """

    def __init__(self, name: str, task_path: str):
        self.name = name
        self.task_path = task_path
        os.makedirs(task_path, exist_ok=True)
        
        # Extract execution options from inputs (set by wrapper)
        self._force_execute = False
        self._create_new_version = False
        
        # Initialize DataVersionManager if task_path exists
        self.dvm = None
        if task_path and os.path.exists(task_path):
            try:
                self.dvm = DataVersionManager(task_path)
            except Exception as e:
                print(f"⚠️ [{self.name}] Failed to initialize DataVersionManager: {e}")

    def update_data_version(self, keys: List[str], file_path: str):
        """Helper to update data version if DVM is available"""
        if self.dvm:
            try:
                self.dvm.update_version(keys, file_path)
            except Exception as e:
                print(f"⚠️ [{self.name}] Failed to update data version for {keys}: {e}")


    def __call__(self, inputs: Dict[str, Any]) -> Any:
        """Node entry point - standardized execution flow"""
        print(f"🔄 [{self.name}] Starting...")
        
        # Extract and store execution options
        self._force_execute = inputs.get('_force_execute', False)
        self._create_new_version = inputs.get('_create_new_version', False)
        
        try:
            result = self.run(inputs)
            print(f"✅ [{self.name}] Completed.")
            return {**inputs, self.name: result}
        except Exception as e:
            print(f"❌ [{self.name}] Failed: {str(e)}")
            raise

    @abstractmethod
    def run(self, inputs: Dict[str, Any]) -> Any:
        """Core logic method that must be implemented by subclasses"""
        raise NotImplementedError
    
    def get_output_fields(self) -> list:
        """
        Declare the list of output field names for this node (for extracting file paths from state)
        
        Subclasses should override this method to declare the output fields they produce.
        The returned field names will be used to extract file paths from state.
        
        Field values can be:
        - Single file path string: 'path/to/file.mp4'
        - File path list: ['path/to/file1.mp3', 'path/to/file2.mp3']
        - Nested list: [['img1.png', 'img2.png'], ['img3.png', 'img4.png']]
        
        Returns:
            List of output field names
        
        Example:
            class ImageNode(BaseNode):
                def get_output_fields(self):
                    return ['generated_images']  # Field name in state
            
            class BGMNode(BaseNode):
                def get_output_fields(self):
                    return ['bgm_path']  # Field name in state
        """
        # Default returns empty list (no file output checking)
        return []

    # ========== Fine-grained incremental execution helper methods ==========
    
    def scan_dirty_elements(self, list_field_value: list) -> dict:
        """
        Scan a list field for elements with embedded _dirty flags
        
        Args:
            list_field_value: List of elements (usually dicts) to scan
        
        Returns:
            Dict mapping index to dirty fields: {0: ['field1'], 2: ['field2', 'field3']}
        
        Example:
            storyboard = inputs.get('storyboard', [])
            dirty_frames = self.scan_dirty_elements(storyboard)
            # Returns: {1: ['first_image_description'], 3: ['last_image_description']}
        """
        dirty_elements = {}
        for idx, element in enumerate(list_field_value):
            if isinstance(element, dict) and element.get('_dirty', False):
                dirty_fields = element.get('_dirty_fields', [])
                if dirty_fields:
                    dirty_elements[idx] = dirty_fields
        return dirty_elements
    
    def clean_dirty_flags(self, list_field_value: list) -> list:
        """
        Remove _dirty metadata from all elements in a list
        
        Args:
            list_field_value: List of elements with potential _dirty flags
        
        Returns:
            Cleaned list without _dirty metadata
        
        Example:
            cleaned_storyboard = self.clean_dirty_flags(storyboard)
        """
        cleaned_list = []
        for element in list_field_value:
            if isinstance(element, dict):
                # Remove all keys starting with '_dirty'
                cleaned_element = {k: v for k, v in element.items() 
                                 if not k.startswith('_dirty')}
                cleaned_list.append(cleaned_element)
            else:
                cleaned_list.append(element)
        return cleaned_list
    
    def has_dirty_elements(self, list_field_value: list) -> bool:
        """
        Quick check if a list has any dirty elements
        
        Args:
            list_field_value: List to check
        
        Returns:
            True if any element has _dirty flag
        """
        return any(isinstance(item, dict) and item.get('_dirty', False) 
                   for item in list_field_value)
    
    # ========== Cache and file management helper methods ==========
    
    def should_use_cache(self, cache_path: str, force_regenerate: bool = False) -> bool:
        """
        Determine whether cache should be used
        
        Args:
            cache_path: Path to cached file
            force_regenerate: If True, force regeneration even if cache exists (for fine-grained execution)
        
        Returns:
            True - Use cache (skip execution)
            False - Don't use cache (execute node)
        """
        if self._force_execute or force_regenerate:
            return False  # Force execution, don't use cache
        return os.path.exists(cache_path)  # Use cache if it exists
    
    def prepare_output_path(self, intended_path: str) -> str:
        """
        Prepare output file path
        
        Logic:
        1. Always use versioned filename format: {name}_v{N}{ext}
        2. Scan directory for existing versions
        3. If create_new_version=True: return next version (N+1)
        4. If create_new_version=False:
           - If versions exist: return latest version (N)
           - If no versions exist: return v1
        """
        dirname = os.path.dirname(intended_path)
        basename = os.path.basename(intended_path)
        name, ext = os.path.splitext(basename)
        
        # Ensure directory exists
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)
            
        # Scan for existing versions
        existing_versions = []
        if os.path.exists(dirname):
            for f in os.listdir(dirname):
                if f.startswith(f"{name}_v") and f.endswith(ext):
                    try:
                        # Extract version number: name_v1.ext -> 1
                        v_str = f[len(name)+2 : -len(ext)]
                        if v_str.isdigit():
                            existing_versions.append(int(v_str))
                    except ValueError:
                        continue
        
        current_max_version = max(existing_versions) if existing_versions else 0
        
        if self._create_new_version:
            # Always create next version
            next_version = current_max_version + 1
            versioned_name = f"{name}_v{next_version}{ext}"
            versioned_path = os.path.join(dirname, versioned_name)
            print(f"📝 [{self.name}] Creating new version: {versioned_name}")
            return os.path.abspath(versioned_path)
        else:
            # Use latest version if exists, otherwise start at v1
            target_version = max(1, current_max_version)
            versioned_name = f"{name}_v{target_version}{ext}"
            versioned_path = os.path.join(dirname, versioned_name)
            # Only log if we are creating a new v1 (no previous versions)
            if target_version == 1 and current_max_version == 0:
                 print(f"📝 [{self.name}] Creating initial version: {versioned_name}")
            return os.path.abspath(versioned_path)
    
    def log_cache_status(self, cache_path: str, using_cache: bool):
        """Log cache usage status"""
        if using_cache:
            print(f"📄 [{self.name}] Using cached: {os.path.basename(cache_path)}")
        elif self._force_execute:
            if os.path.exists(cache_path) and not self._create_new_version:
                print(f"🔄 [{self.name}] Force executing (will overwrite)")
            else:
                print(f"🔄 [{self.name}] Force executing")

    def load_json(self, filename: str):
        path = os.path.join(self.task_path, filename)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"⚠️  Warning: Invalid JSON in {path}, ignoring...")
                return None
        return None

    def save_json(self, filename: str, data):
        path = os.path.join(self.task_path, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 JSON saved: {path}")
    
    def get_versioned_path(self, filepath: str) -> str:
        """
        Generate versioned file path
        Example: image_1.png -> image_1_v1.png -> image_1_v2.png
        """
        if not os.path.exists(filepath):
            return filepath
        
        dirname = os.path.dirname(filepath)
        basename = os.path.basename(filepath)
        name, ext = os.path.splitext(basename)
        
        version = 1
        while True:
            versioned_name = f"{name}_v{version}{ext}"
            versioned_path = os.path.join(dirname, versioned_name) if dirname else versioned_name
            if not os.path.exists(versioned_path):
                return versioned_path
            version += 1 

    def get_metadata_path(self, file_path: str) -> str:
        """Get metadata file path for a given asset path"""
        if not file_path:
            return None
        # e.g. image.png -> image.json
        base, _ = os.path.splitext(file_path)
        return f"{base}.json"

    def save_asset_metadata(self, file_path: str, metadata: dict):
        """Save asset generation metadata"""
        if not file_path or not metadata:
            return
        
        meta_path = self.get_metadata_path(file_path)
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            print(f"💾 Saved metadata: {os.path.basename(meta_path)}")
        except Exception as e:
            print(f"⚠️ Failed to save metadata for {os.path.basename(file_path)}: {e}")

    def load_asset_metadata(self, file_path: str) -> dict:
        """Load asset generation metadata"""
        if not file_path:
            return {}
        
        meta_path = self.get_metadata_path(file_path)
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Failed to load metadata from {os.path.basename(meta_path)}: {e}")
                return {}
        return {}


# ===================== Extended Abstractions =====================
class ToolNode(BaseNode):
    """Abstract base for tool-driven nodes (e.g., video editor).
    Provides hooks for parameter schema and application.
    """
    def get_input_schema(self) -> Dict[str, Any]:
        """Return input_keys schema (for UI/template generation)."""
        return {}

    def get_parameter_schema(self) -> Dict[str, Any]:
        """Return parameter schema with defaults (for UI/template generation)."""
        return {}

    def apply_parameters(self, params: Dict[str, Any]):
        """Apply runtime parameters to the node instance before run()."""
        # Default no-op; subclasses should override
        return


class GenModelNode(BaseNode):
    """Abstract base for generation nodes that use a model (image/video/tts/bgm)."""
    def __init__(self, name: str, task_path: str):
        super().__init__(name, task_path)
        self.config_manager = None  # Will be set by workflow
    
    def set_config_manager(self, config_manager):
        """Set config manager for this node"""
        self.config_manager = config_manager
    
    def get_model_identifier(self) -> Optional[str]:
        """Return the model identifier used by this node (e.g., default_model)."""
        return getattr(self, 'default_model', None)
    
    def get_category(self) -> str:
        """Return category for this node (image_generation, video_generation, tts, bgm)"""
        # Subclasses should override
        return ""

    def get_input_schema(self) -> Dict[str, Any]:
        """Return input_keys schema (optional; can be empty if driven by models_config)."""
        return {}

    def get_parameter_schema(self) -> Dict[str, Any]:
        """Return parameter schema defaults (optional; models_config may supply)."""
        return {}

    def apply_parameters(self, params: Dict[str, Any]):
        """Apply runtime parameters to the node instance before run()."""
        # Default no-op; subclasses may override
        return
    
    def get_model_parameters(self, asset_path: str = None, overrides: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get effective model parameters
        
        Priority:
        1. Global defaults (models_config)
        2. Global runtime params (workflow_config)
        3. Asset-specific metadata (if asset_path provided and exists)
        4. Runtime overrides (overrides dict)
        
        Args:
            asset_path: Path to the asset file (to load existing metadata)
            overrides: Runtime overrides (usually from state/storyboard)
        """
        if not self.config_manager:
            return overrides or {}
        
        category = self.get_category()
        model_name = self.get_model_identifier()
        if not category or not model_name:
            return overrides or {}
        
        # Get default parameters from models_config
        model_config = self.config_manager.get_model_config(category, model_name)
        parameters_def = model_config.get('parameters', {})
        
        # Extract default values from parameter definitions
        params = {}
        for param_name, param_def in parameters_def.items():
            if isinstance(param_def, dict):
                if 'default' in param_def:
                    params[param_name] = param_def['default']
            else:
                params[param_name] = param_def
        
        # Get runtime parameters from workflow_config (overrides defaults)
        node_type = self.name
        workflow_params = self.config_manager.get_node_params(node_type, model_name, {})
        params.update(workflow_params)
        
        # Load asset-specific metadata if available
        if asset_path:
            metadata = self.load_asset_metadata(asset_path)
            if metadata:
                # FILTER METADATA: Only update keys that are actual parameters, 
                # NOT input file paths or prompts which should come from current inputs.
                # We use model_config input_keys + a blacklist of known input-like keys.
                
                # Get input keys from model definition
                input_keys = list(model_config.get('input_keys', {}).keys())
                
                # Standard blacklist of input-related keys to NEVER load from metadata
                blacklist = {
                    'prompt', 'image', 'first_frame', 'last_frame', 
                    'start_image', 'end_image', 'first_frame_image', 'last_frame_image',
                    'reference_image', 'reference_images', 'input_image', 'input_images',
                    'text', 'input_text', 'speaker_audio', 'audio'
                }
                
                filtered_metadata = {
                    k: v for k, v in metadata.items() 
                    if k not in input_keys and k not in blacklist
                }
                
                params.update(filtered_metadata)
                # Log that we are using asset-specific metadata
                # print(f"   📄 [{self.name}] Loaded asset metadata overrides from {os.path.basename(self.get_metadata_path(asset_path))}")
                
        # Apply runtime overrides (highest priority)
        if overrides:
            params.update(overrides)
            
        return params
    
    def convert_input_keys(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Convert unified input keys to model-specific format"""
        if not self.config_manager:
            return inputs
        
        category = self.get_category()
        model_name = self.get_model_identifier()
        if not category or not model_name:
            return inputs
        
        return self.config_manager.convert_input_keys_to_model_format(category, model_name, inputs)