# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

# workflow_applications/story_to_video/story_video_workflow_langgraph.py
"""
LangGraph-based story video creation workflow with checkpoint support and incremental execution.

Features:
- Orchestrates existing nodes in a directed graph
- Persistent checkpoints using SQLite for task resumption
- Workflow graph visualization support
- Incremental re-execution: modify specific results and re-run only affected nodes

Checkpoint & Resume:
- Checkpoints are automatically saved to task_data/{task_id}/checkpoints.sqlite
- Automatically resume from checkpoint if task_path exists with checkpoint
- Use --list-tasks to see all tasks
- Use --task-path {path} to resume (auto-detected if checkpoint exists)

Workflow Visualization:
- Visualize workflow graph structure in multiple formats
- Use --visualize to generate workflow diagrams
- Supported formats: mermaid (default), png, ascii
- Use --viz-format to specify output format
- Use --viz-output to specify output filename

Incremental Re-execution:
- Modify specific parts of workflow results (e.g., image prompts, scene descriptions)
- Re-execute only the nodes affected by your changes
- Unaffected nodes reuse their previous results
- Automatic dependency tracking based on dirty flags

Usage:
  # Run test with default example
  python story_video_workflow_langgraph.py --test
  
  # Start new task (auto-generate task path)
  python story_video_workflow_langgraph.py --story "Once upon a time..."
  
  # Start new task (specify task path)
  python story_video_workflow_langgraph.py --story "Once upon a time..." --task-path task_data/my_story
  
  # List tasks
  python story_video_workflow_langgraph.py --list-tasks
  
  # Rerun by task path
  python story_video_workflow_langgraph.py --rerun --task-path task_data/story_video_langgraph_20250101120000
"""
import os
import sys
import argparse
from datetime import datetime, timezone
import sqlite3
import json
from typing import TypedDict, Annotated, Any, Optional, List
from pydantic import BaseModel, Field

# LangGraph
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

# Add architecture paths
current_dir = os.path.dirname(os.path.abspath(__file__))
arch_root = os.path.join(current_dir, '../../')
sys.path.insert(0, arch_root)

# Data Version Manager
from modules.utils.data_version_manager import DataVersionManager

# Import infrastructure layer
infra_base = __import__('modules.nodes.base_node', fromlist=['BaseNode'])
infra_image = __import__('modules.nodes.image_node', fromlist=['ImageNode'])
infra_video = __import__('modules.nodes.video_node', fromlist=['VideoNode'])
infra_audio = __import__('modules.nodes.audio_node', fromlist=['VoiceoverNode', 'VideoEditNode'])
BaseNode = infra_base.BaseNode
ImageNode = infra_image.ImageNode
VideoNode = infra_video.VideoNode
VoiceoverNode = infra_audio.VoiceoverNode
VideoEditNode = infra_audio.VideoEditNode

# Import business layer
biz_story = __import__('domain_components.analysis.story_analyzer', fromlist=['StoryAnalyzer'])
biz_storyboard = __import__('domain_components.generation.storyboard_designer', fromlist=['StoryboardDesigner'])
biz_story_monologue = __import__('domain_components.generation.story_monologue_designer', fromlist=['StoryMonologueDesigner'])

StoryAnalyzer = biz_story.StoryAnalyzer
StoryboardDesigner = biz_storyboard.StoryboardDesigner
StoryMonologueDesigner = biz_story_monologue.StoryMonologueDesigner


# Reducer function: replace old value with new value
def replace_value(left: Any, right: Any) -> Any:
    """Replace old value with new value, unless new value is None"""
    return right if right is not None else left


# Define WorkflowState schema for LangGraph
class WorkflowState(TypedDict, total=False):
    """State schema for story video creation workflow
    
    NOTE: Keys that match node names are NOT defined here (LangGraph handles them automatically).
    Node names are: story_analysis, character_generation, storyboard_design, image_generation, video_generation, story_tts, video_editing
    
    All intermediate fields must be defined here for LangGraph to merge them into state.
    """
    # Input
    story: Annotated[str, replace_value]
    target_duration: Annotated[int, replace_value]  # Target video duration in seconds (e.g., 30, 60, 90)
    video_duration_per_clip: Annotated[float, replace_value]  # Duration per video clip from model config
    
    # Extracted/derived data (shared between nodes)
    theme: Annotated[str, replace_value]
    mood: Annotated[str, replace_value]
    visual_style: Annotated[str, replace_value]
    protagonist: Annotated[str, replace_value]  # Main character name/description from story analysis
    characters: Annotated[list, replace_value]
    setting: Annotated[str, replace_value]
    scene_descriptions: Annotated[list, replace_value]  # Full scene objects from story analysis
    scene: Annotated[list, replace_value]  # Scene summaries (compatible field)
    
    storyboard: Annotated[list, replace_value]
    storyboard_frames: Annotated[list, replace_value]
    frame_count: Annotated[int, replace_value]
    
    character_image_path: Annotated[str, replace_value]  # Reference character image for consistency
    reference_image_path: Annotated[str, replace_value]  # Reference image for image generation (mapped from character_image_path)
    
    generated_images: Annotated[list, replace_value]
    generated_videos: Annotated[list, replace_value]
    monologue_text: Annotated[str, replace_value]
    voice_style: Annotated[str, replace_value]
    pacing: Annotated[str, replace_value]
    language: Annotated[str, replace_value]
    voiceover_path: Annotated[str, replace_value]
    final_video: Annotated[str, replace_value]  # Final edited video path
    
    # Control flow state
    _dirty_flags: Annotated[dict, replace_value]  # Track which fields have been modified


# ============================================================================
# Pydantic Input Models for Each Node (for dependency tracking)
# ============================================================================

class StoryAnalysisInput(BaseModel):
    """Input for story analysis node"""
    story: str = Field(description="Story content")

class CharacterGenerationInput(BaseModel):
    """Input for character image generation node"""
    story: str = Field(description="Story content")
    theme: Optional[str] = Field(None, description="Story theme")
    characters: Optional[list] = Field(None, description="Characters")
    visual_style: Optional[str] = Field(None, description="Visual style")
    setting: Optional[str] = Field(None, description="Setting")

