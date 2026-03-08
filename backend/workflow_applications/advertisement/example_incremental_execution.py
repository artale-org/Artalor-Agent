#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

"""
Incremental Execution Example - Based on Pydantic Dependency Tracking

Demonstrates how to edit workflow results and automatically trigger re-execution of affected nodes
"""
import sys
import os

# Add path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(current_dir, '../..'))

from workflow_applications.advertisement.ad_creation_workflow_langgraph import (
    get_task_state,
    edit_state,
    edit_list_item,
    run_workflow,
    execute_single_node,
    NODE_INPUT_MODELS,
    setup_task_directory
)


def show_dependencies():
    """Display dependency relationships for all nodes"""
    print("=" * 70)
    print("Workflow Node Dependencies")
    print("=" * 70)
    
    for node_name, input_model in NODE_INPUT_MODELS.items():
        depends_on = list(input_model.model_fields.keys())
        print(f"\n📦 {node_name}")
        print(f"   Depends on: {', '.join(depends_on)}")


def example_edit_and_reexecute(task_path: str):
    """
    Example: Edit state and re-execute
    
    Scenario: Modify product analysis results, all dependent downstream nodes will automatically re-execute
    """
    print("\n" + "=" * 70)
    print("Example 1: Edit Product Analysis Results and Re-execute")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state, task_path = get_task_state(task_path=task_path)
    
    # 2. View current product analysis results
    current_analysis = state.values.get('product_analysis', {})
    print(f"\nCurrent product category: {current_analysis.get('product_category')}")
    print(f"Current target audience: {current_analysis.get('target_audience')}")
    
    # 3. Edit product analysis results
    print("\n📝 Step 2: Edit product analysis results...")
    edit_state(
        app, config, task_path,
        product_category="High-end fashion accessories",  # Modify category
        target_audience="Urban elite women aged 25-40",  # Modify audience
    )
    print("   ✅ Modifications saved to dirty_flags.json")
    
    # 4. Re-execute workflow
    print("\n🔄 Step 3: Re-execute workflow...")
    print("   Workflow will automatically:")
    print("   - script_writing detects product_category/target_audience modified → re-execute")
    print("   - storyboard_design depends on script_writing output → re-execute")
    print("   - image_generation depends on storyboard_design → re-execute")
    print("   - Other nodes automatically skipped (use cache)")
    
    # Use run_workflow (auto-detects resume mode if checkpoint exists)
    final_state = run_workflow(
        task_path=task_path
    )
    
    print("\n✅ Re-execution complete!")
    print(f"   dirty_flags.json automatically cleaned up")


def example_edit_single_field(task_path: str):
    """
    Example: Modify only a single field
    
    Scenario: Modify only ad opening, only dependent nodes will re-execute
    """
    print("\n" + "=" * 70)
    print("Example 2: Modify Only Ad Opening")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state, task_path = get_task_state(task_path=task_path)
    
    # 2. Modify single field
    print("\n📝 Step 2: Modify ad opening...")
    edit_state(
        app, config, task_path,
        ad_hook="Brand new opening: Luxury starts with details."
    )
    print("   ✅ dirty_flags.json saved")
    
    # 3. Re-execute
    print("\n🔄 Step 3: Re-execute workflow...")
    print("   Workflow will automatically:")
    print("   - storyboard_design depends on ad_hook → re-execute")
    print("   - segmented_monologue depends on ad_hook → re-execute")
    print("   - product_analysis doesn't depend on ad_hook → skip (use cache)")
    print("   - script_writing doesn't depend on ad_hook → skip (use cache)")
    
    final_state = run_workflow(
        task_path=task_path
    )
    
    print("\n✅ Re-execution complete!")


