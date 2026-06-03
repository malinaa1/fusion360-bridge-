# Fusion360 Bridge — AI 驱动的 CAD 自动化

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Fusion 360](https://img.shields.io/badge/Fusion%20360-v2703.1.11-blue)](https://www.autodesk.com/products/fusion-360/)

通过文件桥接让 AI 直接操控 Fusion 360 进行 CAD 建模。

---

## 架构

```
AI / CLI  →  写入命令  →  fusion360_command.txt  →  Fusion 360 Add-in (CustomEvent 主线程)  →  执行脚本
           读取结果  ←  fusion360_response.txt  ←  写入 JSON
```

**v2.1 关键修复：CustomEvent 主线程调度**
- 后台线程只做文件 I/O
- 脚本执行通过 CustomEvent 分发到 Fusion 360 主线程
- **不再崩溃**

---

## 安装

### 1. 安装 Fusion 360 Add-in

```powershell
$dest = "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\AddIns\FusionBridge"
New-Item -ItemType Directory -Force -Path $dest
Copy-Item "FusionBridge\*" $dest
```

重启 Fusion 360 → `Shift+S` → Add-Ins → FusionBridge → Run (勾选 Run on Startup)

### 2. 使用 CLI 发送脚本

```bash
python bridge_cli.py send my_script.py --wait
```

### 3. 或直接写命令文件

```python
import json, os
cmd = {"action": "execute_script", "script_path": "/path/to/script.py", "task_id": "my_task"}
with open(os.path.expanduser("~/Documents/fusion360_command.txt"), "w") as f:
    json.dump(cmd, f)
# 等待结果: ~/Documents/fusion360_response.txt
```

---

## 项目结构

```
fusion360-bridge/
├── FusionBridge/                 # Fusion 360 Add-in (v2.1)
│   ├── FusionBridge.manifest     #
│   └── FusionBridge.py           #   CustomEvent 主线程执行
├── bridge_cli.py                 # CLI 工具 & Python SDK
├── mcp_server/                   # MCP stdio 服务器
│   ├── server.py                 #   含 create_gear 内置工具
│   └── setup_mcp.py              #   安装/测试
├── examples/                     # 示例脚本
│   ├── create_spur_gear.py       #   渐开线齿轮
│   ├── create_parametric_box.py  #   参数化方块
│   ├── create_assembly.py        #   装配体
│   ├── surface_modeling.py       #   曲面建模
│   ├── create_drawing.py         #   工程图
│   ├── cam_toolpath.py           #   CAM 刀路
│   └── hello_fusion.py           #   连接测试
├── FUSION360_API_GUIDE.md        # API 学习指南
└── config.json
```

---

## 关键 API 模式

```python
# 入口
app = adsk.core.Application.get()
design = adsk.fusion.Design.cast(app.activeProduct)
root = design.rootComponent

# 草图 → 轮廓 → 拉伸
sketch = root.sketches.add(root.xYConstructionPlane)
sketch.sketchCurves.sketchCircles.addByCenterRadius(center, radius)
extrude = root.features.extrudeFeatures.addSimple(profile, distance, operation)

# Loft（多轮廓放样）
loft = root.features.loftFeatures.createInput(op)
loft.loftSections.add(profile1)
loft.loftSections.add(profile2)

# Sweep（沿路径扫掠）
path = adsk.fusion.Path.create(curve, options)
sweep = root.features.sweepFeatures.createInput(profile, path, op)

# Circular Pattern
coll = adsk.core.ObjectCollection.create(); coll.add(feature)
pat = root.features.circularPatternFeatures.createInput(coll, axis)
pat.quantity = ValueInput.createByReal(20)
```

---

## 踩过的坑

| 问题 | 原因 | 解决 |
|------|------|------|
| Fusion 崩溃 | `exec()` 在后台线程调用 API | CustomEvent 分发到主线程 |
| Revolve 失败 | 轮廓与旋转轴相切 | 换 Loft 方案 |
| Sweep 失败 (ASM_PATH_TANGENT) | 轮廓平面平行于路径方向 | 路径在 XZ → 轮廓用 YZ 平面 |
| Sweep 失败 (ASM_SELF_INTER) | 曲线曲率太大自交 | 减小曲率 |
| Manifest 不识别 | 旧 XML 格式 | JSON 格式 (Fusion v2703+) |
| `import adsk.cam` 失败 | Personal 许可证无 CAM | `try/except ImportError` |
