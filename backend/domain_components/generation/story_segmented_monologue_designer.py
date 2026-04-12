from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from typing import Optional, List
import sys
import os

# Add infrastructure layer to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../modules'))
from modules.nodes.chat_node import ChatNode


class StorySegmentSpec(BaseModel):
    segment_index: int = Field(description="Index of the video segment (0-based)")
    segment_text: str = Field(description="Voiceover text for this segment")
    timing_notes: str = Field(description="Short pacing note for the segment")


class StorySegmentedMonologueResult(BaseModel):
    segments: List[StorySegmentSpec] = Field(description="List of story voiceover segments")
    total_estimated_duration: str = Field(description="Estimated total narration duration")
    language: str = Field(description="Language used for the segmented narration")


STORY_SEGMENTED_MONOLOGUE_TEMPLATE = ChatPromptTemplate.from_template("""
You are a cinematic story narrator adapting one full narration into clip-aligned voiceover segments.

Original story:
{story}

Story context:
- Theme: {theme}
- Mood: {mood}
- Protagonist: {protagonist}
- Setting: {setting}
- Visual style: {visual_style}
- Preferred narration language: {narration_language_preference}
- Language instruction: {narration_language_instruction}

Full narration reference:
{full_monologue_text}

Storyboard clips:
{storyboard_segments}

Create segmented narration that:
1) Produces exactly {num_segments} segments, one for each storyboard clip, in order.
2) Keeps the same overall meaning, tone, and language as the full narration reference.
3) Matches the visual action of each specific clip instead of reading like one unbroken paragraph.
4) Stays inside each segment's target spoken duration and target word count.
5) Flows naturally from segment to segment when the audio clips are concatenated.
6) Avoids repeated introductions, repeated conclusions, and generic filler.
7) Uses natural spoken phrasing, not captions.
8) If a preferred narration language is provided, every segment_text must be fully in that language.

Return:
- segments, where each item includes segment_index, segment_text, and timing_notes
- total_estimated_duration
- language
""")


class StorySegmentedMonologueDesigner:
    """Generate clip-aligned story voiceover segments from a full narration."""

    INPUT_MAPPING = {
        'story': ['story', 'story_text', 'content'],
        'theme': ['theme', 'story_theme', 'analyzed_theme'],
        'mood': ['mood'],
        'protagonist': ['protagonist'],
        'setting': ['setting'],
        'visual_style': ['visual_style', 'visual_style_suggestion'],
        'full_monologue_text': ['monologue_text', 'full_monologue_text'],
        'narration_language_preference': ['narration_language_preference'],
        'narration_language_instruction': ['narration_language_instruction'],
    }

    segment_duration_ratio = [0.72, 0.95]
    word_per_second_ratio = [1.5, 2.2]

    @classmethod
    def create_node(cls, name: str, task_path: str) -> ChatNode:
        node = ChatNode(name=name, task_path=task_path)
        node.configure(
            prompt_template=STORY_SEGMENTED_MONOLOGUE_TEMPLATE,
            output_structure=StorySegmentedMonologueResult
        )

        def custom_run(inputs: dict):
            return cls.custom_run(node, inputs)

        node.run = custom_run
        return node

    @staticmethod
    def custom_run(node, inputs: dict):
        mapped_inputs = {}
        for target_field in StorySegmentedMonologueDesigner.INPUT_MAPPING.keys():
            mapped_inputs[target_field] = StorySegmentedMonologueDesigner._map_input(inputs, target_field)

        storyboard = inputs.get('storyboard') or inputs.get('storyboard_frames') or []
        input_video_durations = inputs.get('video_durations') or []

        if storyboard:
            mapped_inputs['num_segments'] = len(storyboard)
            segments_text = ""
            for i, segment in enumerate(storyboard):
                if hasattr(segment, 'video_description'):
                    scene_summary = getattr(segment, 'scene_summary', 'N/A')
                    video_desc = getattr(segment, 'video_description', 'N/A')
                    first_img = getattr(segment, 'first_image_description', 'N/A')
                    last_img = getattr(segment, 'last_image_description', 'N/A')
                else:
                    scene_summary = segment.get('scene_summary', 'N/A')
                    video_desc = segment.get('video_description', 'N/A')
                    first_img = segment.get('first_image_description', 'N/A')
                    last_img = segment.get('last_image_description', 'N/A')

                vdur = None
                try:
                    if isinstance(input_video_durations, list) and i < len(input_video_durations):
                        vdur = float(input_video_durations[i]) if input_video_durations[i] is not None else None
                except Exception:
                    vdur = None

                if vdur is not None and vdur > 0:
                    min_secs = StorySegmentedMonologueDesigner.segment_duration_ratio[0] * vdur
                    max_secs = StorySegmentedMonologueDesigner.segment_duration_ratio[1] * vdur
                else:
                    min_secs, max_secs = 4.0, 6.0

                min_word_count = max(3, int(min_secs * StorySegmentedMonologueDesigner.word_per_second_ratio[0]))
                max_word_count = max(min_word_count, int(max_secs * StorySegmentedMonologueDesigner.word_per_second_ratio[1]))

                segments_text += f"""
Segment {i + 1}:
- Scene summary: {scene_summary}
- Video description: {video_desc}
- First frame: {first_img}
- Last frame: {last_img}
- Target spoken duration: {min_secs:.2f}-{max_secs:.2f}s
- Target word count: {min_word_count}-{max_word_count}
"""

            mapped_inputs['storyboard_segments'] = segments_text.strip()
        else:
            mapped_inputs['num_segments'] = 0
            mapped_inputs['storyboard_segments'] = "No storyboard segments provided"

        for key, value in list(mapped_inputs.items()):
            if value is None or value == "":
                mapped_inputs[key] = "Not provided"

        result = node.chat_model.with_structured_output(node.output_structure).invoke(
            node.prompt_template.format(**mapped_inputs)
        )
        return result.model_dump() if hasattr(result, 'model_dump') else result

    @classmethod
    def _map_input(cls, inputs: dict, target_field: str) -> Optional[str]:
        possible_fields = cls.INPUT_MAPPING.get(target_field, [target_field])
        for field in possible_fields:
            if field in inputs and inputs[field]:
                return inputs[field]
        return None
