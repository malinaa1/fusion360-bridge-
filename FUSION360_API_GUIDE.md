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

## 九、装配体操作 (Assembly)

### 核心概念

装配体由多个 **Component** 通过 **Joints** 连接而成：

```
rootComponent                    ← 顶层装配体
 ├─ occurrences                  ← 子组件实例集合
 │   ├─ occurrence[0] → Component A
 │   └─ occurrence[1] → Component B
 ├─ asmJoints                    ← 装配关节集合
 └─ jointOrigins                  ← 关节原点集合
```

### 创建子组件

```python
# 方式1：创建空组件
occurrence = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
comp = occurrence.component
comp.name = "MyPart"
# ... 往 comp 中添加草图和特征 ...

# 方式2：插入外部设计
occurrence = root.occurrences.addByInsert(
    external_design,
    adsk.core.Matrix3D.create()
)
```

### 定位组件

```python
# 通过 transform 矩阵移动组件
transform = adsk.core.Matrix3D.create()
transform.translation = adsk.core.Vector3D.create(x, y, z)
occurrence.transform = transform
```

### 创建关节 (Joint)

```python
# 1. 在两个组件上创建关节原点
origin_input = component.jointOrigins.createInput(face)
origin_a = component.jointOrigins.add(origin_input)

# 2. 创建关节
joint_input = root.asmJoints.createInput(
    occurrence_a, origin_a,
    occurrence_b, origin_b
)
joint_input.jointMotionType = JointTypes.RevoluteJointType  # 旋转关节
# 也可用: RigidJointType (固定), SliderJointType (滑动)

joint = root.asmJoints.add(joint_input)
```

### 关节类型

| 类型 | 自由度 | 用途 |
|------|--------|------|
| `RigidJointType` | 0 | 固定连接 |
| `RevoluteJointType` | 1 (旋转) | 铰链、轴承 |
| `SliderJointType` | 1 (平移) | 导轨、滑块 |
| `CylindricalJointType` | 2 | 轴套 |
| `BallJointType` | 3 | 球铰 |

### 示例

运行 `examples/create_assembly.py` → 创建底板+轴+轴套的装配体

---

## 十、曲面建模 (Surface Modeling)

### 放样 (Loft)

在多个轮廓之间创建过渡曲面：

```python
loft_input = root.features.loftFeatures.createInput(
    adsk.fusion.FeatureOperations.NewBodyFeatureOperation
)
# 按顺序添加轮廓
loft_input.loftSections.add(sketch_bottom.profiles.item(0))
loft_input.loftSections.add(sketch_middle.profiles.item(0))
loft_input.loftSections.add(sketch_top.profiles.item(0))
loft_input.isSolid = True  # 实体还是曲面
loft = root.features.loftFeatures.add(loft_input)
```

### 扫掠 (Sweep)

沿路径扫掠轮廓：

```python
sweep_input = root.features.sweepFeatures.createInput(
    profile,        # 要扫掠的轮廓
    path_curve,     # 路径曲线
    FeatureOperations.NewBodyFeatureOperation
)
sweep = root.features.sweepFeatures.add(sweep_input)
```

### 构造平面 (Construction Plane)

在 3D 空间创建草图平面：

```python
# 偏移平面
plane_input = root.constructionPlanes.createInput()
plane_input.setByOffset(reference_plane, ValueInput.createByReal(offset))
new_plane = root.constructionPlanes.add(plane_input)

# 在偏移平面上创建草图
sketch = root.sketches.add(new_plane)
```

### 示例

运行 `examples/surface_modeling.py` → 用 Loft + Sweep 创建瓶子造型

---

## 十一、工程图 (Drawing)

### 创建工程图文档

```python
# 先保存设计
design_doc.saveAs(path, None, "Part Name", "")

# 创建工程图文档
drawing_doc = app.documents.add(
    adsk.core.DocumentTypes.FusionDrawingDocumentType
)
```

### 视图管理

