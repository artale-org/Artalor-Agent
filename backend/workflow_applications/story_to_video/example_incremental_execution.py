#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

"""
Incremental Execution Example for Story Video - Based on Pydantic Dependency Tracking

Demonstrates how to edit workflow results and automatically trigger re-execution of affected nodes
"""
import sys
import os

# Add path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(current_dir, '../..'))

from workflow_applications.story_to_video.story_video_workflow_langgraph import (
    get_task_state,
    edit_state,
    run_workflow,
    execute_single_node,
    NODE_INPUT_MODELS,
)


def show_dependencies():
    """Display dependency relationships for all nodes"""
    print("=" * 70)
    print("Story Video Workflow Node Dependencies")
    print("=" * 70)
    
    for node_name, input_model in NODE_INPUT_MODELS.items():
        depends_on = list(input_model.model_fields.keys())
        print(f"\n📦 {node_name}")
        print(f"   Depends on: {', '.join(depends_on)}")


def example_edit_story_analysis(task_path: str):
    """
    Example: Edit story analysis results and re-execute
    
    Scenario: Modify story theme or mood, all dependent downstream nodes will automatically re-execute
    """
    print("\n" + "=" * 70)
    print("Example 1: Edit Story Analysis Results and Re-execute")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state = get_task_state(task_path=task_path)
    
    # 2. View current story analysis results
    current_analysis = state.get('story_analysis', {})
    print(f"\nCurrent theme: {current_analysis.get('theme')}")
    print(f"Current mood: {current_analysis.get('mood')}")
    print(f"Current visual style: {current_analysis.get('visual_style')}")
    
    # 3. Edit story analysis results
    print("\n📝 Step 2: Edit story analysis results...")
    edit_state(
        app, config, task_path,
        theme="Dark fantasy adventure",  # Modify theme
        mood="Mysterious and suspenseful",  # Modify mood
        visual_style="Cinematic with dramatic lighting"  # Modify visual style
    )
    print("   ✅ Modifications saved to dirty_flags.json")
    
    # 4. Re-execute workflow
    print("\n🔄 Step 3: Re-execute workflow...")
    print("   Workflow will automatically:")
    print("   - storyboard_design detects theme/mood/visual_style modified → re-execute")
    print("   - image_generation depends on storyboard_design → re-execute")
    print("   - video_generation depends on image_generation → re-execute")
    print("   - story_analysis already has results → skip (use cache)")
    
    final_state = run_workflow(task_path=task_path, rerun=True)
    
    print("\n✅ Re-execution complete!")
    print(f"   dirty_flags.json automatically cleaned up")


def example_edit_single_field(task_path: str):
    """
    Example: Modify only a single field
    
    Scenario: Modify only visual style, only dependent nodes will re-execute
    """
    print("\n" + "=" * 70)
    print("Example 2: Modify Only Visual Style")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state = get_task_state(task_path=task_path)
    
    # 2. Modify single field
    print("\n📝 Step 2: Modify visual style...")
    edit_state(
        app, config, task_path,
        visual_style="Anime-style with vibrant colors and dynamic camera angles"
    )
    print("   ✅ dirty_flags.json saved")
    
    # 3. Re-execute
    print("\n🔄 Step 3: Re-execute workflow...")
    print("   Workflow will automatically:")
    print("   - storyboard_design depends on visual_style → re-execute")
    print("   - image_generation depends on storyboard_design → re-execute")
    print("   - story_analysis doesn't depend on visual_style → skip (use cache)")
    
    final_state = run_workflow(task_path=task_path, rerun=True)
    
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
    app, config, state = get_task_state(task_path=task_path)
    
    # 2. View current image generation results
    print("\n📸 Step 2: View current image generation results...")
    generated_images = state.get('generated_images', [])
    print(f"   Current images: {len(generated_images)} images")
    for i, img in enumerate(generated_images[:2]):  # Show first 2
        if isinstance(img, list):
            print(f"      {i+1}. First: {img[0] if len(img) > 0 else 'None'}")
            print(f"         Last:  {img[1] if len(img) > 1 else 'None'}")
        else:
            print(f"      {i+1}. {img}")
    
    # 3. Execute only image_generation node
    print("\n🎯 Step 3: Execute only image_generation node...")
    print("   This will:")
    print("   - Only re-run image_generation node")
    print("   - Skip all other nodes (use cache)")
    print("   - Generate new images based on current storyboard")
    
    new_state = execute_single_node(app, config, 'image_generation', task_path)
    
    print(f"\n✅ Image regeneration complete!")
    print(f"   New images: {len(new_state.get('generated_images', []))} images")


