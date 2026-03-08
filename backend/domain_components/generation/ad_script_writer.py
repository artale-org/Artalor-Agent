# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from typing import List
import sys
import os

# Add infrastructure layer to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../modules'))
from modules.nodes.chat_node import ChatNode

# 1. Output data structure definition
class AdScript(BaseModel):
    hook: str = Field(description="Opening hook, 3-5 seconds")
    main_content: str = Field(description="Main content, 15-20 seconds")
    call_to_action: str = Field(description="Call to action, 3-5 seconds")
    visual_notes: str = Field(description="Visual presentation notes")
    audio_notes: str = Field(description="Audio music suggestions")
    duration_estimate: str = Field(description="Total duration estimate")

# 2. Dynamic prompt template function
def create_ad_script_template(target_duration: int = 30) -> ChatPromptTemplate:
    """
    Create ad script template with dynamic duration allocation
    
    Args:
        target_duration: Target video duration in seconds (default: 30)
    
    Returns:
        ChatPromptTemplate configured for the target duration
    """
    # Calculate time allocation based on target duration
    # Proportions: Hook ~15%, Main ~70%, CTA ~15%
    hook_duration = max(2, int(target_duration * 0.15))
    main_duration = max(5, int(target_duration * 0.70))
    cta_duration = max(2, int(target_duration * 0.15))
    
    # Adjust hook duration range text
    if hook_duration < 3:
        hook_range = f"{hook_duration} seconds"
    else:
        hook_range = f"{hook_duration-1}-{hook_duration+1} seconds"
    
    # Adjust main duration range text
    if main_duration < 8:
        main_range = f"{main_duration-1}-{main_duration+1} seconds"
    else:
        main_range = f"{main_duration-3}-{main_duration+2} seconds"
    
    # Adjust CTA duration range text
    if cta_duration < 3:
        cta_range = f"{cta_duration} seconds"
    else:
        cta_range = f"{cta_duration-1}-{cta_duration+1} seconds"
    
    template_text = f"""
You are a professional advertising copywriter and strategist. Based on the product analysis results, create an engaging advertisement script.

Advertisement requirement:
{{requirement}}

Product analysis results:
- Product category: {{product_category}}
- Visual style: {{visual_style}}
- Target audience: {{target_audience}}
- Core selling points: {{selling_points}}
- Emotional keywords: {{mood_keywords}}
- Main colors: {{color_palette}}

Reference image understanding (align visuals with the user's actual product; do not invent new products):
{{reference_image_context}}

Please create a {target_duration}-second advertisement script with the following structure:

1. **Opening Hook** ({hook_range}):
   - Quick attention-grabbing opening
   - Resonate with target audience
   - Can be a question, surprise, or emotional trigger

2. **Main Content** ({main_range}):
   - Highlight product's core selling points
   - Show product usage scenarios or effects
   - Emphasize product value and experience

3. **Call to Action** ({cta_range}):
   - Clear guidance for purchase or learning more
   - Create urgency or uniqueness
   - Brand reinforcement

4. **Visual Presentation Notes**:
   - Detailed description of visuals for each stage
   - Design compositions based on product features
   - Consider color, lighting, composition and other visual elements

5. **Audio Music Suggestions**:
   - Music style and rhythm suggestions
   - Match product character and target audience
   - Sound effect suggestions

Requirements:
- Copy should be concise and powerful, easy to understand and remember
- Make full use of product's unique selling points
- Visual descriptions should be specific for image and video generation
- Overall style should be consistent with product character
- Consider effectiveness on social media platforms
- Total duration should be approximately {target_duration} seconds
"""
    
    return ChatPromptTemplate.from_template(template_text)

# Keep default template for backward compatibility
AD_SCRIPT_TEMPLATE = create_ad_script_template(30)

