# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

"""
Domain Components Agent Tools Collection
Centralized collection of all Agent Tools from domain components
"""

from typing import List
from langchain_core.tools import BaseTool

# Import all Agent Tools from domain components
from domain_components.analysis.product_analyzer import ProductAnalyzerTool
from domain_components.analysis.story_analyzer import StoryAnalyzerTool
from domain_components.generation.ad_script_writer import AdScriptWriterTool
from domain_components.generation.storyboard_designer import StoryboardDesignerTool
from domain_components.generation.ad_storyboard_designer import AdStoryboardDesignerTool
from modules.tools.langchain_agent_tools import ImageGeneratorTool, VideoGeneratorTool


# ============================================================================
# Tool Collections
# ============================================================================

# Analysis Tools
ANALYSIS_TOOLS = [
    ProductAnalyzerTool(),
    StoryAnalyzerTool(),
]

# Generation Tools  
GENERATION_TOOLS = [
    AdScriptWriterTool(),
    StoryboardDesignerTool(),
    AdStoryboardDesignerTool(),
    ImageGeneratorTool(),
    VideoGeneratorTool(),
]

# All Domain Component Tools
ALL_DOMAIN_TOOLS = ANALYSIS_TOOLS + GENERATION_TOOLS

# Tools by category
ADVERTISEMENT_TOOLS = [
    ProductAnalyzerTool(),
    AdScriptWriterTool(),
    AdStoryboardDesignerTool(),
]

STORY_TOOLS = [
    StoryAnalyzerTool(),
    StoryboardDesignerTool(),
]


# ============================================================================
# Utility Functions
# ============================================================================

def get_all_domain_tools() -> List[BaseTool]:
    """Get all domain component agent tools"""
    return ALL_DOMAIN_TOOLS.copy()


def get_analysis_tools() -> List[BaseTool]:
    """Get analysis agent tools"""
    return ANALYSIS_TOOLS.copy()


def get_generation_tools() -> List[BaseTool]:
    """Get generation agent tools"""
    return GENERATION_TOOLS.copy()


def get_advertisement_tools() -> List[BaseTool]:
    """Get advertisement workflow agent tools"""
    return ADVERTISEMENT_TOOLS.copy()


def get_story_tools() -> List[BaseTool]:
    """Get story workflow agent tools"""
    return STORY_TOOLS.copy()


def get_tool_by_name(tool_name: str) -> BaseTool:
    """Get a specific tool by name"""
    for tool in ALL_DOMAIN_TOOLS:
        if tool.name == tool_name:
            return tool
    raise ValueError(f"Tool '{tool_name}' not found")


def list_all_tools() -> dict:
    """List all available tools with their descriptions"""
    tools_info = {}
    for tool in ALL_DOMAIN_TOOLS:
        tools_info[tool.name] = {
            "description": tool.description.strip(),
            "category": _get_tool_category(tool.name)
        }
    return tools_info


def _get_tool_category(tool_name: str) -> str:
    """Get tool category based on tool name"""
    if tool_name in ['product_analyzer', 'story_analyzer']:
        return "Analysis"
    elif tool_name in ['ad_script_writer', 'storyboard_designer', 'ad_storyboard_designer']:
        return "Generation"
    else:
        return "Unknown"


# ============================================================================
# Tool Information
# ============================================================================

TOOL_WORKFLOW_MAPPING = {
    "Advertisement Workflow": [
        "product_analyzer",
        "ad_script_writer", 
        "ad_storyboard_designer"
    ],
    "Story-to-Video Workflow": [
        "story_analyzer",
        "storyboard_designer"
    ]
}

TOOL_DESCRIPTIONS = {
    "product_analyzer": "Analyze product features and characteristics for advertisement creation",
    "story_analyzer": "Analyze story content and break down scenes for video production",
    "ad_script_writer": "Create engaging advertisement scripts based on product analysis",
    "storyboard_designer": "Create detailed storyboards for video production from story scenes",
    "ad_storyboard_designer": "Create detailed advertisement storyboards for video production"
}


if __name__ == "__main__":
    print("🛠️  Domain Components Agent Tools Collection")
    print("=" * 60)
    
    print(f"\n📊 Available Tools Summary:")
    print(f"  • Total Tools: {len(ALL_DOMAIN_TOOLS)}")
    print(f"  • Analysis Tools: {len(ANALYSIS_TOOLS)}")
    print(f"  • Generation Tools: {len(GENERATION_TOOLS)}")
    
    print(f"\n🔧 Tool Details:")
    tools_info = list_all_tools()
    for tool_name, info in tools_info.items():
        print(f"  • {tool_name} ({info['category']})")
        print(f"    {info['description'][:100]}...")
    
    print(f"\n🔄 Workflow Mappings:")
    for workflow, tools in TOOL_WORKFLOW_MAPPING.items():
        print(f"  • {workflow}:")
        for tool in tools:
            print(f"    - {tool}")
    
    print(f"\n✅ All tools loaded successfully!") 