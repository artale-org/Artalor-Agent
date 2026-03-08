# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from typing import Optional, List
import sys
import os

# Add infrastructure layer to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../modules'))
from modules.nodes.chat_node import ChatNode


class AdMonologueSpec(BaseModel):
    language: str = Field(description="Language of the monologue, e.g., en")
    voice_style: str = Field(description="Voice style or persona, e.g., warm, confident, energetic")
    pacing: str = Field(description="Reading pace guidance, e.g., medium, slow, fast")
    monologue_text: str = Field(description="Final monologue text for voiceover")


AD_MONOLOGUE_TEMPLATE = ChatPromptTemplate.from_template("""
You are a senior advertising copywriter and voiceover director. Design a concise, production-ready monologue for the advertisement below.

Advertisement requirement:
{requirement}

Product analysis (if provided):
- Category: {product_category}
- Visual style: {visual_style}
- Selling points: {selling_points}
- Mood: {mood_keywords}
- Colors: {color_palette}

Script highlights (if provided):
- Hook: {hook}
- Main content: {main_content}
- Call to action: {call_to_action}

Reference image understanding (if provided):
{reference_image_context}

Storyboard theme (if provided): {visual_theme}

Constraints:
1) The monologue must align with the user's real product (do not invent a different product).
2) Keep the text clear and impactful; suitable for voiceover.
3) Prefer ~12-25 seconds of speech for typical 20-30s ads, unless content needs shorter/longer pacing.
4) Provide: language (e.g., en), voice_style, pacing, and monologue_text.
""")


class AdMonologueDesigner:
    """Advertisement monologue designer based on ChatNode."""

    # Input mapping similar to other components
    INPUT_MAPPING = {
        'requirement': ['ad_requirement', 'requirement', 'brief'],
        'product_category': ['analyzed_category', 'product_category', 'category'],
        'visual_style': ['product_style', 'visual_style', 'style'],
        'selling_points': ['selling_points', 'key_benefits'],
        'mood_keywords': ['mood', 'mood_keywords', 'emotions'],
        'color_palette': ['colors', 'color_palette', 'primary_colors'],
        'hook': ['ad_hook', 'hook', 'opening'],
        'main_content': ['ad_main_content', 'main_content', 'content'],
        'call_to_action': ['ad_cta', 'call_to_action', 'cta'],
        'reference_image_descriptions': ['reference_image_descriptions'],
        'visual_theme': ['visual_theme', 'theme']
    }

    OUTPUT_MAPPING = {
        'monologue_text': 'ad_monologue_text',
        'voice_style': 'ad_voice_style',
        'pacing': 'ad_pacing',
        'language': 'ad_language'
    }

    @classmethod
    def create_node(cls, name: str, task_path: str, **config) -> ChatNode:
        node = ChatNode(name, task_path)
        node.prompt_template = AD_MONOLOGUE_TEMPLATE
        node.output_structure = AdMonologueSpec

        def custom_run(inputs: dict):
            mapped_inputs = {}
            for target_field in cls.INPUT_MAPPING.keys():
                mapped_inputs[target_field] = cls._map_input(inputs, target_field)

            if not mapped_inputs.get('requirement'):
                raise ValueError("No requirement found in inputs")

            # Build reference image context
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

            # Fill None fields
            for key, value in list(mapped_inputs.items()):
                if value is None:
                    mapped_inputs[key] = "Not provided"

            result = (node.prompt_template | node.chat_model.with_structured_output(node.output_structure)).invoke(mapped_inputs)
            data = result.model_dump() if hasattr(result, 'model_dump') else result

            # Map outputs
            for s, t in cls.OUTPUT_MAPPING.items():
                if s in data:
                    data[t] = data[s]
            return data

        node.run = custom_run
        return node

    @classmethod
    def _map_input(cls, inputs: dict, target_field: str) -> Optional[str]:
        possible_fields = cls.INPUT_MAPPING.get(target_field, [target_field])
        for field in possible_fields:
            if field in inputs and inputs[field]:
                return inputs[field]
        return None


# New data models for segmented monologue
class AdSegmentSpec(BaseModel):
    segment_index: int = Field(description="Index of the video segment (0-based)")
    segment_text: str = Field(description="Voiceover text for this segment")
    timing_notes: str = Field(description="Timing and pacing notes for this segment")


class AdSegmentedMonologueResult(BaseModel):
    segments: List[AdSegmentSpec] = Field(description="List of voiceover segments")
    total_estimated_duration: str = Field(description="Estimated total duration")
    voice_style: str = Field(description="Recommended voice style")
    language: str = Field(description="Language code")


# Template for segmented monologue
AD_SEGMENTED_MONOLOGUE_TEMPLATE = ChatPromptTemplate.from_template("""
You are an expert advertisement copywriter creating segmented voiceover scripts.

Create voiceover text for each video segment based on the storyboard and overall context:

Product requirement: {requirement}
Product category: {product_category}
Visual style: {visual_style}
Key selling points: {selling_points}
Mood/emotions: {mood_keywords}

Overall script context:
- Hook: {hook}
- Main content: {main_content}
- Call to action: {call_to_action}

Reference image understanding: {reference_image_context}

Storyboard segments:
{storyboard_segments}

Create a voiceover script for each segment that:
1) Matches the visual content of that specific segment
2) Flows naturally from one segment to the next
3) Maintains overall narrative coherence
4) STRICT: You must output exactly {num_segments} segments (one per storyboard item), in order

CRITICAL WORD COUNT REQUIREMENT:
5) CRITICAL: Each segment has a "Target word count" field (e.g., "5-8" or "1-2")
You MUST generate EXACTLY the number of words within that range for each segment
7) Count ONLY actual words (nouns, verbs, adjectives, etc.), NOT punctuation or symbols
8) If target is "1-2", generate 1 or 2 words ONLY. If "5-8", generate 5-8 words ONLY.
9) Being even one word over or under the range is UNACCEPTABLE

ADDITIONAL REQUIREMENTS:
10) Keep the language natural and engaging within the word count constraint
11) Ensure the last segment includes a clear call-to-action
12) Natural speech rate: approximately 2-3 words per second

Provide segments as a structured list with timing guidance.
""")


