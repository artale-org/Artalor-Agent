# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

# modules/tools/audio_gen.py
from langchain_core.tools import BaseTool
# from kokoro_onnx import Kokoro
# import soundfile as sf
import uuid
# import torch
# from diffusers.pipelines.audioldm2.pipeline_audioldm2 import AudioLDM2Pipeline
from typing import List, Union, Literal
from pydantic import BaseModel, Field
import os
import replicate
import requests
from datetime import datetime
import numpy as np
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips, concatenate_audioclips
from moviepy.audio.AudioClip import AudioArrayClip


# Define structured output data model
class Narration(BaseModel):
    type: Literal["narration"] = Field(default="narration")
    voice_actor: str = Field(..., description="Voice actor/persona, e.g., Morgan Freeman")
    emotion: str = Field(..., description="Vocal emotion, e.g., calm, excited, sad")
    content: str = Field(..., description="Narration content")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")


class AmbientSound(BaseModel):
    type: Literal["ambient_sound"] = Field(default="ambient_sound")
    description: str = Field(..., description="Detailed description of ambient sound")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")


AudioSegment = Union[Narration, AmbientSound]


class AudioScript(BaseModel):
    segments: List[AudioSegment]


def replicate_tts(text: str, voice: str = None, model: str = "lucataco/xtts", output_dir: str = "audios", speed: float = None) -> str:
    """Generate TTS via Replicate model and return local file path."""
    inputs = { "text": text }
    if voice:
        inputs["voice"] = voice
    if speed is not None:
        # Many TTS models accept a generic 'speed' parameter; safe to pass when supported
        inputs["speed"] = speed
    prediction = replicate.predictions.create(model, input=inputs)
    while prediction.status in ("starting", "processing"):
        prediction = replicate.predictions.get(prediction.id)
    if prediction.status != "succeeded":
        raise RuntimeError(f"Replicate TTS failed: {prediction.status}")
    url = prediction.output if isinstance(prediction.output, str) else prediction.output[0]
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    out_path = os.path.join(output_dir, f"tts_{ts}.mp3")
    data = requests.get(url).content
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path

def replicate_bgm(prompt: str, duration_s: float = 20.0, model: str = "stability-ai/stable-audio-open-1.0", output_dir: str = "audios") -> str:
    """Generate background music via Replicate model and return local file path."""
    inputs = { "prompt": prompt, "duration": int(duration_s + 0.99) }  # input for duration is int
    prediction = replicate.predictions.create(model, input=inputs)
    while prediction.status in ("starting", "processing"):
        prediction = replicate.predictions.get(prediction.id)
    if prediction.status != "succeeded":
        raise RuntimeError(f"Replicate BGM failed: {prediction.status}")
    url = prediction.output if isinstance(prediction.output, str) else prediction.output[0]
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    out_path = os.path.join(output_dir, f"bgm_{ts}.mp3")
    data = requests.get(url).content
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path

# --- Added: Simple editing utility to mux video + narration + bgm ---

def _compute_rms(audio_array: np.ndarray) -> float:
    if audio_array.size == 0:
        return 0.0
    # ensure float
    arr = audio_array.astype(np.float32, copy=False)
    return float(np.sqrt(np.mean(np.square(arr))))

def _normalize_audio_clip(clip: AudioFileClip, target_rms: float) -> AudioArrayClip:
    """Return a new AudioArrayClip whose RMS matches target_rms (simple RMS normalization)."""
    try:
        fps = getattr(clip, 'fps', 44100)
        arr = clip.to_soundarray(fps=fps)
        rms = _compute_rms(arr)
        if rms <= 0.0:
            # silent or invalid, return silent clip of same duration
            num_samples = int(max(clip.duration, 0) * fps)
            channels = arr.shape[1] if arr.ndim == 2 else 1
            silent = np.zeros((num_samples, channels), dtype=np.float32)
            return AudioArrayClip(silent, fps=fps).with_duration(clip.duration)
        scale = target_rms / rms
        arr2 = np.clip(arr * scale, -1.0, 1.0).astype(np.float32)
        return AudioArrayClip(arr2, fps=fps).with_duration(clip.duration)
    except Exception:
        # On failure, fall back to original
        return clip

def _scale_audio_clip(clip: AudioFileClip, factor: float) -> AudioArrayClip:
    """Return a new AudioArrayClip scaled by factor."""
    try:
        fps = getattr(clip, 'fps', 44100)
        arr = clip.to_soundarray(fps=fps)
        arr2 = np.clip(arr * factor, -1.0, 1.0).astype(np.float32)
        return AudioArrayClip(arr2, fps=fps).with_duration(clip.duration)
    except Exception:
        return clip

def _make_silence(duration_s: float, fps: int = 44100, channels: int = 2) -> AudioArrayClip:
    """Create a silent AudioArrayClip of given duration, fps, and channels."""
    if duration_s <= 0:
        duration_s = 0.0001
    num_samples = int(duration_s * fps)
    arr = np.zeros((num_samples, max(1, channels)), dtype=np.float32)
    return AudioArrayClip(arr, fps=fps).with_duration(duration_s)

