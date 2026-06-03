#!/usr/bin/env python3
"""
Setup script — configures Claude Code to use the Fusion360 MCP server.

Usage:
    python setup_mcp.py install    —  add MCP config to Claude Code
    python setup_mcp.py uninstall  —  remove MCP config
    python setup_mcp.py test       —  test connection to Fusion 360
"""

import json
import os
import sys
import subprocess
from pathlib import Path

MCP_SERVER_PATH = Path(__file__).parent / "server.py"
CLAUDE_CONFIG = Path.home() / ".claude" / "settings.json"


def install():
    """Add Fusion360 MCP server to Claude Code settings."""
    config = {}
    if CLAUDE_CONFIG.exists():
        with open(CLAUDE_CONFIG, "r", encoding="utf-8") as f:
            config = json.load(f)

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    mcp_config = {
        "command": sys.executable,
        "args": [str(MCP_SERVER_PATH)],
        "description": "Fusion 360 CAD modeling bridge"
    }

    if "fusion360" in config["mcpServers"]:
        print("[!] fusion360 MCP server already configured. Updating...")
        config["mcpServers"]["fusion360"] = mcp_config
    else:
        config["mcpServers"]["fusion360"] = mcp_config
        print("[+] Added fusion360 MCP server to Claude Code config")

    os.makedirs(CLAUDE_CONFIG.parent, exist_ok=True)
    with open(CLAUDE_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"[✓] Config written to: {CLAUDE_CONFIG}")
    print(f"[✓] MCP server path: {MCP_SERVER_PATH}")
    print()
    print("Next steps:")
    print("  1. Install Fusion360 Bridge add-in in Fusion 360")
    print("  2. Restart Claude Code")
    print("  3. Use: 'create a gear with 20 teeth in Fusion 360'")


def uninstall():
    """Remove Fusion360 MCP config."""
    if not CLAUDE_CONFIG.exists():
        print("[!] No Claude Code config found.")
        return

    with open(CLAUDE_CONFIG, "r", encoding="utf-8") as f:
        config = json.load(f)

    if "mcpServers" in config and "fusion360" in config["mcpServers"]:
        del config["mcpServers"]["fusion360"]
        with open(CLAUDE_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print("[-] Removed fusion360 MCP server config.")


def test():
    """Quick test — write a command file and check if Fusion responds."""
    from mcp_server.server import send_to_fusion

    print("Testing connection to Fusion 360...")
    result = send_to_fusion(
        "import adsk.core; app=adsk.core.Application.get(); "
        "print(f'Fusion {app.version} running!')",
        timeout=15
    )
    if result.get("success"):
        print(f"[✓] CONNECTED! stdout: {result.get('stdout', '').strip()}")
    else:
        print(f"[✗] FAILED: {result.get('error', 'No response')}")
        print("Make sure Fusion 360 is running with the Bridge add-in active.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    if cmd == "install":
        install()
    elif cmd == "uninstall":
        uninstall()
    elif cmd == "test":
        test()
    else:
        print(f"Usage: python setup_mcp.py [install|uninstall|test]")