def example_execute_single_node(task_path: str):
    """
    Example: Execute only a single node
    
    Scenario: Only want to regenerate images without re-executing entire workflow
    """
    print("\n" + "=" * 70)
    print("Example 3: Execute Single Node - Regenerate Images Only")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state, task_path = get_task_state(task_path=task_path)
    
    # 2. View current image generation results
    print("\n📸 Step 2: View current image generation results...")
    generated_images = state.values.get('generated_images', [])
    print(f"   Current images: {len(generated_images)} images")
    for i, img in enumerate(generated_images[:2]):  # Show first 2
        print(f"      {i+1}. {img}")
    
    # 3. Execute only image_generation node
    print("\n🎯 Step 3: Execute only image_generation node...")
    print("   This will:")
    print("   - Only re-run image_generation node")
    print("   - Skip all other nodes (use cache)")
    print("   - Mark generated_images as dirty (downstream needs re-execution)")
    
    new_state = execute_single_node(app, config, 'image_generation', task_path)
    
    print(f"\n✅ Image regeneration complete!")
    print(f"   New images: {len(new_state.get('generated_images', []))} images")
    print(f"   dirty_flags.json updated - downstream nodes marked for re-execution")


def example_edit_single_storyboard_frame(task_path: str):
    """
    Example: Edit only one storyboard frame and regenerate only that image
    
    Scenario: Not satisfied with one storyboard frame's image prompt, want to modify and regenerate
    only that specific image without affecting other images
    """
    print("\n" + "=" * 70)
    print("Example 3: Fine-Grained Incremental Execution - Edit Single Frame")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state, task_path = get_task_state(task_path=task_path)
    
    # 2. View current storyboard
    print("\n🎬 Step 2: View current storyboard frames...")
    storyboard = state.values.get('storyboard', [])
    generated_images = state.values.get('generated_images', [])
    
    print(f"   Total frames: {len(storyboard)}")
    for i, frame in enumerate(storyboard[:3]):  # Show first 3 frames
        first_desc = frame.get('first_image_description', '')[:60] if isinstance(frame, dict) else str(frame)[:60]
        print(f"   Frame {i}: {first_desc}...")
    
    print(f"\n   Total generated images: {len(generated_images)}")
    
    # 3. Modify only one frame (e.g., frame 1)
    frame_index = 1  # Modify the 2nd frame
    print(f"\n📝 Step 3: Modify only Frame {frame_index}...")
    
    if frame_index < len(storyboard):
        current_frame = storyboard[frame_index]
        if isinstance(current_frame, dict):
            old_prompt = current_frame.get('first_image_description', '')[:100]
            print(f"   Old prompt: {old_prompt}...")
        
        # New prompt - ONLY modify first_image_description, NOT last_image_description
        new_prompt = "A close-up shot of the LV handbag on a marble table, dramatic lighting from the side, gold hardware gleaming, professional product photography"
        print(f"\n   New prompt (ONLY for first frame): {new_prompt}")
        
        # Use edit_list_item to modify only first_image_description of this frame
        # This will ONLY regenerate the first image, keeping the last image cached
        edit_list_item(
            app, config, task_path,
            list_field='storyboard',
            index=frame_index,
            first_image_description=new_prompt  # Only modify first_image_description
        )
        
        print(f"\n   ✅ Only storyboard[{frame_index}].first_image_description is marked as dirty")
        print(f"   ✅ Other frames remain unchanged")
    
    # 4. Execute image_generation node
    print(f"\n🎯 Step 4: Execute image_generation node...")
    print(f"   This will:")
    print(f"   - Only regenerate FIRST image for Frame {frame_index}")
    print(f"   - Keep Frame {frame_index}'s LAST image cached")
    print(f"   - Keep all other frames' images unchanged")
    
    new_state = execute_single_node(app, config, 'image_generation', task_path)
    
    new_images = new_state.get('generated_images', [])
    print(f"\n✅ Image regeneration complete!")
    print(f"   Total images: {len(new_images)}")
    print(f"   Only Frame {frame_index}'s FIRST image was regenerated")
    print(f"   Frame {frame_index}'s LAST image was kept from cache")
    print(f"   All other {len(new_images) - 1} frames remain unchanged")
    
    # Show which image was updated
    if frame_index < len(new_images):
        updated_image = new_images[frame_index]
        print(f"\n   Updated image: {updated_image}")
    
    print(f"\n💡 Summary:")
    print(f"   1. Modified only storyboard[{frame_index}].first_image_description")
    print(f"   2. Regenerated only Frame {frame_index}'s first image (not last image)")
    print(f"   3. All other {len(storyboard) - 1} frames and images unchanged")
    print(f"   4. Achieved MAXIMUM granularity - only 1 image regenerated out of {len(new_images) * 2} total images")
    print(f"   5. Saved time and API costs by avoiding full regeneration")


