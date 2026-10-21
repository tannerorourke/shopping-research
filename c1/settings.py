"""
Settings access for the c1 package. Wraps the shared settings module so the
rest of c1 reads one small surface, and resolves the unpacked extension path
and its manifest version (the server warns when that version drifts).
"""
import json
import os
import pathlib

import settings
from settings import C1Settings

__all__ = ["C1Settings", "load", "extension_path", "manifest_version"]


def load() -> C1Settings:
    return settings.current().c1


def extension_path(s: C1Settings) -> str:
    # -- relative paths anchor at the repo root so cwd never matters
    return str((settings.ROOT / os.path.expanduser(s.extension_dir)).resolve())


def manifest_version(s: C1Settings) -> str | None:
    manifest = pathlib.Path(extension_path(s)) / "manifest.json"
    if not manifest.is_file():
        return None
    return json.loads(manifest.read_text(encoding="utf-8")).get("version")
