# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

import json
import os
from typing import List, Dict, Any, Optional

class DataVersionManager:
    def __init__(self, task_path: str):
        self.task_path = task_path
        self.file_path = os.path.join(task_path, 'data_version.json')
        self.data = {}
        self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"⚠️ Failed to load data_version.json: {e}")
                self.data = {}

    def save(self):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def initialize_from_storyboard(self, storyboard: List[Dict], global_assets: Optional[List[str]] = None, segment_assets: Optional[List[str]] = None):
        """
        Initialize data structure based on storyboard.
        Structure:
        {
            "sub_video_0": {
                "image": {"curr_version": None, "historical_version": []},
                "video": {"curr_version": None, "historical_version": []},
                "voiceover": {"curr_version": None, "historical_version": []}
            },
            ...
            "bgm": {"curr_version": None, "historical_version": []},
            "final_video": {"curr_version": None, "historical_version": []}
        }
        
        Args:
            storyboard: List of storyboard frame dicts.
            global_assets: List of global asset keys to initialize (default: ['bgm', 'final_video']).
            segment_assets: List of per-segment asset types (default: ['image_first', 'image_last', 'video', 'voiceover']).
        """
        if not storyboard:
            return
        
        if global_assets is None:
            global_assets = ['bgm', 'final_video']
        if segment_assets is None:
            segment_assets = ['image_first', 'image_last', 'video', 'voiceover']
            
        # Force reload to ensure we don't overwrite with stale data
        self._load()

        for i, _ in enumerate(storyboard):
            key = f"sub_video_{i}"
            if key not in self.data:
                self.data[key] = {}
            
            for asset_type in segment_assets:
                if asset_type not in self.data[key]:
                    self.data[key][asset_type] = {
                        "curr_version": None,
                        "historical_version": []
                    }
        
        # Global assets
        for key in global_assets:
            if key not in self.data:
                self.data[key] = {
                    "curr_version": None,
                    "historical_version": []
                }
        
        self.save()

    def update_version(self, keys: List[str], file_path: str):
        """
        Update version for a specific asset.
        keys: e.g., ['sub_video_0', 'image'] or ['bgm']
        """
        if not file_path:
            return
            
        # Force reload to ensure we don't overwrite with stale data
        self._load()

        current = self.data
        for k in keys:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        # Ensure structure exists
        if 'historical_version' not in current:
            current['historical_version'] = []
        if 'curr_version' not in current:
            current['curr_version'] = None
            
        current_val = current['curr_version']
        
        # Logic:
        # If curr_version != new_path (includes Case 1: curr is None, and Case 2: curr is different)
        # Then update curr_version AND append new_path to historical_version
        if current_val != file_path:
            current['curr_version'] = file_path
            if file_path not in current['historical_version']:
                current['historical_version'].append(file_path)
            
            print(f"🔄 [DataVersionManager] Updated {keys}: {file_path}")
            self.save()
            print(f"💾 [DataVersionManager] Version saved to disk: {self.file_path}")
        else:
            print(f"ℹ️ [DataVersionManager] No update needed for {keys} (already {file_path})")

    def get_current_version(self, keys: List[str]) -> Optional[str]:
        """
        Get current version path for a specific asset.
        Returns None if not found or if curr_version is None.
        """
        # Force reload to ensure we get the latest version
        self._load()
        
        current = self.data
        for k in keys:
            current = current.get(k)
            if current is None:
                return None
        
        return current.get('curr_version')