class StoryboardDesignInput(BaseModel):
    """Input for storyboard design node"""
    story: str = Field(description="Story content")
    theme: Optional[str] = Field(None, description="Story theme")
    mood: Optional[str] = Field(None, description="Story mood")
    visual_style: Optional[str] = Field(None, description="Visual style")
    characters: Optional[list] = Field(None, description="Characters")
    setting: Optional[str] = Field(None, description="Setting")
    scene_descriptions: Optional[list] = Field(None, description="Scene descriptions from story analysis")
    scene: Optional[list] = Field(None, description="Scene summaries (compatible field)")

class ImageGenerationInput(BaseModel):
    """Input for image generation node"""
    storyboard: Optional[List] = Field(None, description="Storyboard")
    storyboard_frames: Optional[List] = Field(None, description="Storyboard frame list")
    reference_image_path: Optional[str] = Field(None, description="Reference character image path for consistency")

class VideoGenerationInput(BaseModel):
    """Input for video generation node"""
    generated_images: List = Field(description="Generated image list")
    storyboard: Optional[List] = Field(None, description="Storyboard")
    storyboard_frames: Optional[List] = Field(None, description="Storyboard frame list")

class StoryTTSInput(BaseModel):
    """Input for story TTS node"""
    story: str = Field(description="Story content")
    theme: Optional[str] = Field(None, description="Story theme")
    mood: Optional[str] = Field(None, description="Story mood")
    protagonist: Optional[str] = Field(None, description="Story protagonist")
    setting: Optional[str] = Field(None, description="Story setting")
    scene_descriptions: Optional[List] = Field(None, description="Scene descriptions from story analysis")
    storyboard: Optional[List] = Field(None, description="Storyboard frames")
    target_duration: Optional[int] = Field(None, description="Target video duration")

class VideoEditInput(BaseModel):
    """Input for video edit node"""
    generated_videos: List = Field(description="Generated video list")
    voiceover_path: Optional[str] = Field(None, description="Full voiceover path")

# Node input model mapping
NODE_INPUT_MODELS = {
    'story_analysis': StoryAnalysisInput,
    'character_generation': CharacterGenerationInput,
    'storyboard_design': StoryboardDesignInput,
    'image_generation': ImageGenerationInput,
    'video_generation': VideoGenerationInput,
    'story_tts': StoryTTSInput,
    'video_editing': VideoEditInput,
}


def _extract_file_paths_from_value(value) -> list:
    """Recursively extract all file path strings from value"""
    paths = []
    
    if isinstance(value, str):
        paths.append(value)
    elif isinstance(value, list):
        for item in value:
            paths.extend(_extract_file_paths_from_value(item))
    elif isinstance(value, dict):
        for v in value.values():
            paths.extend(_extract_file_paths_from_value(v))
    
    return paths


def _get_missing_files_for_node(node_instance, state: dict, node_name: str) -> list:
    """Check if node's output files exist"""
    if not node_instance or not hasattr(node_instance, 'get_output_fields'):
        return []
    
    try:
        output_fields = node_instance.get_output_fields()
        if not output_fields:
            return []
        
        all_paths = []
        empty_markers = []
        for field_name in output_fields:
            field_value = state.get(field_name)
            if field_value is None:
                continue

            if isinstance(field_value, list):
                for idx, item in enumerate(field_value):
                    if not item:
                        empty_markers.append(f"[{node_name}] {field_name}[{idx}] is empty")

            paths = _extract_file_paths_from_value(field_value)
            all_paths.extend(paths)
        
        missing = []
        missing.extend(empty_markers)
        for p in all_paths:
            if p is None:
                continue
            if isinstance(p, str) and p.strip() == "":
                missing.append(f"[{node_name}] empty path in output fields")
                continue
            if isinstance(p, str) and not os.path.exists(p):
                missing.append(p)
        return missing
        
    except Exception as e:
        print(f"⚠️  [{node_name}] Error checking files: {e}")
        return []


def wrap_node_with_dirty_check(node_func, node_name: str, node_instance=None):
    """
    Node wrapper: Automatically check dependencies and decide whether to force execution
    
    Logic:
    1. Get node's input dependencies from NODE_INPUT_MODELS
    2. Check if dependency fields are marked as dirty
    3. Check if output files previously produced by node still exist
    4. If any dependency is dirty or output files are missing, force execute the node
    5. After execution, clear processed dirty flags
    """
    input_model = NODE_INPUT_MODELS.get(node_name)
    depends_on = []
    if input_model:
        depends_on = list(input_model.model_fields.keys())
    
    def wrapped_node(state: dict) -> dict:
        force_execute = state.get('_force_execute', False)
        create_new_version = state.get('_create_new_version', False)
        dirty_flags = state.get('_dirty_flags', {}).copy()
        
        # Check if there are dirty elements in list fields
        has_dirty_elements = False
        if depends_on:
            for field in depends_on:
                field_value = state.get(field)
                if isinstance(field_value, list):
                    dirty_count = sum(1 for item in field_value if isinstance(item, dict) and item.get('_dirty', False))
                    if dirty_count > 0:
                        has_dirty_elements = True
                        print(f"🎯 [{node_name}] Detected {dirty_count} dirty element(s) in '{field}'")
                        break
        
        # Check 1: If any dependency field is dirty, force execution
        if not force_execute and not has_dirty_elements and depends_on:
            for field in depends_on:
                if dirty_flags.get(field, False):
                    print(f"🔄 [{node_name}] Detected modified dependency field '{field}', forcing re-execution")
                    force_execute = True
                    break
        
        # Check 2: If files previously produced by node don't exist, force execution
        if not force_execute and not has_dirty_elements:
            missing_files = _get_missing_files_for_node(node_instance, state, node_name)
            
            if missing_files:
                print(f"🔄 [{node_name}] Detected {len(missing_files)} missing output files, forcing re-execution")
                for f in missing_files[:3]:
                    print(f"   ❌ Missing: {os.path.basename(f)}")
                if len(missing_files) > 3:
                    print(f"   ... and {len(missing_files) - 3} more files")
                force_execute = True
        
        # If has_dirty_elements, enable fine-grained execution
        if has_dirty_elements:
            print(f"   ✅ Fine-grained mode enabled for [{node_name}]")
            force_execute = False
        
        # Execute node
        result = node_func(state, force_execute=force_execute, create_new_version=create_new_version)
        
        # Clear processed dirty flags
        if result and depends_on:
            for field in depends_on:
                if field in dirty_flags:
                    dirty_flags.pop(field, None)
            
            result['_dirty_flags'] = dirty_flags
        
        return result
    
    return wrapped_node


