# Fusion360 MCP Bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Fusion 360](https://img.shields.io/badge/Fusion%20360-v2703-blue)](https://www.autodesk.com/products/fusion-360/)

通过 **MCP (Model Context Protocol)** 将 AI 助手连接到 Fusion 360，实现自然语言驱动的 CAD 建模。

---

## 架构

```
┌──────────┐  MCP stdio   ┌──────────────┐   file    ┌─────────────────┐
│ Claude   │ ←──────────→ │ mcp_server/  │ ←──────→ │ Fusion 360      │
│ (AI)     │  JSON-RPC    │ server.py    │  command │ Add-in (v2.0)   │
└──────────┘              └──────────────┘          └─────────────────┘
                            ~/Documents/             单文件监控
                            fusion360_command.txt    原子读写
                            fusion360_response.txt   无竞态
```

**相比 v1.0 目录轮询的改进：**
- MCP 标准协议，Claude Code 原生集成
- 单文件通信，无 "seen set" 丢失脚本
- 原子读写，无竞态条件
- 不会导致 Fusion 360 崩溃

---

## 快速开始

### 1. 安装 Fusion 360 Add-in

```powershell
$dest = "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\AddIns\FusionBridge"
New-Item -ItemType Directory -Force -Path $dest
Copy-Item "FusionBridge\*" $dest
```

重启 Fusion 360 → `Shift+S` → Add-Ins → FusionBridge → Run (勾选 Run on Startup)

### 2. 配置 MCP Server

```bash
python mcp_server/setup_mcp.py install
```

### 3. 重启 Claude Code

下次启动时，MCP server 自动加载。直接说话即可：

> "在 Fusion 360 里画一个模数 3mm、20 齿的齿轮"

---

## MCP 工具列表

| 工具 | 说明 |
|------|------|
| `execute_fusion_script` | 执行任意 Fusion 360 Python 脚本 |
| `get_fusion_status` | 检查 Fusion 360 连接状态 |
| `create_gear` | 一键创建渐开线齿轮 |

---

## 项目结构

```
fusion360-bridge/
├── mcp_server/                  # MCP stdio 服务器
│   ├── server.py                #   主服务器 (Claude Code ↔ Fusion)
│   └── setup_mcp.py             #   安装/测试/卸载工具
├── FusionBridge/                # Fusion 360 Add-in (v2.0)
│   ├── FusionBridge.manifest    #   JSON 格式清单
│   └── FusionBridge.py          #   单文件命令监控
├── bridge_cli.py                # CLI 工具 (独立使用)
├── examples/                    # 示例脚本
│   ├── create_spur_gear.py      #   渐开线齿轮
│   ├── create_assembly.py       #   装配体
│   ├── surface_modeling.py      #   曲面建模
│   ├── create_drawing.py        #   工程图
│   ├── cam_toolpath.py          #   CAM 刀路
│   ├── create_parametric_box.py
│   ├── batch_export_bodies.py
│   └── hello_fusion.py
├── FUSION360_API_GUIDE.md       # API 学习指南
├── config.json
└── LICENSE
```

---

## 故障排除

| 问题 | 解决 |
|------|------|
| MCP 连接超时 | 确认 Fusion 360 运行且 Add-in 已启动 |
| 脚本执行无响应 | 检查 `~/Documents/fusion360_command.txt` |
| Add-in 未加载 | manifest 需 JSON 格式 (Fusion v2703+) |

---

## 参考项目

- [fusion360-claude-ultimate](https://github.com/Misterbra/fusion360-claude-ultimate)
- [fusion-mcp-server](https://github.com/Joe-Spencer/fusion-mcp-server)
- [fusion360-mcp-server](https://github.com/mycelia1/fusion360-mcp-server)
