# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

# refactored_architecture/1_infrastructure/nodes/image_node.py
import os
import sys
from modules.nodes.base_node import BaseNode, GenModelNode

sys.path.append(os.path.join(os.path.dirname(__file__), '../../../modules'))
from modules.tools.image_gen import generate_image
from modules.tools.utils import filter_description

class ImageNode(GenModelNode):
    """Image generation node"""

    def __init__(self, name: str, task_path: str):
        super().__init__(name, task_path)
        self.default_model = 'google/nano-banana-pro'
        self.preprocessing_func = None
        self.postprocessing_func = None
    
    def get_category(self) -> str:
        return "image_generation"

    def configure(self, default_model=None, preprocessing=None, postprocessing=None):
        if default_model:
            self.default_model = default_model
        if preprocessing:
            self.preprocessing_func = preprocessing
        if postprocessing:
            self.postprocessing_func = postprocessing

    def run(self, inputs: dict):
        """
        Standard run method following the unified fine-grained execution architecture
        
        Architecture pattern:
        1. Preprocessing
        2. Scan for dirty elements using BaseNode.scan_dirty_elements()
        3. If dirty elements exist: incremental execution
        4. Else: full execution
        5. Clean dirty flags using BaseNode.clean_dirty_flags()
        6. Postprocessing
        """
        # Step 1: Preprocessing
        if self.preprocessing_func:
            inputs = self.preprocessing_func(inputs)
        
        if 'image_descriptions' in inputs:
            image_descriptions = inputs['image_descriptions']
        elif 'storyboard' in inputs and inputs['storyboard'] is not None:
            image_descriptions = self._convert_storyboard_to_descriptions(inputs['storyboard'])
        else:
            raise ValueError("ImageNode requires 'storyboard' or 'image_descriptions' in inputs")

        reference_image = inputs.get('reference_image_path')
        product_features = self._extract_product_features(inputs.get('reference_image_descriptions'))
        
        # Step 2: Scan for dirty elements (using BaseNode helper)
        storyboard = inputs.get('storyboard', [])
        dirty_frames = self.scan_dirty_elements(storyboard)
        
        # Step 3: Decide execution path
        if dirty_frames and not self._force_execute:
            # ✅ Incremental execution - only process dirty frames
            result = self._incremental_execution(
                dirty_frames, storyboard, inputs.get('generated_images', []),
                image_descriptions, reference_image, product_features
            )
        else:
            # ✅ Full execution - process all frames
            result = self._full_execution(
                image_descriptions, reference_image, product_features
            )
        
        # Step 4: Postprocessing
        if self.postprocessing_func:
            result = self.postprocessing_func(result)
        
        return result
    
    def _incremental_execution(self, dirty_frames: dict, storyboard: list, 
                               existing_images: list, image_descriptions: list,
                               reference_image, product_features) -> dict:
        """
        Incremental execution: only regenerate dirty frames
        
        This is the fine-grained execution path following the unified architecture
        """
        print(f"🎯 [ImageNode] Incremental execution: processing {len(dirty_frames)} frame(s)")
        print(f"   Dirty frames: {list(dirty_frames.keys())}")
        
        # Start with existing results
        generated_images = existing_images.copy() if existing_images else [None] * len(image_descriptions)
        
        # Only process dirty frames
        for idx, dirty_fields in dirty_frames.items():
            if idx < len(image_descriptions):
                print(f"   🔄 Processing frame {idx}, dirty fields: {dirty_fields}")
                
                # Determine which parts need regeneration based on dirty fields
                need_first = 'first_image_description' in dirty_fields
                need_last = 'last_image_description' in dirty_fields
                
                # Generate only what's needed
                image_pair = self._generate_image_pair(
                    image_descriptions[idx], idx, reference_image, product_features,
                    force_regenerate_first=need_first,
                    force_regenerate_last=need_last
                )
                
                # Update at specific index
                if idx < len(generated_images):
                    generated_images[idx] = image_pair
                else:
                    # Extend list if needed
                    while len(generated_images) <= idx:
                        generated_images.append(None)
                    generated_images[idx] = image_pair
                
                # Update data version for this frame
                if image_pair:
                    first_path, last_path = image_pair
                    # Currently DVM tracks 'image' as a single asset. 
                    # Since video gen usually uses first/last or just one, we track the first generated one or handle logic?
                    # Original logic tracked 'sub_video_{i}/image' -> path.
                    # ImageNode generates a pair [first, last]. 
                    # Usually video gen uses first_frame and last_frame.
                    # Let's stick to tracking 'image' as the first_frame for now as it's the primary visual,
                    # OR if DVM structure is strictly one file per key, we might need 'image_first', 'image_last'?
                    # The user's DVM structure showed "image": {...}.
                    # Assuming 'image' refers to the primary image asset. 
                    # Let's update with first_path if available.
                    if first_path:
                        self.update_data_version([f'sub_video_{idx}', 'image_first'], first_path)
                    if last_path:
                        self.update_data_version([f'sub_video_{idx}', 'image_last'], last_path)
                
                print(f"   ✅ Updated generated_images[{idx}]")
        
        # Clean dirty flags using BaseNode helper
        cleaned_storyboard = self.clean_dirty_flags(storyboard)
        
        return {
            'generated_images': generated_images,
            'storyboard': cleaned_storyboard
        }
    
    def _full_execution(self, image_descriptions: list, reference_image, product_features) -> dict:
        """
        Full execution: regenerate all frames
        
        This is the standard execution path when no dirty frames exist or force_execute is True
        """
        if self._force_execute:
            print(f"🔄 [ImageNode] Full regeneration (force_execute=True)")
        else:
            print(f"🔄 [ImageNode] Full regeneration (no dirty frames)")
        
        generated_images = []
        for idx, desc in enumerate(image_descriptions):
            image_pair = self._generate_image_pair(desc, idx, reference_image, product_features)
            generated_images.append(image_pair)
            
            # Update data version
            if image_pair:
                first_path, last_path = image_pair
                if first_path:
                    self.update_data_version([f'sub_video_{idx}', 'image_first'], first_path)
                if last_path:
                    self.update_data_version([f'sub_video_{idx}', 'image_last'], last_path)
        
        return {'generated_images': generated_images}
    
    def get_output_fields(self) -> list:
        """Declare node output fields (field names in state)"""
        return ['generated_images']

    def _extract_product_features(self, reference_descriptions):
        """Extract detailed product features from reference image analysis"""
        if not reference_descriptions or not isinstance(reference_descriptions, list) or len(reference_descriptions) == 0:
            return None
        
        # Combine features from all reference images (usually just one product image)
        features = []
        for desc in reference_descriptions:
            if isinstance(desc, dict):
                # Build comprehensive product feature string
                feature_parts = []
                
                # Core identifying features
                if desc.get('product_category'):
                    feature_parts.append(f"Product type: {desc['product_category']}")
                if desc.get('brand_info'):
                    feature_parts.append(f"Brand: {desc['brand_info']}")
                
                # Critical visual features
                if desc.get('shape_structure'):
                    feature_parts.append(f"Shape: {desc['shape_structure']}")
                if desc.get('color_scheme'):
                    feature_parts.append(f"Colors: {desc['color_scheme']}")
                if desc.get('material_texture'):
                    feature_parts.append(f"Material: {desc['material_texture']}")
                if desc.get('distinctive_features'):
                    feature_parts.append(f"Key features: {desc['distinctive_features']}")
                if desc.get('size_proportion'):
                    feature_parts.append(f"Proportions: {desc['size_proportion']}")
                
                if feature_parts:
                    features.append(" | ".join(feature_parts))
        
        if not features:
            return None
        
        # Combine all product features into consistency instruction
        combined = " AND ".join(features)
        return f"[CRITICAL: Product must match these exact specifications - {combined}]"
    
    def _convert_storyboard_to_descriptions(self, storyboard):
        descriptions = []
        for idx, board in enumerate(storyboard):
            if hasattr(board, 'first_image_description'):
                first_desc = board.first_image_description
                last_desc = board.last_image_description
                # Create dict representation for overrides if it's an object
                overrides = board.__dict__ if hasattr(board, '__dict__') else {}
            else:
                first_desc = board.get('first_image_description', '')
                last_desc = board.get('last_image_description', '')
                overrides = board  # It's already a dict
            
            # Create sub-video directory
            sub_video_dir = os.path.join(self.task_path, f'sub_video_{idx}')
            os.makedirs(sub_video_dir, exist_ok=True)
            
            descriptions.append({
                'first_image': {
                    'prompt': first_desc,
                    'output_path': os.path.join(sub_video_dir, 'image_first.png')
                },
                'last_image': {
                    'prompt': last_desc,
                    'output_path': os.path.join(sub_video_dir, 'image_last.png')
                },
                'overrides': overrides  # Pass full item for parameter overrides
            })
        return descriptions

    def _generate_image_pair(self, desc, idx, reference_image, product_features=None, force_regenerate_first=False, force_regenerate_last=False):
        """
        Generate a pair of images (first and last frame)
        
        Args:
            desc: Image description dict
            idx: Image index
            reference_image: Reference image path
            product_features: Product feature constraints
            force_regenerate_first: If True, force regeneration of first frame (for fine-grained execution)
            force_regenerate_last: If True, force regeneration of last frame (for fine-grained execution)
        """
        os.makedirs(os.path.dirname(desc['first_image']['output_path']), exist_ok=True)
        def _latest_existing_path(intended_path: str) -> str:
            """
            Return latest existing versioned path if any, otherwise fall back to intended_path.
            - If image_first_vN.png exists, return max N.
            - Else if intended_path exists (legacy non-versioned), return it.
            - Else return intended_path (non-existent; caller will generate).
            """
            dirname = os.path.dirname(intended_path)
            basename = os.path.basename(intended_path)
            name, ext = os.path.splitext(basename)

            if dirname and os.path.exists(dirname):
                max_v = 0
                for f in os.listdir(dirname):
                    if not (f.startswith(f"{name}_v") and f.endswith(ext)):
                        continue
                    v_str = f[len(name) + 2: -len(ext)]
                    if v_str.isdigit():
                        max_v = max(max_v, int(v_str))
                if max_v > 0:
                    return os.path.abspath(os.path.join(dirname, f"{name}_v{max_v}{ext}"))

            if os.path.exists(intended_path):
                return os.path.abspath(intended_path)
            return os.path.abspath(intended_path)

        current_first_path = _latest_existing_path(desc['first_image']['output_path'])
        current_last_path = _latest_existing_path(desc['last_image']['output_path'])

        if force_regenerate_first or not os.path.exists(current_first_path):
            first_path = self.prepare_output_path(desc['first_image']['output_path'])
        else:
            first_path = current_first_path

        if force_regenerate_last or not os.path.exists(current_last_path):
            last_path = self.prepare_output_path(desc['last_image']['output_path'])
        else:
            last_path = current_last_path
        # -------------------------------------------------------

        # Get overrides from storyboard item
        overrides = {}
        raw_overrides = desc.get('overrides', {})
        
        # Define known business fields to exclude from model parameters
        # Exclude fields that are part of storyboard structure but not image generation model parameters
        exclude_fields = {
            'frame_id', 'scene_type', 'duration', 'first_image_description', 
            'last_image_description', 'video_description', 'camera_movement', 
            'text_overlay', 'transition', 'id', 'index',
            'first_image', 'last_image' # These are structural
        }
        
        overrides = {k: v for k, v in raw_overrides.items() if k not in exclude_fields}
        
        # Generate first image - use base class method to determine if cache should be used
        should_generate_first = not self.should_use_cache(first_path, force_regenerate=force_regenerate_first) and desc['first_image']['prompt']
        
        if should_generate_first:
            self.log_cache_status(first_path, False)
            print(f"🖼️  [Image Generation] Generating first frame {idx+1}...")
            
            # Enhance prompt with product features for consistency
            first_prompt = desc['first_image']['prompt']
            if product_features:
                first_prompt = f"{first_prompt}\n\n{product_features}"
                print(f"🎯 [Image Generation] Added product consistency constraints")
            
            # Get effective model parameters (Global Defaults -> Metadata -> Overrides)
            model_params = self.get_model_parameters(asset_path=first_path, overrides=overrides)
            
            # Prepare inputs for key conversion
            api_inputs = {
                'prompt': filter_description(first_prompt),
                'reference_image': reference_image
            }
            
            # Use the effective model for key conversion if available in params
            current_model = model_params.get('model', self.default_model)
            
            # Convert unified keys to model-specific format
            # Note: We use config_manager directly to specify the correct model
            converted_inputs = api_inputs
            if self.config_manager:
                converted_inputs = self.config_manager.convert_input_keys_to_model_format(
                    self.get_category(), current_model, api_inputs
                )
            
            # Merge converted inputs with model params (converted keys override)
            # Filter out any parameter definition objects - only keep actual values
            filtered_model_params = {}
            for k, v in model_params.items():
                # Skip if it's a parameter definition dict (has 'type' key)
                if isinstance(v, dict) and 'type' in v:
                    # Extract default value if available
                    if 'default' in v:
                        filtered_model_params[k] = v['default']
                    # Otherwise skip this parameter
                else:
                    # It's already a value, use it directly
                    filtered_model_params[k] = v
            
            api_kwargs = {**filtered_model_params, **converted_inputs}
            
            # Extract prompt for function parameter
            prompt = api_kwargs.pop('prompt', filter_description(first_prompt))
            
            # Always pass reference_image explicit parameter (Component Responsibility: Pass what you have)
            ref_image = reference_image
            
            # Remove generic reference_image from kwargs to avoid confusion/duplication at tool layer
            if 'reference_image' in api_kwargs:
                api_kwargs.pop('reference_image')
            
            # Save config BEFORE generation so it exists even if generation fails
            metadata_to_save = {
                'model': current_model,
                'prompt': prompt,
                'original_prompt': desc['first_image']['prompt'],
                **api_kwargs
            }
            self.save_asset_metadata(first_path, metadata_to_save)
            
            param_dict = {'prompt': prompt, 'file_path': first_path, 'ref_image_path': ref_image, 'model': current_model, **api_kwargs}
            result_path = generate_image(
                **param_dict
            )
            # If generation failed, keep the intended path for error handling
            if result_path is None:
                print(f"❌ [Image Generation] First frame {idx+1} generation failed")
                first_path = None
            else:
                first_path = result_path
                
        elif os.path.exists(first_path):
            self.log_cache_status(first_path, True)
        else:
            print(f"⚠️  [Image Generation] No prompt for first frame {idx+1}")
            first_path = None

        # Generate last image
        should_generate_last = not self.should_use_cache(last_path, force_regenerate=force_regenerate_last) and desc['last_image']['prompt']
        
        if should_generate_last:
            print(f"🖼️  [Image Generation] Generating last frame {idx+1}...")
            # Build enhanced prompt to explicitly continue after the reference first frame
            last_prompt_raw = desc['last_image']['prompt']
            
            # Add product features for consistency
            if product_features:
                last_prompt_raw = f"{last_prompt_raw}\n\n{product_features}"
                print(f"🎯 [Image Generation] Added product consistency constraints")
            
            # Build reference images for last frame: ONLY use product reference images (no first frame)
            # This allows last frame to have different composition/angle while maintaining product consistency
            combined_reference = None
            if reference_image is not None:
                # Product reference image ONLY - no first frame to avoid copying composition
                if isinstance(reference_image, list):
                    combined_reference = list(reference_image)  # Copy list
                elif isinstance(reference_image, str):
                    combined_reference = [reference_image]
                else:
                    combined_reference = []
                print(f"🖼️  [Image Generation] Using only product ref image(s) for last frame {idx+1} (no first frame to allow variation)")
            else:
                # No product reference available, generate without reference
                combined_reference = None
                print(f"🖼️  [Image Generation] No reference images for last frame {idx+1}")

            # Get effective model parameters (Global Defaults -> Metadata -> Overrides)
            model_params = self.get_model_parameters(asset_path=last_path, overrides=overrides)
            
            # Prepare inputs for key conversion
            api_inputs = {
                'prompt': filter_description(last_prompt_raw),
                'reference_image': combined_reference
            }
            
            # Use the effective model for key conversion if available in params
            current_model = model_params.get('model', self.default_model)
            
            # Convert unified keys to model-specific format
            converted_inputs = api_inputs
            if self.config_manager:
                converted_inputs = self.config_manager.convert_input_keys_to_model_format(
                    self.get_category(), current_model, api_inputs
                )
            
            # Merge converted inputs with model params (converted keys override)
            filtered_model_params = {}
            for k, v in model_params.items():
                if isinstance(v, dict) and 'type' in v:
                    if 'default' in v:
                        filtered_model_params[k] = v['default']
                else:
                    filtered_model_params[k] = v
            
            api_kwargs = {**filtered_model_params, **converted_inputs}
            
            # Extract prompt for function parameter
            prompt = api_kwargs.pop('prompt', filter_description(last_prompt_raw))
            
            # Always pass reference_image explicit parameter
            ref_image = combined_reference
            
            # Remove generic reference_image from kwargs to avoid confusion/duplication
            if 'reference_image' in api_kwargs:
                api_kwargs.pop('reference_image')
            
            # Save config BEFORE generation so it exists even if generation fails
            metadata_to_save = {
                'model': current_model,
                'prompt': prompt,
                'original_prompt': desc['last_image']['prompt'],
                **api_kwargs
            }
            self.save_asset_metadata(last_path, metadata_to_save)
            
            param_dict = {'prompt': prompt, 'file_path': last_path, 'ref_image_path': ref_image, 'model': current_model, **api_kwargs}
            result_path = generate_image(**param_dict)
            # If generation failed, keep the intended path for error handling
            if result_path is None:
                print(f"❌ [Image Generation] Last frame {idx+1} generation failed")
                last_path = None
            else:
                last_path = result_path
        elif os.path.exists(last_path):
            print(f"🖼️  [Image Generation] Last frame {idx+1} already exists...")
        else:
            print(f"⚠️  [Image Generation] No prompt for last frame {idx+1}")
            last_path = None
            
        # Return whatever we have - None values will show as placeholders in frontend
        # Do NOT substitute one image for another - it's misleading
        if first_path is None:
            print(f"⚠️  [Image Generation] First frame {idx+1} not available (will show placeholder)")
        if last_path is None:
            print(f"⚠️  [Image Generation] Last frame {idx+1} not available (will show placeholder)")

        return [first_path, last_path]