# 3. Business component class
class AdScriptWriter:
    """Advertisement script generation business component - self-contained node, template, structure"""
    
    # Input-output mapping configuration
    INPUT_MAPPING = {
        'requirement': ['ad_requirement', 'requirement', 'brief'],
        'product_category': ['analyzed_category', 'product_category', 'category'],
        'visual_style': ['product_style', 'visual_style', 'style'],
        'target_audience': ['audience', 'target_audience'],
        'selling_points': ['selling_points', 'key_benefits'],
        'mood_keywords': ['mood', 'mood_keywords', 'emotions'],
        'color_palette': ['colors', 'color_palette', 'primary_colors'],
        'reference_image_descriptions': ['reference_image_descriptions'],
        'target_duration': ['target_duration']  # Target video duration in seconds
    }
    
    OUTPUT_MAPPING = {
        'hook': 'ad_hook',
        'main_content': 'ad_main_content',
        'call_to_action': 'ad_cta',
        'visual_notes': 'ad_visual_notes',
        'audio_notes': 'ad_audio_notes',
        'duration_estimate': 'ad_duration'
    }
    
    @classmethod
    def create_node(cls, name: str, task_path: str, **config) -> ChatNode:
        """Factory method: create advertisement script generation node"""
        node = ChatNode(name, task_path)
        
        # Configure node
        node.prompt_template = AD_SCRIPT_TEMPLATE
        node.output_structure = AdScript
        
        # Custom run logic
        def custom_run(inputs):
            # Input mapping processing
            mapped_inputs = {}
            for target_field in cls.INPUT_MAPPING.keys():
                mapped_inputs[target_field] = cls._map_input(inputs, target_field)
            
            # Check required fields
            if not mapped_inputs['requirement']:
                raise ValueError("No requirement found in inputs")
            
            # Process list type fields
            if isinstance(mapped_inputs['selling_points'], list):
                mapped_inputs['selling_points'] = ', '.join(mapped_inputs['selling_points'])
            if isinstance(mapped_inputs['mood_keywords'], list):
                mapped_inputs['mood_keywords'] = ', '.join(mapped_inputs['mood_keywords'])
            if isinstance(mapped_inputs['color_palette'], list):
                mapped_inputs['color_palette'] = ', '.join(mapped_inputs['color_palette'])
            
            # Handle null values
            for key, value in mapped_inputs.items():
                if value is None:
                    mapped_inputs[key] = "Not provided"

            # Build reference image context string for the prompt
            ref_ctx = "Not provided"
            rid = mapped_inputs.get('reference_image_descriptions')
            if isinstance(rid, list) and len(rid) > 0:
                try:
                    lines = []
                    for item in rid:
                        if isinstance(item, dict):
                            idx = item.get('index', '?')
                            summary = item.get('summary', '')
                            elements = item.get('key_elements', [])
                            if isinstance(elements, list):
                                elements_str = ', '.join([str(e) for e in elements])
                            else:
                                elements_str = str(elements)
                            lines.append(f"Image {idx}: {summary} | elements: {elements_str}")
                        else:
                            lines.append(str(item))
                    ref_ctx = "\n".join(lines)
                except Exception:
                    ref_ctx = "Provided but failed to parse"
            mapped_inputs['reference_image_context'] = ref_ctx
            
            # Get target duration and create dynamic template
            target_duration = mapped_inputs.get('target_duration')
            if target_duration is None or target_duration == "Not provided":
                target_duration = 30  # Default to 30 seconds
            else:
                try:
                    target_duration = int(target_duration)
                except (ValueError, TypeError):
                    target_duration = 30
            
            # Create dynamic prompt template based on target duration
            dynamic_template = create_ad_script_template(target_duration)
            
            # Call LLM with dynamic template
            result = (dynamic_template | node.chat_model.with_structured_output(node.output_structure)).invoke(mapped_inputs)
            
            # Output mapping processing  
            output = cls._map_output(result.model_dump())
            return output
        
        node.run = custom_run
        return node
    
    @classmethod
    def _map_input(cls, inputs: dict, target_field: str):
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
        
        return {**result, **mapped_result} 


# ============================================================================
# LangChain Agent Tool Version
# ============================================================================

from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun
from typing import Optional
import json

class AdScriptInput(BaseModel):
    """Input parameters for advertisement script writing tool"""
    requirement: str = Field(description="Advertisement requirement or brief")
    product_category: Optional[str] = Field(default=None, description="Product category (optional)")
    visual_style: Optional[str] = Field(default=None, description="Visual style preference (optional)")
    target_audience: Optional[str] = Field(default=None, description="Target audience (optional)")
    selling_points: Optional[str] = Field(default=None, description="Key selling points (optional)")
    mood_keywords: Optional[str] = Field(default=None, description="Emotional keywords (optional)")
    color_palette: Optional[str] = Field(default=None, description="Color palette (optional)")

class AdScriptWriterTool(BaseTool):
    """Advertisement script writing tool - Create engaging ad scripts based on product analysis"""
    
    name: str = "ad_script_writer"
    description: str = """
    Professional advertisement script writing tool. Creates engaging 30-second ad scripts with:
    - Attention-grabbing opening hook (3-5 seconds)
    - Compelling main content (15-20 seconds)
    - Strong call-to-action (3-5 seconds)
    - Detailed visual presentation notes
    - Audio and music suggestions
    - Duration estimates
    
    This tool creates scripts optimized for social media platforms and video advertisement production.
    """
    args_schema: type = AdScriptInput
    
    def _run(
        self,
        requirement: str,
        product_category: Optional[str] = None,
        visual_style: Optional[str] = None,
        target_audience: Optional[str] = None,
        selling_points: Optional[str] = None,
        mood_keywords: Optional[str] = None,
        color_palette: Optional[str] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """Execute advertisement script writing"""
        try:
            print(f"✍️ [AdScriptWriterTool] Starting ad script creation...")
            print(f"✍️ [AdScriptWriterTool] Requirement: {requirement[:100]}...")
            
            # Prepare input data
            input_data = {
                'requirement': requirement,
                'product_category': product_category or "Not specified",
                'visual_style': visual_style or "Not specified",
                'target_audience': target_audience or "Not specified",
                'selling_points': selling_points or "Not specified",
                'mood_keywords': mood_keywords or "Not specified",
                'color_palette': color_palette or "Not specified"
            }
            
            # Create temporary node for script writing
            writer = AdScriptWriter()
            node = writer.create_node("temp_script_writer", ".")
            
            # Execute script writing
            result = node.run(input_data)
            
            # Format output for better readability
            formatted_result = {
                "script_summary": f"Advertisement script created for: {requirement[:50]}...",
                "hook": result.get('hook', 'Not generated'),
                "main_content": result.get('main_content', 'Not generated'),
                "call_to_action": result.get('call_to_action', 'Not generated'),
                "visual_notes": result.get('visual_notes', 'Not provided'),
                "audio_notes": result.get('audio_notes', 'Not provided'),
                "duration_estimate": result.get('duration_estimate', 'Not estimated'),
                "raw_data": result  # Full data for other tools to use
            }
            
            json_str = json.dumps(formatted_result, ensure_ascii=False)
            print(f"✍️ [AdScriptWriterTool] Script creation completed")
            return json_str
            
        except Exception as e:
            error_msg = f"❌ Error occurred during ad script writing: {str(e)}"
            print(f"✍️ [AdScriptWriterTool] {error_msg}")
            return error_msg 