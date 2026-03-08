# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

# modules/nodes/audio_node.py
import os
import sys
from modules.nodes.base_node import BaseNode, ToolNode, GenModelNode

# Add tools path for audio utilities
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../modules'))
from modules.tools.audio_gen import replicate_tts, replicate_bgm, mux_video_with_audio_segments


class VoiceoverNode(GenModelNode):
    """Voiceover generation node using Replicate TTS"""

    def __init__(self, name: str, task_path: str):
        super().__init__(name, task_path)
        self.default_model = 'coqui/xtts-v2'
        self.voice = None
        self.output_dir = os.path.join(task_path, 'audios')
        os.makedirs(self.output_dir, exist_ok=True)
        
    def configure(self, default_model=None, voice=None):
        if default_model:
            self.default_model = default_model
        if voice:
            self.voice = voice

    def run(self, inputs: dict):
        # Extract monologue text from various possible keys
        voice_text = (inputs.get('ad_monologue_text') or 
                     inputs.get('monologue_text') or 
                     inputs.get('hook', '') + ' ' + inputs.get('main_content', '') + ' ' + inputs.get('call_to_action', ''))
        
        if not voice_text or not voice_text.strip():
            print("⚠️ [VoiceoverNode] No text found for voiceover generation")
            return {'voiceover_path': None}

        # Generate output path
        intended_path = os.path.join(self.output_dir, 'voiceover.mp3')
        voiceover_path = self.prepare_output_path(intended_path)
        
        # Check if should use cached file
        if self.should_use_cache(voiceover_path):
            self.log_cache_status(voiceover_path, True)
            return {'voiceover_path': voiceover_path}
        
        self.log_cache_status(voiceover_path, False)
        
        try:
            # Get effective parameters
            overrides = inputs.get(self.name, {}) if isinstance(inputs.get(self.name), dict) else {}
            model_params = self.get_model_parameters(asset_path=voiceover_path, overrides=overrides)
            current_model = model_params.get('model', self.default_model)
            
            print(f"🎤 [VoiceoverNode] Generating voiceover with model: {current_model}")
            print(f"🎤 [VoiceoverNode] Text: {voice_text[:100]}...")
            
            # Extract voice if provided in params
            voice = model_params.get('voice', self.voice)
            
            # Save config BEFORE generation so it exists even if generation fails
            metadata_to_save = {
                'model': current_model,
                'voice': voice,
                'text': voice_text.strip(),
                **model_params
            }
            self.save_asset_metadata(voiceover_path, metadata_to_save)
            
            result_path = replicate_tts(
                text=voice_text.strip(),
                voice=voice,
                model=current_model,
                output_dir=self.output_dir
            )
            
            # Rename to consistent filename for caching
            if result_path and os.path.exists(result_path):
                os.rename(result_path, voiceover_path)
                
                print(f"✅ [VoiceoverNode] Voiceover generated: {voiceover_path}")
                
                # VoiceoverNode typically generates a single file (not segmented per sub_video)
                # But DVM structure has voiceover under sub_video_{i}.
                # VoiceoverNode is usually for the whole ad if not segmented?
                # Or maybe it's not used in the main segmented workflow?
                # The segmented workflow uses SegmentedVoiceoverNode.
                # If this node is used, we might want to store it under a global key if DVM supported it?
                # DVM has 'bgm', 'final_video'. Maybe add 'voiceover_full'?
                # For now, skipping DVM update for full VoiceoverNode unless we add a key.
                
                return {'voiceover_path': voiceover_path}
            else:
                print(f"❌ [VoiceoverNode] Generation failed")
                return {'voiceover_path': None}
            
        except Exception as e:
            print(f"❌ [VoiceoverNode] Failed: {str(e)}")
            return {'voiceover_path': None}
    
    def get_output_fields(self) -> list:
        """Declare node output fields (field names in state)"""
        return ['voiceover_path']


