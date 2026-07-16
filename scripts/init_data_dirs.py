"""Create the data/ directory structure required by the project."""

from pathlib import Path

DIRS = [
    # API sources
    "data/sources/api/arxiv/metadata",
    "data/sources/api/arxiv/pdfs",
    "data/sources/api/github/releases",
    "data/sources/api/github/repos",
    "data/sources/api/zenodo/records",
    "data/sources/api/huggingface/models",
    # Web sources
    "data/sources/web/paperswithcode/papers",
    "data/sources/web/franka/panda",
    "data/sources/web/robotiq/grippers",
    "data/sources/web/allegro/hand",
    "data/sources/web/mujoco/examples",
    "data/sources/web/isaac/examples",
    # Datasets
    "data/sources/datasets/ycb/models",
    "data/sources/datasets/graspnet",
    "data/sources/datasets/dexgraspnet/data",
    "data/sources/datasets/google_scanned/models",
    # System
    "data/experience_db",
    "data/output_packages",
]

for d in DIRS:
    Path(d).mkdir(parents=True, exist_ok=True)
    print(f"  ✓ {d}")

print("data/ 目录结构已创建")
