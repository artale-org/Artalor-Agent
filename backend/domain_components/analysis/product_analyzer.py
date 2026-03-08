# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

# 2_business_components/analysis/product_analyzer.py
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from typing import List
import sys
import os

# Add infrastructure layer to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../modules'))
from modules.nodes.chat_node import ChatNode

# 1. Output data structure definition
class ProductFeature(BaseModel):
    feature_name: str = Field(description="Feature name")
    feature_description: str = Field(description="Feature detailed description")
    visual_importance: int = Field(description="Visual importance score 1-10")

class ProductAnalysisResult(BaseModel):
    product_category: str = Field(description="Product category")
    visual_style: str = Field(description="Visual style")
    key_features: List[ProductFeature] = Field(description="Key features list")
    color_palette: List[str] = Field(description="Main colors")
    mood_keywords: List[str] = Field(description="Emotional keywords")
    target_audience: str = Field(description="Target audience")
    selling_points: List[str] = Field(description="Selling points")

# 2. Prompt template definition
PRODUCT_ANALYSIS_TEMPLATE = ChatPromptTemplate.from_template("""
You are a professional product analyst and marketing expert. Please carefully analyze the provided product requirement description and provide detailed product analysis for advertisement creation.

Product requirement description:
{requirement}

Please conduct the following analysis:

1. **Product Category Identification**: Determine the specific category and market positioning of the product
2. **Visual Style Analysis**: Analyze the overall visual style of the product (modern, classic, minimalist, luxury, etc.)
3. **Key Feature Extraction**: Identify the main visual features and unique selling points
   - Design characteristics
   - Material texture
   - Color coordination
   - Craftsmanship details
4. **Color Analysis**: Infer the main colors and color schemes of the product
5. **Emotional Keywords**: Summarize the emotions and atmosphere conveyed by the product (warm, elegant, energetic, etc.)
6. **Target Audience**: Analyze the target consumer group of the product
7. **Selling Points**: Summarize the core selling points and competitive advantages of the product

Requirements:
- Analysis should be specific and detailed, facilitating subsequent advertisement creative design
- Focus on visualizable features to guide image and video generation
- Emotional keywords should accurately reflect product character
- Selling points should highlight the unique value of the product
""")

# 3. Business component class
class ProductAnalyzer:
    """Product analysis business component - self-contained node, template, structure"""
    
    # Input-output mapping configuration
    INPUT_MAPPING = {
        'requirement': ['ad_requirement', 'requirement', 'product_requirement'],
        'product_image': ['subject_image_path', 'product_image', 'image_path', 'subject_image']
    }
    
    OUTPUT_MAPPING = {
        'product_category': 'analyzed_category',
        'visual_style': 'product_style',
        'key_features': 'product_features',
        'color_palette': 'colors',
        'mood_keywords': 'mood',
        'target_audience': 'audience',
        'selling_points': 'selling_points'
    }
    
    @classmethod
    def create_node(cls, name: str, task_path: str, **config) -> ChatNode:
        """Factory method: create product analysis node"""
        node = ChatNode(name, task_path)
        
        # Configure node
        node.prompt_template = PRODUCT_ANALYSIS_TEMPLATE
        node.output_structure = ProductAnalysisResult
        
        # Custom run logic
        def custom_run(inputs):
            # Input mapping processing
            requirement = cls._map_input(inputs, 'requirement')
            
            if not requirement:
                raise ValueError("No requirement found in inputs")
            
            # Call LLM
            result = (node.prompt_template | node.chat_model.with_structured_output(node.output_structure)).invoke({
                'requirement': requirement
            })
            
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

class ProductAnalysisInput(BaseModel):
    """Input parameters for product analysis tool"""
    requirement: str = Field(description="Product requirement description or advertisement brief")

class ProductAnalyzerTool(BaseTool):
    """Product analysis tool - Analyze product features and characteristics for advertisement creation"""
    
    name: str = "product_analyzer"
    description: str = """
    Professional product analysis tool for advertisement creation. Analyzes product requirements and provides:
    - Product category identification
    - Visual style analysis
    - Key feature extraction
    - Color palette analysis
    - Emotional keywords
    - Target audience identification
    - Core selling points
    
    This tool helps create targeted advertising content by understanding product characteristics.
    """
    args_schema: type = ProductAnalysisInput
    
    def _run(
        self,
        requirement: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """Execute product analysis"""
        try:
            print(f"🔍 [ProductAnalyzerTool] Starting product analysis...")
            print(f"🔍 [ProductAnalyzerTool] Requirement: {requirement[:100]}...")
            
            # Create temporary node for analysis
            analyzer = ProductAnalyzer()
            node = analyzer.create_node("temp_analyzer", ".")
            
            # Execute analysis
            result = node.run({'requirement': requirement})
            
            # Format output as JSON string for agent consumption
            formatted_result = {
                "analysis_summary": f"Product analysis completed for: {requirement[:50]}...",
                "product_category": result.get('product_category', 'Not determined'),
                "visual_style": result.get('visual_style', 'Not specified'),
                "target_audience": result.get('target_audience', 'Not identified'),
                "selling_points": result.get('selling_points', []),
                "mood_keywords": result.get('mood_keywords', []),
                "color_palette": result.get('color_palette', []),
                "raw_data": result  # Full data for other tools to use
            }
            
            success_msg = f"✅ Product analysis completed successfully!\n{json.dumps(formatted_result, indent=2, ensure_ascii=False)}"
            print(f"🔍 [ProductAnalyzerTool] Analysis completed")
            return success_msg
            
        except Exception as e:
            error_msg = f"❌ Error occurred during product analysis: {str(e)}"
            print(f"🔍 [ProductAnalyzerTool] {error_msg}")
            return error_msg 