# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

"""
LangChain Agent Tools for Image and Video Generation
Encapsulating existing image and video generation functions as standard LangChain tools
"""

import json
import os
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun

# Import existing generators
from .image_gen import generate_image
from .video_gen import generate_video
# from .audio_gen import NarrationAudioGeneratorTool, AmbientSoundAudioGeneratorTool


class ImageGenerationInput(BaseModel):
    """Input parameters for image generation tool"""
    prompt: str = Field(description="Text description for image generation")
    model: str = Field(
        default="black-forest-labs/flux-1.1-pro", 
        description="Generation model, options: dall-e-3, kling-v1, kling-v1-5, kling-v2, black-forest-labs/flux-1.1-pro"
    )
    ref_image_path: Optional[str] = Field(
        default=None, 
        description="Reference image path (optional), used for image-to-image generation"
    )
    file_path: Optional[str] = Field(
        default=None, 
        description="File path to save the image (optional), auto-generated if not specified"
    )


class VideoGenerationInput(BaseModel):
    """Input parameters for video generation tool"""
    prompt: str = Field(description="Text description for video generation")
    start_image_path: Optional[str] = Field(
        default=None, 
        description="Image path for video start frame (optional)"
    )
    end_image_path: Optional[str] = Field(
        default=None, 
        description="Image path for video end frame (optional)"
    )
    model: str = Field(
        default="kwaivgi/kling-v1.6-standard",
        description="Generation model, options: kling-v1, kling-v1-5, kling-v1-6, kwaivgi/kling-v1.6-standard, minimax/video-01-director, wavespeedai/wan-2.1-i2v-480p"
    )
    file_path: Optional[str] = Field(
        default=None, 
        description="File path to save the video (optional), auto-generated if not specified"
    )


class ImageGeneratorTool(BaseTool):
    """Image generation tool - Generate images based on text descriptions"""
    
    name: str = "image_generator"
    description: str = """
    Tool for generating images. Supports multiple models:
    - DALL-E 3 (dall-e-3): OpenAI's image generation model
    - Kling series (kling-v1, kling-v1-5, kling-v2): Kuaishou's image generation models
    - Flux (black-forest-labs/flux-1.1-pro): High-quality image generation model on Replicate
    
    Can generate images based on text descriptions, also supports image-to-image generation with reference images.
    """
    args_schema: type = ImageGenerationInput
    
    def _run(
        self, 
        prompt: str,
        model: str = "black-forest-labs/flux-1.1-pro",
        ref_image_path: Optional[str] = None,
        file_path: Optional[str] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
        **kwargs
    ) -> str:
        """Execute image generation"""
        try:
            print(f"🎨 [ImageGeneratorTool] Starting image generation...")
            print(f"🎨 [ImageGeneratorTool] Model: {model}")
            print(f"🎨 [ImageGeneratorTool] Prompt: {prompt[:100]}...")
            
            # Call existing image generation function
            result_path = generate_image(
                prompt=prompt,
                model=model,
                file_path=file_path,
                ref_image_path=ref_image_path,
                **kwargs
            )
            
            if result_path:
                abs_path = os.path.abspath(result_path)
                success_msg = f"✅ Image generation successful! Saved to: {abs_path}"
                print(f"🎨 [ImageGeneratorTool] {success_msg}")
                return success_msg
            else:
                error_msg = "❌ Image generation failed, returned empty path"
                print(f"🎨 [ImageGeneratorTool] {error_msg}")
                return error_msg
                
        except Exception as e:
            error_msg = f"❌ Error occurred during image generation: {str(e)}"
            print(f"🎨 [ImageGeneratorTool] {error_msg}")
            return error_msg


class VideoGeneratorTool(BaseTool):
    """Video generation tool - Generate videos based on text descriptions and images"""
    
    name: str = "video_generator"
    description: str = """
    Tool for generating videos. Supports multiple models:
    - Kling series (kling-v1, kling-v1-5, kling-v1-6): Kuaishou's video generation models
    - Kling Replicate (kwaivgi/kling-v1.6-standard): Kling model on Replicate
    - MiniMax (minimax/video-01-director): MiniMax's video generation model
    - WAN (wavespeedai/wan-2.1-i2v-480p): WAN image-to-video model
    
    Can generate videos based on text descriptions and start/end images. At least one image is required.
    """
    args_schema: type = VideoGenerationInput
    
    def _run(
        self,
        prompt: str,
        start_image_path: Optional[str] = None,
        end_image_path: Optional[str] = None,
        model: str = "kwaivgi/kling-v1.6-pro",
        file_path: Optional[str] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
        **kwargs
    ) -> str:
        """Execute video generation"""
        try:
            print(f"🎬 [VideoGeneratorTool] Starting video generation...")
            print(f"🎬 [VideoGeneratorTool] Model: {model}")
            print(f"🎬 [VideoGeneratorTool] Prompt: {prompt[:100]}...")
            
            if not start_image_path and not end_image_path:
                placeholder_msg = "ℹ️ No images provided; returning placeholder video generation result."
                print(f"🎬 [VideoGeneratorTool] {placeholder_msg}")
                return placeholder_msg
            
            # Validate image files exist
            if start_image_path and not os.path.exists(start_image_path):
                error_msg = f"❌ Start image file does not exist: {start_image_path}"
                print(f"🎬 [VideoGeneratorTool] {error_msg}")
                return error_msg
                
            if end_image_path and not os.path.exists(end_image_path):
                error_msg = f"❌ End image file does not exist: {end_image_path}"
                print(f"🎬 [VideoGeneratorTool] {error_msg}")
                return error_msg
            
            # Call existing video generation function
            result_path = generate_video(
                prompt=prompt,
                start_image_path=start_image_path,
                end_image_path=end_image_path,
                model=model,
                file_path=file_path
            )
            
            if result_path:
                abs_path = os.path.abspath(result_path)
                success_msg = f"✅ Video generation successful! Saved to: {abs_path}"
                print(f"🎬 [VideoGeneratorTool] {success_msg}")
                return success_msg
            else:
                error_msg = "❌ Video generation failed, returned empty path"
                print(f"🎬 [VideoGeneratorTool] {error_msg}")
                return error_msg
                
        except Exception as e:
            error_msg = f"❌ Error occurred during video generation: {str(e)}"
            print(f"🎬 [VideoGeneratorTool] {error_msg}")
            return error_msg


