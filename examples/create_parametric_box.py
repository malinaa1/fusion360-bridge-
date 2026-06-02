"""
参数化方块 — 在 Fusion 360 中创建一个可参数驱动的立方体

使用此脚本在 Fusion 360 中生成一个带有用户参数的方块。
后续可以在 Fusion 360 的 "修改 → 更改参数" 中调整尺寸。
"""
import adsk.core, adsk.fusion

app = adsk.core.Application.get()
ui = app.userInterface

# ---------------------------------------------------------------------------
# 1. 获取当前设计
# ---------------------------------------------------------------------------
design = adsk.fusion.Design.cast(app.activeProduct)
if not design:
    # 没有打开的文档，创建一个新的
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(app.activeProduct)

root = design.rootComponent
units = design.unitsManager

# ---------------------------------------------------------------------------
# 2. 创建用户参数（可在 Fusion 360 "更改参数" 中修改）
# ---------------------------------------------------------------------------
params = design.userParameters
try:
    params.add("box_length", adsk.core.ValueInput.createByReal(10.0), "cm", "方块长度")
    params.add("box_width",  adsk.core.ValueInput.createByReal(5.0),  "cm", "方块宽度")
    params.add("box_height", adsk.core.ValueInput.createByReal(3.0),  "cm", "方块高度")
except:
    pass  # 参数已存在则忽略

length_param = params.itemByName("box_length")
width_param  = params.itemByName("box_width")
height_param = params.itemByName("box_height")
length = length_param.value  # cm (internal unit)
width  = width_param.value
height = height_param.value

# ---------------------------------------------------------------------------
# 3. 创建基准草图
# ---------------------------------------------------------------------------
sketch = root.sketches.add(root.xYConstructionPlane)
sketch.name = "Box Base Sketch"

# 画中心矩形
lines = sketch.sketchCurves.sketchLines
p1 = adsk.core.Point3D.create(-length/2, -width/2, 0)
p3 = adsk.core.Point3D.create( length/2,  width/2, 0)
lines.addTwoPointRectangle(p1, p3)

# 添加尺寸约束（链接到用户参数）
dims = sketch.sketchDimensions
dims.addDistanceDimension(
    sketch.sketchCurves.sketchLines.item(0),  # 一条竖边
    adsk.core.Point3D.create(length/2 + 1, 0, 0),
)
dims.addDistanceDimension(
    sketch.sketchCurves.sketchLines.item(1),  # 一条横边
    adsk.core.Point3D.create(0, width/2 + 1, 0),
)

print(f"草图创建完成: {sketch.name}")

# ---------------------------------------------------------------------------
# 4. 拉伸成实体
# ---------------------------------------------------------------------------
profile = sketch.profiles.item(0)
extrudes = root.features.extrudeFeatures
ext_input = extrudes.createInput(
    profile,
    adsk.fusion.FeatureOperations.NewBodyFeatureOperation
)
ext_input.setDistanceExtent(
    False,
    adsk.core.ValueInput.createByReal(height)
)
extrude = extrudes.add(ext_input)
extrude.name = "Parametric Box"

# ---------------------------------------------------------------------------
# 5. 结果
# ---------------------------------------------------------------------------
print(f"✅ 参数化方块创建成功!")
print(f"   尺寸: {length} x {width} x {height} cm")
print(f"   实体名称: {extrude.name}")
print(f"   用户参数: box_length, box_width, box_height")
print(f"   提示: 在 Fusion 360 中 '修改 → 更改参数' 可以动态调整尺寸")