def example_edit_single_last_image_with_edit_list_item(task_path: str):
    """
    Example: Use edit_list_item to modify ONLY last_image_description of one frame
    and regenerate ONLY that frame's LAST image (FIRST image remains cached)
    """
    print("\n" + "=" * 70)
    print("Example 3b: Fine-Grained - Edit Single LAST Image via edit_list_item")
    print("=" * 70)

    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state, task_path = get_task_state(task_path=task_path)

    # 2. Inspect storyboard & images
    storyboard = state.values.get('storyboard', [])
    generated_images = state.values.get('generated_images', [])
    print(f"   Total frames: {len(storyboard)}")

    # Choose frame index (2nd frame for demo)
    frame_index = 1
    if frame_index >= len(storyboard):
        print(f"⚠️  storyboard too short for demo (need index {frame_index})")
        return

    # Show current last_image_description
    curr = storyboard[frame_index]
    old_desc = curr.get('last_image_description', '') if isinstance(curr, dict) else ''
    print(f"\n📝 Current last_image_description (frame {frame_index}): {old_desc[:100]}...")

    # 3. Update only last_image_description via edit_list_item
    new_prompt = (
        "A refined closing shot highlighting the brand logo with soft rim lighting,"
        " clean background, and elegant color grading"
    )
    print(f"\n📝 Updating last_image_description to: {new_prompt}")
    edit_list_item(
        app, config, task_path,
        list_field='storyboard',
        index=frame_index,
        last_image_description=new_prompt  # Only modify last_image_description
    )
    print(f"   ✅ storyboard[{frame_index}].last_image_description marked dirty")

    # 4. Execute image_generation only
    print(f"\n🎯 Step 4: Execute ONLY image_generation node...")
    print(f"   This will regenerate ONLY the LAST image for frame {frame_index}")
    new_state = execute_single_node(app, config, 'image_generation', task_path)

    # 5. Summarize
    new_images = new_state.get('generated_images', [])
    print(f"\n✅ Image regeneration complete (last image only)")
    if frame_index < len(new_images):
        print(f"   Frame {frame_index} images: {new_images[frame_index]}")
    print(f"   Other frames/images remain unchanged")