```python
drawing = drawing_doc.products.item(0)
sheet = drawing.rootView  # 图纸

# 创建基础视图
base_view = sheet.sheetViews.addBaseView(
    source_design,     # 源 3D 设计
    Point2D.create(x, y),  # 图纸位置
    ValueInput.createByReal(scale),  # 比例
    ViewOrientations.FrontViewOrientation,
    DrawingViewStyles.VisibleEdgesDrawingViewStyle,
    "View Name"
)

# 创建投影视图
projected_view = sheet.sheetViews.addProjectedView(
    base_view,
    Point2D.create(x, y),
    ViewOrientations.TopViewOrientation
)
```

### 尺寸标注

```python
drawing_curves = base_view.drawingCurves
dims = sheet.drawingDimensions

# 通用尺寸
dims.addGeneralDimension(
    drawing_curves.item(0),  # 标注对象
    Point2D.create(x, y)     # 位置
)
```

### 导出 PDF

```python
export_mgr = drawing_doc.products.item(0).exportManager
pdf_opts = export_mgr.createPDFExportOptions(output_path)
export_mgr.execute(pdf_opts)
```

### 示例

运行 `examples/create_drawing.py` → 创建支架零件并生成工程图

---

## 十二、CAM 刀路规划

### CAM 模块

```python
import adsk.cam  # 需要 Manufacturing 许可证

cam_mgr = adsk.cam.CAMManager.get()
```

### 创建 Setup

```python
setup_input = cam_mgr.setupOperations.createInput(
    adsk.cam.OperationTypes.SetupOperation
)
# 设置毛坯模式
setup_input.stockMode = SetupStockModes.RelativeBoxStockMode
# 设置工件坐标系原点
setup_input.wcsOriginPoint = Point3D.create(0, 0, 0)
setup = cam_mgr.setupOperations.add(setup_input)
```

### 2D Pocket 铣削

```python
pocket_input = cam_mgr.pocket2DOperations.createInput(
    adsk.cam.OperationTypes.Pocket2DOperation
)
# 选择加工面、设置切削参数
pocket_input.maximumStepdown = ValueInput.createByReal(0.3)  # 每刀深度 3mm
pocket = cam_mgr.pocket2DOperations.add(pocket_input)
```

### 2D Contour (轮廓铣削)

```python
contour_input = cam_mgr.contour2DOperations.createInput(
    adsk.cam.OperationTypes.Contour2DOperation
)
contour = cam_mgr.contour2DOperations.add(contour_input)
```

### 后处理 (生成 G-code)

```python
post_input = cam_mgr.postProcess.createInput(
    adsk.cam.PostProcessInput.GenericPost
)
post_input.outputFile = r"C:\output\part.nc"
post_input.openInEditor = False
cam_mgr.postProcess.execute(post_input)
```

### 常用操作类型

| 操作 | 类 | 用途 |
|------|-----|------|
| 面铣 (Facing) | `FaceOperation` | 平面精加工 |
| 袋铣 (Pocket) | `Pocket2DOperation` | 挖槽/内腔 |
| 轮廓 (Contour) | `Contour2DOperation` | 外形精加工 |
| 钻孔 (Drill) | `DrillOperation` | 钻孔 |
| 自适应 (Adaptive) | `AdaptiveClearingOperation` | 高效粗加工 |

### 示例

运行 `examples/cam_toolpath.py` → 创建带槽零件并设置 CAM 刀路

---

## 十三、学习资源

- **官方 API 参考**: `help.autodesk.com/view/fusion360/ENU/` → API Reference Manual
- **对象模型 PDF**: 在官方帮助页面搜索 "Fusion 360 API Object Model"
- **Autodesk 开发者博客**: `blog.autodesk.io`
- **Fusion 360 API 论坛**: `forums.autodesk.com/t5/fusion-api-and-scripts-forum/`
- **Maker Show 视频**: Microsoft Learn 搜索 "Intro to Fusion 360 API"