def build_app(task_path: str = None, compile_graph: bool = True, workflow_config_path: str = None, resume: bool = None):
    """
    Build LangGraph workflow application
    
    Automatically detects whether to resume from checkpoint or create new task:
    - If task_path exists and has checkpoint: resume from checkpoint
    - If task_path doesn't exist or has no checkpoint: create new task
    - If task_path is None: auto-generate new task path
    
    Args:
        task_path: Path to task directory
        compile_graph: If False, return uncompiled graph (for visualization)
        workflow_config_path: Path to workflow config file (optional)
        resume: [DEPRECATED] Auto-detected based on task_path and checkpoint
    
    Returns:
        If compile_graph=True: (app, task_path, config_manager)
        If compile_graph=False: graph object
    """
    # Auto-detect resume mode
    resume = False
    if task_path and os.path.exists(task_path):
        checkpoint_db = os.path.join(task_path, 'checkpoints.sqlite')
        resume = os.path.exists(checkpoint_db)
        if resume:
            print(f"🔍 Auto-detected: task_path exists with checkpoint, using resume mode")
    
    # Determine task path
    if resume:
        if not task_path:
            raise ValueError("task_path is required for resume mode")
        if not os.path.exists(task_path):
            raise FileNotFoundError(f"Cannot resume: task path not found: {task_path}")
        checkpoint_db = os.path.join(task_path, 'checkpoints.sqlite')
        if not os.path.exists(checkpoint_db):
            raise FileNotFoundError(f"Cannot resume: checkpoint not found at {checkpoint_db}")
        print(f"📂 Resuming from existing task: {task_path}")
    else:
        if not task_path:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            task_path = os.path.join('task_data', f"story_video_langgraph_{timestamp}")
        os.makedirs(task_path, exist_ok=True)
        print(f"📁 Created new task directory: {task_path}")
    
    # Initialize configuration manager
    from config_manager import ConfigManager
    config_manager = ConfigManager(task_path, workflow_config_path)
    
    # Instantiate real nodes
    story_analyzer = StoryAnalyzer.create_node('story_analysis', task_path)
    character_generator = ImageNode('character_generation', task_path)
    storyboard_designer = StoryboardDesigner.create_node('storyboard_design', task_path)
    image_generator = ImageNode('image_generation', task_path)
    video_generator = VideoNode('video_generation', task_path)
    story_monologue_designer = StoryMonologueDesigner.create_node('story_tts_text', task_path)
    voiceover_generator = VoiceoverNode('tts', task_path)
    video_editor = VideoEditNode('video_editing', task_path)
    
    # Set config_manager for GenModelNodes
    character_generator.set_config_manager(config_manager)
    image_generator.set_config_manager(config_manager)
    video_generator.set_config_manager(config_manager)
    voiceover_generator.set_config_manager(config_manager)
    # Note: VideoEditNode doesn't need config_manager (it's a tool node, not a model node)
    
    # Register node instances
    node_registry = {
        'story_analysis': story_analyzer,
        'character_generation': character_generator,
        'storyboard_design': storyboard_designer,
        'image_generation': image_generator,
        'video_generation': video_generator,
        'story_tts': voiceover_generator,
        'video_editing': video_editor,
    }

    # Configure infra defaults
    workflow_config = config_manager.workflow_config
    image_gen_config = workflow_config.get('image_generation', {})
    video_gen_config = workflow_config.get('video_generation', {})
    tts_config = workflow_config.get('tts', {})
    
    # Configure all image/video generators with their models
    character_generator.configure(default_model=image_gen_config.get('model', 'bytedance/seedream-4.5'))
    image_generator.configure(default_model=image_gen_config.get('model', 'bytedance/seedream-4.5'))
    # video_generator.configure(default_model=video_gen_config.get('model', 'lucataco/wan-2.2-first-last-frame:003fd8a38ff17cb6022c3117bb90f7403cb632062ba2b098710738d116847d57'))
    video_generator.configure(default_model=video_gen_config.get('model', 'google/veo-3.1-fast'))
    voiceover_generator.configure(default_model=tts_config.get('model', 'minimax/speech-02-hd'), voice=tts_config.get('parameters', {}).get('voice_id'))

    # Node wrappers for LangGraph
    def node_story_analysis(state: dict, force_execute=False, create_new_version=False) -> dict:
        state_with_options = {**state, '_force_execute': force_execute, '_create_new_version': create_new_version}
        result = story_analyzer(state_with_options)
        if 'story_analysis' in result:
            return result['story_analysis']
        return result

    def node_character_generation(state: dict, force_execute=False, create_new_version=False) -> dict:
        """Generate a single character reference image for consistency across all frames"""
        
        # Check if user already uploaded a character image — skip generation if so
        character_dir = os.path.join(task_path, 'character_reference')
        if os.path.isdir(character_dir):
            for fname in os.listdir(character_dir):
                fpath = os.path.join(character_dir, fname)
                if os.path.isfile(fpath) and not fname.startswith('.'):
                    print(f"✅ User-uploaded character image found: {fpath} — skipping generation")
                    return {
                        'character_image_path': fpath,
                        'reference_image_path': fpath,
                    }
        
        state_with_options = {**state, '_force_execute': force_execute, '_create_new_version': create_new_version}
        
        # Get protagonist from story analysis (now directly provided by StoryAnalyzer)
        protagonist = state.get('protagonist', '')
        visual_style = state.get('visual_style', '')
        setting = state.get('setting', '')
        
        # Build character prompt
        if protagonist:
            prompt = f"A full body portrait of {protagonist}"
            if visual_style:
                prompt += f", {visual_style}"
            if setting:
                # Extract general setting (e.g., "mystical forest" from scene)
                prompt += f", fantasy adventure setting"
        else:
            # Fallback prompt
            prompt = f"A fantasy adventure character portrait"
            if visual_style:
                prompt += f", {visual_style}"
        
        # Create dedicated directory for character reference image
        character_dir = os.path.join(task_path, 'character_reference')
        os.makedirs(character_dir, exist_ok=True)
        character_image_path = os.path.join(character_dir, 'character.png')
        
        # Provide image_descriptions directly to avoid sub_video_0 conflict
        # Use same path for both first/last - ImageNode will skip last if first already exists
        state_with_options['image_descriptions'] = [{
            'first_image': {
                'prompt': prompt,
                'output_path': character_image_path
            },
            'last_image': {
                'prompt': prompt,
                'output_path': character_image_path  # Same path - will reuse first image
            }
        }]
        
        print(f"🎨 Generating character reference image")
        print(f"   Protagonist: {protagonist or 'generic character'}")
        print(f"   Prompt: {prompt}")
        print(f"   Save path: {character_image_path}")
        print(f"🔍 image_descriptions being passed: {state_with_options['image_descriptions']}")
        
        result = character_generator(state_with_options)
        
        # Debug: Print the full result to see what we got
        print(f"🔍 Character generation result keys: {result.keys() if isinstance(result, dict) else 'not a dict'}")
        if isinstance(result, dict) and 'character_generation' in result:
            char_gen_result = result['character_generation']
            print(f"🔍 character_generation content: {char_gen_result}")
            if 'generated_images' in char_gen_result:
                print(f"🔍 generated_images: {char_gen_result['generated_images']}")
        
        # Extract the generated character image path and store it
        updates = {}
        if 'character_generation' in result:
            char_result = result['character_generation']
            generated_images = char_result.get('generated_images', [])
            character_image = None

            if generated_images:
                first_entry = generated_images[0]
                # ImageNode returns [first_path, last_path]
                if isinstance(first_entry, (list, tuple)) and first_entry:
                    character_image = first_entry[0]
                elif isinstance(first_entry, dict):
                    # In some cases ImageNode may return dicts
                    character_image = first_entry.get('first_image') or first_entry.get('image')
                elif isinstance(first_entry, str):
                    character_image = first_entry

            if character_image:
                updates['character_image_path'] = character_image
                updates['reference_image_path'] = character_image  # Also set as reference
                print(f"✅ Character image generated: {character_image}")
            else:
                print(f"⚠️ No usable character image found in generated_images: {generated_images}")
            return {**char_result, **updates}
        else:
            print(f"⚠️ No 'character_generation' key in result")
        
        return result

    def node_storyboard_design(state: dict, force_execute=False, create_new_version=False) -> dict:
        state_with_options = {**state, '_force_execute': force_execute, '_create_new_version': create_new_version}
        result = storyboard_designer(state_with_options)
        
        # Initialize DataVersionManager with storyboard structure
        if 'storyboard_design' in result:
            sb_data = result['storyboard_design']
            sb = sb_data.get('storyboard') or sb_data.get('storyboard_frames')
            if sb:
                try:
                    dvm = DataVersionManager(task_path)
                    dvm.initialize_from_storyboard(sb, global_assets=['voiceover', 'final_video'], segment_assets=['image_first', 'image_last', 'video'])
                    print(f"📦 Initialized data versioning for {len(sb)} segments with global voiceover support")
                except Exception as e:
                    print(f"⚠️ Failed to initialize data versioning: {e}")
        
        if 'storyboard_design' in result:
            return result['storyboard_design']
        return result

    def node_image_generation(state: dict, force_execute=False, create_new_version=False) -> dict:
        """Generate storyboard images using character image as reference for consistency"""
        state_with_options = {**state, '_force_execute': force_execute, '_create_new_version': create_new_version}
        updates = {}
        
        # Map character_image_path to reference_image_path for ImageNode
        character_image_path = state.get('character_image_path')
        
        # Create node inputs with explicit reference image mapping
        node_inputs = state_with_options.copy()
        if character_image_path:
            # Inject character image as reference image for this node execution
            node_inputs['reference_image_path'] = [character_image_path]  # ImageNode expects a list
            # Also update output state for consistency
            updates['reference_image_path'] = character_image_path
            print(f"🎨 Using character reference image: {character_image_path}")
        
        result = image_generator(node_inputs)
        if 'image_generation' in result:
            updates.update(result['image_generation'])
        else:
            updates.update(result)
        
        return updates

    def node_video_generation(state: dict, force_execute=False, create_new_version=False) -> dict:
        state_with_options = {**state, '_force_execute': force_execute, '_create_new_version': create_new_version}
        
        # Load current images from DataVersionManager
        dvm = DataVersionManager(task_path)
        current_imgs = []
        
        # Determine number of segments
        num_segments = 0
        if state.get('storyboard'):
            num_segments = len(state.get('storyboard'))
        elif state.get('storyboard_frames'):
            num_segments = len(state.get('storyboard_frames'))
        elif state.get('generated_images'):
            num_segments = len(state.get('generated_images'))
        else:
            raise ValueError(
                "[Video Gen] Cannot determine num_segments. "
                "Expected one of state['storyboard'], state['storyboard_frames'], or state['generated_images']."
            )

        print(f"🔍 [Video Gen] Looking for {num_segments} images in DataVersionManager")

        skipped_segments = []
        for i in range(num_segments):
            img_first_raw = dvm.get_current_version([f'sub_video_{i}', 'image_first'])
            img_last_raw = dvm.get_current_version([f'sub_video_{i}', 'image_last'])

            if not img_first_raw:
                img_first_raw = dvm.get_current_version([f'sub_video_{i}', 'image'])

            # Check image_first (required)
            if not img_first_raw or not isinstance(img_first_raw, str):
                print(f"⚠️  [Video Gen] Missing image_first for sub_video_{i}, skipping this segment")
                skipped_segments.append(i)
                current_imgs.append(None)
                continue
            if not os.path.isabs(img_first_raw):
                print(f"⚠️  [Video Gen] image_first path is not absolute for sub_video_{i}: {img_first_raw}, skipping")
                skipped_segments.append(i)
                current_imgs.append(None)
                continue
            if not os.path.exists(img_first_raw):
                print(f"⚠️  [Video Gen] image_first file does not exist for sub_video_{i}: {img_first_raw}, skipping")
                skipped_segments.append(i)
                current_imgs.append(None)
                continue

            # Check image_last (use image_first as fallback)
            use_first_as_last = False
            if not img_last_raw or not isinstance(img_last_raw, str):
                print(f"⚠️  [Video Gen] Missing image_last for sub_video_{i}, using image_first as fallback")
                img_last_raw = img_first_raw
                use_first_as_last = True
            elif not os.path.isabs(img_last_raw):
                print(f"⚠️  [Video Gen] image_last path is not absolute for sub_video_{i}: {img_last_raw}, using image_first as fallback")
                img_last_raw = img_first_raw
                use_first_as_last = True
            elif not os.path.exists(img_last_raw):
                print(f"⚠️  [Video Gen] image_last file does not exist for sub_video_{i}: {img_last_raw}, using image_first as fallback")
                img_last_raw = img_first_raw
                use_first_as_last = True

            if use_first_as_last:
                print(f"   ℹ️  Note: Video for sub_video_{i} will have same start/end frame")

            current_imgs.append([img_first_raw, img_last_raw])

        # Check if we have at least one valid segment
        valid_segments = [img for img in current_imgs if img is not None]
        if len(valid_segments) == 0:
            raise ValueError(f"[Video Gen] No valid image pairs found. All {num_segments} segments are missing images.")
        
        if skipped_segments:
            print(f"⚠️  [Video Gen] Skipped segments due to missing image_first: {skipped_segments}")

        print(f"📦 Loaded {len(valid_segments)} valid image pairs from version manager (total segments: {num_segments})")
        state_with_options['generated_images'] = current_imgs
        state_with_options['skipped_video_segments'] = skipped_segments

        result = video_generator(state_with_options)

        if 'video_generation' in result:
            return result['video_generation']
        return result

    def node_story_tts(state: dict, force_execute=False, create_new_version=False) -> dict:
        state_with_options = {**state, '_force_execute': force_execute, '_create_new_version': create_new_version}

        monologue_result = story_monologue_designer(state_with_options)
        updates = monologue_result.get('story_tts_text', monologue_result) if isinstance(monologue_result, dict) else {}

        tts_inputs = state_with_options.copy()
        tts_inputs.update(updates)
        tts_overrides = dict(tts_config.get('parameters', {}))
        if tts_overrides:
            tts_inputs['tts'] = tts_overrides

        tts_result = voiceover_generator(tts_inputs)
        if 'tts' in tts_result:
            updates.update(tts_result['tts'])
        else:
            updates.update(tts_result)

        return updates

    def node_edit(state: dict, force_execute=False, create_new_version=False) -> dict:
        state_with_options = {**state, '_force_execute': force_execute, '_create_new_version': create_new_version}
        
        # Load generated videos from DataVersionManager
        try:
            dvm = DataVersionManager(task_path)
            
            # Load videos - check folders until we find one that doesn't exist
            valid_vids = []
            
            for i in range(100):  # Reasonable limit
                # Check if sub_video_i folder exists
                sub_video_dir = os.path.join(task_path, f'sub_video_{i}')
                if not os.path.exists(sub_video_dir):
                    print(f"📦 Stopped at sub_video_{i} (folder doesn't exist)")
                    break
                
                # Get video for this segment
                vid = dvm.get_current_version([f'sub_video_{i}', 'video'])
                
                # Only include if video exists
                if vid and isinstance(vid, str) and os.path.exists(vid):
                    valid_vids.append(vid)
                    print(f"📦 Loaded segment {i}: video")
                else:
                    print(f"⚠️ Skipping segment {i}: missing or invalid video")
                    # Continue checking remaining folders
            
            if valid_vids:
                state_with_options['generated_videos'] = valid_vids
                print(f"📦 Loaded {len(valid_vids)} videos from version manager")

            voiceover_path = dvm.get_current_version(['voiceover'])
            if voiceover_path and isinstance(voiceover_path, str) and os.path.exists(voiceover_path):
                state_with_options['voiceover_path'] = voiceover_path
                print(f"📦 Loaded full voiceover from version manager: {voiceover_path}")
                    
        except Exception as e:
            print(f"⚠️ Failed to load videos from version manager: {e}")
            print("❌ CRITICAL: Could not load assets from DataVersionManager! Using state fallback.")
        
        result = video_editor(state_with_options)
        
        # Note: DataVersionManager updates are now handled automatically by GenModelNode/VideoEditNode
        
        if 'video_editing' in result:
            return result['video_editing']
        return result

    # Build graph
    graph_builder = StateGraph(WorkflowState)
    
    # Add nodes (wrapped with dirty check)
    graph_builder.add_node('story_analysis', wrap_node_with_dirty_check(node_story_analysis, 'story_analysis', story_analyzer))
    graph_builder.add_node('character_generation', wrap_node_with_dirty_check(node_character_generation, 'character_generation', character_generator))
    graph_builder.add_node('storyboard_design', wrap_node_with_dirty_check(node_storyboard_design, 'storyboard_design', storyboard_designer))
    graph_builder.add_node('image_generation', wrap_node_with_dirty_check(node_image_generation, 'image_generation', image_generator))
    graph_builder.add_node('video_generation', wrap_node_with_dirty_check(node_video_generation, 'video_generation', video_generator))
    graph_builder.add_node('story_tts', wrap_node_with_dirty_check(node_story_tts, 'story_tts', voiceover_generator))
    graph_builder.add_node('video_editing', wrap_node_with_dirty_check(node_edit, 'video_editing', video_editor))
    
    # Add edges (linear workflow)
    graph_builder.add_edge(START, 'story_analysis')
    graph_builder.add_edge('story_analysis', 'character_generation')
    graph_builder.add_edge('character_generation', 'storyboard_design')
    graph_builder.add_edge('storyboard_design', 'image_generation')
    graph_builder.add_edge('image_generation', 'video_generation')
    graph_builder.add_edge('video_generation', 'story_tts')
    graph_builder.add_edge('story_tts', 'video_editing')
    graph_builder.add_edge('video_editing', END)
    
    if not compile_graph:
        return graph_builder
    
    # Compile graph with checkpoint support
    checkpoint_db = os.path.join(task_path, 'checkpoints.sqlite')
    # Create connection and SqliteSaver instance
    conn = sqlite3.connect(checkpoint_db, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    print(f"💾 Checkpoint database: {checkpoint_db}")
    app = graph_builder.compile(checkpointer=checkpointer)
    
    # Attach node registry to app
    app._node_registry = node_registry
    app._task_path = task_path
    app._config_manager = config_manager
    
    return app, task_path, config_manager


def get_dirty_flags_path(task_path: str) -> str:
    """Get path to dirty flags JSON file"""
    return os.path.join(task_path, 'dirty_flags.json')


def save_dirty_flags(task_path: str, dirty_flags: dict):
    """Save dirty flags to JSON file"""
    if not dirty_flags:
        dirty_file = get_dirty_flags_path(task_path)
        if os.path.exists(dirty_file):
            os.remove(dirty_file)
            print(f"🧹 Cleaned up dirty flags file: {os.path.basename(dirty_file)}")
        return
    
    dirty_file = get_dirty_flags_path(task_path)
    with open(dirty_file, 'w', encoding='utf-8') as f:
        json.dump(dirty_flags, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved dirty flags to: {os.path.basename(dirty_file)}")


def load_dirty_flags(task_path: str) -> dict:
    """Load dirty flags from JSON file"""
    dirty_file = get_dirty_flags_path(task_path)
    if not os.path.exists(dirty_file):
        return {}
    
    try:
        with open(dirty_file, 'r', encoding='utf-8') as f:
            dirty_flags = json.load(f)
        print(f"📂 Loaded dirty flags: {len(dirty_flags)} fields marked")
        return dirty_flags
    except Exception as e:
        print(f"⚠️  Failed to load dirty flags: {e}")
        return {}


def run_workflow(task_path: str = None, story: str = None, workflow_config_path: str = None, rerun: bool = None, target_duration: int = 60):
    """
    Run story video workflow
    
    Automatically detects whether to resume from checkpoint or create new task:
    - If task_path exists and has checkpoint: resume from checkpoint
    - If task_path doesn't exist or has no checkpoint: create new task
    
    Args:
        task_path: Task directory path (optional, auto-generated if not provided)
        story: Story content (required for new tasks, optional for resume)
        workflow_config_path: Workflow config file path (optional)
        rerun: [DEPRECATED] Auto-detected based on task_path and checkpoint existence.
        target_duration: Target video duration in seconds (default: 60)
    
    Returns:
        Final state dictionary
    """
    import hashlib
    
    # Check if we're in resume mode (BEFORE build_app potentially creates the file)
    checkpoint_db = None
    is_resume_mode = False
    if task_path:
        checkpoint_db = os.path.join(task_path, 'checkpoints.sqlite')
        is_resume_mode = os.path.exists(checkpoint_db)
    
    # Build app
    app, actual_task_path, config_manager = build_app(task_path=task_path, workflow_config_path=workflow_config_path)
    
    # Ensure each task has a workflow_config.json under its directory
    cfg_path = os.path.join(actual_task_path, 'workflow_config.json')
    try:
        if workflow_config_path and os.path.exists(workflow_config_path):
            with open(workflow_config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f) or {}
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            config_manager.workflow_config = cfg
            print(f"📝 Persisted provided workflow config → {cfg_path}")
        else:
            if not os.path.exists(cfg_path):
                template_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    'config', 'story_workflow_config_template.json'
                )
                default_cfg = {}
                if os.path.exists(template_path):
                    with open(template_path, 'r', encoding='utf-8') as f:
                        default_cfg = json.load(f) or {}
                
                with open(cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(default_cfg, f, indent=2, ensure_ascii=False)
                config_manager.workflow_config = default_cfg
                print(f"📝 Created default workflow config → {cfg_path}")
    except Exception as e:
        print(f"⚠️  Failed to ensure workflow_config.json: {e}")
    
    # Generate stable thread_id based on task_path
    thread_id = hashlib.md5(actual_task_path.encode()).hexdigest()[:16]
    
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 50
    }
    
    # Get duration parameters from config
    workflow_config = config_manager.workflow_config
    cfg_target_duration = workflow_config.get('global_settings', {}).get('target_duration', target_duration)
    video_clip_duration = workflow_config.get('video_generation', {}).get('parameters', {}).get('duration', 8)
    
    node_registry = getattr(app, '_node_registry', {})
    
    if is_resume_mode:
        print(f"📁 Task directory (LangGraph): {actual_task_path}")
        print(f"🔑 Thread ID: {thread_id}")
        print("♻️  Resuming workflow from checkpoint...")
        
        # Update state with provided inputs if any
        state_updates = {}
        if story:
            state_updates['story'] = story
            print(f"📝 Updating story in state")
        
        # Load dirty flags (if exist)
        dirty_flags = load_dirty_flags(actual_task_path)
        if dirty_flags:
            state_updates['_dirty_flags'] = dirty_flags
        
        # Inject duration parameters
        state_updates['target_duration'] = cfg_target_duration
        state_updates['video_duration_per_clip'] = video_clip_duration
        
        # Apply all state updates at once
        if state_updates:
            app.update_state(config, state_updates)
        
        # Check if any nodes need re-execution
        current_state = app.get_state(config)
        needs_rerun = False
        
        # Reason 1: Check dirty flags
        if dirty_flags:
            print(f"🔄 Detected {len(dirty_flags)} fields marked as modified")
            for field_name in list(dirty_flags.keys())[:3]:
                print(f"   🏷️  {field_name}")
            if len(dirty_flags) > 3:
                print(f"   ... and {len(dirty_flags) - 3} more fields")
            needs_rerun = True
        
        # Reason 2: Check for missing files
        for node_name, node_instance in node_registry.items():
            if not node_instance:
                continue
            
            missing_files = _get_missing_files_for_node(node_instance, current_state.values, node_name)
            
            if missing_files:
                print(f"🔄 Detected {len(missing_files)} missing output files for node [{node_name}]")
                for f in missing_files[:2]:
                    print(f"   ❌ {os.path.basename(f) if isinstance(f, str) else f}")
                if len(missing_files) > 2:
                    print(f"   ... and {len(missing_files) - 2} more files")
                needs_rerun = True
                # Mark first dependency field as dirty to trigger re-execution
                input_model = NODE_INPUT_MODELS.get(node_name)
                if input_model:
                    first_dep = list(input_model.model_fields.keys())[0] if input_model.model_fields else None
                    if first_dep:
                        dirty_flags[first_dep] = True
                        print(f"   → Mark {first_dep} as dirty to trigger re-execution")
        
        # Reload workflow config if it exists in task_path (may have been updated)
        try:
            task_config_path = os.path.join(actual_task_path, 'workflow_config.json')
            if workflow_config_path and os.path.exists(workflow_config_path):
                config_manager.workflow_config_path = workflow_config_path
                config_manager.workflow_config = config_manager._load_workflow_config()
            elif os.path.exists(task_config_path):
                config_manager.workflow_config_path = None
                config_manager.workflow_config = config_manager._load_workflow_config()
        except Exception as e:
            print(f"⚠️  Failed to reload workflow config: {e}")
        
        # If need to rerun, reset execution position to start node
        if needs_rerun:
            app.update_state(config, {'_dirty_flags': dirty_flags}, as_node='__start__')
            print(f"\n🔄 Re-execute workflow from start node\n")
        else:
            print(f"✅ No need to re-execute, all files complete and no modifications")
        
        # Final check: Ensure story exists in state
        current_state = app.get_state(config)
        state_values = current_state.values
        
        if not state_values.get('story'):
            if story:
                app.update_state(config, {'story': story})
                print(f"📝 Injected story into state (safety check)")
            else:
                raise ValueError("Cannot resume: story not found in checkpoint and not provided")
        
        # Rerun with None as initial state - LangGraph will use checkpoint
        final_state = app.invoke(None, config=config)
    else:
        # Validate inputs for new task
        if not story:
            raise ValueError("story is required for new task")
        
        print("🚀 Starting Story Video Workflow...")
        print(f"📖 Story: {story[:100]}..." if len(story) > 100 else f"📖 Story: {story}")
        print("-" * 70)
        print(f"🎯 Target Duration: {cfg_target_duration} seconds")
        print(f"📹 Video Clip Duration: {video_clip_duration} seconds (from model config)")
        print(f"🎬 Calculated Frames: {max(3, min(8, int(cfg_target_duration / video_clip_duration + 0.5)))}")
        print("-" * 70)
        
        # Initialize state
        initial_state = {
            'story': story,
            'target_duration': cfg_target_duration,
            'video_duration_per_clip': video_clip_duration,
            '_dirty_flags': {}
        }
        
        print(f"📁 Task directory (LangGraph): {actual_task_path}")
        print(f"🔑 Thread ID: {thread_id}")
        print("🚀 Running LangGraph workflow...")
        final_state = app.invoke(initial_state, config=config)
    
    # Clean up dirty flags after workflow completion
    if '_dirty_flags' in final_state and final_state['_dirty_flags']:
        print("🧹 Cleaning modification flags...")
        save_dirty_flags(actual_task_path, {})
        app.update_state(config, {'_dirty_flags': {}})
        final_state = app.get_state(config).values
    
    # Save configuration records
    config_manager.save_records()
    
    # Create completion marker
    with open(os.path.join(actual_task_path, '__complete__'), 'w') as f:
        f.write('done')
    
    print("✅ Story Video Workflow completed.")
    print(f"💾 Results saved in: {actual_task_path}")
    return final_state


def get_task_state(task_path: str, workflow_config_path: str = None):
    """
    Get current state of a task (for viewing and modification)
    
    Args:
        task_path: Task path
        workflow_config_path: Optional workflow config path
    
    Returns:
        (app, config, state, task_path, config_manager) tuple
    """
    import hashlib
    
    if not os.path.exists(task_path):
        raise FileNotFoundError(f"Task path not found: {task_path}")
    
    # Determine workflow_config_path priority
    if not workflow_config_path and task_path:
        task_config_path = os.path.join(task_path, 'workflow_config.json')
        if os.path.exists(task_config_path):
            workflow_config_path = task_config_path
    
    # Build app in resume mode
    app, actual_task_path, config_manager = build_app(task_path=task_path, workflow_config_path=workflow_config_path)
    
    thread_id = hashlib.md5(actual_task_path.encode()).hexdigest()[:16]
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 50
    }
    
    # Load dirty flags (if exist)
    dirty_flags = load_dirty_flags(actual_task_path)
    if dirty_flags:
        app.update_state(config, {'_dirty_flags': dirty_flags})
    
    state = app.get_state(config)
    return app, config, state, actual_task_path, config_manager