class BGMNode(GenModelNode):
    """Background music generation node using Replicate"""

    def __init__(self, name: str, task_path: str):
        super().__init__(name, task_path)
        self.default_model = 'meta/musicgen-large'
        self.default_duration = 20.0
        self.output_dir = os.path.join(task_path, 'audios')
        os.makedirs(self.output_dir, exist_ok=True)
        
    def configure(self, default_model=None, default_duration=None):
        if default_model:
            self.default_model = default_model
        if default_duration:
            self.default_duration = default_duration

    def run(self, inputs: dict):
        # Build BGM prompt from mood and style
        mood = inputs.get('mood_keywords', 'energetic')
        style = inputs.get('visual_style', 'modern')
        
        bgm_prompt = f"Background music for an advertisement. Mood: {mood}. Style: {style}, cinematic, clean mix."
        
        # Calculate BGM duration based on total video duration
        bgm_duration = self.default_duration  # fallback default
        video_durations = inputs.get('video_durations', [])
        if video_durations:
            try:
                total_video_duration = sum(float(d) for d in video_durations if d is not None)
                if total_video_duration > 0:
                    bgm_duration = total_video_duration
                    print(f"🎵 [BGMNode] Using total video duration: {bgm_duration:.1f}s")
            except Exception as e:
                print(f"⚠️  [BGMNode] Failed to calculate video duration, using default: {e}")
        
        # Generate output path
        intended_path = os.path.join(self.output_dir, 'bgm.mp3')
        bgm_path = self.prepare_output_path(intended_path)
        
        # Check if should use cached file
        if self.should_use_cache(bgm_path):
            self.log_cache_status(bgm_path, True)
            return {'bgm_path': bgm_path}
        
        self.log_cache_status(bgm_path, False)
        
        try:
            # Get effective parameters
            overrides = inputs.get(self.name, {}) if isinstance(inputs.get(self.name), dict) else {}
            model_params = self.get_model_parameters(asset_path=bgm_path, overrides=overrides)
            current_model = model_params.get('model', self.default_model)
            current_duration = model_params.get('duration', bgm_duration)
            
            print(f"🎵 [BGMNode] Generating BGM with model: {current_model}")
            print(f"🎵 [BGMNode] Prompt: {bgm_prompt}")
            print(f"🎵 [BGMNode] Duration: {current_duration:.1f}s")
            
            # Save config BEFORE generation so it exists even if generation fails
            metadata_to_save = {
                'model': current_model,
                'prompt': bgm_prompt,
                'duration': current_duration,
                **model_params
            }
            self.save_asset_metadata(bgm_path, metadata_to_save)
            
            result_path = replicate_bgm(
                prompt=bgm_prompt,
                duration_s=current_duration,
                model=current_model,
                output_dir=self.output_dir
            )
            
            # Rename to consistent filename for caching
            if result_path and os.path.exists(result_path):
                os.rename(result_path, bgm_path)
                
                # Update data version
                self.update_data_version(['bgm'], bgm_path)
                
                print(f"✅ [BGMNode] BGM generated: {bgm_path}")
                return {'bgm_path': bgm_path}
            else:
                print(f"❌ [BGMNode] Generation failed")
                return {'bgm_path': None}
            
        except Exception as e:
            print(f"❌ [BGMNode] Failed: {str(e)}")
            return {'bgm_path': None}
    
    def get_output_fields(self) -> list:
        """Declare node output fields (field names in state)"""
        return ['bgm_path']


