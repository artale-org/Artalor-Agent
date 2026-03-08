# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

"""
Video generation tool adapter - Provides video generation capabilities for new architecture
Reuses existing modules/tools/video_gen.py functionality
"""
import sys
import os

# Add existing modules path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../modules'))

# Import existing video generation functionality
from modules.tools.video_gen import generate_video as _original_generate_video
from modules.tools.utils import filter_description

def generate_video(prompt: str, start_image: str, end_image: str, file_path: str = None, model: str = 'wavespeedai/wan-2.1-i2v-480p', **kwargs) -> str:
    """
    Architecture-adapted video generation function
    
    Args:
        prompt: Video description prompt
        image_paths: List of image file paths
        file_path: Output file path
        model: Model to use
        **kwargs: Other parameters
    
    Returns:
        str: Generated video file path
    """
    return _original_generate_video(
        prompt=prompt,
        start_image_path=start_image,
        end_image_path=end_image,
        file_path=file_path,
        model=model,
        **kwargs
    )

def batch_generate_videos(video_specs: list, output_dir: str, model: str = 'wavespeedai/wan-2.1-i2v-480p') -> list:
    """
    Batch video generation - convenience function specific to new architecture
    
    Args:
        video_specs: List of video specifications, each containing {'prompt', 'start_image', 'end_image'}
        output_dir: Output directory
        model: Model to use
    
    Returns:
        list: List of generated video file paths
    """
    os.makedirs(output_dir, exist_ok=True)
    generated_videos = []
    
    for i, spec in enumerate(video_specs):
        file_path = os.path.join(output_dir, f'video_{i:03d}.mp4')
        try:
            result_path = generate_video(
                prompt=filter_description(spec['prompt']),
                start_image=spec['start_image'],
                end_image=spec['end_image'],
                file_path=file_path,
                model=model
            )
            generated_videos.append(result_path)
            print(f"✅ Generated video {i+1}/{len(video_specs)}: {result_path}")
        except Exception as e:
            print(f"❌ Failed to generate video {i+1}: {e}")
            generated_videos.append(None)
    
    return generated_videos 