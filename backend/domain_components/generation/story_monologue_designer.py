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
    monologue_text: str = Field(description="Production-ready narration text sized to the target runtime of the full video")


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
- Preferred narration language: {narration_language_preference}
- Language instruction: {narration_language_instruction}
- Spoken length target: {spoken_length_guidance}
- Approximate word target: {word_budget_guidance}
- Sentence guidance: {sentence_guidance}

Scene summaries:
{scene_descriptions}

Write a narration that:
1) Summarizes what the story is about.
2) Reflects the emotional tone of the story.
3) Frames the role of the final video as a visual retelling of the story.
4) Sounds natural when spoken as one continuous voiceover track.
5) Avoids literal scene-by-scene captioning.
6) Fills most of the requested runtime instead of reading like a short trailer tag.
7) Uses enough detail to match the target duration while still sounding natural.
8) Does not pad with repetition, filler, or generic conclusions.
9) If a preferred narration language is provided, write the monologue_text fully in that language and set the language field accordingly.
10) Never default back to English when a non-English narration language is requested.

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
        'narration_language_preference': ['narration_language_preference'],
    }

    OUTPUT_MAPPING = {
        'monologue_text': 'monologue_text',
        'voice_style': 'voice_style',
        'pacing': 'pacing',
        'language': 'language',
    }

    @staticmethod
    def _estimate_word_budget(target_duration: int) -> tuple[str, str, str]:
        """Return runtime guidance for a natural single-track narration."""
        try:
            duration = max(15, int(target_duration))
        except (TypeError, ValueError):
            duration = 60

        # Rough voiceover planning guidance for a natural story narration.
        target_words = max(35, int(duration * 2.2))
        min_words = max(30, int(target_words * 0.9))
        max_words = int(target_words * 1.1)

        min_sentences = max(3, round(duration / 12))
        max_sentences = max(min_sentences + 1, round(duration / 8))

        spoken_length_guidance = f"Aim for about {max(8, duration - 5)} to {duration} seconds when spoken naturally."
        word_budget_guidance = f"Target roughly {min_words} to {max_words} words."
        sentence_guidance = f"Usually {min_sentences} to {max_sentences} sentences, depending on pacing and complexity."
        return spoken_length_guidance, word_budget_guidance, sentence_guidance

    @staticmethod
    def _normalize_language_preference(language_preference: Optional[str]) -> tuple[str, str]:
        """Map TTS language selection to a strong narration-language instruction."""
        if not language_preference or language_preference in {"Not provided", "None", "Automatic"}:
            return "Not provided", "Use the most natural language for the story context."

        normalized = str(language_preference).strip()
        mapping = {
            "English": ("English", "Write the monologue fully in English. Set language to en or English."),
            "Chinese": ("Simplified Chinese", "Write the monologue fully in Simplified Chinese. Do not use English except unavoidable proper nouns. Set language to zh or Chinese."),
            "Chinese,Yue": ("Cantonese Chinese", "Write the monologue fully in Cantonese Chinese. Prefer Traditional Chinese characters and natural Cantonese phrasing. Do not write standard Mandarin prose."),
            "Cantonese": ("Cantonese Chinese", "Write the monologue fully in Cantonese Chinese. Prefer Traditional Chinese characters and natural Cantonese phrasing."),
            "Japanese": ("Japanese", "Write the monologue fully in Japanese. Set language to ja or Japanese."),
            "Korean": ("Korean", "Write the monologue fully in Korean. Set language to ko or Korean."),
            "French": ("French", "Write the monologue fully in French."),
            "Spanish": ("Spanish", "Write the monologue fully in Spanish."),
            "Portuguese": ("Portuguese", "Write the monologue fully in Portuguese."),
            "German": ("German", "Write the monologue fully in German."),
            "Italian": ("Italian", "Write the monologue fully in Italian."),
            "Russian": ("Russian", "Write the monologue fully in Russian."),
            "Arabic": ("Arabic", "Write the monologue fully in Arabic."),
            "Vietnamese": ("Vietnamese", "Write the monologue fully in Vietnamese."),
            "Indonesian": ("Indonesian", "Write the monologue fully in Indonesian."),
            "Thai": ("Thai", "Write the monologue fully in Thai."),
            "Hindi": ("Hindi", "Write the monologue fully in Hindi."),
        }
        return mapping.get(normalized, (normalized, f"Write the monologue fully in {normalized}."))

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

            if mapped_inputs.get('narration_language_preference') in (None, "", "None", "Automatic"):
                mapped_inputs['narration_language_preference'] = "Not provided"

            normalized_language, language_instruction = cls._normalize_language_preference(
                mapped_inputs.get('narration_language_preference')
            )
            mapped_inputs['narration_language_preference'] = normalized_language
            mapped_inputs['narration_language_instruction'] = language_instruction

            spoken_length_guidance, word_budget_guidance, sentence_guidance = cls._estimate_word_budget(
                mapped_inputs.get('target_duration')
            )
            mapped_inputs['spoken_length_guidance'] = spoken_length_guidance
            mapped_inputs['word_budget_guidance'] = word_budget_guidance
            mapped_inputs['sentence_guidance'] = sentence_guidance

            for key, value in list(mapped_inputs.items()):
                if value is None:
                    mapped_inputs[key] = "Not provided"

            result = (node.prompt_template | node.chat_model.with_structured_output(node.output_structure)).invoke(mapped_inputs)
            data = result.model_dump() if hasattr(result, 'model_dump') else result

            preferred_language = mapped_inputs.get('narration_language_preference')
            if preferred_language and preferred_language not in {"Not provided", "English"} and data.get('monologue_text'):
                translation_prompt = ChatPromptTemplate.from_template("""
You are a professional story narrator localizing a voiceover script.

Target language: {target_language}
Instruction: {language_instruction}

Current voice style: {voice_style}
Current pacing: {pacing}

Rewrite the following narration fully in the target language.
- Keep the meaning, cinematic tone, pacing, and approximate spoken length.
- Do not summarize it further.
- Do not leave the output in English.
- Return only the rewritten narration text.

Narration:
{monologue_text}
""")
                translated = node.chat_model.invoke(
                    translation_prompt.format_messages(
                        target_language=preferred_language,
                        language_instruction=mapped_inputs['narration_language_instruction'],
                        voice_style=data.get('voice_style', 'cinematic'),
                        pacing=data.get('pacing', 'measured'),
                        monologue_text=data['monologue_text'],
                    )
                )
                translated_text = getattr(translated, 'content', None)
                if translated_text:
                    data['monologue_text'] = translated_text.strip()
                    data['language'] = preferred_language

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
