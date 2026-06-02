# Fusion 360 Python API 学习指南

> 结合 `gear_v14.py` (成功创建的渐开线齿轮) 理解 API 核心概念

---

## 一、API 对象模型 (Object Model)

Fusion 360 的所有操作都通过这个层级结构访问：

```
Application                          ← 整个 Fusion 程序
 └─ Documents                        ← 所有打开的文档
     └─ Document                     ← 单个文档
         └─ Design                   ← 设计工作区 (activeProduct)
             └─ rootComponent        ← 根组件 (所有内容的容器)
                 ├─ sketches         ← 草图集合
                 │   └─ Sketch
                 │       └─ sketchCurves
                 │           ├─ sketchCircles
                 │           ├─ sketchLines
                 │           ├─ sketchArcs
                 │           └─ sketchFittedSplines   ← 样条曲线!
                 ├─ features
                 │   ├─ extrudeFeatures
                 │   ├─ circularPatternFeatures
                 │   └─ ...
                 ├─ bRepBodies       ← 实体集合
                 └─ constructionPlanes
                     ├─ xYConstructionPlane
                     ├─ xZConstructionPlane
                     └─ yZConstructionPlane
```

### 在我们的齿轮脚本中：

```python
# gear_v14.py 第 14-17 行
app = adsk.core.Application.get()        # ← Application
design = adsk.fusion.Design.cast(app.activeProduct)  # ← Design
rt = design.rootComponent                # ← rootComponent
extrudes = rt.features.extrudeFeatures   # ← extrudeFeatures 集合
```

---

## 二、核心数据类型

| 类型 | 用途 | 示例 |
|------|------|------|
| `Point3D.create(x, y, z)` | 3D 坐标 (单位: cm) | `center = Point3D.create(0, 0, 0)` |
| `ValueInput.createByReal(n)` | 数值输入 (cm) | `ValueInput.createByReal(1.0)` |
| `ValueInput.createByString(s)` | 带单位的字符串 | `ValueInput.createByString("360 deg")` |
| `ObjectCollection.create()` | 对象集合 (传给 feature 输入) | `coll = ObjectCollection.create()` |

### 在我们的齿轮脚本中：

```python
# gear_v14.py 第 49-50 行
def to_coll(pts):
    c = adsk.core.ObjectCollection.create()   # ← ObjectCollection
    for p in pts: c.add(p)
    return c

# gear_v14.py 第 98-99 行
ci.setDistanceExtent(False,
    adsk.core.ValueInput.createByReal(thickness))  # ← ValueInput
```

---

## 三、创建草图的完整流程

### 1. 创建草图
```python
sketch = rootComponent.sketches.add(rootComponent.xYConstructionPlane)
sketch.name = "My Sketch"
```

### 2. 绘制几何体

| 方法 | 说明 |
|------|------|
| `sketchCircles.addByCenterRadius(center, radius)` | 画圆 |
| `sketchLines.addByTwoPoints(p1, p2)` | 画直线 |
| `sketchArcs.addByCenterStartSweep(center, startPt, sweepAngle)` | 画圆弧 |
| `sketchFittedSplines.add(pointCollection)` | 画拟合样条 (通过所有点) |

### 在我们的齿轮脚本中 — 6条曲线构成一个闭合齿槽：

```python
# gear_v14.py 第 82-87 行
s = sk2.sketchCurves

# ① 径向线 (齿根 → 基圆)
s.sketchLines.addByTwoPoints(V_root_R, pts_R[0])

# ② 渐开线样条 (基圆 → 齿顶) — 右齿面
s.sketchFittedSplines.add(to_coll(pts_R))

# ③ 齿顶弧 (连接两条渐开线的顶端)
s.sketchArcs.addByCenterStartSweep(center, pts_R[-1],
    short_sweep(pts_R[-1], pts_L[-1]))

# ④ 渐开线样条 (齿顶 → 基圆) — 左齿面 (反转)
s.sketchFittedSplines.add(to_coll(list(reversed(pts_L))))

# ⑤ 径向线 (基圆 → 齿根)
s.sketchLines.addByTwoPoints(pts_L[0], V_root_L)

# ⑥ 齿根弧 (连接两条径向线的底端)
s.sketchArcs.addByCenterStartSweep(center, V_root_L,
    short_sweep(V_root_L, V_root_R))
```

**关键：** 6条曲线通过共享 Point3D 对象形成闭环 → Fusion 自动识别为 Profile

---

## 四、拉伸 (Extrude) 操作

### 创建实体 (New Body)
```python
extInput = extrudes.createInput(profile, FeatureOperations.NewBodyFeatureOperation)
extInput.setDistanceExtent(False, ValueInput.createByReal(thickness))
feature = extrudes.add(extInput)
```

### 切割 (Cut)
```python
cutInput = extrudes.createInput(profile, FeatureOperations.CutFeatureOperation)
cutInput.setDistanceExtent(False, ValueInput.createByReal(thickness))
cutFeature = extrudes.add(cutInput)
```

### FeatureOperations 类型

| 操作 | 含义 |
|------|------|
| `NewBodyFeatureOperation` | 创建新的独立实体 |
| `JoinFeatureOperation` | 合并到已有实体 |
| `CutFeatureOperation` | 从已有实体中切除 |
| `IntersectFeatureOperation` | 只保留交集部分 |