def edit_state(app, config, task_path: str = None, mark_dirty: bool = False, **field_updates):
    """
    Generic state editing interface - can edit any field and optionally mark as dirty
    
    Args:
        app: Compiled LangGraph application
        config: Configuration dictionary (includes thread_id)
        task_path: Task path (for saving dirty flags)
        mark_dirty: Whether to mark modified fields as dirty (default: False)
        **field_updates: Fields to update, using keyword arguments
    """
    if not field_updates:
        print("⚠️  No fields provided for update")
        return
    
    # Get current state
    current_state = app.get_state(config)
    dirty_flags = current_state.values.get('_dirty_flags', {})
    
    # Mark all updated fields as dirty (top-level) if requested
    if mark_dirty:
        for field_name in field_updates.keys():
            dirty_flags[field_name] = True
            print(f"🏷️  Marked field as modified: {field_name}")
    
    # Deep process list fields to embed element-level dirty for fine-grained incremental
    updates = dict(field_updates)
    for field_name, new_value in list(field_updates.items()):
        try:
            old_value = current_state.values.get(field_name)
            if isinstance(old_value, list) and isinstance(new_value, list):
                old_len = len(old_value)
                new_len = len(new_value)
                if old_len == new_len:
                    for i in range(new_len):
                        old_item = old_value[i]
                        new_item = new_value[i]
                        if isinstance(old_item, dict) and isinstance(new_item, dict):
                            if old_item != new_item and not new_item.get('_dirty'):
                                new_value[i] = {**new_item, '_dirty': True}
                    updates[field_name] = new_value
        except Exception:
            pass
    
    updates['_dirty_flags'] = dirty_flags
    app.update_state(config, updates)
    
    # Persist dirty flags
    if task_path and mark_dirty:
        save_dirty_flags(task_path, dirty_flags)
    
    print(f"✅ Updated {len(field_updates)} field(s) in state")


