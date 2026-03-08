# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

# refactored_architecture/1_infrastructure/nodes/chat_node.py
from .base_node import BaseNode
import sys
import os

# Add existing modules path to reuse LLM client
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../modules'))
from modules.tools.utils import get_llm_client

class ChatNode(BaseNode):

    def __init__(self, name: str, task_path: str):
        super().__init__(name, task_path)
        self.chat_model = get_llm_client()
        self.prompt_template = None
        self.output_structure = None
        self.enable_cache = True

    def __call__(self, inputs: dict) -> dict:
        print(f"🔄 [{self.name}] Starting...")

        # Extract and store execution options (handled by base class)
        self._force_execute = inputs.get('_force_execute', False)
        self._create_new_version = inputs.get('_create_new_version', False)

        # Determine cache filename and prepare path
        cache_filename = f'{self.name}.json'
        cache_path = os.path.join(self.task_path, cache_filename)
        actual_cache_path = self.prepare_output_path(cache_path)  # Use base class method to handle versioning

        # Try to load cache using unified method
        if self.enable_cache and self.should_use_cache(actual_cache_path):
            cached_data = self.load_json(os.path.basename(actual_cache_path))
            if cached_data:
                self.log_cache_status(actual_cache_path, True)  # Unified logging
                return {**inputs, self.name: cached_data}

        # Execute node
        self.log_cache_status(actual_cache_path, False)  # Unified logging
        
        try:
            result = self.run(inputs)
            
            # Save result to cache
            if self.enable_cache:
                self.save_json(os.path.basename(actual_cache_path), result)
            
            print(f"✅ [{self.name}] Completed.")
            return {**inputs, self.name: result}
        except Exception as e:
            print(f"❌ [{self.name}] Failed: {str(e)}")
            raise

    def configure(self, prompt_template=None, output_structure=None, enable_cache=True):
        if prompt_template:
            self.prompt_template = prompt_template
        if output_structure:
            self.output_structure = output_structure
        self.enable_cache = enable_cache

    def run(self, inputs: dict):
        if not self.prompt_template:
            raise ValueError(f"ChatNode {self.name} requires prompt_template configuration")
        
        if self.output_structure:
            result = (self.prompt_template | self.chat_model.with_structured_output(self.output_structure)).invoke(inputs)
            return result.model_dump() if hasattr(result, 'model_dump') else result
        else:
            result = self.chat_model.invoke(self.prompt_template.format_messages(**inputs))
            return result.content 