def example_edit_single_storyboard_frame(task_path: str):
    """
    Example: Edit only one storyboard frame and regenerate only that image
    
    Scenario: Not satisfied with one storyboard frame's image prompt, want to modify and regenerate
    only that specific image without affecting other images
    """
    print("\n" + "=" * 70)
    print("Example 4: Fine-Grained Incremental Execution - Edit Single Frame")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state = get_task_state(task_path=task_path)
    
    # 2. View current storyboard
    print("\n🎬 Step 2: View current storyboard frames...")
    storyboard = state.get('storyboard', []) or state.get('storyboard_frames', [])
    generated_images = state.get('generated_images', [])
    
    print(f"   Total frames: {len(storyboard)}")
    for i, frame in enumerate(storyboard[:3]):  # Show first 3 frames
        if isinstance(frame, dict):
            scene_desc = frame.get('scene_description', '')[:60]
            print(f"   Frame {i}: {scene_desc}...")
        else:
            print(f"   Frame {i}: {str(frame)[:60]}...")
    
    print(f"\n   Total generated images: {len(generated_images)}")
    
    # 3. Modify only one frame (e.g., frame 1)
    frame_index = 1  # Modify the 2nd frame
    print(f"\n📝 Step 3: Modify only Frame {frame_index}...")
    
    if frame_index < len(storyboard):
        current_frame = storyboard[frame_index]
        if isinstance(current_frame, dict):
            old_desc = current_frame.get('scene_description', '')[:100]
            print(f"   Old description: {old_desc}...")
        
        # New description
        new_description = "A dramatic close-up of the hero's face, determination in their eyes, cinematic lighting with rim light effect"
        print(f"\n   New description: {new_description}")
        
        # Mark this frame as dirty by editing the storyboard
        # Create a copy of the storyboard with the modified frame
        new_storyboard = storyboard.copy()
        if isinstance(new_storyboard[frame_index], dict):
            new_storyboard[frame_index] = {**new_storyboard[frame_index], 'scene_description': new_description, '_dirty': True}
        
        edit_state(
            app, config, task_path,
            storyboard=new_storyboard
        )
        
        print(f"\n   ✅ storyboard[{frame_index}] is marked as dirty")
        print(f"   ✅ Other frames remain unchanged")
    
    # 4. Execute image_generation node
    print(f"\n🎯 Step 4: Execute image_generation node...")
    print(f"   This will:")
    print(f"   - Only regenerate images for Frame {frame_index}")
    print(f"   - Keep all other frames' images unchanged")
    
    new_state = execute_single_node(app, config, 'image_generation', task_path)
    
    new_images = new_state.get('generated_images', [])
    print(f"\n✅ Image regeneration complete!")
    print(f"   Total images: {len(new_images)}")
    print(f"   Only Frame {frame_index}'s images were regenerated")
    print(f"   All other {len(new_images) - 1} frames remain unchanged")


def example_regenerate_videos_only(task_path: str):
    """
    Example: Regenerate only videos without regenerating images
    
    Scenario: Images are good, but want to try different video generation parameters
    """
    print("\n" + "=" * 70)
    print("Example 5: Regenerate Videos Only (Keep Images)")
    print("=" * 70)
    
    # 1. Load task state
    print("\n📂 Step 1: Load task state...")
    app, config, state = get_task_state(task_path=task_path)
    
    # 2. View current videos
    print("\n🎥 Step 2: View current videos...")
    generated_videos = state.get('generated_videos', [])
    print(f"   Current videos: {len(generated_videos)} videos")
    for i, video in enumerate(generated_videos[:2]):  # Show first 2
        print(f"      {i+1}. {video}")
    
    # 3. Execute only video_generation node
    print("\n🎯 Step 3: Execute only video_generation node...")
    print("   This will:")
    print("   - Only re-run video_generation node")
    print("   - Use existing images from cache")
    print("   - Generate new videos with potentially different parameters")
    
    new_state = execute_single_node(app, config, 'video_generation', task_path)
    
    new_videos = new_state.get('generated_videos', [])
    print(f"\n✅ Video regeneration complete!")
    print(f"   New videos: {len(new_videos)} videos")
    print(f"   Images were not regenerated (used from cache)")


def run_all_examples(task_path: str):
    """Run all examples in sequence"""
    print("\n" + "=" * 70)
    print("Running All Story Video Incremental Execution Examples")
    print("=" * 70)
    
    # Show dependencies first
    show_dependencies()
    
    # Run examples
    examples = [
        ("Show Dependencies", show_dependencies),
        ("Edit Story Analysis", lambda: example_edit_story_analysis(task_path)),
        ("Edit Single Field", lambda: example_edit_single_field(task_path)),
        ("Execute Single Node", lambda: example_execute_single_node(task_path)),
        ("Edit Single Frame", lambda: example_edit_single_storyboard_frame(task_path)),
        ("Regenerate Videos Only", lambda: example_regenerate_videos_only(task_path)),
    ]
    
    for i, (name, func) in enumerate(examples, 1):
        print(f"\n{'=' * 70}")
        print(f"Example {i}: {name}")
        print(f"{'=' * 70}")
        try:
            if i > 1:  # Skip first one (already ran show_dependencies)
                func()
        except Exception as e:
            print(f"❌ Example failed: {e}")
            import traceback
            traceback.print_exc()
        
        if i < len(examples):
            input("\nPress Enter to continue to next example...")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Story Video Incremental Execution Examples')
    parser.add_argument('--task-path', type=str, required=True, help='Task directory path')
    parser.add_argument('--example', type=str, choices=['1', '2', '3', '4', '5', 'all'], 
                        default='all', help='Which example to run')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.task_path):
        print(f"❌ Error: Task path not found: {args.task_path}")
        sys.exit(1)
    
    print(f"\n📂 Using task path: {args.task_path}")
    
    if args.example == 'all':
        run_all_examples(args.task_path)
    elif args.example == '1':
        example_edit_story_analysis(args.task_path)
    elif args.example == '2':
        example_edit_single_field(args.task_path)
    elif args.example == '3':
        example_execute_single_node(args.task_path)
    elif args.example == '4':
        example_edit_single_storyboard_frame(args.task_path)
    elif args.example == '5':
        example_regenerate_videos_only(args.task_path)
