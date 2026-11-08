# 课程要求摘要（来自 Project Description + Implementation Appendix）

## 任务

对 12 个 720p30、无音轨的视频，分别压到原文件大小的 **5%** 与 **2%**，构建
`内容分析 → 参数决策 → FFmpeg x264 编码 → 体积/质量检查 → 回退重编` 闭环。
只能用 FFmpeg 的 libx264；不得删帧或截短；输出必须完整时长、可解码。

## 关键公式

```
target_bytes = floor(S * r)                 # S 原始字节，r = 0.05 / 0.02
video_bps    = 0.98 * 8 * target_bytes / T  # T 秒；0.98 是容器开销余量
next_bps     = bps * target_bytes / actual_bytes * 0.98   # 超预算时
```

- 十进制单位：1 MB = 1,000,000 B；1 kbps = 1,000 bit/s
- 不要把预算四舍五入到 MB
- 最多 3 次尝试；保留所有可用候选

## 两遍编码

```
ffmpeg -y -i INPUT -an -c:v libx264 -preset medium -pix_fmt yuv420p \
  -b:v RATEk -pass 1 -passlogfile JOB -f null NUL
ffmpeg -y -i INPUT -an -c:v libx264 -preset medium -pix_fmt yuv420p \
  -b:v RATEk -pass 2 -passlogfile JOB -movflags +faststart OUT.mp4
```

解码校验：

```
ffmpeg -v error -xerror -i OUT.mp4 -map 0:v:0 -f null NUL
```

## 内容特征（起步版）

- 平均绝对灰度帧差（时间变化）
- 边缘像素占比（细节强度）

可选进阶：运动强度、场景切换、纹理复杂度、预训练模型 / VLLM。

## x264 可调项

`preset`、`crf` / `b:v`、`g`、`bf`、`refs`、`aq-mode`、`aq-strength`、
`sc_threshold`、`me_method`、`subq`、`rc-lookahead`、`tune`、`psy-rd`、
`deblock`、`x264-params`。

## 评测

- 指标：PSNR-Y（全帧聚合后取对数）与 MS-SSIM；记录实现与配置
- 同时间点抽帧对比：模糊、块效应、拖影、细节丢失
- 记录：目标/实际大小、目标/实际码率、FFmpeg 参数、运行时间、尝试轮次
- 时间从读元数据开始到评测结束（含两次 pass、重试、API 等待）

## 交付

1. 可运行代码（依赖、启动命令、FFmpeg 版本、输入约束）
2. 报告（流程、特征、决策、反馈、结果、局限、成员贡献、第三方来源）
3. 实验结果（≥3 视频 × 两档：参数、输出、特征曲线、日志、代表帧）
4. 5–6 页 PPT，5 分钟展示

## 评分

| 项 | 权重 |
|---|---|
| 系统完整性 | 35% |
| 实验设计与分析 | 25% |
| 报告与可复现性 | 20% |
| 展示与团队协作 | 10% |
| 结果数值 | 10% |
