"""
Runtime path resolution for running as script or as PyInstaller executable.
- App dir: where .exe lives (frozen) or project root; use for .env, Excel, writable data.
- Resource dir: where bundled data is (e.g. templates, frontend/build); _MEIPASS when frozen.
"""
import os
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def get_app_dir() -> Path:
    """Directory for config and data: exe directory when frozen, else project root."""
    if _is_frozen():
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()


def get_resource_dir() -> Path:
    """Directory for read-only bundled files (templates, frontend/build)."""
    if _is_frozen():
        return Path(sys._MEIPASS).resolve()  # type: ignore[attr-defined]
    return Path(__file__).parent.resolve()


# Convenience: single "base" for backward compatibility (app dir = where to find .env and Data)
def get_base_dir() -> Path:
    """Same as get_app_dir(): where the application runs from (exe dir or project root)."""
    return get_app_dir()