def execute_single_node(app, config, node_name: str, task_path: str = None, create_new_version: bool = True, mark_dirty: bool = False):
    """
    Execute ONLY a single node independently without executing downstream nodes
    
    Args:
        app: Compiled LangGraph application
        config: Configuration dictionary (includes thread_id)
        node_name: Name of node to execute
        task_path: Task path (for persisting dirty flags)
        create_new_version: If True, create versioned output files
        mark_dirty: Whether to mark output fields as dirty
    
    Returns:
        Updated state values after node execution
    """
    print(f"🎯 Executing ONLY single node: {node_name}")
    
    # Get dependency and output info for this node
    input_model = NODE_INPUT_MODELS.get(node_name)
    depends_on = []
    if input_model:
        depends_on = list(input_model.model_fields.keys())
        print(f"   Dependencies: {', '.join(depends_on)}")
    
    node_instance = getattr(app, '_node_registry', {}).get(node_name)
    output_fields = []
    if node_instance and hasattr(node_instance, 'get_output_fields'):
        output_fields = node_instance.get_output_fields()
        print(f"   Outputs: {', '.join(output_fields)}")
    
    # Get current state
    current_state = app.get_state(config)
    state_values = current_state.values.copy()
    
    # Check if there are dirty elements in list fields (embedded dirty flags)
    has_dirty_elements = False
    for key, value in state_values.items():
        if isinstance(value, list):
            dirty_count = sum(1 for item in value if isinstance(item, dict) and item.get('_dirty', False))
            if dirty_count > 0:
                has_dirty_elements = True
                print(f"   🎯 Found {dirty_count} dirty element(s) in '{key}'")
                break
    
    if has_dirty_elements:
        print(f"   🎯 Fine-grained mode: dirty elements detected, node will handle incrementally")
        state_values['_force_execute'] = False
    else:
        print(f"   ♻️  No element-level dirty: letting node use cache/missing detection")
        state_values['_force_execute'] = False
    
    state_values['_create_new_version'] = create_new_version
    
    # Load workflow config and assemble node runtime params for this task
    try:
        if task_path:
            from config_manager import ConfigManager
            task_config_path = os.path.join(task_path, 'workflow_config.json')
            wf_config_path = task_config_path if os.path.exists(task_config_path) else None
            
            _cm = ConfigManager(task_path, workflow_config_path=wf_config_path)
            node_registry = getattr(app, '_node_registry', {})
            
            # Update node instance with new ConfigManager
            if node_instance and hasattr(node_instance, 'set_config_manager'):
                node_instance.set_config_manager(_cm)
                print(f"   🔄 Updated ConfigManager for node '{node_name}'")
                
            print(f"   📋 Loaded workflow config for node execution")
    except Exception as e:
        print(f"⚠️  Failed to load workflow config: {e}")
    
    print(f"   🔄 Executing node function...")
    
    if not node_instance:
        print(f"   ⚠️  Node instance not found for '{node_name}'")
        return state_values
    
    try:
        # Call the node instance directly with current state
        result = node_instance(state_values)
        
        # Extract the node's output using the actual instance name
        result_key = getattr(node_instance, 'name', None) or node_name
        if result_key in result:
            node_output = result[result_key]
            print(f"   ✅ Node executed successfully")
            
            # Update state with node output
            if isinstance(node_output, dict):
                state_values.update(node_output)
            else:
                state_values[result_key] = node_output
        else:
            print(f"   ⚠️  No output found in result for '{node_name}' (looked for key '{result_key}')")
    except Exception as e:
        print(f"   ❌ Node execution failed: {e}")
        import traceback
        traceback.print_exc()
        return state_values
    
    # Update dirty flags
    dirty_flags = state_values.get('_dirty_flags', {}).copy()
    
    # Clean up force execute flag
    if '_force_execute' in dirty_flags:
        del dirty_flags['_force_execute']
    state_values.pop('_force_execute', None)
    state_values.pop('_create_new_version', None)
    
    # Clear dirty flags for this node's dependency fields (processed)
    if depends_on:
        for field in depends_on:
            if field in dirty_flags:
                dirty_flags.pop(field, None)
                print(f"   ✓ Cleared dirty flag for dependency field '{field}'")
    
    # Mark this node's output fields as dirty (output changed, downstream needs re-execution)
    if output_fields and mark_dirty:
        for field in output_fields:
            dirty_flags[field] = True
            print(f"   🏷️  Marked output field '{field}' as dirty (downstream nodes need re-execution)")
    
    # Update state in checkpoint
    state_values['_dirty_flags'] = dirty_flags
    app.update_state(config, state_values)
    
    # Persist dirty flags
    if task_path and mark_dirty:
        save_dirty_flags(task_path, dirty_flags)
        print(f"   💾 Saved dirty flags to {os.path.basename(get_dirty_flags_path(task_path))}")
    
    print(f"✅ Node '{node_name}' execution completed (ONLY this node, downstream not executed)")
    
    # Return updated state
    return app.get_state(config).values