def example_modify_single_video_prompt_and_regenerate(task_path: str, frame_index: int = 0):
    """
    Example: Modify ONLY one frame's video_description and regenerate ONLY that video's clip
    (By deleting that video's existing file so the node regenerates only that index)
    """
    print("\n" + "=" * 70)
    print("Example 6: Modify Single Video Prompt and Regenerate Only That Video")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state, task_path = get_task_state(task_path=task_path)
    storyboard = state.values.get('storyboard', []) or []
    videos = state.values.get('generated_videos', []) or []
    
    if frame_index >= len(storyboard):
        print(f"⚠️  Invalid frame_index {frame_index}, storyboard has {len(storyboard)} frames")
        return
    
    # 2. Show current video description and path
    print("\n🎬 Step 2: Current video description and path...")
    old_desc = storyboard[frame_index].get('video_description', '') if isinstance(storyboard[frame_index], dict) else ''
    old_path = videos[frame_index] if frame_index < len(videos) else None
    print(f"   Frame {frame_index}: old video_description: {old_desc[:120]}...")
    print(f"   Frame {frame_index}: current video path: {old_path}")
    
    # 3. Modify single frame's video_description via edit_state (no new API)
    print("\n📝 Step 3: Modify single frame video_description...")
    new_desc = "A faster-paced dynamic scene highlighting the product in motion, energetic transitions, modern urban background"
    print(f"   New video_description: {new_desc}")
    new_storyboard = list(storyboard)
    if isinstance(new_storyboard[frame_index], dict):
        new_frame = dict(new_storyboard[frame_index])
        new_frame['video_description'] = new_desc
        new_storyboard[frame_index] = new_frame
    else:
        # If non-dict, wrap as dict minimally
        new_storyboard[frame_index] = {'video_description': new_desc}
    edit_state(app, config, task_path, storyboard=new_storyboard)
    
    # 4. Delete ONLY this video's existing file to trigger single-index regeneration
    print("\n🧹 Step 4: Remove only this video's existing file (if exists) to force regen for this index...")
    if old_path and isinstance(old_path, str) and os.path.exists(old_path):
        try:
            os.remove(old_path)
            print(f"   ✅ Removed existing video file: {old_path}")
        except Exception as e:
            print(f"   ⚠️  Failed to remove old video file: {e}")
    else:
        print("   ℹ️ No existing video file to remove for this index")
    
    # 5. Execute ONLY video_generation node
    print("\n🎯 Step 5: Execute ONLY video_generation node...")
    new_state = execute_single_node(app, config, 'video_generation', task_path)
    
    # 6. Show updated path
    new_videos = new_state.get('generated_videos', []) or []
    new_path = new_videos[frame_index] if frame_index < len(new_videos) else None
    print("\n✅ Video regeneration complete (single index)!")
    print(f"   Frame {frame_index}: new video path: {new_path}")
    print(f"   File exists: {os.path.exists(new_path) if new_path else False}")
    print("   Other videos remain cached (not regenerated)")


def example_modify_single_tts_segment_and_regenerate(task_path: str, segment_index: int = 0):
    """
    Example: Modify ONLY one segment's TTS text and regenerate ONLY that audio
    (By deleting that segment's existing audio so the node regenerates only that index)
    """
    print("\n" + "=" * 70)
    print("Example 7: Modify Single TTS Segment and Regenerate Only That Audio")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state, task_path = get_task_state(task_path=task_path)
    segments = state.values.get('segments', []) or []
    seg_vo = state.values.get('segmented_voiceover_generation', {}) or {}
    seg_paths = seg_vo.get('segmented_voiceover_paths') or state.values.get('segmented_voiceover_paths', []) or []
    
    if segment_index >= len(segments):
        print(f"⚠️  Invalid segment_index {segment_index}, segments has {len(segments)} items")
        return
    
    # 2. Show current segment text and path
    print("\n🎤 Step 2: Current segment text and path...")
    seg = segments[segment_index] if isinstance(segments[segment_index], dict) else {}
    old_text = seg.get('segment_text', '')
    old_audio = seg_paths[segment_index] if segment_index < len(seg_paths) else None
    print(f"   Segment {segment_index}: old text: {old_text[:120]}...")
    print(f"   Segment {segment_index}: current audio: {old_audio}")
    
    # 3. Modify single segment text via edit_state (no new API)
    print("\n📝 Step 3: Modify single segment text...")
    new_text = "Discover the essence of style — crafted with precision, designed to impress."
    print(f"   New segment_text: {new_text}")
    new_segments = list(segments)
    if isinstance(new_segments[segment_index], dict):
        new_seg = dict(new_segments[segment_index])
        new_seg['segment_text'] = new_text
        new_segments[segment_index] = new_seg
    else:
        new_segments[segment_index] = {'segment_text': new_text}
    edit_state(app, config, task_path, segments=new_segments)
    
    # 4. Delete ONLY this segment's audio to trigger single-index regeneration
    print("\n🧹 Step 4: Remove only this segment's audio (if exists) to force regen for this index...")
    if old_audio and isinstance(old_audio, str) and os.path.exists(old_audio):
        try:
            os.remove(old_audio)
            print(f"   ✅ Removed existing audio file: {old_audio}")
        except Exception as e:
            print(f"   ⚠️  Failed to remove old audio file: {e}")
    else:
        print("   ℹ️ No existing segment audio to remove for this index")
    
    # 5. Execute ONLY segmented_tts node
    print("\n🎯 Step 5: Execute ONLY segmented_tts node...")
    new_state = execute_single_node(app, config, 'segmented_tts', task_path)
    
    # 6. Show updated segment path
    new_seg_vo = new_state.get('segmented_voiceover_generation', {}) or {}
    new_paths = new_seg_vo.get('segmented_voiceover_paths') or new_state.get('segmented_voiceover_paths', []) or []
    new_audio = new_paths[segment_index] if segment_index < len(new_paths) else None
    print("\n✅ Segmented TTS regeneration complete (single index)!")
    print(f"   Segment {segment_index}: new audio: {new_audio}")
    print(f"   File exists: {os.path.exists(new_audio) if new_audio else False}")
    print("   Other segments remain cached (not regenerated)")

