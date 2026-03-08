# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

from typing import Union, List, Dict
import json
import re
import os
from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun

# Reuse existing Image & Video tools
from modules.tools.langchain_agent_tools import ImageGeneratorTool, VideoGeneratorTool

class MultiStoryboardVideoInput(dict):
    """Input parameters: storyboard_json can be either a str or a dict"""
    pass

class MultiStoryboardVideoGeneratorTool(BaseTool):
    """Generate videos in batch for a list of storyboards; returns one video path per storyboard."""

    name: str = "multi_storyboard_video_generator"
    description: str = (
        "Generates videos for each storyboard inside storyboard_json. "
        "For every storyboard, it will: 1) generate keyframe images by calling image_generator; "
        "2) call video_generator to compose the video. Returns a JSON with 'videos' list."
    )

    def _run(
        self,
        storyboard_json: Union[str, Dict],
        run_manager: CallbackManagerForToolRun = None,
        **kwargs,
    ) -> str:
        # Parse the input
        if isinstance(storyboard_json, str):
            # Try to parse directly; if it fails, use regex to capture the first {...} JSON block
            try:
                data = json.loads(storyboard_json)
            except json.JSONDecodeError:
                match_json = re.search(r"\{.*\}", storyboard_json, re.DOTALL)
                if not match_json:
                    return "❌ Invalid JSON for storyboard_json"
                try:
                    data = json.loads(match_json.group())
                except Exception:
                    return "❌ Invalid JSON for storyboard_json"
        else:
            data = storyboard_json

        storyboards: List[Dict] = data.get("storyboards") or []
        if not storyboards and data.get("storyboard_frames"):
            # Fallback – derive storyboards from `storyboard_frames` list by grouping on `scene_type`
            raw_frames = data.get("storyboard_frames", [])
            if raw_frames and isinstance(raw_frames, list):
                scene_groups: Dict[str, List[Dict]] = {}
                for frm in raw_frames:
                    scene = frm.get("scene_type", "unknown") if isinstance(frm, dict) else "unknown"
                    scene_groups.setdefault(scene, []).append(frm)

                storyboards = [
                    {
                        "storyboard_id": idx,
                        "scene_type": scene,
                        "frames": frms,
                        "frame_count": len(frms)
                    }
                    for idx, (scene, frms) in enumerate(scene_groups.items(), 1)
                ]

                # If grouping somehow fails, fall back to a single storyboard
                if not storyboards:
                    storyboards = [{
                        "storyboard_id": 1,
                        "scene_type": "combined",
                        "frames": raw_frames,
                        "frame_count": len(raw_frames)
                    }]
            else:
                # Non-list or empty – still create a single storyboard to avoid error
                storyboards = [{
                    "storyboard_id": 1,
                    "scene_type": "combined",
                    "frames": raw_frames,
                    "frame_count": len(raw_frames) if isinstance(raw_frames, list) else 0
                }]

        if not storyboards and data.get("frames"):
            raw_frames = data.get("frames", [])
            if raw_frames and isinstance(raw_frames, list):
                scene_groups: Dict[str, List[Dict]] = {}
                for frm in raw_frames:
                    scene = frm.get("scene_type", "unknown") if isinstance(frm, dict) else "unknown"
                    scene_groups.setdefault(scene, []).append(frm)

                storyboards = [
                    {
                        "storyboard_id": idx,
                        "scene_type": scene,
                        "frames": frms,
                        "frame_count": len(frms)
                    }
                    for idx, (scene, frms) in enumerate(scene_groups.items(), 1)
                ]

                if not storyboards:
                    storyboards = [{
                        "storyboard_id": 1,
                        "scene_type": "combined",
                        "frames": raw_frames,
                        "frame_count": len(raw_frames)
                    }]
            else:
                storyboards = [{
                    "storyboard_id": 1,
                    "scene_type": "combined",
                    "frames": raw_frames,
                    "frame_count": len(raw_frames) if isinstance(raw_frames, list) else 0
                }]

        # Additional fallback for alias `storyboard` used by some designers
        if not storyboards and data.get("storyboard"):
            storyboards = [
                {
                    "storyboard_id": 1,
                    "scene_type": "combined",
                    "frames": data.get("storyboard", [])
                }
            ]

        # If still empty and raw_data exists, inspect that layer and search for storyboards
        if not storyboards and isinstance(data.get("raw_data"), dict):
            raw = data["raw_data"]
            storyboards = raw.get("storyboards") or []
            if not storyboards and raw.get("storyboard_frames"):
                storyboards = [{
                    "storyboard_id": 1,
                    "scene_type": "combined",
                    "frames": raw.get("storyboard_frames", [])
                }]
            if not storyboards and raw.get("storyboard"):
                storyboards = [{
                    "storyboard_id": 1,
                    "scene_type": "combined",
                    "frames": raw.get("storyboard", [])
                }]
            if not storyboards and raw.get("frames"):
                storyboards = [{
                    "storyboard_id": 1,
                    "scene_type": "combined",
                    "frames": raw.get("frames", [])
                }]

        # Heuristic fallback: search for any list field that looks like frames
        if not storyboards:
            for key, value in data.items():
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    sample_keys = value[0].keys()
                    if any(k in sample_keys for k in ("first_image_description", "scene_type", "video_description")):
                        storyboards = [{
                            "storyboard_id": 1,
                            "scene_type": key,
                            "frames": value
                        }]
                        break

        if not storyboards:
            return "❌ No storyboard found in input JSON"

        image_tool = ImageGeneratorTool()
        video_tool = VideoGeneratorTool()
        videos: List[str] = []

        for sb in storyboards:
            frames: List[Dict] = sb.get("frames", []) or sb.get("storyboard_frames", [])
            keyframe_paths: List[str] = []
            for idx, frame in enumerate(frames, 1):
                prompt = frame.get("first_image_description") or frame.get("first_frame_description") or frame.get("scene_summary") or "Product advertisement frame"
                # Call image generation tool
                img_result = image_tool.invoke({"prompt": prompt})
                # Try to extract the file path from the returned text
                match = re.search(r"Saved to:\s*(.*)$", img_result, re.MULTILINE)
                img_path = match.group(1).strip() if match else img_result
                keyframe_paths.append(img_path)

            # Assemble video prompt
            video_prompt = f"Compose advertisement video for storyboard {sb.get('storyboard_id', '?')}"
            video_result = video_tool.invoke({
                "prompt": video_prompt,
                "start_image_path": keyframe_paths[0] if keyframe_paths else None,
                "end_image_path": keyframe_paths[-1] if keyframe_paths else None,
            })
            match_v = re.search(r"Saved to:\s*(.*)$", video_result, re.MULTILINE)
            video_path = match_v.group(1).strip() if match_v else video_result
            videos.append(video_path)

        output = {
            "total_videos": len(videos),
            "videos": videos
        }
        return json.dumps(output, ensure_ascii=False)

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError("Async not implemented for MultiStoryboardVideoGeneratorTool") 