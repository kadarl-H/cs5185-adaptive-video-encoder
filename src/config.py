"""Shared paths and constants."""
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
