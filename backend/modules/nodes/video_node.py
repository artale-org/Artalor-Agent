# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

# refactored_architecture/1_infrastructure/nodes/video_node.py
import os
import sys
from .base_node import BaseNode, GenModelNode

sys.path.append(os.path.join(os.path.dirname(__file__), '../../../modules'))
from modules.tools.video_gen import generate_video
from modules.tools.utils import filter_description

class VideoNode(GenModelNode):
    """Video generation node"""
    
    def __init__(self, name: str, task_path: str):
        super().__init__(name, task_path)
        self.default_model = 'wavespeedai/wan-2.1-i2v-480p'
        self.preprocessing_func = None
        self.postprocessing_func = None
    
    def get_category(self) -> str:
        return "video_generation"

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
        
        Architecture pattern (same as ImageNode):
        1. Preprocessing
        2. Scan for dirty elements using BaseNode.scan_dirty_elements()
        3. If dirty elements exist: incremental execution (only dirty videos)
        4. Else: full execution (all videos)
        5. Clean dirty flags using BaseNode.clean_dirty_flags()
        6. Postprocessing
        """
        if self.preprocessing_func:
            inputs = self.preprocessing_func(inputs)

        if 'images' in inputs:
            image_pairs = inputs['images']
        elif 'generated_images' in inputs:
            image_pairs = inputs['generated_images']
        else:
            raise ValueError("VideoNode requires 'images' or 'generated_images' in inputs")

        if 'storyboard' in inputs:
            storyboard = inputs['storyboard']
        elif 'video_descriptions' in inputs:
            storyboard = [{'video_description': desc} for desc in inputs['video_descriptions']]
        else:
            raise ValueError("VideoNode requires 'storyboard' or 'video_descriptions' in inputs")

        # Step 2: Scan for dirty elements (using BaseNode helper)
        dirty_frames = self.scan_dirty_elements(storyboard)

        # Step 3: Decide execution path
        if dirty_frames and not self._force_execute:
            # Incremental execution - only process dirty videos
            result = self._incremental_execution(
                dirty_frames, storyboard, image_pairs
            )
        else:
            # Full execution - process all videos
            result = self._full_execution(storyboard, image_pairs)
        
        if self.postprocessing_func:
            result = self.postprocessing_func(result)
            
        return result
    
    def _incremental_execution(self, dirty_frames: dict, storyboard: list,
                               image_pairs: list) -> dict:
        """
        Incremental execution: only regenerate dirty videos
        
        This is the fine-grained execution path following the unified architecture
        (same pattern as ImageNode._incremental_execution)
        """
        print(f"🎯 [VideoNode] Incremental execution: processing {len(dirty_frames)} video(s)")
        print(f"   Dirty frames: {list(dirty_frames.keys())}")
        
        generated_videos = []
        
        for idx, (image_pair, board_item) in enumerate(zip(image_pairs, storyboard)):
            if idx in dirty_frames:
                # Dirty video - regenerate with new version
                print(f"   🔄 Regenerating video {idx}, dirty fields: {dirty_frames[idx]}")
                # Clean dirty metadata from board_item before passing to generation
                clean_item = {k: v for k, v in board_item.items() 
                             if not k.startswith('_dirty')} if isinstance(board_item, dict) else board_item
                video_path = self._generate_video(image_pair, clean_item, idx)
                generated_videos.append(video_path)
            else:
                # Not dirty - find and return existing cached video
                video_path = self._get_existing_video(idx)
                if video_path:
                    print(f"   📄 Using cached video {idx}: {os.path.basename(video_path)}")
                else:
                    # Cached video missing, need to generate
                    print(f"   ⚠️ Cached video {idx} missing, regenerating...")
                    clean_item = {k: v for k, v in board_item.items() 
                                 if not k.startswith('_dirty')} if isinstance(board_item, dict) else board_item
                    video_path = self._generate_video(image_pair, clean_item, idx)
                generated_videos.append(video_path)
        
        # Clean dirty flags using BaseNode helper
        cleaned_storyboard = self.clean_dirty_flags(storyboard)
        
        return {
            'generated_videos': generated_videos,
            'storyboard': cleaned_storyboard
        }
    
    def _full_execution(self, storyboard: list, image_pairs: list) -> dict:
        """
        Full execution: generate all videos
        
        This is the standard execution path when no dirty frames exist or force_execute is True
        """
        if self._force_execute:
            print(f"🔄 [VideoNode] Full regeneration (force_execute=True)")
        else:
            print(f"🔄 [VideoNode] Full regeneration (no dirty frames)")
        
        generated_videos = []
        for idx, (image_pair, board_item) in enumerate(zip(image_pairs, storyboard)):
            video_path = self._generate_video(image_pair, board_item, idx)
            generated_videos.append(video_path)
        
        return {'generated_videos': generated_videos}
    
    def _get_existing_video(self, idx: int):
        """
        Get the latest existing versioned video file path for a given segment index.
        Returns None if no video file exists.
        """
        sub_video_dir = os.path.join(self.task_path, f'sub_video_{idx}')
        if not os.path.exists(sub_video_dir):
            return None
        
        name = 'video'
        ext = '.mp4'
        
        # Look for versioned files: video_v1.mp4, video_v2.mp4, ...
        max_v = 0
        for f in os.listdir(sub_video_dir):
            if f.startswith(f"{name}_v") and f.endswith(ext):
                v_str = f[len(name) + 2: -len(ext)]
                if v_str.isdigit():
                    max_v = max(max_v, int(v_str))
        
        if max_v > 0:
            return os.path.abspath(os.path.join(sub_video_dir, f"{name}_v{max_v}{ext}"))
        
        # Fallback: check non-versioned file
        plain_path = os.path.join(sub_video_dir, f"{name}{ext}")
        if os.path.exists(plain_path):
            return os.path.abspath(plain_path)
        
        return None
    
    def get_output_fields(self) -> list:
        """Declare node output fields (field names in state)"""
        return ['generated_videos']

    def _generate_video(self, image_pair, board_item, idx):
        # Handle potential single image or pair
        if isinstance(image_pair, list) and len(image_pair) == 2:
            first_image, last_image = image_pair
        elif isinstance(image_pair, str):
            first_image = image_pair
            last_image = None
        elif isinstance(image_pair, list) and len(image_pair) == 1:
            first_image = image_pair[0]
            last_image = None
        else:
            # Handle None or empty list gracefully
            first_image = None
            last_image = None
            print(f"⚠️ [Video Generation] Warning: image_pair for idx {idx} is not a standard pair: {image_pair}")
        
        # Create sub-video directory
        sub_video_dir = os.path.join(self.task_path, f'sub_video_{idx}')
        os.makedirs(sub_video_dir, exist_ok=True)
        
        intended_path = os.path.join(sub_video_dir, 'video.mp4')
        video_path = self.prepare_output_path(intended_path)
        # os.makedirs(os.path.dirname(video_path), exist_ok=True) # Already created above

        # Check if we have valid images
        if first_image is None and last_image is None:
            print(f"❌ [Video Generation] No valid images for video {idx+1}, skipping...")
            return None

        # Check if should use cached video
        if self.should_use_cache(video_path):
            self.log_cache_status(video_path, True)
            return video_path
        
        self.log_cache_status(video_path, False)
        print(f"🎬 [Video Generation] Generating video {idx+1}...")
        
        # Get video description and overrides
        overrides = {}
        # Define known business fields to exclude from model parameters
        # duration is excluded because it's a string (e.g. "5s") in storyboard but models expect int/float if they support it
        exclude_fields = {
            'frame_id', 'scene_type', 'duration', 'first_image_description', 
            'last_image_description', 'video_description', 'camera_movement', 
            'text_overlay', 'transition', 'id', 'index'
        }
        
        if hasattr(board_item, 'video_description'):
            video_desc = board_item.video_description
            raw_overrides = board_item.__dict__ if hasattr(board_item, '__dict__') else {}
        else:
            video_desc = board_item.get('video_description', '')
            raw_overrides = board_item if isinstance(board_item, dict) else {}
            
        # Filter overrides
        overrides = {k: v for k, v in raw_overrides.items() if k not in exclude_fields}
        
        # Get last image description to guide video generation toward consistent end state
        # if hasattr(board_item, 'last_image_description'):
        #     last_img_desc = board_item.last_image_description
        # else:
        #     last_img_desc = board_item.get('last_image_description', '')
        
        # Enhance video prompt with target end state for consistency
        # if last_img_desc:
        #     enhanced_video_desc = (
        #         f"{video_desc}\n\n"
        #         f"TARGET END STATE (video's final frame should match this): {last_img_desc}"
        #     )
        #     print(f"🎯 [Video Generation] Enhanced with target end state for consistency")
        # else:
        enhanced_video_desc = video_desc

        # Ensure we have at least one valid image
        valid_first_image = first_image if first_image and os.path.exists(first_image) else None
        valid_last_image = last_image if last_image and os.path.exists(last_image) else None
        
        if valid_first_image is None and valid_last_image is None:
            print(f"❌ [Video Generation] No valid image files for video {idx+1}")
            return None
        
        # Fill missing image with the available one
        if valid_first_image is None and valid_last_image is not None:
            print(f"⚠️  [Video Generation] Video {idx+1}: first_frame missing, using last_frame as fallback")
            valid_first_image = valid_last_image
        elif valid_last_image is None and valid_first_image is not None:
            print(f"⚠️  [Video Generation] Video {idx+1}: last_frame missing, using first_frame as fallback")
            valid_last_image = valid_first_image

        try:
            # Get effective model parameters (Global Defaults -> Metadata -> Overrides)
            model_params = self.get_model_parameters(asset_path=video_path, overrides=overrides)
            
            # Prepare inputs for key conversion
            api_inputs = {
                'prompt': filter_description(enhanced_video_desc),
                'first_frame': valid_first_image,
                'last_frame': valid_last_image
            }
            
            # Use the effective model for key conversion if available in params
            current_model = model_params.get('model', self.default_model)
            model_config = self.config_manager.get_model_config(self.get_category(), current_model) if self.config_manager else {}
            allowed_keys = set((model_config.get('input_keys') or {}).keys()) | set((model_config.get('parameters') or {}).keys())
            
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
            if allowed_keys:
                api_kwargs = {k: v for k, v in api_kwargs.items() if k in allowed_keys or k == 'prompt'}
            
            # Extract prompt for function parameter
            prompt = api_kwargs.pop('prompt', filter_description(enhanced_video_desc))
            
            # Remove model from api_kwargs since it's passed explicitly below
            api_kwargs.pop('model', None)
            
            # Prepare metadata to save (do this before generation attempt)
            metadata_to_save = {
                'model': current_model,
                'prompt': prompt,
                **api_kwargs
            }
            
            # Extract image frame keys
            # We always pass the paths to generate_video to ensure validation logic works,
            # even if the keys are also present in kwargs (which _replicate_gen handles correctly).
            start_image = valid_first_image
            end_image = valid_last_image
            
            # Save config BEFORE generation so it exists even if generation fails
            metadata_to_save = {
                'model': current_model,
                'prompt': prompt,
                'original_prompt': video_desc,
                **api_kwargs
            }
            self.save_asset_metadata(video_path, metadata_to_save)
            
            param_dict = {'prompt': prompt, 'start_image_path': start_image, 'end_image_path': end_image, 'file_path': video_path, 'model': current_model, **api_kwargs}
            result_path = generate_video(
                **param_dict
            )
            
            if result_path is None:
                print(f"❌ [Video Generation] Video {idx+1} generation failed")
                # Save metadata even when generation fails so frontend can display config
                self.save_asset_metadata(video_path, metadata_to_save)
                print(f"💾 [Video Generation] Saved metadata for failed video: {video_path}.json")
                return None
            
            # Update data version
            self.update_data_version([f'sub_video_{idx}', 'video'], result_path)
                
            return result_path
        except Exception as e:
            print(f"❌ [Video Generation] Video {idx+1} generation error: {str(e)}")
            # Save metadata even when exception occurs so frontend can display config
            try:
                metadata_to_save = {
                    'model': current_model if 'current_model' in locals() else self.default_model,
                    'prompt': prompt if 'prompt' in locals() else enhanced_video_desc,
                    'error': str(e)
                }
                self.save_asset_metadata(video_path, metadata_to_save)
                print(f"💾 [Video Generation] Saved metadata for errored video: {video_path}.json")
            except Exception as save_error:
                print(f"⚠️ [Video Generation] Failed to save metadata: {save_error}")
            return None 