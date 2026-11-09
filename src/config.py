"""Shared paths and constants."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
LOG_DIR = ROOT / "logs"
REPORT_DIR = ROOT / "reports"

DATASET_DIRNAME = "CS5185_Project_Video_Dataset"

# 课程设定的两档目标
RATIOS = (0.05, 0.02)

DEV_IDS = ("01", "02", "03", "04", "07", "08")
TEST_IDS = ("05", "06", "09", "10")

# 预算公式里的 2% 容器开销余量
OVERHEAD = 0.98
# 体积命中容差（±3% 视为达标）
SIZE_TOLERANCE = 0.03
MAX_ATTEMPTS = 3
DEFAULT_PRESET = "medium"


def ensure_dirs() -> None:
    for d in (OUT_DIR, LOG_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def ffmpeg_bin_dir() -> Path | None:
    """Locate a bundled FFmpeg build (tools/ffmpeg/.../bin) if one exists."""
    cache = ROOT / "tools" / "FFMPEG_BIN.txt"
    if cache.exists():
        candidate = Path(cache.read_text(encoding="utf-8").strip())
        if (candidate / "ffmpeg.exe").exists() or (candidate / "ffmpeg").exists():
            return candidate
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for exe in (ROOT / "tools").rglob(exe_name):
        return exe.parent
    return None


def ensure_ffmpeg_on_path() -> None:
    """Make a bundled FFmpeg visible to subprocesses and shutil.which()."""
    bin_dir = ffmpeg_bin_dir()
    if bin_dir is None:
        return
    path = os.environ.get("PATH", "")
    if str(bin_dir) not in path.split(os.pathsep):
        os.environ["PATH"] = str(bin_dir) + os.pathsep + path


ensure_ffmpeg_on_path()
