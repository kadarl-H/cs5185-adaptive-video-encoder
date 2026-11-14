"""Compare pretrained-network features with the handcrafted CV features."""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def spearman(a, b):
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    ra = (ra - ra.mean()) / (ra.std() + 1e-9)
    rb = (rb - rb.mean()) / (rb.std() + 1e-9)
    return float(np.mean(ra * rb))


def main():
    nn = {}
    with (REPORTS / "features_nn.csv").open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            nn[row["video"]] = row

    cvs = {}
    for path in (REPORTS / "features").glob("*.csv"):
        with path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            continue
        diff = np.mean([float(r["frame_diff"]) for r in rows])
        edge = np.mean([float(r["edge_fraction"]) for r in rows])
        cvs[path.stem] = (diff, edge)

    common = sorted(set(nn) & set(cvs))
    print(f"{'video':16s} {'cv_diff':>8s} {'cv_edge':>8s} {'nn_drift':>9s} {'nn_spread':>10s} {'top1'}")
    for v in common:
        d, e = cvs[v]
        r = nn[v]
        print(f"{v:16s} {d:8.2f} {e:8.3f} {float(r['nn_drift']):9.4f} "
              f"{float(r['nn_spread']):10.4f} {r['nn_top1']}")

    d = np.array([cvs[v][0] for v in common])
    e = np.array([cvs[v][1] for v in common])
    drift = np.array([float(nn[v]["nn_drift"]) for v in common])
    spread = np.array([float(nn[v]["nn_spread"]) for v in common])

    print("\nSpearman(cv_diff, nn_drift)  =", round(spearman(d, drift), 3))
    print("Spearman(cv_edge, nn_spread) =", round(spearman(e, spread), 3))

    for name, a, b in (("diff vs drift", d, drift), ("edge vs spread", e, spread)):
        ma, mb = a > np.median(a), b > np.median(b)
        print(f"{name}: median-split agreement {np.mean(ma == mb):.2f}")


if __name__ == "__main__":
    main()
