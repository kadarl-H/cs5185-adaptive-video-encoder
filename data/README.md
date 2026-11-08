# 数据目录

把课程提供的 zip 解压到这里，保持下面的结构（`data/` 已被 `.gitignore` 忽略，不会进仓库）：

```
data/
└─ CS5185_Project_Video_Dataset/
   ├─ 01_FourPeople.mp4
   ├─ 02_Beauty.mp4
   ├─ ...
   ├─ 12_ControlledBurn.mp4
   ├─ metadata/
   │  ├─ 01_FourPeople.json
   │  └─ ...
   ├─ licenses/
   └─ preview.jpg
```

- 开发集：01, 02, 03, 04, 07, 08
- 测试集（保留，不要用于调参）：05, 06, 09, 10
- 11、12 课程未明确分配

解压后先跑 `python -m src.probe --data data/CS5185_Project_Video_Dataset` 核对元数据。
