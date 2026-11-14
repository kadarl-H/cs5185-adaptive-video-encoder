"""Pretrained-network content features (MobileNetV2 ONNX via OpenCV DNN).

    python -m scripts.nn_features

For each video: sample N frames, run MobileNetV2, and derive
  nn_drift   mean 1 - cosine(embedding_t, embedding_t+1)   (semantic change)
  nn_spread  mean per-dimension std across frames           (visual variety)
  nn_entropy mean class-distribution entropy                (semantic ambiguity)
  nn_top1    most frequent ImageNet class

Writes reports/features_nn.csv.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "mobilenet_v2.onnx"
SYNSET = ROOT / "models" / "synset.txt"
DATASET = ROOT / "data" / "CS5185_Project_Video_Dataset"
OUT = ROOT / "reports" / "features_nn.csv"


def load_labels():
    labels = []
    if not SYNSET.exists():
        return labels
    for line in SYNSET.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) == 2:
            labels.append(parts[1].split(",")[0].strip())
    return labels


def frame_indices(total: int, n: int) -> list[int]:
    if total <= n:
        return list(range(total))
    return [int(round(i * (total - 1) / (n - 1))) for i in range(n)]


def main():
    if not MODEL.exists():
        raise SystemExit(f"missing model: {MODEL}")

    net = cv2.dnn.readNetFromONNX(str(MODEL))
    names = net.getLayerNames()
    output_names = net.getUnconnectedOutLayersNames()
    embed_name = next((n for n in ("global_pool", "GlobalAveragePool", "gap") if n in names), None)
    labels = load_labels()
    print("layers:", len(names), "output:", output_names,
          "embedding layer:", embed_name or "(using output probabilities)")

    rows = []
    for video in sorted(DATASET.glob("*.mp4")):
        cap = cv2.VideoCapture(str(video))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        idxs = frame_indices(total, 8)
        feats, probs = [], []
        for idx in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                continue
            blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (224, 224),
                                         swapRB=True, crop=False)
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)
            blob = (blob - mean) / std
            net.setInput(blob)
            if embed_name:
                feats.append(net.forward(embed_name).flatten())
            p = net.forward().flatten()
            probs.append(p)
        cap.release()
        if len(probs) < 2:
            continue

        e = np.array(feats) if feats else None
        if e is not None and len(e) == len(probs):
            e = e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-9)
            drift = float(np.mean(1 - np.sum(e[1:] * e[:-1], axis=1)))
            spread = float(np.mean(np.std(e, axis=0)))
        else:
            p = np.array(probs)
            p = p / (np.linalg.norm(p, axis=1, keepdims=True) + 1e-9)
            drift = float(np.mean(1 - np.sum(p[1:] * p[:-1], axis=1)))
            spread = float(np.mean(np.std(p, axis=0)))

        p = np.array(probs)
        p = p / (p.sum(axis=1, keepdims=True) + 1e-9)
        entropy = float(np.mean([-(v * np.log(v + 1e-9)).sum() for v in p]))
        top1 = [int(np.argmax(v)) for v in p]
        best = max(set(top1), key=top1.count)
        label = labels[best] if best < len(labels) else str(best)

        rows.append({
            "video": video.stem,
            "nn_drift": round(drift, 5),
            "nn_spread": round(spread, 5),
            "nn_entropy": round(entropy, 4),
            "nn_top1": label,
            "nn_top1_share": round(top1.count(best) / len(top1), 2),
        })
        print(rows[-1])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("written", OUT)


if __name__ == "__main__":
    main()
