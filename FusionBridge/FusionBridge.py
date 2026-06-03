"""
Fusion360 Bridge Add-in v2.0
==============================
MCP-compatible bridge: watches a single command file, executes scripts,
writes results to a single response file.

Communication:
  ~/Documents/fusion360_command.txt   ← command (JSON)
  ~/Documents/fusion360_response.txt  → result (JSON)

Much more reliable than directory-watching v1:
  - Atomic single-file read/write
  - No "seen set" confusion
  - Proper state machine
  - No orphaned script files
"""

import adsk.core
import adsk.fusion

try:
    import adsk.cam
    HAS_CAM = True
except ImportError:
    adsk.cam = None
    HAS_CAM = False

import traceback
import threading
import time
import os
import sys
import json
import io

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
COMMAND_FILE  = os.path.expanduser("~/Documents/fusion360_command.txt")
RESPONSE_FILE = os.path.expanduser("~/Documents/fusion360_response.txt")
LOG_FILE      = os.path.expanduser("~/fusion360-bridge/logs/bridge.log")

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
_running = False
_last_command_mtime = 0
_app = None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _log(msg):
    try:
        ts = time.strftime("%H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except:
        pass

# ---------------------------------------------------------------------------
# Script execution
# ---------------------------------------------------------------------------
def _execute_script(script_path):
    """Execute a Python script file and return the result dict."""
    t0 = time.time()
    result = {"success": False, "stdout": "", "stderr": "", "error": None}

    try:
        with open(script_path, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        result["error"] = f"Read error: {e}"
        return result

    ns = _build_namespace()
    old_out, old_err = sys.stdout, sys.stderr
    cap_out, cap_err = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = cap_out, cap_err

    try:
        exec(compile(source, script_path, "exec"), ns)
        result["success"] = True
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        result["stdout"] = cap_out.getvalue()
        result["stderr"] = cap_err.getvalue()

    result["duration_ms"] = round((time.time() - t0) * 1000, 1)
    return result


def _build_namespace():
    return {
        "adsk": adsk, "core": adsk.core, "fusion": adsk.fusion, "cam": adsk.cam,
        "HAS_CAM": HAS_CAM,
        "Point3D": adsk.core.Point3D,
        "Vector3D": adsk.core.Vector3D,
        "Matrix3D": adsk.core.Matrix3D,
        "ValueInput": adsk.core.ValueInput,
        "app": _app,
        "ui": _app.userInterface if _app else None,
        "math": __import__("math"), "json": json, "os": os,
        "sys": sys, "time": time,
        "__name__": "__fusion_bridge__",
    }


# ---------------------------------------------------------------------------
# Main loop (background thread)
# ---------------------------------------------------------------------------
def _bridge_loop():
    """Watch command file, execute scripts, write results."""
    global _last_command_mtime

    _log("Bridge v2.0 started — watching command file")
    _log(f"Command: {COMMAND_FILE}")
    _log(f"Response: {RESPONSE_FILE}")

    try:
        _last_command_mtime = os.path.getmtime(COMMAND_FILE)
    except OSError:
        _last_command_mtime = 0

    while _running:
        try:
            current_mtime = os.path.getmtime(COMMAND_FILE)
            if current_mtime > _last_command_mtime:
                _last_command_mtime = current_mtime

                with open(COMMAND_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()

                if not content:
                    time.sleep(0.5)
                    continue

                command = json.loads(content)
                action = command.get("action", "")
                task_id = command.get("task_id", "unknown")

                _log(f"Processing: {task_id} ({action})")

                if action == "execute_script":
                    script_path = command.get("script_path", "")
                    result = _execute_script(script_path)
                    result["task_id"] = task_id

                    with open(RESPONSE_FILE, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)

                    try:
                        os.remove(script_path)
                    except OSError:
                        pass

                    _log(f"Done: {task_id} ok={result['success']}")

                elif action == "ping":
                    with open(RESPONSE_FILE, "w", encoding="utf-8") as f:
                        json.dump({"pong": True, "version": "2.0"}, f)

                # Clear for next command
                try:
                    with open(COMMAND_FILE, "w", encoding="utf-8") as f:
                        f.write("")
                    _last_command_mtime = os.path.getmtime(COMMAND_FILE)
                except OSError:
                    pass

        except (json.JSONDecodeError, KeyError) as e:
            _log(f"Parse error: {e}")
            time.sleep(1)
        except OSError:
            time.sleep(1)
        except Exception as e:
            _log(f"Error: {e}")
            time.sleep(1)

        time.sleep(0.5)

    _log("Stopped.")


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------
def run(context):
    global _running, _app

    _app = adsk.core.Application.get()
    _log(f"Bridge v2.0 starting — Fusion {_app.version}")

    for f in (COMMAND_FILE, RESPONSE_FILE):
        try:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            if not os.path.exists(f):
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write("")
        except:
            pass

    _running = True
    t = threading.Thread(target=_bridge_loop, daemon=True, name="f360-bridge")
    t.start()

    _log("Ready.")

    try:
        _app.userInterface.messageBox(
            "Fusion360 Bridge v2.0 active.\nReady to receive commands.",
            "Fusion360 Bridge"
        )
    except:
        pass


def stop(context):
    global _running
    _running = False
    _log("Stopped.")
