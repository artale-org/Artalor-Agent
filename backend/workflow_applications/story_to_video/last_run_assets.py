# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

import json
import os
from typing import Dict, Optional


LAST_RUN_FILENAME = "last_run_assets.json"


def _slot_key(group_key: str, item_key: str) -> str:
    return f"{group_key}::{item_key}"


def load_last_run_assets(task_path: str) -> Dict[str, str]:
    """
    Load snapshot of asset versions used by the last successful workflow run.
    Format: { "group::item": "/abs/path/to/file", ... }
    """
    if not task_path:
        return {}
    path = os.path.join(task_path, LAST_RUN_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        return {}


def get_last_run_asset(task_path: str, group_key: str, item_key: str) -> Optional[str]:
    assets = load_last_run_assets(task_path)
    return assets.get(_slot_key(group_key, item_key))


def save_last_run_assets(task_path: str) -> Dict[str, str]:
    """
    Persist snapshot of current data_version.json as "last workflow run used these versions".
    Only writes if data_version.json exists and is valid.
    """
    if not task_path:
        raise ValueError("task_path is required")

    dv_path = os.path.join(task_path, "data_version.json")
    if not os.path.exists(dv_path):
        return {}

    with open(dv_path, "r", encoding="utf-8") as f:
        dv = json.load(f) or {}

    snapshot: Dict[str, str] = {}

    for group_key, group_value in (dv or {}).items():
        if isinstance(group_value, dict) and "curr_version" in group_value:
            curr = group_value.get("curr_version")
            if curr:
                snapshot[_slot_key(group_key, group_key)] = str(curr)
        elif isinstance(group_value, dict):
            for item_key, item_value in group_value.items():
                if isinstance(item_value, dict) and "curr_version" in item_value:
                    curr = item_value.get("curr_version")
                    if curr:
                        snapshot[_slot_key(group_key, item_key)] = str(curr)

    out_path = os.path.join(task_path, LAST_RUN_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    return snapshot
