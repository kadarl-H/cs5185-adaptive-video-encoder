"""Convenience entry point.

    python run.py --split dev --ratios 0.05 0.02
    python run.py --split dev --baseline --baseline-gop 60
    python run.py --video data/.../01_FourPeople.mp4 --ratio 0.05
"""
from src.pipeline import main

if __name__ == "__main__":
    main()
