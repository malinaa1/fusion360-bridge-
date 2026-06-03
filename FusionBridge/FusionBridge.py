"""
Fusion360 Bridge Add-in v2.1
==============================
FIXED: Uses CustomEvent for MAIN-THREAD execution.
Watcher thread only does file I/O. No more crashes.
"""

import adsk.core, adsk.fusion
try: import adsk.cam; HAS_CAM = True
except ImportError: adsk.cam = None; HAS_CAM = False

import traceback, threading, time, os, sys, json, io

COMMAND_FILE  = os.path.expanduser("~/Documents/fusion360_command.txt")
RESPONSE_FILE = os.path.expanduser("~/Documents/fusion360_response.txt")
LOG_FILE      = os.path.expanduser("~/fusion360-bridge/logs/bridge.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

_app = None; _running = False; _last_mtime = 0; _handlers = []
_event_id = "FusionBridgeCmdEvent_v2"

def _log(msg):
    try:
        with open(LOG_FILE,"a",encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except: pass

# ---- Main-thread script execution (called via CustomEvent) ----
_tasks = []  # queue: list of command dicts

def _process_tasks():
    """Called on MAIN THREAD by CustomEvent handler."""
    while _tasks:
        cmd = _tasks.pop(0)
        task_id = cmd.get("task_id","?")
        script_path = cmd.get("script_path","")
        t0 = time.time()
        result = {"task_id":task_id,"success":False,"stdout":"","stderr":"","error":None}
        try:
            with open(script_path,"r",encoding="utf-8") as f:
                source = f.read()
        except Exception as e:
            result["error"]=f"Read error: {e}"
            _write(result); continue

        ns = {"adsk":adsk,"core":adsk.core,"fusion":adsk.fusion,"cam":adsk.cam,
              "HAS_CAM":HAS_CAM,"Point3D":adsk.core.Point3D,"Vector3D":adsk.core.Vector3D,
              "Matrix3D":adsk.core.Matrix3D,"ValueInput":adsk.core.ValueInput,
              "app":_app,"ui":_app.userInterface if _app else None,
              "math":__import__("math"),"json":json,"os":os,"sys":sys,"time":time,
              "__name__":"__fusion_bridge__"}
        old_out,old_err=sys.stdout,sys.stderr
        co,ce=io.StringIO(),io.StringIO()
        sys.stdout,sys.stderr=co,ce
        try:
            exec(compile(source,script_path,"exec"),ns)
            result["success"]=True
        except Exception as e:
            result["error"]=f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        finally:
            sys.stdout,sys.stderr=old_out,old_err
            result["stdout"]=co.getvalue(); result["stderr"]=ce.getvalue()
            result["duration_ms"]=round((time.time()-t0)*1000,1)
        _write(result)
        try: os.remove(script_path)
        except: pass
        _log(f"Done: {task_id} ok={result['success']} {result['duration_ms']}ms")

def _write(r):
    try:
        with open(RESPONSE_FILE,"w",encoding="utf-8") as f:
            json.dump(r,f,indent=2,ensure_ascii=False)
    except Exception as e: _log(f"Write error: {e}")

# ---- CustomEvent handler (main thread) ----
class _Handler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try: _process_tasks()
        except Exception as e: _log(f"Handler: {e}")

# ---- File watcher (background thread, I/O ONLY) ----
def _watcher():
    global _last_mtime
    _log("Watcher started")
    try:
        with open(COMMAND_FILE,"w") as f: f.write("")
        with open(RESPONSE_FILE,"w") as f: f.write("")
    except: pass
    while _running:
        try:
            mtime = os.path.getmtime(COMMAND_FILE)
            if mtime > _last_mtime:
                _last_mtime = mtime
                with open(COMMAND_FILE,"r",encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    cmd = json.loads(content)
                    _tasks.append(cmd)
                    # FIRE event → main thread picks up
                    _app.fireCustomEvent(_event_id, "")
                    _log(f"Queued: {cmd.get('task_id','?')}")
                with open(COMMAND_FILE,"w") as f: f.write("")
                _last_mtime = os.path.getmtime(COMMAND_FILE)
        except: pass
        time.sleep(0.5)
    _log("Watcher stopped")

# ---- Add-in lifecycle ----
def run(context):
    global _running, _app
    _app = adsk.core.Application.get()
    _log(f"v2.1 starting — Fusion {_app.version}")
    os.makedirs(os.path.dirname(COMMAND_FILE), exist_ok=True)
    # Register event
    evt = _app.registerCustomEvent(_event_id)
    h = _Handler()
    evt.add(h)
    _handlers.append(h)
    _running = True
    threading.Thread(target=_watcher, daemon=True, name="bridge-w").start()
    _log("Ready (main-thread-safe)")

def stop(context):
    global _running
    _running = False
    _log("Stopped.")