def example_execute_bgm_node_and_rerun_edit(task_path: str):
    """
    Example: Modify BGM prompt and regenerate
    
    Scenario: Not satisfied with BGM, want to change mood and regenerate
    """
    print("\n" + "=" * 70)
    print("Example 5: Modify BGM Prompt and Regenerate")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state, task_path = get_task_state(task_path=task_path)
    
    # 2. View current BGM and prompt
    print("\n🎵 Step 2: View current BGM configuration...")
    bgm_path = state.values.get('bgm_path')
    mood_keywords = state.values.get('mood_keywords', 'energetic')
    visual_style = state.values.get('visual_style', 'modern')
    video_durations = state.values.get('video_durations', [])
    total_duration = sum(float(d) for d in video_durations if d) if video_durations else 20.0
    
    print(f"   Current BGM file: {bgm_path}")
    print(f"   Current mood_keywords: {mood_keywords}")
    print(f"   Current visual_style: {visual_style}")
    print(f"   Total video duration: {total_duration:.1f}s")
    
    # Construct the BGM prompt (same logic as BGMNode)
    current_prompt = f"Background music for an advertisement. Mood: {mood_keywords}. Style: {visual_style}, cinematic, clean mix."
    print(f"\n   Current BGM prompt:")
    print(f"   >>> {current_prompt}")
    
    # 3. Modify mood keywords
    print("\n📝 Step 3: Modify mood keywords...")
    new_mood_keywords = "dramatic, powerful, epic"  # Example modification
    print(f"   Old mood: {mood_keywords}")
    print(f"   New mood: {new_mood_keywords}")
    
    new_prompt = f"Background music for an advertisement. Mood: {new_mood_keywords}. Style: {visual_style}, cinematic, clean mix."
    print(f"\n   New BGM prompt:")
    print(f"   >>> {new_prompt}")
    
    # 4. Update state with new mood
    print("\n🏷️  Step 4: Update state and mark as dirty...")
    edit_state(app, config, task_path, mood_keywords=new_mood_keywords)
    print(f"   ✅ mood_keywords updated and marked as dirty")
    
    # 5. Execute only bgm node
    print("\n🎯 Step 5: Execute ONLY bgm node (regenerate BGM)...")
    print("   This will:")
    print("   - Only re-run bgm node")
    print("   - Generate new BGM with new mood")
    print("   - NOT execute edit node (downstream)")
    
    new_state = execute_single_node(app, config, 'bgm', task_path)
    
    new_bgm_path = new_state.get('bgm_path')
    print(f"\n✅ BGM regeneration complete!")
    print(f"   New BGM: {new_bgm_path}")
    print(f"   File exists: {os.path.exists(new_bgm_path) if new_bgm_path else False}")
    
    # 6. Optional: Execute edit node to composite new BGM
    print(f"\n🎬 Step 6: Execute ONLY edit node to composite new video...")
    print(f"   This will:")
    print(f"   - Only re-run edit node")
    print(f"   - Composite video with NEW BGM")
    print(f"   - Keep everything else unchanged")
    
    final_state = execute_single_node(app, config, 'edit', task_path)
    
    final_video = final_state.get('final_video')
    print(f"\n🎉 Final video with new BGM:")
    print(f"   Video path: {final_video}")
    print(f"   File exists: {os.path.exists(final_video) if final_video else False}")
    
    print(f"\n💡 Summary:")
    print(f"   1. Changed mood from '{mood_keywords}' to '{new_mood_keywords}'")
    print(f"   2. Regenerated BGM only (no other nodes executed)")
    print(f"   3. Re-composited final video with new BGM")
    print(f"   4. All other content (images, videos, voiceover) unchanged")


