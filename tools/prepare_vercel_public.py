from __future__ import annotations

import shutil
from pathlib import Path


RUNTIME_STATIC_DIRECTORIES = ("css", "img", "js")


def prepare_public_assets(repo_root: Path) -> Path:
    """Copy only runtime assets into Vercel's public directory."""
    repo_root = repo_root.resolve()
    source_root = (repo_root / "app" / "static").resolve()
    target_root = (repo_root / "public" / "static").resolve()
    target_root.relative_to(repo_root)

    if not source_root.is_dir():
        raise FileNotFoundError(f"Static source directory does not exist: {source_root}")

    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True)

    for directory_name in RUNTIME_STATIC_DIRECTORIES:
        source = source_root / directory_name
        if not source.is_dir():
            raise FileNotFoundError(f"Runtime asset directory does not exist: {source}")
        shutil.copytree(source, target_root / directory_name)

    return target_root


if __name__ == "__main__":
    prepare_public_assets(Path(__file__).resolve().parents[1])
