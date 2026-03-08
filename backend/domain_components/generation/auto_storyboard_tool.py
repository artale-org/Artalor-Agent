# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

"""
Auto Storyboard Designer Tool
=============================
Given the JSON string returned by the ad script writer tool, automatically extract
the fields `hook`, `main_content`, and `call_to_action`, then call the real
`AdStoryboardDesignerTool` from `domain_components` to create a storyboard.
"""

import json
from typing import Optional, Union
from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun
from pydantic import BaseModel, Field

# Import the real storyboard tool implementation
after_import_error = None
try:
    from domain_components.generation.ad_storyboard_designer import AdStoryboardDesignerTool
except Exception as e:
    after_import_error = e

class AutoStoryboardInput(BaseModel):
    """Input payload coming from AdScriptWriterTool (raw JSON string or parsed dict)."""
    script_json: Union[str, dict] = Field(description="JSON string (or parsed dict) returned by the ad_script_writer tool")

class AutoStoryboardDesignerTool(BaseTool):
    """Automatically generate a storyboard based on the advertising-script JSON."""
    name: str = "auto_storyboard_designer"
    description: str = (
        "Extracts hook, main_content, and call_to_action from the JSON produced by "
        "ad_script_writer, then calls ad_storyboard_designer to generate a full storyboard."
    )
    args_schema: type = AutoStoryboardInput

    def _run(
        self,
        script_json: Union[str, dict],
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        if after_import_error:
            return f"❌ Failed to load AdStoryboardDesignerTool: {after_import_error}"

        try:
            # If the input is already a dict, use it directly; otherwise parse the JSON string
            if isinstance(script_json, dict):
                data = script_json
            else:
                data = json.loads(script_json)
            hook = data.get("hook") or data.get("ad_hook") or data.get("Hook")
            main_content = data.get("main_content") or data.get("ad_main_content") or data.get("Main Content")
            call_to_action = data.get("call_to_action") or data.get("ad_cta") or data.get("Call To Action") or data.get("call_to_action")
            visual_notes = data.get("visual_notes") or data.get("ad_visual_notes")
            product_category = data.get("product_category")
            visual_style = data.get("visual_style")
            selling_points = data.get("selling_points")
            color_palette = data.get("color_palette")

            if not (hook and main_content and call_to_action):
                return "❌ Missing required fields hook/main_content/call_to_action in input JSON"

            storyboard_tool = AdStoryboardDesignerTool()
            input_payload = {
                "hook": hook,
                "main_content": main_content,
                "call_to_action": call_to_action,
                "visual_notes": visual_notes,
                "product_category": product_category,
                "visual_style": visual_style,
                "selling_points": selling_points,
                "color_palette": color_palette,
            }
            result = storyboard_tool.run(input_payload)
            return result
        except json.JSONDecodeError:
            return "❌ Invalid JSON string"
        except Exception as e:
            return f"❌ Failed to generate storyboard: {str(e)}"

    def _arun(self, *args, **kwargs):
        raise NotImplementedError("Async not implemented.") 