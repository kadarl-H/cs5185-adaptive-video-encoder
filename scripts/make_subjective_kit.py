"""Build a subjective-comparison kit: original | baseline | adaptive at t=2.5s."""
from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import cv2
import numpy as np

from src.encode import _ffmpeg

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
DATASET = ROOT / "data" / "CS5185_Project_Video_Dataset"
OUT = ROOT / "reports" / "subjective"
VIDEOS = ["01_FourPeople", "03_Bosphorus", "07_Mobcal"]
RATIOS = ["5%", "2%"]
T = 2.5


def load(name):
    with (LOGS / name).open(encoding="utf-8-sig") as fh:
        return {(r["video_id"], r["ratio"]): r for r in csv.DictReader(fh)}


def grab(src: Path, dst: Path) -> bool:
    exe = _ffmpeg()
    cmd = [exe, "-y", "-ss", str(T), "-i", str(src), "-frames:v", "1",
           "-q:v", "2", str(dst)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def panel(path: Path, label: str) -> np.ndarray:
    img = cv2.imread(str(path))
    if img is None:
        raise RuntimeError(f"cannot read {path}")
    img = cv2.resize(img, (1280, 720))
    bar = np.full((46, 1280, 3), 30, np.uint8)
    cv2.putText(bar, label, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    return np.vstack([bar, img])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = load("baseline.csv")
    adaptive = load("results.csv")
    cards = []

    for name in VIDEOS:
        for ratio in RATIOS:
            key = (name, ratio)
            base_out = Path(baseline[key]["output"])
            ada_out = Path(adaptive[key]["output"])
            tmp = OUT / f"{name}_{ratio}_tmp"
            tmp.mkdir(exist_ok=True)
            orig_png = tmp / "orig.png"
            base_png = tmp / "base.png"
            ada_png = tmp / "ada.png"
            grab(DATASET / f"{name}.mp4", orig_png)
            grab(base_out, base_png)
            grab(ada_out, ada_png)

            top = np.hstack([
                panel(orig_png, "Original"),
                panel(base_png, f"Baseline  PSNR {float(baseline[key]['psnr_y_db']):.2f}"),
                panel(ada_png, f"Adaptive  PSNR {float(adaptive[key]['psnr_y_db']):.2f}"),
            ])
            dst = OUT / f"{name}_{ratio.replace('%','pct')}.png"
            cv2.imwrite(str(dst), top)
            cards.append((name, ratio, dst.name))
            print("wrote", dst)

    html = ["""<!doctype html><meta charset="utf-8">
<title>CS5185 subjective comparison</title>
<style>
body{font-family:system-ui,sans-serif;margin:24px;background:#fafafa}
img{width:100%;border:1px solid #ccc;margin:8px 0}
table{border-collapse:collapse;margin:12px 0}
td,th{border:1px solid #bbb;padding:6px 10px}
select{padding:2px 6px}
button{padding:8px 16px;font-size:15px}
</style>
<h1>主观比较打分表</h1>
<p>每个视频、每个预算看一张三联图（原片 / 基线 / 自适应），对两种压缩结果分别打 1–5 分。</p>
<p>1 = 很差，3 = 可接受，5 = 几乎无差别。建议在同一显示器、原分辨率下观看；表格下方的“导出 CSV”会下载填写结果。</p>
"""]
    for i, (name, ratio, fname) in enumerate(cards, 1):
        html.append(f"<h3>{i}. {name} — {ratio}</h3><img src='{fname}'>")
        for method in ("baseline", "adaptive"):
            html.append(
                f"<table><tr><th>{method}</th><th>清晰度</th><th>块效应</th><th>运动流畅</th></tr>"
                f"<tr><td>评分</td>"
                f"<td><select class='score' data-v='{name}' data-r='{ratio}' data-m='{method}' data-k='sharp'>"
                + "".join(f"<option>{x}</option>" for x in range(1, 6)) + "</select></td>"
                f"<td><select class='score' data-v='{name}' data-r='{ratio}' data-m='{method}' data-k='block'>"
                + "".join(f"<option>{x}</option>" for x in range(1, 6)) + "</select></td>"
                f"<td><select class='score' data-v='{name}' data-r='{ratio}' data-m='{method}' data-k='motion'>"
                + "".join(f"<option>{x}</option>" for x in range(1, 6)) + "</select></td>"
                "</tr></table>"
            )
    html.append("""<button onclick="exportCsv()">导出 CSV</button>
<script>
function exportCsv(){
  const rows=[["video","ratio","method","sharpness","blockiness","motion"]];
  document.querySelectorAll("select.score").forEach(s=>{
    rows.push([s.dataset.v,s.dataset.r,s.dataset.m,s.value,
      document.querySelector(`select[data-v='${s.dataset.v}'][data-r='${s.dataset.r}'][data-m='${s.dataset.m}'][data-k='block']`).value,
      document.querySelector(`select[data-v='${s.dataset.v}'][data-r='${s.dataset.r}'][data-m='${s.dataset.m}'][data-k='motion']`).value]);
  });
  const csv=rows.map(r=>r.join(",")).join("\\n");
  const a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));
  a.download="scores.csv";a.click();
}
</script>""")
    (OUT / "index.html").write_text("\n".join(html), encoding="utf-8")
    print("written", OUT / "index.html")


if __name__ == "__main__":
    main()
