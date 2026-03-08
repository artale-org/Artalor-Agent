# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

"""
Configuration Manager - Manage workflow configurations and generation records

Features:
1. Load model and tool definitions from tools/ (general config)
2. Optionally load workflow_config.json (runtime config)
3. Record configuration and file generation information for current run
4. Support configuration inheritance and overrides
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

# Import node classes for robust isinstance checks
try:
    from modules.nodes.image_node import ImageNode
    from modules.nodes.video_node import VideoNode
    from modules.nodes.audio_node import VoiceoverNode, BGMNode, VideoEditNode, SegmentedVoiceoverNode
except Exception:
    # Defer import errors to runtime usage; detection will fallback to None
    ImageNode = VideoNode = VoiceoverNode = BGMNode = VideoEditNode = SegmentedVoiceoverNode = None


class ConfigManager:
    """Configuration Manager"""
    
    def __init__(self, task_path: str, workflow_config_path: str = None):
        """
        Initialize configuration manager
        
        Args:
            task_path: Task directory path
            workflow_config_path: Workflow configuration file path (optional)
        """
        self.task_path = task_path
        self.workflow_config_path = workflow_config_path
        
        # Resolve project root directory (same as _load_workflow_config does)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        
        # General config file paths (project level, relative to project root)
        self.MODELS_CONFIG_PATH = os.path.join(project_root, 'config', 'models_config.json')
        self.TOOLS_CONFIG_PATH = os.path.join(project_root, 'config', 'tools_config.json')
        
        # Load general config (model and tool definitions)
        self.models_config = self._load_json(self.MODELS_CONFIG_PATH)
        self.tools_config = self._load_json(self.TOOLS_CONFIG_PATH)
        
        # Load workflow config (if provided)
        self.workflow_config = self._load_workflow_config()
        
        # Initialize records
        self.workflow_config_used = self._init_workflow_config_used()
        self.file_records = self._load_file_records()
    
    def _load_json(self, filepath: str) -> Dict:
        """Load JSON file"""
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️  Failed to load {filepath}: {e}")
                return {}
        else:
            print(f"⚠️  Config file does not exist: {filepath}")
            return {}
    
    def _load_workflow_config(self) -> Dict:
        """
        Load workflow configuration with priority:
        1. If workflow_config_path is provided and exists, use it
        2. Else if task_path exists, try to load task_path/workflow_config.json
        3. Else use default template (ad_workflow_config_template.json)
        """
        # Priority 1: Use provided workflow_config_path if exists
        if self.workflow_config_path and os.path.exists(self.workflow_config_path):
            config = self._load_json(self.workflow_config_path)
            print(f"📋 Loaded workflow config: {self.workflow_config_path}")
            return config
        
        # Priority 2: Try to load from task_path if available
        if self.task_path:
            task_config_path = os.path.join(self.task_path, 'workflow_config.json')
            if os.path.exists(task_config_path):
                config = self._load_json(task_config_path)
                print(f"📋 Loaded workflow config from task directory: {task_config_path}")
                return config
        
        # Priority 3: Use default template
        if self.workflow_config_path:
            print(f"⚠️  Config file does not exist: {self.workflow_config_path}")
        default_template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'config', 'ad_workflow_config_template.json'
        )
        if os.path.exists(default_template_path):
            config = self._load_json(default_template_path)
            print(f"📋 Loaded default workflow config template: {default_template_path}")
            return config
        
        print(f"📝 No workflow config provided, using default parameters")
        return {}
    
    def _init_workflow_config_used(self) -> Dict:
        """Initialize configuration record for current run"""
        return {
            "description": "Complete configuration used for this workflow run",
            "task_path": self.task_path,
            "workflow_config_source": self.workflow_config_path or "Default config",
            "created_at": datetime.now().isoformat(),
            "nodes": {}
        }
    
    def _load_file_records(self) -> Dict:
        """Load file generation records"""
        records_file = os.path.join(self.task_path, 'file_generation_records.json')
        if os.path.exists(records_file):
            return self._load_json(records_file)
        return {
            "description": "File generation records - keyed by file path",
            "task_path": self.task_path,
            "created_at": datetime.now().isoformat(),
            "files": {}
        }
    
    def get_model_config(self, category: str, model_name: str) -> Dict:
        """
        Get model configuration (including input keys and parameter definitions)
        
        Args:
            category: Category (image_generation, video_generation, tts, bgm)
            model_name: Model name (may include version hash like "model_name:hash")
        
        Returns:
            Model configuration dictionary
        """
        models = self.models_config.get('models', {})
        category_models = models.get(category, {})
        
        # Handle model name with version hash (format: "model_name:hash")
        # Always extract base name first, as models_config.json typically stores base names
        model_base_name = model_name.split(':')[0] if ':' in model_name else model_name
        
        # Try to find model with base name first (most common case)
        model_def = category_models.get(model_base_name, {})
        
        # If not found with base name, try with full name (including version hash)
        # This handles cases where model is stored with version hash in config
        if not model_def:
            model_def = category_models.get(model_name, {})
            if model_def:
                print(f"📝 Using model config for {model_name} (with version hash)")
        
        # If found with base name, log it
        if model_def and model_base_name != model_name:
            print(f"📝 Using model config for {model_base_name} (version hash '{model_name.split(':', 1)[1]}' ignored)")
        
        if not model_def:
            print(f"⚠️  Model definition not found: {category}/{model_name} (tried base name: {model_base_name})")
            return {'input_keys': {}, 'parameters': {}}
        
        return model_def
    
    def get_tool_config(self, category: str, tool_name: str) -> Dict:
        """
        Get tool configuration
        
        Args:
            category: Tool category (video_editor, audio_processor, etc.)
            tool_name: Tool name
        
        Returns:
            Tool configuration dictionary
        """
        tools = self.tools_config.get('tools', {})
        category_tools = tools.get(category, {})
        tool_def = category_tools.get(tool_name, {})
        
        if not tool_def:
            print(f"⚠️  Tool definition not found: {category}/{tool_name}")
            return {'input_keys': {}, 'parameters': {}}
        
        return tool_def
    
    def get_node_params(self, node_type: str, model_or_tool: str, default_params: Dict = None) -> Dict:
        """
        Get node's runtime parameters (from workflow config or defaults)
        
        Args:
            node_type: Node type
            model_or_tool: Model or tool name
            default_params: Default parameters (should be values, not definitions)
        
        Returns:
            Parameter dictionary (merged) - all values are actual parameter values, not definitions
        """
        # Start from default parameters
        params = default_params.copy() if default_params else {}
        
        # Ensure default_params doesn't contain definition objects
        filtered_defaults = {}
        for k, v in params.items():
            if isinstance(v, dict) and 'type' in v:
                # It's a parameter definition, extract default value
                if 'default' in v:
                    filtered_defaults[k] = v['default']
            else:
                # It's already a value
                filtered_defaults[k] = v
        params = filtered_defaults
        
        # Get override parameters from workflow config
        if self.workflow_config:
            node_config = self.workflow_config.get(node_type, {})
            config_model_or_tool = node_config.get('model') or node_config.get('tool')
            if config_model_or_tool == model_or_tool:
                # Merge parameters, config file takes priority
                config_params = node_config.get('parameters', {})
                # Ensure config_params are values, not definitions
                filtered_config = {}
                for k, v in config_params.items():
                    if isinstance(v, dict) and 'type' in v:
                        # It's a parameter definition, extract default value
                        if 'default' in v:
                            filtered_config[k] = v['default']
                    else:
                        # It's already a value
                        filtered_config[k] = v
                params.update(filtered_config)
        
        return params
    
    def record_node_usage(self, node_name: str, model_or_tool: str, 
                          category: str, parameters: Dict):
        """
        Record model/tool and parameters used by node
        
        Args:
            node_name: Node name
            model_or_tool: Model or tool name used
            category: Category
            parameters: Actually used parameters
        """
        self.workflow_config_used['nodes'][node_name] = {
            'timestamp': datetime.now().isoformat(),
            'type': category,
            'model_or_tool': model_or_tool,
            'parameters': parameters
        }
    
    def record_file_generation(self, file_path: str, node_name: str,
                               model_or_tool: str, inputs: Dict, 
                               parameters: Dict, metadata: Dict = None):
        """
        Record file generation information
        
        Args:
            file_path: Generated file path
            node_name: Name of node that generated this file
            model_or_tool: Model or tool used
            inputs: Input data
            parameters: Parameters used
            metadata: Metadata (generation time, success status, etc.)
        """
        self.file_records['files'][file_path] = {
            'node': node_name,
            'model_or_tool': model_or_tool,
            'timestamp': datetime.now().isoformat(),
            'inputs': inputs,
            'parameters': parameters,
            'metadata': metadata or {}
        }
    
    def save_records(self):
        """Save all records to file"""
        os.makedirs(self.task_path, exist_ok=True)
        
        # Save workflow_config_used.json
        config_used_file = os.path.join(self.task_path, 'workflow_config_used.json')
        with open(config_used_file, 'w', encoding='utf-8') as f:
            json.dump(self.workflow_config_used, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved run config: {os.path.basename(config_used_file)}")
        
        # Save file_generation_records.json
        file_records_file = os.path.join(self.task_path, 'file_generation_records.json')
        with open(file_records_file, 'w', encoding='utf-8') as f:
            json.dump(self.file_records, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved file records: {os.path.basename(file_records_file)}")
    
    def get_file_generation_info(self, file_path: str) -> Optional[Dict]:
        """
        Query generation information for a file
        
        Args:
            file_path: File path
        
        Returns:
            Generation information dictionary, None if not found
        """
        return self.file_records['files'].get(file_path)
    
    def list_all_files(self) -> List[str]:
        """List all recorded file paths"""
        return list(self.file_records['files'].keys())
    
    def export_summary(self) -> Dict:
        """Export summary information"""
        return {
            'task_path': self.task_path,
            'workflow_config_source': self.workflow_config_path or 'Default config',
            'total_nodes': len(self.workflow_config_used['nodes']),
            'total_files': len(self.file_records['files']),
            'nodes': list(self.workflow_config_used['nodes'].keys()),
            'files': list(self.file_records['files'].keys())
        }

    # ===================== New: Node params assembly =====================
    def _detect_node_category_and_name(self, node_name: str, node_instance) -> Optional[Dict[str, str]]:
        """Infer category and model/tool name using class inheritance instead of name heuristics."""
        try:
            if node_instance is None:
                return None
            # Prefer robust isinstance checks
            if ImageNode and isinstance(node_instance, ImageNode):
                return {
                    'type': 'model',
                    'category': 'image_generation',
                    'name': getattr(node_instance, 'default_model', None)
                }
            if VideoNode and isinstance(node_instance, VideoNode):
                return {
                    'type': 'model',
                    'category': 'video_generation',
                    'name': getattr(node_instance, 'default_model', None)
                }
            if VoiceoverNode and isinstance(node_instance, VoiceoverNode):
                return {
                    'type': 'model',
                    'category': 'tts',
                    'name': getattr(node_instance, 'default_model', None)
                }
            if SegmentedVoiceoverNode and isinstance(node_instance, SegmentedVoiceoverNode):
                return {
                    'type': 'model',
                    'category': 'tts',
                    'name': getattr(node_instance, 'default_model', None)
                }
            if BGMNode and isinstance(node_instance, BGMNode):
                return {
                    'type': 'model',
                    'category': 'bgm',
                    'name': getattr(node_instance, 'default_model', None)
                }
            if VideoEditNode and isinstance(node_instance, VideoEditNode):
                return {
                    'type': 'tool',
                    'category': 'video_editor',
                    'name': 'VideoEditNode'
                }
        except Exception:
            return None
        return None

    def generate_node_parameter_map(self, node_instances: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Generate runtime parameter map for all workflow nodes from models_config/tools_config
        and optional workflow_config overrides.
        
        Returns: { node_name: { 'kind': 'model'|'tool', 'category': str, 'name': str, 'parameters': dict } }
        """
        result: Dict[str, Dict[str, Any]] = {}
        if not isinstance(node_instances, dict):
            return result
        
        for node_name, node_instance in node_instances.items():
            meta = self._detect_node_category_and_name(node_name, node_instance)
            if not meta or not meta.get('category'):
                continue
            kind = meta['type']
            category = meta['category']
            name = meta['name']
            params: Dict[str, Any] = {}
            
            # Prefer node-declared schema when available
            declared_schema = {}
            if hasattr(node_instance, 'get_parameter_schema'):
                try:
                    declared_schema = node_instance.get_parameter_schema() or {}
                except Exception:
                    declared_schema = {}
            if declared_schema:
                # Flatten schema to defaults for runtime unless full schema desired
                params = {}
                for k, v in declared_schema.items():
                    params[k] = v.get('default') if isinstance(v, dict) else v
            
            if kind == 'model' and name and not params:
                model_def = self.get_model_config(category, name)
                parameters_def = model_def.get('parameters', {})
                # Extract default values from parameter definitions
                params = {}
                for param_name, param_def in parameters_def.items():
                    if isinstance(param_def, dict) and 'default' in param_def:
                        params[param_name] = param_def['default']
                    elif not isinstance(param_def, dict):
                        params[param_name] = param_def
                # Apply workflow overrides if any
                params = self.get_node_params(node_type=node_name, model_or_tool=name, default_params=params)
            elif kind == 'tool':
                # Tool nodes may declare their own schema; otherwise read from tools_config
                if not params:
                    tool_def = self.get_tool_config(category, meta['name'])
                    params = (tool_def.get('parameters') or {}).copy()
                params = self.get_node_params(node_type=node_name, model_or_tool=meta['name'], default_params=params)
            else:
                params = {}
            
            result[node_name] = {
                'kind': kind,
                'category': category,
                'name': name,
                'parameters': params
            }
        return result
    
    def save_node_parameter_map(self, node_param_map: Dict[str, Dict[str, Any]]):
        """Persist node parameter map for inspection/debugging."""
        try:
            out_path = os.path.join(self.task_path, 'node_runtime_params.json')
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(node_param_map, f, indent=2, ensure_ascii=False)
            print(f"💾 Saved node runtime parameters: {out_path}")
        except Exception as e:
            print(f"⚠️  Failed to save node params: {e}")
    
    def convert_input_keys_to_model_format(self, category: str, model_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert unified input keys to model-specific format
        
        Args:
            category: Category (image_generation, video_generation, tts, bgm)
            model_name: Model name
            inputs: Input dict with unified keys (prompt, reference_image, first_frame, last_frame, text, etc.)
        
        Returns:
            Dict with model-specific keys based on models_config.json input_keys mapping
        """
        return inputs


if __name__ == '__main__':
    # Test configuration manager
    print("\n🧪 Test ConfigManager")
    print("=" * 70)
    
    test_task = 'test_task'
    os.makedirs(test_task, exist_ok=True)
    
    # Initialize (no workflow config provided)
    manager = ConfigManager(test_task)
    
    # Get model configuration
    print("\n📸 Get image generation model config:")
    img_model_config = manager.get_model_config('image_generation', 'google/nano-banana')
    print(f"   Input keys: {list(img_model_config.get('input_keys', {}).keys())}")
    print(f"   Parameters: {list(img_model_config.get('parameters', {}).keys())}")
    
    # Get tool configuration
    print("\n🎬 Get video editing tool config:")
    video_tool_config = manager.get_tool_config('video_editor', 'VideoEditNode')
    print(f"   Input keys: {list(video_tool_config.get('input_keys', {}).keys())}")
    print(f"   Parameters: {list(video_tool_config.get('parameters', {}).keys())}")
    
    # Cleanup
    import shutil
    if os.path.exists(test_task):
        shutil.rmtree(test_task)
    
    print("\n✅ Test complete")