def list_tasks(base_dir: str = 'task_data'):
    """List all available tasks"""
    if not os.path.exists(base_dir):
        print(f"No tasks found in {base_dir}")
        return []
    
    tasks = []
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path) and item.startswith('story_video'):
            checkpoint_db = os.path.join(item_path, 'checkpoints.sqlite')
            has_checkpoint = os.path.exists(checkpoint_db)
            is_complete = os.path.exists(os.path.join(item_path, '__complete__'))
            tasks.append({
                'name': item,
                'path': item_path,
                'has_checkpoint': has_checkpoint,
                'is_complete': is_complete
            })
    
    if tasks:
        print(f"\n📋 Found {len(tasks)} story video tasks:")
        for task in tasks:
            status = "✅ Complete" if task['is_complete'] else "🔄 In Progress"
            checkpoint = "📦 Has checkpoint" if task['has_checkpoint'] else "❌ No checkpoint"
            print(f"  {task['name']}: {status}, {checkpoint}")
            print(f"    Path: {task['path']}")
    else:
        print(f"No story video tasks found in {base_dir}")
    
    return tasks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Story Video Workflow - LangGraph Version')
    parser.add_argument('--story', type=str, help='Story content')
    parser.add_argument('--story-file', type=str, help='Path to file containing story text')
    parser.add_argument('--task-path', type=str, help='Task path')
    parser.add_argument('--config', type=str, help='Workflow config file path')
    parser.add_argument('--target-duration', type=int, default=60, help='Target video duration in seconds')
    parser.add_argument('--test', action='store_true', help='Run test with default story')
    parser.add_argument('--rerun', action='store_true', help='Rerun workflow in incremental mode')
    parser.add_argument('--list-tasks', action='store_true', help='List all tasks')
    
    args = parser.parse_args()
    
    if args.list_tasks:
        list_tasks()
    elif args.test:
        test_story_workflow()
    elif args.task_path:
        # Load story from file if provided
        story_text = args.story
        if args.story_file and os.path.exists(args.story_file):
            with open(args.story_file, 'r', encoding='utf-8') as f:
                story_text = f.read().strip()
            print(f"📖 Loaded story from file: {args.story_file}")
        
        run_workflow(
            task_path=args.task_path,
            story=story_text,
            workflow_config_path=args.config,
            target_duration=args.target_duration
        )
    elif args.story or args.story_file:
        story_text = args.story
        if args.story_file and os.path.exists(args.story_file):
            with open(args.story_file, 'r', encoding='utf-8') as f:
                story_text = f.read().strip()
        
        run_workflow(
            story=story_text,
            workflow_config_path=args.config,
            target_duration=args.target_duration
        )
    else:
        parser.print_help()