def mux_video_with_audio_segments(
    video_paths: list,
    narration_paths: list = None,
    bgm_path: str = None,
    output_path: str = None,
    *,
    video_volume: float = 0.35,
    video_volumes: list = None,  # Per-segment video volumes (overrides video_volume if provided)
    narration_volume: float = 0.60,
    bgm_volume: float = 0.90,
    normalize: bool = True,
    fade_duration: float = 0.5,
) -> str:
    """
    Merge multiple video segments with corresponding narration segments and overall BGM.
    
    Audio Processing with Normalization:
    1. For each video segment:
       - Preserve original video audio (normalized, scaled by video_volume or video_volumes[i])
       - Add narration/TTS (normalized, scaled to narration_volume)
       - Mix both tracks together
    2. Concatenate all video segments
    3. Add BGM to final video (normalized, scaled to bgm_volume)
    
    Args:
        video_volumes: Optional list of per-segment video volumes. If provided, overrides video_volume.
                      If not provided or shorter than video_paths, falls back to video_volume.
    
    All audio tracks are normalized first (RMS-based) to ensure consistent loudness,
    then scaled to appropriate levels before mixing to prevent volume inconsistencies.
    """
    if not video_paths or not any(os.path.exists(vp) for vp in video_paths if vp):
        raise ValueError("No valid video paths provided")
    
    # Load valid videos
    video_segments = []
    opened_audios = []  # defer closing until after write
    for i, vp in enumerate(video_paths):
        if not vp or not os.path.exists(vp):
            print(f"⚠️ [VideoMux] Skipping invalid video path: {vp}")
            continue
            
        video = VideoFileClip(vp)
        
        # Collect audio tracks to mix
        audio_tracks = []
        
        # 1. Preserve and normalize original video audio (if exists)
        if video.audio is not None:
            # Determine volume for this segment
            if video_volumes and isinstance(video_volumes, list) and i < len(video_volumes):
                current_video_volume = float(video_volumes[i])
            else:
                current_video_volume = float(video_volume)
            
            print(f"🔊 [VideoMux] Preserving original video audio for segment {i+1} (volume: {current_video_volume:.2f})")
            try:
                if normalize:
                    original_audio_norm = _normalize_audio_clip(video.audio, target_rms=0.10)
                else:
                    original_audio_norm = video.audio
                original_audio_scaled = _scale_audio_clip(original_audio_norm, current_video_volume)
                # Ensure video audio starts at time 0 for proper mixing
                original_audio_scaled = original_audio_scaled.with_start(0)
                audio_tracks.append(original_audio_scaled)
                opened_audios.extend([original_audio_norm, original_audio_scaled])
            except Exception as e:
                print(f"⚠️ [VideoMux] Failed to process original audio: {str(e)}")
        
        # 2. Add corresponding narration if available (do NOT close before final write)
        if narration_paths and i < len(narration_paths) and narration_paths[i] and not (isinstance(narration_paths[i], str) and str(narration_paths[i]).startswith('dummy://')):
            # Assume absolute path protocol; resolve once and validate
            np_raw = narration_paths[i]
            narration_path = os.path.abspath(np_raw)
            if narration_path and os.path.exists(narration_path):
                print(f"🎤 [VideoMux] Resolved narration path: {narration_path}")
                print(f"🎤 [VideoMux] Adding narration to segment {i+1}")
                try:
                    narration = AudioFileClip(narration_path)
                    
                    # Check if narration loaded properly
                    if narration.reader is None:
                        print(f"⚠️ [VideoMux] Narration file corrupted: {narration_path}")
                    else:
                        # Adjust narration to match video duration
                        if narration.duration > video.duration:
                            narration = narration.subclipped(0, video.duration)
                        elif narration.duration < video.duration:
                            # Pad with silence using manual array concatenation
                            # (concatenate_audioclips has a bug that loses audio at the beginning)
                            try:
                                fps = getattr(narration, 'fps', 44100)
                                narration_arr = narration.to_soundarray(fps=fps)
                                channels = narration_arr.shape[1] if narration_arr.ndim == 2 else 1
                            except Exception:
                                fps, channels = 44100, 2
                                narration_arr = narration.to_soundarray(fps=fps)
                            remaining = max(0.0, float(video.duration) - float(narration.duration))
                            silence_samples = int(remaining * fps)
                            silence_arr = np.zeros((silence_samples, channels), dtype=np.float32)
                            padded_arr = np.concatenate([narration_arr, silence_arr], axis=0)
                            narration = AudioArrayClip(padded_arr, fps=fps).with_duration(video.duration)
                        
                        narration_norm = _normalize_audio_clip(narration, target_rms=0.12) if normalize else narration
                        narration_scaled = _scale_audio_clip(narration_norm, float(narration_volume))
                        # Ensure narration starts at time 0 for proper mixing
                        narration_scaled = narration_scaled.with_start(0)
                        audio_tracks.append(narration_scaled)
                        opened_audios.extend([narration_norm, narration_scaled])
                        
                        # Close original reader
                        try:
                            narration.close()
                        except Exception:
                            pass
                except Exception as e:
                    print(f"⚠️ [VideoMux] Failed to load narration {narration_path}: {str(e)}")
            else:
                print(f"⚠️ [VideoMux] Narration file not found at: {narration_path}")
        
        # 3. Mix all audio tracks for this segment
        if audio_tracks:
            print(f"🎚️ [VideoMux] Mixing {len(audio_tracks)} audio track(s) for segment {i+1}")
            mixed_audio = CompositeAudioClip(audio_tracks)
            video = video.with_audio(mixed_audio)
            opened_audios.append(mixed_audio)
        
        video_segments.append(video)
    
    if not video_segments:
        raise ValueError("No valid video segments created")
    
    print(f"🎬 [VideoMux] Concatenating {len(video_segments)} video segments")
    
    # Concatenate all video segments
    if len(video_segments) == 1:
        final_video = video_segments[0]
    else:
        final_video = concatenate_videoclips(video_segments)
    
    # Add BGM to the final concatenated video (defer close until after write)
    if bgm_path and not (isinstance(bgm_path, str) and bgm_path.startswith('dummy://')):
        print(f"🎵 [VideoMux] Adding BGM to final video")
        try:
            resolved_bgm = os.path.abspath(bgm_path)
            if not os.path.exists(resolved_bgm):
                print(f"⚠️ [VideoMux] BGM file not found at: {resolved_bgm}")
                bgm = None
            else:
                print(f"🎵 [VideoMux] Resolved BGM path: {resolved_bgm}")
                bgm = AudioFileClip(resolved_bgm)
                if bgm.reader is None:
                    print(f"⚠️ [VideoMux] BGM file corrupted: {resolved_bgm}")
                    bgm = None
                else:
                    print(f"🎵 [VideoMux] BGM loaded successfully, duration: {bgm.duration}s")
        except Exception as e:
            print(f"⚠️ [VideoMux] Failed to load BGM {bgm_path}: {str(e)}")
            bgm = None
    else:
        bgm = None
    
    if bgm:
        print(f"🎵 [VideoMux] Processing BGM with normalization={normalize}")
        # Adjust BGM duration to match final video without looping (pad with silence)
        if bgm.duration > final_video.duration:
            bgm = bgm.subclipped(0, final_video.duration)
        elif bgm.duration < final_video.duration:
            # Pad with silence using manual array concatenation
            # (concatenate_audioclips has a bug that loses audio at the beginning)
            try:
                fps = getattr(bgm, 'fps', 44100)
                bgm_arr = bgm.to_soundarray(fps=fps)
                channels = bgm_arr.shape[1] if bgm_arr.ndim == 2 else 1
            except Exception:
                fps, channels = 44100, 2
                bgm_arr = bgm.to_soundarray(fps=fps)
            remaining = max(0.0, float(final_video.duration) - float(bgm.duration))
            silence_samples = int(remaining * fps)
            silence_arr = np.zeros((silence_samples, channels), dtype=np.float32)
            padded_arr = np.concatenate([bgm_arr, silence_arr], axis=0)
            bgm = AudioArrayClip(padded_arr, fps=fps).with_duration(final_video.duration)
        
        # Normalize BGM to consistent loudness
        if normalize:
            print(f"🎚️ [VideoMux] Normalizing BGM audio")
            bgm_norm = _normalize_audio_clip(bgm, target_rms=0.08)
        else:
            bgm_norm = bgm
        # Scale to configured volume
        bgm_scaled = _scale_audio_clip(bgm_norm, float(bgm_volume))
        # Ensure BGM starts at time 0 for proper mixing
        bgm_scaled = bgm_scaled.with_start(0)
        if fade_duration and fade_duration > 0:
            try:
                # Prefer clip methods if available to avoid import dependency on moviepy.audio.fx
                if hasattr(bgm_scaled, 'audio_fadein'):
                    bgm_scaled = bgm_scaled.audio_fadein(fade_duration)
                if hasattr(bgm_scaled, 'audio_fadeout'):
                    bgm_scaled = bgm_scaled.audio_fadeout(fade_duration)
            except Exception:
                pass
        print(f"🔉 [VideoMux] BGM scaled to {bgm_volume:.2f} for background mixing")
        
        # Mix BGM with existing audio (video + narration)
        if final_video.audio:
            print(f"🎚️ [VideoMux] Mixing BGM with existing audio tracks")
            mixed_audio = CompositeAudioClip([final_video.audio, bgm_scaled])
            final_video = final_video.with_audio(mixed_audio)
            opened_audios.append(mixed_audio)
        else:
            final_video = final_video.with_audio(bgm_scaled)
        opened_audios.extend([bgm, bgm_norm, bgm_scaled])
    
    # Set output path
    if not output_path:
        os.makedirs("videos", exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        output_path = os.path.join("videos", f"final_complete_{ts}.mp4")
    
    print(f"💾 [VideoMux] Writing final video: {output_path}")
    final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
    
    # Clean up (close AFTER writing to avoid NoneType readers)
    try:
        final_video.close()
    except Exception:
        pass
    for clip in opened_audios:
        try:
            clip.close()
        except Exception:
            pass
    for video in video_segments:
        try:
            video.close()
        except Exception:
            pass
    
    return output_path