class AdSegmentedMonologueDesigner:
    """Advertisement segmented monologue designer for multi-segment videos."""

    INPUT_MAPPING = {
        'requirement': ['ad_requirement', 'requirement', 'brief'],
        'product_category': ['analyzed_category', 'product_category', 'category'],
        'visual_style': ['product_style', 'visual_style', 'style'],
        'selling_points': ['selling_points', 'key_benefits'],
        'mood_keywords': ['mood', 'mood_keywords', 'emotions'],
        'hook': ['hook', 'opening'],
        'main_content': ['main_content', 'body'],
        'call_to_action': ['call_to_action', 'cta'],
        'reference_image_context': ['reference_image_descriptions', 'image_context'],
        'storyboard': ['storyboard', 'storyboard_design']
    }

    segment_duration_ratio = [0.6, 0.8]
    word_per_second_ratio = [1.5, 2]

    
    @classmethod
    def create_node(cls, name: str, task_path: str):
        """Create a ChatNode configured for segmented monologue design."""
        node = ChatNode(name=name, task_path=task_path)
        node.configure(
            prompt_template=AD_SEGMENTED_MONOLOGUE_TEMPLATE,
            output_structure=AdSegmentedMonologueResult
        )
        
        # Set custom run method
        def custom_run(inputs: dict):
            return cls.custom_run(node, inputs)
        
        node.run = custom_run
        return node

    @staticmethod
    def custom_run(node, inputs: dict):
        """Custom run method to format storyboard segments."""
        # Map inputs using INPUT_MAPPING
        mapped_inputs = {}
        for target_field in AdSegmentedMonologueDesigner.INPUT_MAPPING.keys():
            mapped_inputs[target_field] = AdSegmentedMonologueDesigner._map_input(inputs, target_field)
        
        # Also keep raw video durations list for per-segment numeric guidance
        input_video_durations = inputs.get('video_durations')
        # Optional per-segment explicit target seconds override: List[Tuple[min_secs, max_secs]]
        input_segment_word_count = inputs.get('segment_target_word_count')
        
        # Format storyboard segments for the template
        storyboard = inputs.get('storyboard', [])
        if storyboard:
            mapped_inputs['num_segments'] = len(storyboard)
            segments_text = ""
            for i, segment in enumerate(storyboard):
                if hasattr(segment, 'video_description'):
                    video_desc = segment.video_description
                    first_img = getattr(segment, 'first_image_description', 'N/A')
                    last_img = getattr(segment, 'last_image_description', 'N/A')
                else:
                    video_desc = segment.get('video_description', 'N/A')
                    first_img = segment.get('first_image_description', 'N/A')
                    last_img = segment.get('last_image_description', 'N/A')
                
                # Numeric video duration
                vdur = None
                try:
                    if isinstance(input_video_durations, list) and i < len(input_video_durations):
                        vdur = float(input_video_durations[i]) if input_video_durations[i] is not None else None
                except Exception:
                    vdur = None
                
                # Determine target seconds range (integers)
                if vdur is not None and vdur > 0:
                    min_secs, max_secs = AdSegmentedMonologueDesigner.segment_duration_ratio[0] * vdur, AdSegmentedMonologueDesigner.segment_duration_ratio[1] * vdur
                else:
                    min_secs, max_secs = 3, 4
                target_dur_str = f"{min_secs:.2f}–{max_secs:.2f}s"
                
                if isinstance(input_segment_word_count, list) and i < len(input_segment_word_count):
                    min_word_count, max_word_count = input_segment_word_count[i]
                else:
                    min_word_count = int(min_secs * AdSegmentedMonologueDesigner.word_per_second_ratio[0])
                    max_word_count = int(max_secs * AdSegmentedMonologueDesigner.word_per_second_ratio[1])
                
                # Ensure word counts are integers
                min_word_count = int(min_word_count)
                max_word_count = int(max_word_count)
                word_count_str = f"{min_word_count}-{max_word_count}"
                segments_text += f"""
Segment {i+1}:
- Video description: {video_desc}
- First frame: {first_img}
- Last frame: {last_img}
- Target spoken duration: {target_dur_str}
- Target word count: {word_count_str}
"""
            mapped_inputs['storyboard_segments'] = segments_text.strip()
        else:
            mapped_inputs['storyboard_segments'] = "No storyboard segments provided"
            mapped_inputs['num_segments'] = 0
        
        # Format reference image context
        ref_images = inputs.get('reference_image_descriptions', [])
        if ref_images and isinstance(ref_images, list):
            context_text = "\n".join([f"- {desc}" for desc in ref_images])
            mapped_inputs['reference_image_context'] = context_text
        else:
            mapped_inputs['reference_image_context'] = "No reference images provided"
        
        # Fill None fields
        for key, value in list(mapped_inputs.items()):
            if value is None:
                mapped_inputs[key] = "Not provided"
        
        # Use ChatNode's default run
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