class VideoEditNode(ToolNode):
    """Video editing node to mux video + voiceover + BGM"""

    def __init__(self, name: str, task_path: str):
        super().__init__(name, task_path)
        self.output_dir = os.path.join(task_path, 'final_videos')
        os.makedirs(self.output_dir, exist_ok=True)
        # Default tool parameters (can be overridden by apply_parameters)
        self.video_volume = 0.35
        self.video_volumes = None  # Per-segment volumes (if set, overrides video_volume)
        self.narration_volume = 0.60
        self.bgm_volume = 0.90
        self.normalize = True
        self.fade_duration = 0.5
        
    def configure(self, output_dir=None):
        if output_dir:
            self.output_dir = output_dir
            os.makedirs(self.output_dir, exist_ok=True)

    def run(self, inputs: dict):
        # Apply runtime parameters from state if provided
        try:
            prm = inputs.get('_node_runtime_params', {}).get('edit', {}).get('parameters', {})
            if prm:
                print(f"🧩 [VideoEditNode] Applying parameters: {prm}")
            self.apply_parameters(prm)
        except Exception as e:
            print(f"⚠️ [VideoEditNode] Failed to apply runtime parameters: {e}")
        # Get input paths
        videos = inputs.get('generated_videos', [])
        
        # Get segmented voiceover paths (new approach)
        segmented_voiceover_paths = []
        if 'segmented_voiceover_generation' in inputs and inputs['segmented_voiceover_generation']:
            segmented_voiceover_paths = inputs['segmented_voiceover_generation'].get('segmented_voiceover_paths', [])
        elif 'segmented_voiceover_paths' in inputs:
            segmented_voiceover_paths = inputs['segmented_voiceover_paths']
        
        # Get BGM path from various possible sources  
        bgm_path = None
        if 'bgm_generation' in inputs and inputs['bgm_generation']:
            bgm_path = inputs['bgm_generation'].get('bgm_path')
            print(f"🎵 [VideoEditNode] Found BGM from bgm_generation: {bgm_path}")
        elif 'bgm_path' in inputs:
            bgm_path = inputs['bgm_path']
            print(f"🎵 [VideoEditNode] Found BGM from direct path: {bgm_path}")
        
        if not videos:
            print("⚠️ [VideoEditNode] No videos found for editing")
            return {'final_video': None}
        
        print(f"✂️ [VideoEditNode] Processing {len(videos)} video segments")
        print(f"✂️ [VideoEditNode] Segmented voiceovers: {len(segmented_voiceover_paths)} segments")
        print(f"✂️ [VideoEditNode] BGM: {bgm_path}")
        
        # Generate output path for the final concatenated video
        intended_path = os.path.join(self.output_dir, "final_complete_video.mp4")
        output_path = self.prepare_output_path(intended_path)
        
        # Check if should use cached file
        if self.should_use_cache(output_path):
            self.log_cache_status(output_path, True)
            return {'final_video': output_path}
        
        self.log_cache_status(output_path, False)
        
        try:
            print(f"✂️ [VideoEditNode] Creating complete video from segments...")
            
            # Prepare video_volumes parameter
            # If video_volumes is set and is a list, use it; otherwise use video_volume for all
            volumes_param = {}
            if self.video_volumes and isinstance(self.video_volumes, list):
                volumes_param['video_volumes'] = self.video_volumes
                print(f"🔊 [VideoEditNode] Using per-segment volumes: {self.video_volumes}")
            else:
                volumes_param['video_volume'] = self.video_volume
                print(f"🔊 [VideoEditNode] Using global volume: {self.video_volume}")
            
            final_path = mux_video_with_audio_segments(
                video_paths=videos,
                narration_paths=segmented_voiceover_paths,
                bgm_path=bgm_path,
                output_path=output_path,
                **volumes_param,
                narration_volume=self.narration_volume,
                bgm_volume=self.bgm_volume,
                normalize=self.normalize,
                fade_duration=self.fade_duration,
            )
            
            # Save metadata
            metadata_to_save = {
                'video_volume': self.video_volume,
                'video_volumes': self.video_volumes,
                'narration_volume': self.narration_volume,
                'bgm_volume': self.bgm_volume,
                'normalize': self.normalize,
                'fade_duration': self.fade_duration,
                'bgm_path': bgm_path,
                'segments_count': len(segmented_voiceover_paths),
                'videos_count': len(videos)
            }
            self.save_asset_metadata(final_path, metadata_to_save)
            
            # Update data version
            self.update_data_version(['final_video'], final_path)
            
            print(f"✅ [VideoEditNode] Created final complete video: {final_path}")
            return {'final_video': final_path}
            
        except Exception as e:
            print(f"❌ [VideoEditNode] Failed to create complete video: {str(e)}")
            raise Exception(f"Video editing failed: {str(e)}")
    
    def get_output_fields(self) -> list:
        """Declare node output fields (field names in state)"""
        return ['final_video']

    # ---- ToolNode interface ----
    def get_input_schema(self) -> dict:
        return {
            'generated_videos': {'type': 'list[string]', 'required': True, 'description': 'Generated video file path list'},
            'segmented_voiceover_paths': {'type': 'list[string]', 'required': False, 'description': 'Segmented voiceover audio path list'},
            'segmented_voiceover_generation': {'type': 'dict', 'required': False, 'description': 'Segmented voiceover generation result (alternative to segmented_voiceover_paths)'},
            'bgm_path': {'type': 'string', 'required': False, 'description': 'Background music file path'},
            'bgm_generation': {'type': 'dict', 'required': False, 'description': 'BGM generation result (alternative to bgm_path)'}
        }

    def get_parameter_schema(self) -> dict:
        return {
            'video_volume': {'type': 'float', 'default': 0.35, 'range': [0.0, 2.0], 'description': 'Global video audio volume (used if video_volumes not set)'},
            'video_volumes': {'type': 'list[float]', 'default': None, 'description': 'Per-segment video volumes (overrides video_volume if provided)'},
            'narration_volume': {'type': 'float', 'default': 0.60, 'range': [0.0, 2.0], 'description': 'Narration audio volume'},
            'bgm_volume': {'type': 'float', 'default': 0.90, 'range': [0.0, 2.0], 'description': 'Background music volume'},
            'normalize': {'type': 'boolean', 'default': True, 'description': 'Normalize all audio tracks'},
            'fade_duration': {'type': 'float', 'default': 0.5, 'range': [0.0, 5.0], 'description': 'Fade in/out duration (seconds)'}
        }

    def apply_parameters(self, params: dict):
        if not isinstance(params, dict):
            return
        self.video_volume = float(params.get('video_volume', self.video_volume))
        
        # Handle video_volumes (can be list or None)
        if 'video_volumes' in params:
            vv = params['video_volumes']
            if vv is None:
                self.video_volumes = None
            elif isinstance(vv, list):
                self.video_volumes = [float(v) for v in vv]
            else:
                print(f"⚠️ [VideoEditNode] Invalid video_volumes type: {type(vv)}, ignoring")
        
        self.narration_volume = float(params.get('narration_volume', self.narration_volume))
        self.bgm_volume = float(params.get('bgm_volume', self.bgm_volume))
        self.normalize = bool(params.get('normalize', self.normalize))
        self.fade_duration = float(params.get('fade_duration', self.fade_duration))


