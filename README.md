# Claude Bridge — AI 驱动的 Fusion 360 自动化建模

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Fusion 360](https://img.shields.io/badge/Fusion%20360-v2703-blue)](https://www.autodesk.com/products/fusion-360/)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB)](https://www.python.org/)

让 **Claude AI** 通过文件系统桥接直接操控 **Fusion 360**，实现自然语言驱动的 CAD 建模。

> "帮我在 Fusion 360 里画一个模数 3mm、20 齿的渐开线齿轮" → 自动生成并执行

---

## 架构

```
┌──────────┐   写入 .py 脚本   ┌──────────────┐   自动执行   ┌─────────────┐
│  Claude  │ ───────────────→ │  scripts/    │ ──────────→ │ Fusion 360  │
│  (AI)    │                  │  (监控目录)   │             │ Add-in      │
│          │ ←─────────────── │  output/     │ ←────────── │ (主线程)     │
└──────────┘   读取 JSON 结果  └──────────────┘   写入结果   └─────────────┘
```

**零网络端口、零额外进程** — 纯文件系统通信，安全可靠。

---

## 快速开始

### 1. 安装 Add-in

```powershell
# 复制到 Fusion 360 Add-ins 目录
$dest = "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\AddIns\ClaudeBridge"
New-Item -ItemType Directory -Force -Path $dest
Copy-Item "ClaudeBridge\*" $dest
```

重启 Fusion 360 → `Shift+S` → Add-Ins 标签 → 找到 **Claude Bridge** → Run → 勾选 `Run on Startup`

### 2. 发送第一个脚本

```bash
# 使用 CLI 工具
python bridge_cli.py send examples/hello_fusion.py --wait

# 或直接拖入 scripts 目录
cp my_script.py ~/fusion360-bridge/scripts/
```

### 3. 查看结果

```bash
python bridge_cli.py list        # 查看任务状态
python bridge_cli.py result <id> # 读取执行结果
```

---

## CLI 工具

```bash
# 发送脚本文件
python bridge_cli.py send <file.py> --wait

# 发送代码片段
python bridge_cli.py send-code "print('Hello Fusion!')" --wait

# 持续监控模式
python bridge_cli.py listen
```

### Python API

```python
from bridge_cli import BridgeClient

client = BridgeClient()
task_id = client.send_code('''
import adsk.core, adsk.fusion
app = adsk.core.Application.get()
# ... your modeling code ...
''')
result = client.wait_for(task_id, timeout=60)
```

---

## 示例

| 示例 | 说明 |
|------|------|
| `examples/hello_fusion.py` | 连接测试 |
| `examples/create_parametric_box.py` | 参数化方块 (带用户参数) |
| `examples/create_spur_gear.py` | **渐开线直齿轮** — 6 曲线闭环 + 圆周阵列 |
| `examples/batch_export_bodies.py` | 批量导出所有实体为 STL |

---

## 齿轮生成器

`examples/create_spur_gear.py` — 真正的渐开线齿形，非近似：

```
齿槽 = 右径向线 + 渐开线样条 + 齿顶弧 + 渐开线样条 + 左径向线 + 齿根弧
         └─────────────── 6 条曲线形成闭合轮廓 ───────────────┘
```

**可调参数：** 模数、齿数、厚度、轴孔径、压力角

### 技术要点

- 渐开线公式：`(x, y) = rb·(cos θ + θ·sin θ, sin θ − θ·cos θ)`
- 弧的方向计算：`short_sweep()` 确保走短路径而非绕圈
- 共享 Point3D 端点确保曲线精确闭合

完整 API 学习指南见 [FUSION360_API_GUIDE.md](FUSION360_API_GUIDE.md)

---

## 项目结构

```
fusion360-bridge/
├── ClaudeBridge/                    # Fusion 360 Add-in
│   ├── ClaudeBridge.manifest        #   JSON 格式清单
│   └── ClaudeBridge.py              #   Add-in 主代码 (监控+执行)
├── bridge_cli.py                    # CLI 工具 & Python SDK
├── config.json                      # 配置文件
├── examples/                        # 示例脚本
│   ├── hello_fusion.py
│   ├── create_parametric_box.py
│   ├── create_spur_gear.py
│   └── batch_export_bodies.py
├── FUSION360_API_GUIDE.md           # API 学习指南
├── scripts/                         # (自动创建) 待执行脚本
│   └── done/                        # (自动创建) 已执行归档
├── output/                          # (自动创建) 执行结果 JSON
└── logs/                            # (自动创建) Bridge 日志
```

---

## 踩坑记录 & API 注意事项

| # | 问题 | 解决 |
|---|------|------|
| 1 | `import adsk.cam` 在 Personal 许可证下失败 | `try/except ImportError` |
| 2 | Manifest XML 格式在 v2703 中不识别 | 改用 JSON 格式 |
| 3 | 草图曲线未闭合 → 无 Profile | 共享 Point3D 端点 + 6 条曲线闭环 |
| 4 | 圆弧走了长路径 (324° 而非 36°) | `short_sweep()` 约束到 [-π, π] |
| 5 | `setAllExtent(True)` 在 XY 平面切不到 | 改用 `setDistanceExtent` |
| 6 | `CircularPatternFeatures.createInput()` 需要 ObjectCollection | 不能直接传单个 feature |
| 7 | `TimerEventHandler` 在 v2703 中不存在 | 后台线程直接执行，不用 Timer |

---

## 兼容性

- **Fusion 360**: v2.0.0+ (测试于 v2703.1.11)
- **Python**: 3.14 (Fusion 内嵌) / 3.x (CLI 工具)
- **OS**: Windows (macOS/Linux 需调整路径)

---

## 安全

- Bridge 仅监听本地文件夹 (`~/fusion360-bridge/scripts/`)
- 无网络端口暴露
- 脚本在 Fusion 360 进程中执行，权限与 Fusion 360 一致
- 只执行你放入的脚本

---

## License

MIT — 详见 [LICENSE](LICENSE)

---

*Built with Claude AI × Fusion 360 API*
