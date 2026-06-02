"""
批量导出实体 — 将文档中所有实体导出为 STL 文件

此脚本遍历当前文档的所有实体，并将每个实体导出为独立的 STL 文件。
"""
import adsk.core, adsk.fusion
import os

app = adsk.core.Application.get()
ui = app.userInterface

design = adsk.fusion.Design.cast(app.activeProduct)
if not design:
    print("❌ 请先打开一个 Fusion 360 文档")
    raise SystemExit

root = design.rootComponent
doc = app.activeDocument

# 输出目录
export_dir = os.path.join(OUTPUT_DIR, "exports")
os.makedirs(export_dir, exist_ok=True)

# 收集所有实体
bodies = []
def collect_bodies(component, path=""):
    for body in component.bRepBodies:
        bodies.append((body, f"{path}{component.name}"))
    for occ in component.allOccurrences:
        collect_bodies(occ.component, f"{path}{occ.component.name}/")

collect_bodies(root)

print(f"找到 {len(bodies)} 个实体")

# 导出每个实体
export_mgr = design.exportManager
for i, (body, comp_path) in enumerate(bodies):
    # 创建唯一文件名
    safe_name = f"{comp_path}_{body.name}".replace("/", "_").replace(" ", "_")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._-")
    stl_path = os.path.join(export_dir, f"{safe_name}.stl")

    # 导出 STL
    stl_options = export_mgr.createSTLExportOptions(body, stl_path)
    stl_options.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementMedium
    export_mgr.execute(stl_options)

    print(f"  [{i+1}/{len(bodies)}] 导出: {stl_path}")

print(f"\n✅ 全部导出完成! 文件保存在: {export_dir}")