# ============================================================================
# Tool Collections and Export Functions
# ============================================================================

# Export all tools
ALL_GENERATION_TOOLS = [
    ImageGeneratorTool(),
    VideoGeneratorTool(),
    # NarrationAudioGeneratorTool(),
    # AmbientSoundAudioGeneratorTool(),
]

# Tools grouped by category
IMAGE_TOOLS = [ImageGeneratorTool()]
VIDEO_TOOLS = [VideoGeneratorTool()]
# AUDIO_TOOLS = [NarrationAudioGeneratorTool(), AmbientSoundAudioGeneratorTool()]

# Import domain components tools
try:
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))
    from domain_components.agent_tools_collection import get_all_domain_tools
    DOMAIN_TOOLS = get_all_domain_tools()
    ALL_TOOLS = ALL_GENERATION_TOOLS + DOMAIN_TOOLS
    print(f"✅ Successfully imported {len(DOMAIN_TOOLS)} domain component tools")
except ImportError as e:
    print(f"⚠️ Warning: Could not import domain component tools: {e}")
    DOMAIN_TOOLS = []
    ALL_TOOLS = ALL_GENERATION_TOOLS


def get_all_tools() -> List[BaseTool]:
    """Get all tools including generation and domain component tools"""
    return ALL_TOOLS.copy()


def get_generation_tools() -> List[BaseTool]:
    """Get generation tools only"""
    return ALL_GENERATION_TOOLS.copy()


def get_image_tools() -> List[BaseTool]:
    """Get image generation tools"""
    return IMAGE_TOOLS.copy()


def get_video_tools() -> List[BaseTool]:
    """Get video generation tools"""
    return VIDEO_TOOLS.copy()

def get_audio_tools() -> List[BaseTool]:
    """Get audio generation tools"""
    return AUDIO_TOOLS.copy()

def get_domain_tools() -> List[BaseTool]:
    """Get domain component tools"""
    return DOMAIN_TOOLS.copy()


def list_all_available_tools() -> dict:
    """List all available tools with their information"""
    tools_info = {}
    for tool in ALL_TOOLS:
        tools_info[tool.name] = {
            "description": tool.description.strip(),
            "category": _categorize_tool(tool.name)
        }
    return tools_info


def _categorize_tool(tool_name: str) -> str:
    """Categorize tool based on its name"""
    if tool_name in ['image_generator']:
        return "Image Generation"
    elif tool_name in ['video_generator']:
        return "Video Generation"
    elif tool_name in ['product_analyzer', 'story_analyzer']:
        return "Content Analysis"
    elif tool_name in ['ad_script_writer', 'storyboard_designer', 'ad_storyboard_designer']:
        return "Content Generation"
    else:
        return "Other"


if __name__ == "__main__":
    # Test tools
    print("🧪 Testing LangChain Agent Tools...")
    print("=" * 60)
    
    # Test image generation tool
    image_tool = ImageGeneratorTool()
    print(f"📋 Image tool name: {image_tool.name}")
    print(f"📋 Image tool description: {image_tool.description[:100]}...")
    
    # Test video generation tool
    video_tool = VideoGeneratorTool()
    print(f"📋 Video tool name: {video_tool.name}")
    print(f"📋 Video tool description: {video_tool.description[:100]}...")
    
    print(f"\n📊 Tools Summary:")
    print(f"  • Generation Tools: {len(ALL_GENERATION_TOOLS)}")
    print(f"  • Domain Tools: {len(DOMAIN_TOOLS)}")
    print(f"  • Total Tools: {len(ALL_TOOLS)}")
    
    print(f"\n🔧 Available Tools:")
    tools_info = list_all_available_tools()
    for tool_name, info in tools_info.items():
        print(f"  • {tool_name} ({info['category']})")
    
    print(f"\n✅ All tools loaded successfully!")
