# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

import json
import os
from typing import Dict


MANUAL_DIRTY_FILENAME = "manual_dirty_flags.json"


def _key(group_key: str, item_key: str) -> str:
    return f"{group_key}::{item_key}"


def load_manual_dirty_flags(task_path: str) -> Dict[str, bool]:
    """
    Load UI-only manual dirty flags for a task.
    This is intentionally separate from workflow dirty_flags.json and should NOT propagate.
    """
    if not task_path:
        return {}
    path = os.path.join(task_path, MANUAL_DIRTY_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        # Normalize values to bool
        return {str(k): bool(v) for k, v in data.items()}
    except Exception:
        return {}


def is_manual_dirty(task_path: str, group_key: str, item_key: str) -> bool:
    flags = load_manual_dirty_flags(task_path)
    return bool(flags.get(_key(group_key, item_key), False))


def set_manual_dirty(task_path: str, group_key: str, item_key: str, dirty: bool = True) -> Dict[str, bool]:
    """
    Set or clear manual dirty for a single asset slot.
    Persists to manual_dirty_flags.json in the task folder.
    """
    if not task_path:
        raise ValueError("task_path is required")
    if not group_key or not item_key:
        raise ValueError("group_key and item_key are required")

    path = os.path.join(task_path, MANUAL_DIRTY_FILENAME)
    flags = load_manual_dirty_flags(task_path)

    k = _key(group_key, item_key)
    if bool(dirty):
        flags[k] = True
    else:
        flags.pop(k, None)

    if flags:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(flags, f, indent=2, ensure_ascii=False)
    else:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    return flags


def clear_all_manual_dirty(task_path: str) -> None:
    """
    Clear all manual dirty flags (UI-only).
    Typically called after a successful workflow run which establishes a new baseline.
    """
    if not task_path:
        return
    path = os.path.join(task_path, MANUAL_DIRTY_FILENAME)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