### 在我们的齿轮脚本中：

```python
# gear_v14.py 第 67-69 行 — 创建齿轮毛坯 (New Body)
ei = extrudes.createInput(sk1.profiles.item(0),
    adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
ei.setDistanceExtent(False, ValueInput.createByReal(thickness))

# gear_v14.py 第 98-99 行 — 切割齿槽 (Cut)
ci = extrudes.createInput(prof,
    adsk.fusion.FeatureOperations.CutFeatureOperation)
ci.setDistanceExtent(False, ValueInput.createByReal(thickness))
```

---

## 五、圆周阵列 (Circular Pattern)

```python
# 1. 把要阵列的对象放入 ObjectCollection
pc = adsk.core.ObjectCollection.create()
pc.add(cutFeature)

# 2. 创建阵列输入
pi = rootComponent.features.circularPatternFeatures.createInput(
    pc,                              # 要阵列的对象
    rootComponent.zConstructionAxis  # 旋转轴
)

# 3. 设置参数
pi.quantity = ValueInput.createByReal(20)        # 20 个副本
pi.totalAngle = ValueInput.createByString("360 deg")  # 全周

# 4. 执行
pat = rootComponent.features.circularPatternFeatures.add(pi)
```

### 在我们的齿轮脚本中：

```python
# gear_v14.py 第 105-109 行
pc = adsk.core.ObjectCollection.create()
pc.add(cut)
pi = rt.features.circularPatternFeatures.createInput(pc, rt.zConstructionAxis)
pi.quantity = adsk.core.ValueInput.createByReal(teeth)
pi.totalAngle = adsk.core.ValueInput.createByString("360 deg")
pat = rt.features.circularPatternFeatures.add(pi)
```

---

## 六、脚本的标准结构

```python
import adsk.core, adsk.fusion, traceback

def run(context):          # ← Fusion 360 调用的入口
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        # 获取或创建设计文档
        design = adsk.fusion.Design.cast(app.activeProduct)

        # ... 你的建模代码 ...

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
```

### 对比：Script 与 Add-in

| | Script (脚本) | Add-in (附加模块) |
|---|---|---|
| 入口 | `run(context)` | `run(context)` + `stop(context)` |
| 生命周期 | 执行完即结束 | 随 Fusion 启动/关闭 |
| 适用场景 | 一次性建模操作 | 常驻后台 (如我们的 Bridge!) |
| 文件夹 | `API/Scripts/` | `API/AddIns/` |
| 清单文件 | 不需要 | 需要 `.manifest` (JSON 格式) |

---

## 七、我们踩过的坑 & 解决方案

| 问题 | 原因 | 解决 |
|------|------|------|
| Add-in 加载后没反应 | `import adsk.cam` 导入失败 (许可证不含 CAM) | 用 `try/except ImportError` 包裹 |
| Add-in 列表里找不到 | Manifest 用了旧 XML 格式 | 改用 JSON 格式 (Fusion 2703+) |
| 渐开线轮廓 = 0 个 profile | 齿顶缺少连接弧 → 曲线未闭合 | 添加 addendum arc 闭合回路 |
| 轮廓面积 = 22.98 cm² (错误) | 齿根弧走了 324° 长路径 | 用 `short_sweep()` 确保走短路径 |
| 切割找不到目标体 | `setAllExtent` + XY 平面 | 改用 `setDistanceExtent(False, thickness)` |
| 阵列 API 报错 | `CircularPatternFeatures.createInput()` 需要 ObjectCollection | 包装成 `ObjectCollection` |
| `sketchCurves.sketchCurves.xxx` | `sketchCurves` 就是集合本身 | 去掉重复的 `.sketchCurves` |

---

## 八、齿轮脚本关键技术点回顾

### 渐开线公式
```python
def involute_xy(rb, theta):
    """rb=基圆半径, theta=展开角 (弧度)"""
    return (rb*(cos(θ) + θ*sin(θ)),
            rb*(sin(θ) - θ*cos(θ)))
```

### 齿轮参数关系
```
模数 m          →  决定齿的大小
齿数 z          →  决定齿的数量
分度圆半径      = m × z / 2
基圆半径        = 分度圆半径 × cos(压力角)   # 压力角通常 20°
齿顶圆半径      = 分度圆半径 + m
齿根圆半径      = 分度圆半径 − 1.25×m
```

### 齿槽 = 6条曲线组成的闭环
```
右径向线 (根→基) → 右渐开线样条 → 齿顶弧 → 左渐开线样条 → 左径向线 → 齿根弧
    ↑                                                                      │
    └──────────────────── 回到起点 (共享端点) ────────────────────────────┘
```

---

## 九、学习资源

- **官方 API 参考**: `help.autodesk.com/view/fusion360/ENU/` → API Reference Manual
- **对象模型 PDF**: 在官方帮助页面搜索 "Fusion 360 API Object Model"
- **Autodesk 开发者博客**: `blog.autodesk.io`
- **Fusion 360 API 论坛**: `forums.autodesk.com/t5/fusion-api-and-scripts-forum/`
- **Maker Show 视频**: Microsoft Learn 搜索 "Intro to Fusion 360 API"

---


