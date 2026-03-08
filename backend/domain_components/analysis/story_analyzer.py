# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

# refactored_architecture/2_business_components/analysis/story_analyzer.py
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from typing import List
import sys
import os

# Add infrastructure layer to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../modules'))
from modules.nodes.chat_node import ChatNode

# 1. Output data structure definition
class SceneDescription(BaseModel):
    scene_id: int = Field(description="Scene number")
    scene_summary: str = Field(description="Scene summary, within 100 words")
    key_elements: List[str] = Field(description="Key visual elements list")
    emotional_tone: str = Field(description="Emotional tone")
    duration_estimate: str = Field(description="Estimated duration")

class StoryAnalysisResult(BaseModel):
    story_theme: str = Field(description="Story theme")
    story_structure: str = Field(description="Story structure analysis")
    protagonist: str = Field(description="Main character/protagonist name or description")
    scene_descriptions: List[SceneDescription] = Field(description="Scene descriptions list")
    visual_style_suggestion: str = Field(description="Visual style suggestion")

# 2. Prompt template definition
STORY_ANALYSIS_TEMPLATE = ChatPromptTemplate.from_template("""
You are a professional story analyst and visual director. Please carefully analyze the story content below and provide detailed scene breakdown for video production.

Story content:
{story_content}

Please analyze according to the following requirements:

1. **Story Theme Analysis**: Extract the core theme and deeper meaning of the story
2. **Story Structure Analysis**: Analyze the story's dramatic structure (setup, confrontation, resolution)
3. **Protagonist Identification**: Identify the main character/protagonist by name (e.g., "Altman", "Sarah") or brief description if no name given (e.g., "young traveler", "brave knight")
4. **Scene Breakdown**: Break the story into 3-8 key scenes, each including:
   - Scene summary (concise description of scene content)
   - Key visual elements (characters, objects, environment, etc.)
   - Emotional tone (cheerful, tense, touching, etc.)
   - Estimated duration (several seconds to tens of seconds)
5. **Visual Style Suggestion**: Suggest appropriate visual presentation style based on story characteristics

Requirements:
- Scene breakdown should be logically clear with natural transitions
- Key visual elements should be specific and clear for image generation
- Emotional tone should accurately reflect story atmosphere
- Overall analysis should provide clear guidance for subsequent storyboard design and image generation
""")

# 3. Business component class
class StoryAnalyzer:
    """Story analysis business component - self-contained node, template, structure"""
    
    # Input-output mapping configuration
    INPUT_MAPPING = {
        'story_content': ['story', 'story_text', 'content', 'story_content']
    }
    
    OUTPUT_MAPPING = {
        'story_theme': 'analyzed_theme',
        'story_structure': 'analyzed_structure',
        'protagonist': 'protagonist',  # Direct mapping for character generation
        'scene_descriptions': 'scene',  # Maintain compatibility
        'visual_style_suggestion': 'visual_style'
    }
    
    @classmethod
    def create_node(cls, name: str, task_path: str, **config) -> ChatNode:
        """Factory method: create story analysis node"""
        node = ChatNode(name, task_path)
        
        # Configure node
        node.prompt_template = STORY_ANALYSIS_TEMPLATE
        node.output_structure = StoryAnalysisResult
        
        # Custom run logic
        def custom_run(inputs):
            # Input mapping processing
            story_content = cls._map_input(inputs, 'story_content')
            if not story_content:
                raise ValueError("No story content found in inputs")
            
            # Call LLM
            result = (node.prompt_template | node.chat_model.with_structured_output(node.output_structure)).invoke({
                'story_content': story_content
            })
            
            # Output mapping processing  
            output = cls._map_output(result.model_dump())
            return output
        
        node.run = custom_run
        return node
    
    @classmethod
    def _map_input(cls, inputs: dict, target_field: str) -> str:
        """Input field mapping"""
        possible_fields = cls.INPUT_MAPPING.get(target_field, [target_field])
        for field in possible_fields:
            if field in inputs and inputs[field]:
                return inputs[field]
        return None
    
    @classmethod  
    def _map_output(cls, result: dict) -> dict:
        """Output field mapping"""
        mapped_result = {}
        for source_field, target_field in cls.OUTPUT_MAPPING.items():
            if source_field in result:
                mapped_result[target_field] = result[source_field]
        
        # For compatibility with existing workflows, we need to convert scene_descriptions format
        if 'scene_descriptions' in result:
            scene_list = []
            for scene_desc in result['scene_descriptions']:
                # Convert SceneDescription to simple string format (compatible with original format)
                scene_summary = scene_desc.get('scene_summary', '') if isinstance(scene_desc, dict) else scene_desc.scene_summary
                scene_list.append(scene_summary)
            mapped_result['scene'] = scene_list
            
        return {**result, **mapped_result} 


# ============================================================================
# LangChain Agent Tool Version
# ============================================================================

from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun
from typing import Optional
import json

class StoryAnalysisInput(BaseModel):
    """Input parameters for story analysis tool"""
    story_content: str = Field(description="Story content or narrative text to analyze")

class StoryAnalyzerTool(BaseTool):
    """Story analysis tool - Analyze story content and break down scenes for video production"""
    
    name: str = "story_analyzer"
    description: str = """
    Professional story analysis tool for video production. Analyzes story content and provides:
    - Story theme extraction
    - Story structure analysis (setup, confrontation, resolution)
    - Scene breakdown with detailed descriptions
    - Visual style suggestions
    - Key visual elements identification
    - Emotional tone analysis
    
    This tool helps break down stories into manageable scenes for storyboard design and video creation.
    """
    args_schema: type = StoryAnalysisInput
    
    def _run(
        self,
        story_content: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """Execute story analysis"""
        try:
            print(f"📖 [StoryAnalyzerTool] Starting story analysis...")
            print(f"📖 [StoryAnalyzerTool] Story content: {story_content[:100]}...")
            
            # Create temporary node for analysis
            analyzer = StoryAnalyzer()
            node = analyzer.create_node("temp_story_analyzer", ".")
            
            # Execute analysis
            result = node.run({'story_content': story_content})
            
            # Format scene descriptions for better readability
            scenes_summary = []
            if 'scene_descriptions' in result:
                for i, scene in enumerate(result['scene_descriptions'], 1):
                    if isinstance(scene, dict):
                        scene_text = f"Scene {i}: {scene.get('scene_summary', '')}"
                        scenes_summary.append(scene_text)
                    else:
                        scenes_summary.append(f"Scene {i}: {scene}")
            
            # Format output as JSON string for agent consumption
            formatted_result = {
                "analysis_summary": f"Story analysis completed for: {story_content[:50]}...",
                "story_theme": result.get('story_theme', 'Not identified'),
                "story_structure": result.get('story_structure', 'Not analyzed'),
                "visual_style_suggestion": result.get('visual_style_suggestion', 'Not specified'),
                "total_scenes": len(result.get('scene_descriptions', [])),
                "scenes_summary": scenes_summary,
                "raw_data": result  # Full data for other tools to use
            }
            
            success_msg = f"✅ Story analysis completed successfully!\n{json.dumps(formatted_result, indent=2, ensure_ascii=False)}"
            print(f"📖 [StoryAnalyzerTool] Analysis completed")
            return success_msg
            
        except Exception as e:
            error_msg = f"❌ Error occurred during story analysis: {str(e)}"
            print(f"📖 [StoryAnalyzerTool] {error_msg}")
            return error_msg 