class SegmentedVoiceoverNode(GenModelNode):
    """Segmented voiceover generation node for multi-segment videos"""

    def __init__(self, name: str, task_path: str):
        super().__init__(name, task_path)
        self.default_model = 'coqui/xtts-v2'
        self.voice = None
        # Removed self.output_dir as segments are now stored in sub_video dirs
        
    def configure(self, default_model=None, voice=None):
        if default_model:
            self.default_model = default_model
        if voice:
            self.voice = voice

    def run(self, inputs: dict):
        """
        Standard run method following the unified fine-grained execution architecture
        
        Architecture pattern (same as ImageNode/VideoNode):
        1. Scan for dirty elements using BaseNode.scan_dirty_elements()
        2. If dirty elements exist: incremental execution (only dirty segments)
        3. Else: full execution (all segments)
        4. Clean dirty flags using BaseNode.clean_dirty_flags()
        """
        # Get segmented monologue data
        # Note: workflow unpacks segmented_monologue_design, so segments is directly in inputs
        segments = inputs.get('segments')
        if not segments:
            # Try legacy format for backwards compatibility
            segmented_monologue = inputs.get('segmented_monologue_design')
            if segmented_monologue and segmented_monologue.get('segments'):
                segments = segmented_monologue['segments']
        
        if not segments:
            print("⚠️ [SegmentedVoiceoverNode] No segmented monologue found")
            return {'segmented_voiceover_paths': []}
        
        # Scan for dirty elements (fine-grained execution)
        dirty_segments = self.scan_dirty_elements(segments)
        
        if dirty_segments and not self._force_execute:
            # Incremental execution - only process dirty segments
            result = self._incremental_execution(dirty_segments, segments, inputs)
        else:
            # Full execution - process all segments
            result = self._full_execution(segments, inputs)
        
        return result
    
    def _incremental_execution(self, dirty_segments: dict, segments: list, inputs: dict) -> dict:
        """
        Incremental execution: only regenerate dirty segments
        
        This is the fine-grained execution path following the unified architecture
        (same pattern as ImageNode/VideoNode._incremental_execution)
        """
        print(f"🎯 [SegmentedVoiceoverNode] Incremental execution: processing {len(dirty_segments)} segment(s)")
        print(f"   Dirty segments: {list(dirty_segments.keys())}")
        
        voiceover_paths = []
        
        for i, segment in enumerate(segments):
            if i in dirty_segments:
                # Dirty segment - regenerate
                print(f"   🔄 Regenerating segment {i}, dirty fields: {dirty_segments[i]}")
                # Clean dirty metadata from segment before passing to generation
                clean_segment = {k: v for k, v in segment.items() 
                                if not k.startswith('_dirty')} if isinstance(segment, dict) else segment
                path = self._generate_single_segment(clean_segment, i, inputs)
                voiceover_paths.append(path)
            else:
                # Not dirty - find and return existing cached audio
                existing_path = self._get_existing_voiceover(i)
                if existing_path:
                    print(f"   📄 Using cached segment {i}: {os.path.basename(existing_path)}")
                    voiceover_paths.append(existing_path)
                else:
                    # Cached audio missing, need to generate
                    print(f"   ⚠️ Cached segment {i} missing, regenerating...")
                    clean_segment = {k: v for k, v in segment.items() 
                                    if not k.startswith('_dirty')} if isinstance(segment, dict) else segment
                    path = self._generate_single_segment(clean_segment, i, inputs)
                    voiceover_paths.append(path)
        
        # Clean dirty flags using BaseNode helper
        cleaned_segments = self.clean_dirty_flags(segments)
        
        return {
            'segmented_voiceover_paths': voiceover_paths,
            'segments': cleaned_segments
        }
    
    def _full_execution(self, segments: list, inputs: dict) -> dict:
        """
        Full execution: generate all segments
        
        This is the standard execution path when no dirty segments exist or force_execute is True
        """
        if self._force_execute:
            print(f"🎤 [SegmentedVoiceoverNode] Full regeneration (force_execute=True)")
        else:
            print(f"🎤 [SegmentedVoiceoverNode] Full regeneration (no dirty segments)")
        
        print(f"🎤 [SegmentedVoiceoverNode] Processing {len(segments)} segments")
        
        voiceover_paths = []
        for i, segment in enumerate(segments):
            path = self._generate_single_segment(segment, i, inputs)
            voiceover_paths.append(path)
        
        return {'segmented_voiceover_paths': voiceover_paths}
    
    def _get_existing_voiceover(self, idx: int):
        """
        Get the latest existing versioned voiceover file path for a given segment index.
        Returns None if no voiceover file exists.
        """
        sub_video_dir = os.path.join(self.task_path, f'sub_video_{idx}')
        if not os.path.exists(sub_video_dir):
            return None
        
        name = 'voiceover'
        ext = '.mp3'
        
        # Look for versioned files: voiceover_v1.mp3, voiceover_v2.mp3, ...
        max_v = 0
        for f in os.listdir(sub_video_dir):
            if f.startswith(f"{name}_v") and f.endswith(ext):
                v_str = f[len(name) + 2: -len(ext)]
                if v_str.isdigit():
                    max_v = max(max_v, int(v_str))
        
        if max_v > 0:
            return os.path.abspath(os.path.join(sub_video_dir, f"{name}_v{max_v}{ext}"))
        
        # Fallback: check non-versioned file
        plain_path = os.path.join(sub_video_dir, f"{name}{ext}")
        if os.path.exists(plain_path):
            return os.path.abspath(plain_path)
        
        return None
    
    def _generate_single_segment(self, segment: dict, i: int, inputs: dict):
        """Generate a single TTS segment (extracted from original run loop)"""
        segment_text = segment.get('segment_text', '')
        if not segment_text.strip():
            print(f"⚠️ [SegmentedVoiceoverNode] Empty text for segment {i+1}")
            return None
        
        # Generate output path for this segment
        sub_video_dir = os.path.join(self.task_path, f'sub_video_{i}')
        os.makedirs(sub_video_dir, exist_ok=True)
        
        intended_path = os.path.join(sub_video_dir, 'voiceover.mp3')
        segment_path = self.prepare_output_path(intended_path)
        
        # Check if should use cached segment
        if self.should_use_cache(segment_path):
            self.log_cache_status(segment_path, True)
            return segment_path
        
        self.log_cache_status(segment_path, False)
        
        try:
            # Get effective parameters (overrides from segment dict)
            overrides = segment if isinstance(segment, dict) else {}
            model_params = self.get_model_parameters(asset_path=segment_path, overrides=overrides)
            current_model = model_params.get('model', self.default_model)
            
            print(f"🎤 [SegmentedVoiceoverNode] Generating segment {i+1}: {segment_text[:50]}...")
            print(f"   Using model: {current_model}")
            
            # Generate with adaptive speed to ensure <= 5s
            safe_text = segment_text.strip()
            if len(safe_text) > 220:
                safe_text = safe_text[:220]

            # Determine target duration window based on per-segment overrides or video durations
            seg_targets = inputs.get('segment_target_seconds') or []
            min_target = None
            max_target = None
            if isinstance(seg_targets, list) and i < len(seg_targets):
                tgt = seg_targets[i]
                if isinstance(tgt, (list, tuple)) and len(tgt) == 2:
                    try:
                        min_target = float(int(tgt[0]))
                        max_target = float(int(tgt[1]))
                        if min_target < 1:
                            min_target = 1.0
                        if max_target < min_target:
                            max_target = min_target
                    except Exception:
                        min_target = None
                        max_target = None
            if min_target is None or max_target is None:
                video_durations = inputs.get('video_durations') or []
                seg_video_dur = None
                if isinstance(video_durations, list) and i < len(video_durations):
                    try:
                        seg_video_dur = float(video_durations[i]) if video_durations[i] is not None else None
                    except Exception:
                        seg_video_dur = None
                if seg_video_dur and seg_video_dur > 0:
                    min_target = max(0.5, 0.70 * seg_video_dur)
                    max_target = seg_video_dur
                else:
                    min_target, max_target = 3.0, 5.0

            # Always use 1.0 speed - no speed adjustment
            tts_speed = 1.0
            
            # Extract voice from params
            voice = model_params.get('voice', self.voice)
            
            # Save config BEFORE generation so it exists even if generation fails
            metadata_to_save = {
                'model': current_model,
                'voice': voice,
                'text': safe_text,
                'target_duration': [min_target, max_target],
                **model_params
            }
            self.save_asset_metadata(segment_path, metadata_to_save)
            
            tmp_path = replicate_tts(
                text=safe_text,
                voice=voice,
                model=current_model,
                output_dir=sub_video_dir,
                speed=tts_speed
            )
            # Measure duration
            try:
                from moviepy import AudioFileClip
                clip = AudioFileClip(tmp_path)
                dur = clip.duration
                clip.close()
            except Exception:
                dur = None
                print(f"❌ [SegmentedVoiceoverNode] Failed to measure duration for segment {i+1}")

            if dur is not None:
                os.rename(tmp_path, segment_path)
                
                # Update metadata with actual duration after successful generation
                metadata_to_save['duration'] = dur
                self.save_asset_metadata(segment_path, metadata_to_save)
                
                if dur <= max_target:
                    print(f"✅ [SegmentedVoiceoverNode] Generated segment {i+1} (speed=1.0): {segment_path} ({dur:.2f}s, target {min_target:.2f}-{max_target:.2f}s)")
                else:
                    print(f"⚠️  [SegmentedVoiceoverNode] Generated segment {i+1} (speed=1.0): {segment_path} ({dur:.2f}s > {max_target:.2f}s target) - Script may need regeneration")
                
                # Update data version
                self.update_data_version([f'sub_video_{i}', 'voiceover'], segment_path)
                
                return segment_path
            else:
                # Failed to measure duration, but keep the file
                try:
                    os.rename(tmp_path, segment_path)
                    print(f"⚠️  [SegmentedVoiceoverNode] Generated segment {i+1} but couldn't measure duration: {segment_path}")
                    
                    # Update data version even if duration check failed
                    self.update_data_version([f'sub_video_{i}', 'voiceover'], segment_path)
                    
                    return segment_path
                except Exception:
                    print(f"❌ [SegmentedVoiceoverNode] Failed to save segment {i+1}")
                    return None
                
        except Exception as e:
            print(f"❌ [SegmentedVoiceoverNode] Error generating segment {i+1}: {str(e)}")
            return None
    
    def get_output_fields(self) -> list:
        """Declare node output fields (field names in state)"""
        return ['segmented_voiceover_paths']