def example_manual_invoke():
    """
    Example: Manual invocation (without run_workflow)
    
    Suitable for advanced users who need finer control
    """
    print("\n" + "=" * 70)
    print("Example 6: Manual Invocation (Advanced Usage)")
    print("=" * 70)
    
    task_path = 'task_data/ad_creation_langgraph_test_20251012012755'
    
    # 1. Load state
    app, config, state, task_path = get_task_state(task_path=task_path)
    
    # 2. Edit
    edit_state(app, config, task_path, ad_hook="New opening")
    
    # 3. Manual invocation
    print("\nMethod A: Use app.invoke() to execute manually")
    print("final_state = app.invoke(None, config=config)")
    print("⚠️  Note: Need to manually clean up dirty flags")
    
    print("\nMethod B: Use run_workflow (Recommended)")
    print("final_state = run_workflow(task_path=task_path, rerun=True)")
    print("✅ Automatically handles loading, saving, and cleaning of dirty flags")
    
    print("\nMethod C: Use execute_single_node")
    print("new_state = execute_single_node(app, config, 'image_generation', task_path)")
    print("✅ Execute only specified node, automatically manage dirty flags")


def example_update_video_edit_parameters_and_apply(task_path: str):
    """
    Example: Update VideoEditNode parameters via workflow config and apply to both full workflow and single-node runs
    """
    print("\n" + "=" * 70)
    print("Example X: Update VideoEdit Parameters and Apply")
    print("=" * 70)

    # 1. Load state
    print("\n📂 Step 1: Load task state...")
    app, config, state, task_path = get_task_state(task_path=task_path)

    # 2. Write/merge workflow config at task path (edit node parameters)
    print("\n📝 Step 2: Update workflow config with edit parameters...")
    cfg_path = os.path.join(task_path, 'workflow_config.json')
    current = {}
    if os.path.exists(cfg_path):
        import json
        with open(cfg_path, 'r', encoding='utf-8') as f:
            try:
                current = json.load(f) or {}
            except Exception:
                current = {}
    current.setdefault('edit', {})
    current['edit']['tool'] = 'VideoEditNode'
    current['edit'].setdefault('parameters', {})
    current['edit']['parameters'].update({
        'video_volume': 0.30,
        'narration_volume': 0.70,
        'bgm_volume': 0.50,
        'normalize': True,
        'fade_duration': 0.3,
    })
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Saved workflow config: {cfg_path}")

    # 3. Execute ONLY edit node (should read config and apply)
    print("\n🎯 Step 3: Execute ONLY 'edit' node with new parameters...")
    final_state = execute_single_node(app, config, 'edit', task_path)
    final_video = final_state.get('final_video')
    print(f"   Final video: {final_video}")
    print(f"   Exists: {os.path.exists(final_video) if final_video else False}")

