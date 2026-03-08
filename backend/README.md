# Artalor - AI-Powered Video Generation Platform

Artalor backend: A sophisticated AI-powered platform for generating story videos and advertisement content using a 3-layer modular architecture.

## 🏗️ Architecture Overview

This project implements a **3-layer modular architecture** designed for high cohesion, low coupling, and easy extensibility:

### Layer 1: Infrastructure Layer (`modules/`)
**Purpose**: Provides reusable, domain-agnostic foundational components

```
modules/
├── nodes/                    # Core workflow nodes
│   ├── base_node.py         # Abstract base class for all nodes
│   ├── chat_node.py         # LLM interaction with caching
│   ├── image_node.py        # Image generation infrastructure
│   └── video_node.py        # Video generation infrastructure
└── tools/                   # Utility tools
    ├── utils.py             # General utilities and LLM client
    ├── image_gen.py         # Image generation engine (DALL-E, Kling)
    ├── video_gen.py         # Video generation engine (Replicate, Kling)
    └── adapters/            # Tool adapters for architecture
```

### Layer 2: Business Component Layer (`domain_components/`)
**Purpose**: Domain-specific business logic encapsulating templates, structures, and logic

```
domain_components/
├── analysis/                # Analysis components
│   ├── story_analyzer.py    # Story content analysis
│   └── product_analyzer.py  # Product requirement analysis
└── generation/              # Generation components
    ├── storyboard_designer.py      # Story storyboard design
    ├── ad_script_writer.py         # Advertisement script writing
    └── ad_storyboard_designer.py   # Advertisement storyboard design
```

### Layer 3: Workflow Application Layer (`workflow_applications/`)
**Purpose**: Business scenario orchestration combining different components

```
workflow_applications/
├── story_to_video/
│   └── story_video_workflow_langgraph.py     # Story → Video pipeline
└── advertisement/
    └── ad_creation_workflow_langgraph.py     # Product → Advertisement pipeline
```

## 🚀 Quick Start

### Prerequisites

1. **Python 3.8+**
2. **Virtual Environment Setup**:
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

3. **Install Dependencies**:
```bash
pip install -r requirements.txt
```

4. **Environment Configuration**:
Create a `.env` file in the `backend/` directory:
```env
OPENAI_API_KEY=your_openai_api_key_here
REPLICATE_API_TOKEN=your_replicate_token_here
```

> **Tip:** When using the web UI, you can also configure API keys via the **API Keys** button in the navigation bar. Keys entered there are stored in your browser and sent to the server per-request.

## 📖 Usage Examples

### 1. Story Video Generation

Convert a story into a complete video with images, storyboards, and transitions:

```bash
# Using built-in test story
python workflow_applications/story_to_video/story_video_workflow_langgraph.py --test

# Using custom story text
python workflow_applications/story_to_video/story_video_workflow_langgraph.py \
  --story "Your story content here"

# Using a story file
python workflow_applications/story_to_video/story_video_workflow_langgraph.py \
  --story-file path/to/story.txt

# List existing story tasks
python workflow_applications/story_to_video/story_video_workflow_langgraph.py --list-tasks
```

**CLI Options**:
- `--story`: Story content text
- `--story-file`: Path to a `.txt` file containing story text
- `--task-path`: Resume an existing task directory
- `--target-duration`: Target video duration in seconds (default: 60)
- `--test`: Run with a built-in demo story
- `--list-tasks`: List all existing story tasks

### 2. Advertisement Creation

Create advertisement videos for products:

```bash
# Test with sample product
python workflow_applications/advertisement/ad_creation_workflow_langgraph.py --test

# Create advertisement for your product
python workflow_applications/advertisement/ad_creation_workflow_langgraph.py \
  --requirement "Create a 30-second elegant advertisement for this artwork" \
  --image path/to/your/product/image.jpg

# Resume an existing task
python workflow_applications/advertisement/ad_creation_workflow_langgraph.py \
  --task-path task_data/ad_creation_langgraph_20260308020505

# List existing ad tasks
python workflow_applications/advertisement/ad_creation_workflow_langgraph.py --list-tasks
```

**CLI Options**:
- `--requirement`: Product/ad requirement brief (required for new task)
- `--image`: Path to product image (can be repeated for multiple images, required for new task)
- `--task-path`: Resume an existing task directory
- `--target-duration`: Target video duration in seconds (default: 30, range: 15-120)
- `--config`: Path to workflow config file (optional)
- `--test`: Run with a built-in demo example
- `--list-tasks`: List all existing ad tasks

## 🔧 Configuration Options

### Model Configuration

The platform supports multiple AI models:

**Image Generation**:
- `dall-e-3` (Default) - OpenAI DALL-E 3
- `kling-v2` - Kling AI (with reference image support)

**Video Generation**:
- `wavespeedai/wan-2.1-i2v-480p` (Default) - Replicate WAN model
- `kwaivgi/kling-v1.6-standard` - Kling video model

### Task Management

All workflow runs create timestamped directories:
```
task_data/
├── story_video_langgraph_20260222054147/    # Story workflow results
├── ad_creation_langgraph_20260308020505/    # Advertisement workflow results
└── ...
```

## 🎯 Architecture Benefits

