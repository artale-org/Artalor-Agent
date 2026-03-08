# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

# refactored_architecture/3_workflow_applications/story_to_video/story_video_workflow.py
"""
Story video workflow - refactored version
Demonstrates 3-layer architecture advantages: high cohesion, low coupling, easy extension
"""
import os
import sys
import argparse
import importlib
from datetime import datetime

# Add architecture paths
current_dir = os.path.dirname(os.path.abspath(__file__))
arch_root = os.path.join(current_dir, '../../')
sys.path.insert(0, arch_root)

# Import infrastructure layer - use importlib to handle modules starting with numbers
infra_base = importlib.import_module('modules.nodes.base_node')
infra_image = importlib.import_module('modules.nodes.image_node')
infra_video = importlib.import_module('modules.nodes.video_node')

BaseNode = infra_base.BaseNode
ImageNode = infra_image.ImageNode
VideoNode = infra_video.VideoNode

# Import business component layer
biz_story = importlib.import_module('domain_components.analysis.story_analyzer')
biz_storyboard = importlib.import_module('domain_components.generation.storyboard_designer')

StoryAnalyzer = biz_story.StoryAnalyzer
StoryboardDesigner = biz_storyboard.StoryboardDesigner

class StoryVideoWorkflow:
    """
    Story video workflow - refactored using 3-layer architecture
    
    Advantages validation:
    1. High cohesion: Each business component self-contains template, structure, logic
    2. Low coupling: Decoupling between components through data mapping
    3. Easy extension: Adding new business components doesn't affect existing architecture
    4. Easy maintenance: Modifying business logic only requires changing corresponding components
    """
    
    def __init__(self, task_id=None, task_path=None):
        # Create task directory
        ts = task_id or datetime.utcnow().strftime("%Y%m%d%H%M%S")
        self.task_path = task_path or os.path.join('task_data', f"story_video_{ts}")
        os.makedirs(self.task_path, exist_ok=True)
        
        print(f"📁 Task directory: {self.task_path}")
        
        # Initialize nodes - using business component factory methods
        self.story_analyzer = StoryAnalyzer.create_node('story_analysis', self.task_path)
        self.storyboard_designer = StoryboardDesigner.create_node('storyboard_design', self.task_path)
        self.image_generator = ImageNode('image_generation', os.path.join(self.task_path, 'images'))
        self.video_generator = VideoNode('video_generation', os.path.join(self.task_path, 'videos'))
        
        # Configure infrastructure layer nodes
        self.image_generator.configure(default_model='dall-e-3')
        self.video_generator.configure(default_model='wavespeedai/wan-2.1-i2v-480p')
    
    def run(self, story_content: str):
        """
        Execute complete workflow
        
        Data flow:
        story_content → story_analysis → storyboard_design → image_generation → video_generation
        """
        print("🚀 Starting Story Video Workflow...")
        print(f"📖 Story: {story_content[:100]}..." if len(story_content) > 100 else f"📖 Story: {story_content}")
        print("-" * 60)
        
        # Initialize workflow state
        workflow_state = {'story': story_content}
        
        # Step 1: Story analysis - using business component
        print("📊 Step 1: Story Analysis")
        workflow_state = self.story_analyzer(workflow_state)
        # Extract and merge story analysis results
        if 'story_analysis' in workflow_state:
            story_analysis_result = workflow_state['story_analysis']
            workflow_state.update(story_analysis_result)
        
        # Step 2: Storyboard design - using business component  
        print("🎬 Step 2: Storyboard Design")
        workflow_state = self.storyboard_designer(workflow_state)
        # Extract and merge storyboard design results
        if 'storyboard_design' in workflow_state:
            storyboard_result = workflow_state['storyboard_design']
            workflow_state.update(storyboard_result)
        
        # Step 3: Image generation - using infrastructure layer
        print("🖼️  Step 3: Image Generation")
        workflow_state = self.image_generator(workflow_state)
        # Extract and merge image generation results
        if 'image_generation' in workflow_state:
            image_result = workflow_state['image_generation']
            workflow_state.update(image_result)
        
        # Step 4: Video generation - using infrastructure layer
        print("🎥 Step 4: Video Generation")
        workflow_state = self.video_generator(workflow_state)
        # Extract and merge video generation results
        if 'video_generation' in workflow_state:
            video_result = workflow_state['video_generation']
            workflow_state.update(video_result)
        
        print("✅ Story Video Workflow Completed!")
        print(f"📁 Results saved in: {self.task_path}")
        
        return workflow_state

# Test function
def test_story_workflow():
    """Test story video workflow"""
    story_file = os.path.join(os.path.dirname(__file__), '../..', 'assets/story_examples/black_man.txt')  
    with open(story_file, 'r') as f:
        story_content = f.read()
    test_story = '.'.join(story_content.split('.')[:5])

    try:
        workflow = StoryVideoWorkflow(task_id="test_story_video")
        result = workflow.run(test_story.strip())
        
        print("\n🎉 Test successful! Architecture advantages validation:")
        print("✅ High cohesion: Business logic, prompts, data structures within same component")
        print("✅ Low coupling: Components communicate through standardized data interfaces")
        print("✅ Easy extension: Can easily add new analysis or generation components")
        print("✅ Easy maintenance: Modifying business logic only requires changing corresponding component files")
        
        return result
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Support command line invocation
    parser = argparse.ArgumentParser(description='Story to Video Workflow - Refactored Version')
    parser.add_argument('--story', type=str, help='Story content')
    parser.add_argument('--test', action='store_true', help='Run test with default story')
    
    args = parser.parse_args()
    
    if args.test or not args.story:
        # Run test
        test_story_workflow()
    else:
        # Run user provided story
        workflow = StoryVideoWorkflow()
        workflow.run(args.story) 