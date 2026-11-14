"""Compare adaptive against two baselines: default GOP and GOP=60."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"


def load(name):
    path = LOGS / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main():
    default = {(r["video_id"], r["ratio"]): r for r in load("baseline.csv")}
    gop60 = {(r["video_id"], r["ratio"]): r for r in load("baseline_gop60.csv")}
    adaptive = {(r["video_id"], r["ratio"]): r for r in load("results.csv")
                if r.get("mode") == "adaptive"}

    keys = sorted(set(default) & set(gop60) & set(adaptive))
    if not keys:
        print("no overlapping rows")
        return

    rows = []
    for k in keys:
        d, g, a = default[k], gop60[k], adaptive[k]
        rows.append({
            "video": k[0], "ratio": k[1],
            "default": float(d["psnr_y_db"]),
            "gop60": float(g["psnr_y_db"]),
            "adaptive": float(a["psnr_y_db"]),
            "cand": a.get("candidate", ""),
        })

    print(f"{'video':16s} {'ratio':4s} {'default':>8s} {'gop60':>8s} {'adaptive':>9s} "
          f"{'a-default':>10s} {'a-gop60':>9s} candidate")
    for r in rows:
        print(f"{r['video']:16s} {r['ratio']:4s} {r['default']:8.3f} {r['gop60']:8.3f} "
              f"{r['adaptive']:9.3f} {r['adaptive']-r['default']:+10.3f} "
              f"{r['adaptive']-r['gop60']:+9.3f} {r['cand']}")

    d1 = [r["adaptive"] - r["default"] for r in rows]
    d2 = [r["adaptive"] - r["gop60"] for r in rows]
    print()
    print(f"adaptive - default: mean {sum(d1)/len(d1):+.4f} dB, wins {sum(x>0 for x in d1)}/{len(d1)}")
    print(f"adaptive - gop60  : mean {sum(d2)/len(d2):+.4f} dB, wins {sum(x>0 for x in d2)}/{len(d2)}")

    g = [r["gop60"] - r["default"] for r in rows]
    print(f"gop60 - default   : mean {sum(g)/len(g):+.4f} dB, better {sum(x>0 for x in g)}/{len(g)}")


if __name__ == "__main__":
    main()