### ✅ High Cohesion
Each business component contains its own:
- Prompt templates
- Data structures 
- Processing logic
- Input/output mappings

### ✅ Low Coupling
- Components communicate through standardized data interfaces
- Infrastructure layer is completely reusable across domains
- Easy to modify one component without affecting others

### ✅ Easy Extension
```python
# Add new business component
class NewAnalyzer:
    INPUT_MAPPING = {...}
    OUTPUT_MAPPING = {...}
    
    @classmethod
    def create_node(cls, name, task_path):
        # Self-contained component creation
        pass
```

### ✅ Caching & Resume
- Automatic JSON caching for LLM results
- File existence checking for media generation
- Resume workflows from interruption points

## 📁 Output Structure

Each workflow run produces organized outputs:

### Ad Workflow (`ad_creation_langgraph_*`)
```
task_data/ad_creation_langgraph_YYYYMMDDHHMMSS/
├── upload/                          # Uploaded product image
│   └── product.jpg
├── image_understanding_v1.json      # Product image analysis
├── product_analysis_v1.json         # Product styling & mood keywords
├── script_writing_v1.json           # Ad script with segments
├── storyboard_design_v1.json        # Visual storyboard plan
├── sub_video_0/                     # Per-clip assets
│   ├── image_first_v1.png           # First keyframe
│   ├── image_last_v1.png            # Last keyframe
│   ├── video_v1.mp4                 # Generated video clip
│   ├── segment_v1.mp3               # Voiceover audio segment
│   └── *.json                       # Generation metadata
├── sub_video_1/                     # (same structure per clip)
│   └── ...
├── audios/
│   ├── bgm.mp3                      # Background music
│   └── segments/                    # (legacy) voiceover segments
├── final_videos/
│   └── final_complete_video.mp4     # Assembled final video
├── checkpoints.sqlite               # LangGraph workflow state
├── workflow_config.json             # Workflow configuration
└── logs/
    └── output.log                   # Execution log
```

### Story Workflow (`story_video_langgraph_*`)
```
task_data/story_video_langgraph_YYYYMMDDHHMMSS/
├── story_input.txt                  # Input story text
├── character_reference/             # Optional character image
│   └── character.jpeg
├── story_analysis_v1.json           # Story content analysis
├── storyboard_design_v1.json        # Visual storyboard plan
├── sub_video_0/                     # Per-scene assets
│   ├── image_first_v1.png
│   ├── image_last_v1.png
│   ├── video_v1.mp4
│   └── *.json
├── sub_video_1/
│   └── ...
├── final_videos/
│   └── final_complete_video_v1.mp4  # Assembled final video
├── checkpoints.sqlite               # LangGraph workflow state
└── workflow_config.json
```

## 🛠️ Development

### Adding New Workflows

1. **Create Business Components** (Layer 2):
```python
# domain_components/analysis/new_analyzer.py
class NewAnalyzer:
    @classmethod
    def create_node(cls, name, task_path):
        # Implementation
        pass
```

2. **Create Workflow** (Layer 3):
```python
# workflow_applications/new_domain/new_workflow.py
class NewWorkflow:
    def __init__(self):
        self.analyzer = NewAnalyzer.create_node(...)
        self.generator = ImageNode(...)  # Reuse infrastructure
```

### Extending Infrastructure

Infrastructure components are designed for maximum reusability across domains.

## 🔍 Troubleshooting

### Common Issues

1. **API Quota Exceeded**:
```
"resource pack exhausted"
```
**Solution**: Switch to alternative models or wait for quota reset

2. **Missing Images for Video**:
```
"No valid image found for video generation"
```
**Solution**: Check image generation logs, ensure successful image creation

3. **Import Errors**:
**Solution**: Ensure virtual environment is activated and dependencies installed

### Debug Mode

Enable detailed logging by checking workflow execution steps.

## 📄 License

This project is licensed under the MIT License.

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

Built with ❤️ using Python, LangChain, and multiple AI services.

## 📊 Project Status

**Current Version**: 2.0 (Refactored 3-Layer Architecture)

### ✅ Completed Features
- **Story to Video Pipeline**: Complete story analysis → storyboard → image → video workflow
- **Advertisement Creation Pipeline**: Product analysis → script writing → storyboard → media generation
- **3-Layer Modular Architecture**: Infrastructure, Business Components, Workflow Applications
- **Multi-Model Support**: DALL-E 3, Kling AI, Replicate models
- **Caching & Resume**: Automatic workflow state management and resumption
- **English Internationalization**: All prompts, templates, and interfaces in English

### 🔄 Architecture Migration
The project has been successfully refactored from a monolithic structure to a 3-layer modular architecture:
- ✅ **High Cohesion**: Each component is self-contained with its own templates and logic
- ✅ **Low Coupling**: Standardized data interfaces between layers
- ✅ **Easy Extension**: New domains can be added without affecting existing code
- ✅ **Infrastructure Reuse**: Core nodes (Image, Video, Chat) work across all domains

### 📈 Performance Features
- **Intelligent Caching**: JSON caching for LLM results, file existence checking for media
- **Error Handling**: Graceful degradation when API limits reached
- **Fallback Mechanisms**: Alternative image sources when generation fails
- **Progress Tracking**: Real-time status updates for long-running operations 