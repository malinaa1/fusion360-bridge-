"""
Hello Fusion — 测试 Bridge 连接是否正常

将此脚本发送到 Fusion 360 以验证 Bridge 是否工作。
"""
import adsk.core, adsk.fusion

try:
    app = adsk.core.Application.get()
    ui = app.userInterface
    version = app.version
    build = app.build

    print(f"✅ Fusion360 Bridge 连接正常!")
    print(f"Fusion 360 版本: {version}")
    print(f"Build: {build}")

    # 如果有打开的文档
    doc = app.activeDocument
    if doc:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design:
            print(f"当前文档: {doc.name}")
            print(f"根组件: {design.rootComponent.name}")

    ui.messageBox(
        f"Fusion360 Bridge 连接成功!\\n\\n"
        f"Fusion 360 v{version}\\n"
        f"Build {build}",
        "✅ Bridge OK"
    )
    print("messageBox 已弹出 — 如果你看到弹窗，说明一切正常！")

except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()
