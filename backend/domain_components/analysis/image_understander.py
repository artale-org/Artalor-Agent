# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

import os
import sys
from typing import List
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
import base64
import mimetypes
import argparse
import json
from datetime import datetime

# Reuse infrastructure layer ChatNode
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))
from modules.nodes.chat_node import ChatNode


class ImageDescription(BaseModel):
    index: int = Field(description="Image index (starting from 1)")
    summary: str = Field(description="Overall description of the image")
    
    # Detailed product feature descriptions (for maintaining generation consistency)
    product_category: str = Field(description="Product category (e.g., handbag, beverage, electronics)")
    brand_info: str = Field(description="Brand name, logo, or brand-related visual elements")
    
    # Core visual features (important! for ensuring generated images maintain consistent product form)
    shape_structure: str = Field(description="Detailed shape and structure of the product (e.g., rectangular bottle, curved handle bag)")
    color_scheme: str = Field(description="Main colors and color distribution of the product")
    material_texture: str = Field(description="Material and texture appearance (e.g., glossy metal, matte leather)")
    distinctive_features: str = Field(description="Unique identifying features (e.g., logo placement, patterns, special design elements)")
    
    # Size proportions (helps maintain consistency)
    size_proportion: str = Field(description="Relative size and proportions of product elements")
    
    key_elements: List[str] = Field(description="Additional key visual elements in the image")


class ImageUnderstandingResult(BaseModel):
    descriptions: List[ImageDescription] = Field(description="Per-image description results")


IMAGE_UNDERSTANDING_TEMPLATE = ChatPromptTemplate.from_template(
    """
You are a professional product image analyst. Your task is to analyze reference images in EXTREME DETAIL to ensure generated content maintains PERFECT PRODUCT CONSISTENCY.

Input:
- Reference image path list: {reference_image_path}

**CRITICAL MISSION**: Extract complete product characteristics so that AI-generated images will have IDENTICAL product appearance.

For each product image, provide:

1. **Summary**: Overall description of what's in the image

2. **Product Category**: What type of product is this? (e.g., luxury handbag, beverage bottle, smartphone)

3. **Brand Info**: 
   - Brand name if visible
   - Logo design, position, and appearance
   - Any brand-related text or symbols

4. **Shape & Structure** (CRITICAL for consistency):
   - Overall shape (rectangular, cylindrical, curved, etc.)
   - Structural elements (handles, caps, buttons, pockets, etc.)
   - Proportions and dimensions relationship between parts
   - Any distinctive silhouette features

5. **Color Scheme** (CRITICAL for consistency):
   - Primary color(s) with specific shades
   - Secondary colors
   - Color distribution and patterns
   - Finish (glossy, matte, metallic, etc.)

6. **Material & Texture**:
   - Material type (leather, plastic, metal, glass, fabric, etc.)
   - Texture appearance (smooth, textured, woven, embossed, etc.)
   - Surface finish quality

7. **Distinctive Features** (MOST CRITICAL for identification):
   - Unique design elements that make this product recognizable
   - Logo placement and style
   - Patterns, prints, or decorative elements
   - Hardware details (zippers, clasps, buttons)
   - Labels, text, or graphics on the product
   - Any signature design traits

8. **Size & Proportion**:
   - Relative size of different parts
   - Proportion relationships
   - Scale indicators if present

9. **Key Elements**: Any other visual elements in the scene

**Requirements**:
- Be EXTREMELY detailed and specific - this information will be used to maintain product consistency across all generated images
- Use precise, descriptive language
- Focus on features that make the product uniquely identifiable
- Return structured JSON following the schema
- If multiple images, analyze each separately and maintain list order
"""
)


class ReferenceImageDescriber:
    """Reference image describing component: convert image list into structured text
    Output is used as reference for subsequent product analysis/script/storyboard.
    """

    @classmethod
    def create_node(cls, name: str, task_path: str, **config) -> ChatNode:
        node = ChatNode(name, task_path)
        node.prompt_template = IMAGE_UNDERSTANDING_TEMPLATE
        node.output_structure = ImageUnderstandingResult

        def custom_run(inputs: dict):
            ref_paths = inputs.get('subject_image_path') or inputs.get('reference_image_path')
            if not ref_paths or not isinstance(ref_paths, list):
                return {'descriptions': []}

            # Filter out non-existent paths while preserving order
            valid_paths = []
            for p in ref_paths:
                if isinstance(p, str) and os.path.exists(p):
                    valid_paths.append(p)

            if not valid_paths:
                return {'descriptions': []}

            # Build multimodal message: instruction text + image content parts
            instruction = (
                "You are a professional product image analyst. Analyze the following product images in EXTREME DETAIL "
                "to extract complete product characteristics. For each image, provide:\n"
                "- Overall summary\n"
                "- Product category\n"
                "- Brand information (name, logo, text)\n"
                "- Shape & structure (CRITICAL: overall shape, structural elements, proportions)\n"
                "- Color scheme (CRITICAL: primary/secondary colors, patterns, finish)\n"
                "- Material & texture (type, appearance, finish)\n"
                "- Distinctive features (MOST CRITICAL: unique design elements, logo placement, patterns, hardware, signature traits)\n"
                "- Size & proportion (relative sizes, relationships)\n"
                "- Other key elements\n\n"
                "Be EXTREMELY detailed and specific - this information ensures generated images maintain PERFECT product consistency. "
                "Return structured JSON matching the schema. Keep list order same as input order."
            )

            content_parts = [{
                'type': 'text',
                'text': instruction
            }]

            for img_path in valid_paths:
                mime, _ = mimetypes.guess_type(img_path)
                if mime is None:
                    # default to png if unknown
                    mime = 'image/png'
                with open(img_path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')
                data_uri = f"data:{mime};base64,{b64}"
                content_parts.append({
                    'type': 'image_url',
                    'image_url': {
                        'url': data_uri
                    }
                })

            message = HumanMessage(content=content_parts)

            result = node.chat_model.with_structured_output(node.output_structure).invoke([message])

            return result.model_dump() if hasattr(result, 'model_dump') else result

        node.run = custom_run
        return node



def test_image_understanding(image_paths: list):
    """Simple test runner for image understanding node."""
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    task_path = os.path.join('task_data', f'ad_creation_test_{ts}')
    os.makedirs(task_path, exist_ok=True)

    node = ReferenceImageDescriber.create_node('image_understanding', task_path)
    inputs = {
        'subject_image_path': image_paths
    }
    result_wrapped = node(inputs)
    result = result_wrapped.get('image_understanding', {})
    print(result)
    # Save to JSON for inspection
    # out_path = os.path.join(task_path, 'image_understanding.json')
    # with open(out_path, 'w', encoding='utf-8') as f:
    #     json.dump(result, f, ensure_ascii=False, indent=2)
    # print(f"Saved understanding result to: {out_path}")
    return result


if __name__ == "__main__":
    from modules.tools.utils import load_env
    load_env()
    parser = argparse.ArgumentParser(description='Test reference image understanding')
    parser.add_argument('--images', type=str, required=False, help='Comma-separated image paths')
    args = parser.parse_args()

    if args.images:
        images = [p.strip() for p in args.images.split(',') if p.strip()]
    else:
        # Fallback to sample asset if not provided
        images = [os.path.join('assets', 'ad_examples', 'example1.png')]

    print(f"Testing image understanding with images: {images}")
    test_image_understanding(images)
