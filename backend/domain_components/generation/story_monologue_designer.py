from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from typing import Optional
import sys
import os

# Add infrastructure layer to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../modules'))
from modules.nodes.chat_node import ChatNode


class StoryMonologueSpec(BaseModel):
    language: str = Field(description="Language of the narration, e.g., en")
    voice_style: str = Field(description="Voice persona for the narration, e.g., warm, reflective, cinematic")
    pacing: str = Field(description="Reading pace guidance, e.g., slow, medium, measured")
    monologue_text: str = Field(description="Short, production-ready narration text for the full video")


STORY_MONOLOGUE_TEMPLATE = ChatPromptTemplate.from_template("""
You are a story narrator and trailer writer creating a short voiceover for a finished story video.

Original story:
{story}

Story context:
- Theme: {theme}
- Mood: {mood}
- Protagonist: {protagonist}
- Setting: {setting}
- Visual style: {visual_style}
- Target duration: {target_duration} seconds

Scene summaries:
{scene_descriptions}

Write a concise narration that:
1) Summarizes what the story is about.
2) Reflects the emotional tone of the story.
3) Frames the role of the final video as a visual retelling of the story.
4) Sounds natural when spoken as one continuous voiceover track.
5) Avoids literal scene-by-scene captioning.
6) Stays concise: usually 2-4 short sentences, suitable for a short-form video.

Provide:
- language
- voice_style
- pacing
- monologue_text
""")


class StoryMonologueDesigner:
    """Generate a concise full-video narration from story context."""

    INPUT_MAPPING = {
        'story': ['story', 'story_text', 'content'],
        'theme': ['theme', 'story_theme', 'analyzed_theme'],
        'mood': ['mood'],
        'protagonist': ['protagonist'],
        'setting': ['setting'],
        'visual_style': ['visual_style', 'visual_style_suggestion'],
        'scene_descriptions': ['scene_descriptions', 'scene', 'scenes'],
        'target_duration': ['target_duration'],
    }

    OUTPUT_MAPPING = {
        'monologue_text': 'monologue_text',
        'voice_style': 'voice_style',
        'pacing': 'pacing',
        'language': 'language',
    }

    @classmethod
    def create_node(cls, name: str, task_path: str, **config) -> ChatNode:
        node = ChatNode(name, task_path)
        node.prompt_template = STORY_MONOLOGUE_TEMPLATE
        node.output_structure = StoryMonologueSpec

        def custom_run(inputs: dict):
            mapped_inputs = {}
            for target_field in cls.INPUT_MAPPING.keys():
                mapped_inputs[target_field] = cls._map_input(inputs, target_field)

            if not mapped_inputs.get('story'):
                raise ValueError("No story content found in inputs")

            scene_descriptions = mapped_inputs.get('scene_descriptions')
            if isinstance(scene_descriptions, list):
                formatted_scenes = []
                for idx, item in enumerate(scene_descriptions, start=1):
                    if isinstance(item, dict):
                        summary = item.get('scene_summary') or item.get('summary') or str(item)
                    else:
                        summary = str(item)
                    formatted_scenes.append(f"{idx}. {summary}")
                mapped_inputs['scene_descriptions'] = "\n".join(formatted_scenes)
            elif scene_descriptions is None:
                mapped_inputs['scene_descriptions'] = "Not provided"

            if mapped_inputs.get('target_duration') is None:
                mapped_inputs['target_duration'] = 60

            for key, value in list(mapped_inputs.items()):
                if value is None:
                    mapped_inputs[key] = "Not provided"

            result = (node.prompt_template | node.chat_model.with_structured_output(node.output_structure)).invoke(mapped_inputs)
            data = result.model_dump() if hasattr(result, 'model_dump') else result

            for source_field, target_field in cls.OUTPUT_MAPPING.items():
                if source_field in data:
                    data[target_field] = data[source_field]
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
