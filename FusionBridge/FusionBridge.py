"""
Fusion360 Bridge Add-in
===================================
Automatically watches a folder for Python scripts and executes them
inside Fusion 360's Python environment.

Scripts dropped into the ``scripts/`` folder are picked up, executed
in Fusion 360's context (main thread), and their output is written
back to ``output/`` as JSON result files.


Version: 1.0.0
"""

import adsk.core
import adsk.fusion
import adsk.cam
import traceback
import threading
import queue
import time
import os
import sys
import json
import io
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BRIDGE_ROOT = os.path.expanduser(r"~\fusion360-bridge")
SCRIPTS_DIR = os.path.join(BRIDGE_ROOT, "scripts")
OUTPUT_DIR  = os.path.join(BRIDGE_ROOT, "output")
DONE_DIR    = os.path.join(BRIDGE_ROOT, "scripts", "done")
LOG_DIR     = os.path.join(BRIDGE_ROOT, "logs")

# ---------------------------------------------------------------------------
# Globals — must keep references to handlers to prevent GC
# ---------------------------------------------------------------------------
_script_queue: queue.Queue = queue.Queue()
_running: bool = False
_timer_handler = None
_app: adsk.core.Application = None
_handlers = []  # keep-alive list for all event handlers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_dirs():
    for d in (SCRIPTS_DIR, OUTPUT_DIR, DONE_DIR, LOG_DIR):
        os.makedirs(d, exist_ok=True)


def _log(message: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    log_path = os.path.join(LOG_DIR, "bridge.log")
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def _execute_script(script_path: str):
    task_id = os.path.splitext(os.path.basename(script_path))[0]
    result = {
        "task_id": task_id,
        "script": script_path,
        "success": False,
        "stdout": "",
        "stderr": "",
        "error": None,
        "duration_ms": 0,
    }
    t0 = time.time()

    # Read script
    try:
        with open(script_path, "r", encoding="utf-8") as fh:
            source = fh.read()
    except Exception as exc:
        result["error"] = f"Failed to read script: {exc}"
        _write_result(task_id, result)
        _move_to_done(script_path)
        return

    # Build namespace
    ns = _build_namespace()

    # Capture stdout/stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    capture_out = io.StringIO()
    capture_err = io.StringIO()
    sys.stdout = capture_out
    sys.stderr = capture_err

    try:
        compiled = compile(source, script_path, "exec")
        exec(compiled, ns)
        result["success"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        result["stdout"] = capture_out.getvalue()
        result["stderr"] = capture_err.getvalue()
        result["duration_ms"] = round((time.time() - t0) * 1000, 1)

    _write_result(task_id, result)
    _move_to_done(script_path)
    _log(f"Executed: {task_id}  success={result['success']}  ms={result['duration_ms']}")


def _build_namespace() -> dict:
    """Return the globals namespace for executed scripts."""
    return {
        "adsk": adsk,
        "core": adsk.core,
        "fusion": adsk.fusion,
        "cam": adsk.cam,
        "Point3D": adsk.core.Point3D,
        "Vector3D": adsk.core.Vector3D,
        "Matrix3D": adsk.core.Matrix3D,
        "ValueInput": adsk.core.ValueInput,
        "app": _app,
        "ui": _app.userInterface if _app else None,
        "math": __import__("math"),
        "json": __import__("json"),
        "os": __import__("os"),
        "sys": __import__("sys"),
        "time": __import__("time"),
        "OUTPUT_DIR": OUTPUT_DIR,
        "__name__": "__fusion_bridge__",
    }


def _write_result(task_id: str, result: dict):
    out_path = os.path.join(OUTPUT_DIR, f"{task_id}.json")
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False, default=str)
    except Exception as exc:
        _log(f"Failed to write result for {task_id}: {exc}")


def _move_to_done(script_path: str):
    try:
        fname = os.path.basename(script_path)
        dest = os.path.join(DONE_DIR, fname)
        if os.path.exists(dest):
            base, ext = os.path.splitext(fname)
            dest = os.path.join(DONE_DIR, f"{base}_{int(time.time())}{ext}")
        shutil.move(script_path, dest)
    except Exception as exc:
        _log(f"Failed to move script {script_path}: {exc}")


# ---------------------------------------------------------------------------
# Folder watcher (background thread)
# ---------------------------------------------------------------------------

def _watch_folder():
    _log("Watcher thread started.")
    seen = set()

    # Seed with files already present
    try:
        for f in os.listdir(SCRIPTS_DIR):
            if f.endswith(".py"):
                seen.add(f)
    except Exception:
        pass

    while _running:
        try:
            for f in os.listdir(SCRIPTS_DIR):
                if f.endswith(".py") and f not in seen:
                    seen.add(f)
                    full = os.path.join(SCRIPTS_DIR, f)
                    time.sleep(0.2)  # ensure file write is complete
                    _script_queue.put(full)
                    _log(f"Queued: {f}")
        except Exception as exc:
            _log(f"Watcher error: {exc}")
        time.sleep(1.0)

    _log("Watcher thread stopped.")


# ---------------------------------------------------------------------------
# Timer event handler (main thread)
# ---------------------------------------------------------------------------

class _QueueTimerHandler(adsk.core.TimerEventHandler):
    def notify(self, args: adsk.core.TimerEventArgs):
        try:
            if not _script_queue.empty():
                path = _script_queue.get_nowait()
                _execute_script(path)
        except Exception as exc:
            _log(f"Timer handler error: {exc}")


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------

def run(context):
    """Called by Fusion 360 when the add-in is loaded."""
    global _running, _timer_handler, _app

    _ensure_dirs()
    _app = adsk.core.Application.get()

    _log("=" * 60)
    _log("Bridge Add-in starting up.")
    _log(f"Bridge root : {BRIDGE_ROOT}")
    _log(f"Scripts dir : {SCRIPTS_DIR}")
    _log(f"Output dir  : {OUTPUT_DIR}")

    _running = True

    # Start file-watcher background thread
    watcher = threading.Thread(
        target=_watch_folder, daemon=True, name="bridge-watcher"
    )
    watcher.start()

    # Start processing timer (fires on main thread)
    ui = _app.userInterface
    _timer_handler = _QueueTimerHandler()
    _handlers.append(_timer_handler)  # prevent GC
    ui.timerEvent.add(_timer_handler, 500)  # 500ms

    _log("Bridge Add-in started.")


def stop(context):
    """Called by Fusion 360 when the add-in is unloaded."""
    global _running, _timer_handler

    _running = False

    if _timer_handler is not None:
        try:
            ui = adsk.core.Application.get().userInterface
            ui.timerEvent.remove(_timer_handler)
        except Exception:
            pass
        _handlers.remove(_timer_handler)
        _timer_handler = None

    _log("Bridge Add-in stopped.")
    _log("=" * 60)
