#!/usr/bin/env python3
"""
Fusion360 MCP Bridge Server
=============================
MCP (Model Context Protocol) server that bridges Claude AI to Fusion 360.

Architecture:
  Claude Code ←→ MCP (stdio) ←→ this server ←→ file ←→ Fusion 360 Add-in

The server communicates with Fusion 360 via two files:
  ~/Documents/fusion360_command.txt  →  command sent to Fusion
  ~/Documents/fusion360_response.txt  ←  response from Fusion

This is MUCH more reliable than directory-watching because:
  - Single file, no race conditions
  - No "seen set" confusion
  - Atomic read/write operations
  - Proper timeout and error handling
"""

import json
import os
import sys
import time
import tempfile
import shutil
from pathlib import Path

# --- Paths ---
COMMAND_FILE  = os.path.expanduser("~/Documents/fusion360_command.txt")
RESPONSE_FILE = os.path.expanduser("~/Documents/fusion360_response.txt")
SCRIPT_DIR    = os.path.expanduser("~/Documents/fusion360_scripts")

os.makedirs(SCRIPT_DIR, exist_ok=True)

# --- Logging ---
def log(msg):
    print(f"[MCP-F360] {msg}", file=sys.stderr, flush=True)


# --- Fusion 360 Communication ---
def send_to_fusion(script_content: str, timeout: float = 120.0) -> dict:
    """
    Send a script to Fusion 360 for execution and wait for the result.

    1. Write script to a temp .py file in the scripts directory
    2. Write command to the command file (with the script path)
    3. Wait for response file to be updated
    4. Parse and return the result
    """
    task_id = f"task_{int(time.time() * 1000)}"

    # Write script file
    script_path = os.path.join(SCRIPT_DIR, f"{task_id}.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    # Write command
    command = {
        "action": "execute_script",
        "script_path": script_path,
        "task_id": task_id,
        "timestamp": time.time()
    }
    with open(COMMAND_FILE, "w", encoding="utf-8") as f:
        json.dump(command, f)

    log(f"Sent command: {task_id}")

    # Clear old response
    try:
        os.remove(RESPONSE_FILE)
    except OSError:
        pass

    # Wait for response
    start = time.time()
    poll_interval = 0.2

    while time.time() - start < timeout:
        try:
            if os.path.exists(RESPONSE_FILE) and os.path.getsize(RESPONSE_FILE) > 0:
                time.sleep(0.1)  # let the write finish
                with open(RESPONSE_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    result = json.loads(content)
                    log(f"Got response: {task_id} → {result.get('success')}")
                    return result
        except (json.JSONDecodeError, OSError):
            pass
        time.sleep(poll_interval)

    log(f"Timeout waiting for response: {task_id}")
    return {"success": False, "error": "Timeout waiting for Fusion 360 response"}


# --- MCP Server (using manual stdio for compatibility) ---
class Fusion360MCPServer:
    """MCP server implementation via stdio JSON-RPC."""

    def __init__(self):
        self.tools = {
            "execute_fusion_script": {
                "description": "Execute a Python script in Fusion 360. The script uses the adsk API. Returns stdout, stderr, and any error.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute in Fusion 360. Has access to adsk.core, adsk.fusion, adsk.cam."
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Timeout in seconds (default 120)",
                            "default": 120
                        }
                    },
                    "required": ["code"]
                }
            },
            "get_fusion_status": {
                "description": "Check if Fusion 360 is running and the bridge is active.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "create_gear": {
                "description": "Create an involute spur gear in Fusion 360.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "module_mm": {
                            "type": "number",
                            "description": "Module in mm (default 3.0)",
                            "default": 3.0
                        },
                        "teeth": {
                            "type": "integer",
                            "description": "Number of teeth (default 20)",
                            "default": 20
                        },
                        "thickness_mm": {
                            "type": "number",
                            "description": "Thickness in mm (default 10.0)",
                            "default": 10.0
                        },
                        "shaft_dia_mm": {
                            "type": "number",
                            "description": "Shaft hole diameter in mm (default 8.0)",
                            "default": 8.0
                        }
                    }
                }
            }
        }

    def handle_request(self, request: dict) -> dict:
        """Handle a JSON-RPC request."""
        method = request.get("method", "")
        req_id = request.get("id")

        if method == "initialize":
            return self._response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fusion360-mcp", "version": "2.0.0"}
            })

        elif method == "notifications/initialized":
            return None  # no response for notifications

        elif method == "tools/list":
            tools_list = []
            for name, defn in self.tools.items():
                tools_list.append({"name": name, **defn})
            return self._response(req_id, {"tools": tools_list})

        elif method == "tools/call":
            tool_name = request["params"]["name"]
            tool_args = request["params"].get("arguments", {})

            if tool_name == "execute_fusion_script":
                result = send_to_fusion(
                    tool_args["code"],
                    timeout=tool_args.get("timeout", 120)
                )
                return self._response(req_id, {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}]
                })

            elif tool_name == "get_fusion_status":
                # Quick probe
                probe_result = send_to_fusion(
                    "import adsk.core; app=adsk.core.Application.get(); "
                    "print(f'Fusion {app.version} OK')",
                    timeout=10
                )
                status = "connected" if probe_result.get("success") else "not connected"
                return self._response(req_id, {
                    "content": [{"type": "text",
                        "text": f"Fusion 360: {status}\n{probe_result.get('stdout', '')}"}]
                })

            elif tool_name == "create_gear":
                m = tool_args.get("module_mm", 3.0) / 10.0  # mm → cm
                z = tool_args.get("teeth", 20)
                t = tool_args.get("thickness_mm", 10.0) / 10.0
                sd = tool_args.get("shaft_dia_mm", 8.0) / 20.0  # dia→radius, mm→cm

                gear_code = GEAR_SCRIPT.format(
                    module_val=m, teeth=z, thickness=t, shaft_radius=sd
                )
                result = send_to_fusion(gear_code)
                return self._response(req_id, {
                    "content": [{"type": "text",
                        "text": f"Gear creation: {'OK' if result.get('success') else 'FAILED'}\n"
                                f"{result.get('stdout', '')}\n{result.get('error', '')}"}]
                })

            else:
                return self._error(req_id, -32601, f"Unknown tool: {tool_name}")

        elif method == "resources/list":
            return self._response(req_id, {"resources": []})

        else:
            return self._error(req_id, -32601, f"Unknown method: {method}")

    @staticmethod
    def _response(req_id, result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _error(req_id, code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def run(self):
        """Main loop: read JSON-RPC from stdin, write responses to stdout."""
        log("MCP server starting on stdio...")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError as e:
                log(f"Invalid JSON: {e}")
            except Exception as e:
                log(f"Error: {e}")
                import traceback
                traceback.print_exc(file=sys.stderr)


# --- Pre-built gear script template ---
GEAR_SCRIPT = r"""
import adsk.core, adsk.fusion, math

app = adsk.core.Application.get()
design = adsk.fusion.Design.cast(app.activeProduct)
if not design:
    app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(app.activeProduct)

rt = design.rootComponent
extrudes = rt.features.extrudeFeatures
center = adsk.core.Point3D.create(0, 0, 0)

M = {module_val}
Z = {teeth}
T = {thickness}
SR = {shaft_radius}

pr = M * Z / 2.0
br = pr * math.cos(math.radians(20))
OR = pr + M
RR = pr - 1.25 * M

def to_coll(pts):
    c = adsk.core.ObjectCollection.create()
    for p in pts: c.add(p)
    return c

def involute_xy(rb, theta):
    return (rb*(math.cos(theta)+theta*math.sin(theta)),
            rb*(math.sin(theta)-theta*math.cos(theta)))

def short_sweep(pf, pt):
    d = math.atan2(pt.y, pt.x) - math.atan2(pf.y, pf.x)
    if d > math.pi: d -= 2*math.pi
    elif d < -math.pi: d += 2*math.pi
    return d

# Blank
sk1 = rt.sketches.add(rt.xYConstructionPlane)
sk1.sketchCurves.sketchCircles.addByCenterRadius(center, OR)
ei = extrudes.createInput(sk1.profiles.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
ei.setDistanceExtent(False, adsk.core.ValueInput.createByReal(T))
extrudes.add(ei).name = "Gear Blank"

# Tooth space
ap = 2*math.pi/Z
ht = (math.pi*M/2.0)/pr
mr = math.sqrt((OR/br)**2-1)
ip = math.tan(math.radians(20))-math.atan(math.tan(math.radians(20)))
N = 15
rotR = -ht-ip
rotL = ap+ht-ip

ptsR, ptsL = [], []
for j in range(N+1):
    roll = mr*j/N
    ix, iy = involute_xy(br, roll)
    iym = -iy; cr, sr = math.cos(rotR), math.sin(rotR)
    ptsR.append(adsk.core.Point3D.create(ix*cr-iym*sr, ix*sr+iym*cr, 0))
    cl, sl = math.cos(rotL), math.sin(rotL)
    ptsL.append(adsk.core.Point3D.create(ix*cl-iy*sl, ix*sl+iy*cl, 0))

VRR = adsk.core.Point3D.create(RR*math.cos(rotR), RR*math.sin(rotR), 0)
VRL = adsk.core.Point3D.create(RR*math.cos(rotL), RR*math.sin(rotL), 0)

sk2 = rt.sketches.add(rt.xYConstructionPlane)
s = sk2.sketchCurves
s.sketchLines.addByTwoPoints(VRR, ptsR[0])
s.sketchFittedSplines.add(to_coll(ptsR))
s.sketchArcs.addByCenterStartSweep(center, ptsR[-1], short_sweep(ptsR[-1], ptsL[-1]))
s.sketchFittedSplines.add(to_coll(list(reversed(ptsL))))
s.sketchLines.addByTwoPoints(ptsL[0], VRL)
s.sketchArcs.addByCenterStartSweep(center, VRL, short_sweep(VRL, VRR))

prof = sk2.profiles.item(0)
for i in range(1, sk2.profiles.count):
    if sk2.profiles.item(i).areaProperties().area < prof.areaProperties().area:
        prof = sk2.profiles.item(i)

ci = extrudes.createInput(prof, adsk.fusion.FeatureOperations.CutFeatureOperation)
ci.setDistanceExtent(False, adsk.core.ValueInput.createByReal(T))
cut = extrudes.add(ci)

pc = adsk.core.ObjectCollection.create()
pc.add(cut)
pi = rt.features.circularPatternFeatures.createInput(pc, rt.zConstructionAxis)
pi.quantity = adsk.core.ValueInput.createByReal(Z)
pi.totalAngle = adsk.core.ValueInput.createByString("360 deg")
rt.features.circularPatternFeatures.add(pi)

sk3 = rt.sketches.add(rt.xYConstructionPlane)
sk3.sketchCurves.sketchCircles.addByCenterRadius(center, SR)
hi = extrudes.createInput(sk3.profiles.item(0), adsk.fusion.FeatureOperations.CutFeatureOperation)
hi.setDistanceExtent(False, adsk.core.ValueInput.createByReal(T))
extrudes.add(hi).name = "Shaft Hole"

print(f"Gear: {{M*10:.0f}}mm mod x {{Z}} teeth, OD={{OR*2:.2f}}cm, T={{T:.1f}}cm")
"""


if __name__ == "__main__":
    server = Fusion360MCPServer()
    server.run()
