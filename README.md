# CS5185 · 内容自适应视频编码（Content-Adaptive Video Encoding）

课程小组项目：构建一条「内容分析 → 参数决策 → FFmpeg/x264 编码 → 质量与体积校验 → 回退重编」的完整闭环，
把 12 个 720p30 视频分别压缩到原文件大小的 **5%** 和 **2%**，并保证完整时长、可正常解码。

> 课程要求：只能用 FFmpeg 的 libx264 做编码与封装；不能通过删帧/截短来满足体积；方法与决策逻辑自选但要讲清楚依据。

---

## 快速开始

```powershell
# 1) 环境
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) FFmpeg（必需）
winget install --id Gyan.FFmpeg -e
ffmpeg -version
ffmpeg -hide_banner -h encoder=libx264

# 3) 数据：把 zip 解压到 data/，保持如下结构
#    data/CS5185_Project_Video_Dataset/01_FourPeople.mp4 ...
#    data/CS5185_Project_Video_Dataset/metadata/01_FourPeople.json ...

# 4) 生成预算表
python -m src.probe --data data/CS5185_Project_Video_Dataset --out logs/videos.csv

# 5) 单个视频跑完整流水线（5%）
python -m src.pipeline --video data/CS5185_Project_Video_Dataset/01_FourPeople.mp4 --ratio 0.05

# 6) 全部开发集 × 两档
python -m src.pipeline --split dev --ratios 0.05 0.02

# 7) 统一基线（固定 preset，不做内容自适应）
python -m src.pipeline --split dev --ratios 0.05 0.02 --baseline

# 8) 汇总成表格与图
python -m scripts.summarize
```

## 目录结构

```
src/
  probe.py       读取元数据 / ffprobe，计算 5% 与 2% 的 target_bytes 和目标码率
  features.py    内容分析：灰度帧差、边缘像素占比，输出时间线与图
  decision.py    特征 → x264 参数的规则映射（可替换为搜索 / 模型 / LLM）
  encode.py      两遍 x264 编码 + 体积反馈回退（保留每个候选）
  evaluate.py    PSNR-Y、MS-SSIM、同时间点抽帧
  pipeline.py    端到端编排，产出 logs/results.csv
data/            数据集（不入库）
out/             编码输出与 passlog（不入库）
logs/            CSV / JSONL 日志
reports/         图表、对比帧、报告素材
docs/            课程要求摘要与实现笔记
```

## 流水线

```
metadata ──► 预算计算 ──► 内容特征 ──► 参数决策 ──► 两遍编码 ──► 体积检查
                                              ▲                      │
                                              └──── 回退重编 ◄────────┘
                                                      │
                                              解码校验 + PSNR/MS-SSIM + 抽帧
```

关键规则（来自课程附录）：

- `target_bytes = floor(S * r)`，`video_bps = 0.98 * 8 * target_bytes / T`
- 超预算回退：`next_bps = bps * target_bytes / actual_bytes * 0.98`
- 最多 3 次尝试；**保留可用候选**，后一次失败不能覆盖前一次
- 用十进制 MB / kbps；不要四舍五入到 MB
- 时间统计从读元数据开始，到评测结束（含两次 pass 与重试）

> 实现备注：5 秒短片段上纯 ABR 两遍会明显超出目标体积（实测可达 +40%~+50%），
> `encode.py` 因此固定加 `-maxrate <目标码率> -bufsize <2×目标码率>`，把实际大小压回 ±3% 内。

## 当前结果（Week 1）

统一基线（6 个开发视频 × 5%/2%，共 12 次）：

- 12/12 落在 ±3% 内，平均绝对误差 **1.76%**，最大 2.91%，解码校验 12/12
- 平均 PSNR-Y：5% 档 **39.04 dB**，2% 档 **37.58 dB**
- 明细：[logs/baseline.csv](logs/baseline.csv)，汇总：[reports/baseline_summary.md](reports/baseline_summary.md)

自适应（候选搜索）对比同一基线：

- 8/12 胜出，平均 ΔPSNR **+0.03 dB**，编码耗时约为基线的 5 倍
- 明细：[reports/adaptive_vs_baseline.md](reports/adaptive_vs_baseline.md)

保留测试集（05/06/09/10 × 两档）：8/8 达标；`09_Parkrun` 最难（5%→2% 掉约 3.6 dB）。

关键工程发现：5 秒短片段上纯 ABR 两遍会超预算 40%–50%，必须加 VBV（`-maxrate`/`-bufsize`）。

报告与幻灯片草稿：[report/CS5185_Project_Report.docx](report/CS5185_Project_Report.docx)、
[report/CS5185_Project_Slides.pptx](report/CS5185_Project_Slides.pptx)。

```powershell
python -m scripts.summarize       # 基线表 + PSNR 图
python -m scripts.compare         # 自适应 vs 基线
python -m scripts.export_frames   # 代表帧对比（reports/frames/，不入库）
python scripts/make_report.py     # 生成 docx/pptx（需 python-docx / python-pptx）
```

## 数据划分

| 用途 | 视频 |
|---|---|
| 开发 | 01, 02, 03, 04, 07, 08 |
| 测试（保留） | 05, 06, 09, 10 |
| 未分配 | 11, 12 |

## 团队分工

| 角色 | 负责 | 主要文件 |
|---|---|---|
| A 数据与流水线 | 元数据、预算、编码封装、解码校验、日志 | `probe.py` `encode.py` `pipeline.py` |
| B 内容分析 | 特征、时间线可视化 | `features.py` |
| C 决策与反馈 | 特征→参数映射、回退策略 | `decision.py` |
| D 评测与文档 | 基线、PSNR/MS-SSIM、抽帧、报告/PPT | `evaluate.py` `reports/` |

## 四周计划

- **Week 1**：跑通统一基线；完成元数据、预算表与两条特征曲线
- **Week 2**：特征分析 + 时间线 + 初版参数决策
- **Week 3**：编码、回退、三类视频测试、成功/失败案例分析
- **Week 4**：修问题、整理代码与结果、报告、PPT、预演

## 提交清单

- [ ] 可运行代码 + 依赖 + 启动命令 + FFmpeg 版本
- [ ] 项目报告（流程、特征、决策、反馈、结果、局限、成员贡献、第三方来源）
- [ ] 实验结果：≥3 个视频 × 5%/2%，参数、实际大小、码率、耗时、特征曲线、代表帧
- [ ] 5–6 页 PPT（5 分钟）

## 注意

- 数据集与课程 PDF 不纳入版本库（见 `.gitignore`）。
- 提交前请确认没有把 `auth token`、API key 写进代码或日志。