def example_check_what_will_rerun(dirty_fields: list):
    """
    Analysis: If certain fields are modified, which nodes will re-execute
    
    Args:
        dirty_fields: List of modified fields
    """
    print("\n" + "=" * 70)
    print(f"Analysis: If {dirty_fields} is modified, which nodes will re-execute?")
    print("=" * 70)
    
    affected_nodes = []
    for node_name, input_model in NODE_INPUT_MODELS.items():
        depends_on = list(input_model.model_fields.keys())
        # Check for intersection
        if any(field in depends_on for field in dirty_fields):
            affected_nodes.append(node_name)
            print(f"✅ {node_name:25} - Will re-execute")
        else:
            print(f"⏭️  {node_name:25} - Skip (doesn't depend on these fields)")
    
    print(f"\nTotal {len(affected_nodes)} nodes will re-execute")
    return affected_nodes


if __name__ == '__main__':
#     print("\n" + "=" * 70)
#     print("Incremental Execution Feature Demo")
#     print("=" * 70)
    
#     # 1. Show dependencies
#     show_dependencies()
    
#     # 2. Analysis examples
#     print("\n\n")
#     example_check_what_will_rerun(['reference_image_descriptions'])
    
#     print("\n\n")
#     example_check_what_will_rerun(['ad_hook'])
    
#     print("\n\n")
#     example_check_what_will_rerun(['generated_images'])
    
#     # 3. Usage instructions
#     print("\n\n" + "=" * 70)
#     print("Actual Usage Steps")
#     print("=" * 70)
#     print("""
# Step-by-Step Guide:

# 1. Run workflow to generate initial results
#    python ad_creation_workflow_langgraph.py --test

# 2. Choose your approach:

#    Approach A - Edit state and re-execute workflow (incremental mode)
#    ------------------------------------------------------------------
#    from ad_creation_workflow_langgraph import get_task_state, edit_state, run_workflow
#    task_path = 'task_data/ad_creation_langgraph_test_20251012012755'
#    app, config, state, task_path = get_task_state(task_path=task_path)
   
#    # Edit any field
#    edit_state(app, config, task_path, ad_hook="New opening")
   
#    # Re-execute workflow (only affected nodes will run)
#    run_workflow(task_path=task_path, rerun=True)
   
   
#    Approach B - Execute single node only
#    ------------------------------------------------------------------
#    from ad_creation_workflow_langgraph import get_task_state, execute_single_node
#    task_path = 'task_data/ad_creation_langgraph_test_20251012012755'
#    app, config, state, task_path = get_task_state(task_path=task_path)
   
#    # Execute only one node (e.g., regenerate images)
#    execute_single_node(app, config, 'image_generation', task_path)
   
#    # Optionally continue with downstream nodes
#    execute_single_node(app, config, 'video_generation', task_path)
#    execute_single_node(app, config, 'edit', task_path)
   
   
#    Approach C - Execute single node after editing
#    ------------------------------------------------------------------
#    # Combine edit_state and execute_single_node
#    edit_state(app, config, task_path, mood_keywords="energetic, modern")
#    execute_single_node(app, config, 'bgm', task_path)  # Regenerate BGM with new mood
#    execute_single_node(app, config, 'edit', task_path)  # Re-composite final video
#     """)
    
    # If you want to actually execute examples, uncomment below:
    task_path = 'task_data/ad_creation_langgraph_20251124034055'
    # example_edit_single_field(task_path)
    example_execute_single_node(task_path)
    # example_edit_single_storyboard_frame(task_path)
    # example_execute_bgm_node_and_rerun_edit(task_path)
    # example_modify_single_video_prompt_and_regenerate(task_path, frame_index=2)
    
    print(setup_task_directory())
    
