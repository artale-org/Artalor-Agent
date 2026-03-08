# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

"""
Image generation tool adapter - Provides image generation capabilities for new architecture
Reuses existing modules/tools/image_gen.py functionality
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '../../../modules'))

from modules.tools.image_gen import generate_image as _original_generate_image
from modules.tools.utils import filter_description

def generate_image(prompt: str, file_path: str = None, ref_image_path: str = None, model: str = 'dall-e-3', **kwargs) -> str:
    """
    Architecture-adapted image generation function
    
    Args:
        prompt: Image description prompt
        file_path: Output file path
        ref_image_path: Reference image path (for models like kling that support reference images)
        model: Model to use
        **kwargs: Other parameters
    
    Returns:
        str: Generated image file path
    """
    return _original_generate_image(
        prompt=prompt,
        file_path=file_path,
        ref_image_path=ref_image_path,
        model=model,
        **kwargs
    )

def batch_generate_images(prompts: list, output_dir: str, ref_image_path: str = None, model: str = 'dall-e-3') -> list:

    os.makedirs(output_dir, exist_ok=True)
    generated_images = []
    
    for i, prompt in enumerate(prompts):
        file_path = os.path.join(output_dir, f'image_{i:03d}.png')
        try:
            result_path = generate_image(
                prompt=filter_description(prompt),
                file_path=file_path,
                ref_image_path=ref_image_path,
                model=model
            )
            generated_images.append(result_path)
            print(f"✅ Generated image {i+1}/{len(prompts)}: {result_path}")
        except Exception as e:
            print(f"❌ Failed to generate image {i+1}: {e}")
            generated_images.append(None)
    
    return generated_images 