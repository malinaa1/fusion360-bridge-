#!/usr/bin/env python3
"""
Fusion360 Bridge CLI — Send scripts to Fusion 360 and read results.

Usage (command line)::

    python bridge_cli.py send <script.py>       # Queue a script for execution
    python bridge_cli.py send-code "<code>"     # Queue raw code (auto-wraps into a file)
    python bridge_cli.py result <task_id>       # Read a result JSON
    python bridge_cli.py wait <task_id>         # Wait for a task to complete
    python bridge_cli.py list                   # List queued and completed tasks
    python bridge_cli.py listen                 # Continuous monitor mode
    python bridge_cli.py clean                  # Clean up old scripts and results

Usage (Python API)::

    from bridge_cli import BridgeClient
    client = BridgeClient()
    task_id = client.send_script("path/to/script.py")
    task_id = client.send_code('''
        # Your Fusion 360 Python code here
        import adsk.core, adsk.fusion
        ...
    ''')
    result = client.wait_for(task_id, timeout=60)
    print(result["stdout"])


"""

import os
import sys
import json
import time
import uuid
import shutil
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
BRIDGE_ROOT = r"D:\MOD\fusion360-bridge"
SCRIPTS_DIR = os.path.join(BRIDGE_ROOT, "scripts")
OUTPUT_DIR  = os.path.join(BRIDGE_ROOT, "output")
DONE_DIR    = os.path.join(BRIDGE_ROOT, "scripts", "done")
CONFIG_PATH = os.path.join(BRIDGE_ROOT, "config.json")

# Load config overrides if available
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        BRIDGE_ROOT = cfg.get("bridge_root", BRIDGE_ROOT)
        SCRIPTS_DIR = cfg.get("scripts_dir", SCRIPTS_DIR)
        OUTPUT_DIR  = cfg.get("output_dir", OUTPUT_DIR)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Client class
# ---------------------------------------------------------------------------

class BridgeClient:
    """
    Client for communicating with the Fusion 360 Bridge add-in.

    Scripts written to ``scripts_dir`` are automatically picked up and
    executed by the add-in running inside Fusion 360. Results are written
    as JSON files to ``output_dir``.
    """

    def __init__(
        self,
        scripts_dir: str = SCRIPTS_DIR,
        output_dir: str = OUTPUT_DIR,
        done_dir: str = DONE_DIR,
    ):
        self.scripts_dir = scripts_dir
        self.output_dir = output_dir
        self.done_dir = done_dir
        os.makedirs(self.scripts_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.done_dir, exist_ok=True)

    # -- Sending scripts ------------------------------------------------

    def send_script(self, script_path: str, task_id: Optional[str] = None) -> str:
        """
        Copy a script file to the Fusion 360 scripts directory.

        Args:
            script_path: Path to the .py file to execute in Fusion 360.
            task_id: Optional task identifier (auto-generated if omitted).

        Returns:
            The task ID used to look up results.
        """
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Script not found: {script_path}")

        task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        dest = os.path.join(self.scripts_dir, f"{task_id}.py")

        # Read & re-write so the timestamp is fresh (triggers watcher)
        with open(script_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)

        print(f"[bridge] Sent:  {dest}")
        print(f"[bridge] Task ID: {task_id}")
        return task_id

    def send_code(self, code: str, task_id: Optional[str] = None) -> str:
        """
        Send raw Python code to Fusion 360 for execution.

        Args:
            code: Python source code to execute in Fusion 360.
            task_id: Optional task identifier.

        Returns:
            The task ID used to look up results.
        """
        task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        dest = os.path.join(self.scripts_dir, f"{task_id}.py")

        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(code)

        print(f"[bridge] Sent code as: {dest}")
        print(f"[bridge] Task ID: {task_id}")
        return task_id

    # -- Reading results ------------------------------------------------

    def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Read the result of a completed task.

        Args:
            task_id: Task identifier.

        Returns:
            Result dict, or None if the result isn't ready yet.
        """
        result_path = os.path.join(self.output_dir, f"{task_id}.json")
        if not os.path.exists(result_path):
            return None
        with open(result_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def wait_for(
        self,
        task_id: str,
        timeout: float = 120.0,
        poll_interval: float = 1.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Wait for a task to complete and return its result.

        Args:
            task_id: Task identifier.
            timeout: Maximum seconds to wait.
            poll_interval: Seconds between checks.

        Returns:
            Result dict, or None if timed out.
        """
        t0 = time.time()
        while time.time() - t0 < timeout:
            result = self.get_result(task_id)
            if result is not None:
                self._print_result(result)
                return result
            time.sleep(poll_interval)
        print(f"[bridge] TIMEOUT: task '{task_id}' did not complete within {timeout}s")
        return None

    @staticmethod
    def _print_result(result: dict):
        """Pretty-print a result to the console."""
        status = "OK" if result.get("success") else "FAIL"
        print(f"\n{'=' * 60}")
        print(f"  Task:   {result.get('task_id', '?')}")
        print(f"  Status: {status}  ({result.get('duration_ms', 0)} ms)")
        print(f"{'=' * 60}")
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        if stdout:
            print(f"\n[stdout]\n{stdout}")
        if stderr:
            print(f"\n[stderr]\n{stderr}")
        if result.get("error"):
            print(f"\n[error]\n{result['error']}")
        print()

    # -- Listing --------------------------------------------------------

    def list_tasks(self) -> dict:
        """
        List pending, completed, and done tasks.

        Returns:
            Dict with keys 'pending', 'completed', 'done'.
        """
        pending = sorted(
            [f for f in os.listdir(self.scripts_dir) if f.endswith(".py")]
        )
        completed = sorted(
            [f for f in os.listdir(self.output_dir) if f.endswith(".json")]
        )
        done = sorted(
            [f for f in os.listdir(self.done_dir) if f.endswith(".py")]
        )
        return {"pending": pending, "completed": completed, "done": done}

    def print_list(self):
        """Print task list to console."""
        tasks = self.list_tasks()
        print(f"\n{'=' * 50}")
        print(f"  Pending scripts ({len(tasks['pending'])}):")
        for f in tasks["pending"]:
            print(f"    ⏳ {f}")
        print(f"  Completed results ({len(tasks['completed'])}):")
        for f in tasks["completed"]:
            print(f"    ✅ {f}")
        print(f"  Executed (done/) ({len(tasks['done'])}):")
        for f in tasks["done"]:
            print(f"    📁 {f}")
        print(f"{'=' * 50}\n")

    # -- Cleanup --------------------------------------------------------

    def clean(self, keep_results: int = 0):
        """
        Clean up old scripts and results.

        Args:
            keep_results: Number of recent results to keep (0 = remove all).
        """
        # Clear pending scripts older than 1 hour
        cutoff = time.time() - 3600
        for f in os.listdir(self.scripts_dir):
            if f.endswith(".py"):
                fp = os.path.join(self.scripts_dir, f)
                if os.path.getmtime(fp) < cutoff:
                    os.remove(fp)
                    print(f"  Removed stale: {f}")

        # Clear results
        results = sorted(
            [f for f in os.listdir(self.output_dir) if f.endswith(".json")],
            key=lambda f: os.path.getmtime(os.path.join(self.output_dir, f)),
        )
        to_remove = results[:-keep_results] if keep_results > 0 else results
        for f in to_remove:
            os.remove(os.path.join(self.output_dir, f))
            print(f"  Removed result: {f}")

    # -- Monitor --------------------------------------------------------

    def listen(self):
        """
        Continuous monitor mode: watch for new scripts and print their results.
        Press Ctrl+C to stop.
        """
        print(f"[bridge] Monitoring scripts directory:")
        print(f"[bridge]   {self.scripts_dir}")
        print(f"[bridge] Press Ctrl+C to stop.\n")

        seen = set()
        try:
            # Seed with existing
            for f in os.listdir(self.scripts_dir):
                if f.endswith(".py"):
                    seen.add(f)

            while True:
                # Check for new scripts
                for f in os.listdir(self.scripts_dir):
                    if f.endswith(".py") and f not in seen:
                        seen.add(f)
                        task_id = f.replace(".py", "")
                        print(f"[bridge] New script detected: {task_id}")
                        self.wait_for(task_id)
                        print("[bridge] Ready for next command.\n")

                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[bridge] Monitor stopped.")


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fusion360 Bridge CLI — Send scripts to Fusion 360 and read results.",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- send ---
    send_p = sub.add_parser("send", help="Send a .py script file to Fusion 360")
    send_p.add_argument("script", help="Path to the .py script file")
    send_p.add_argument("--task-id", "-t", default=None, help="Task ID (auto-generated if omitted)")
    send_p.add_argument("--wait", "-w", action="store_true", help="Wait for execution to complete")
    send_p.add_argument("--timeout", type=float, default=120.0, help="Wait timeout in seconds")

    # --- send-code ---
    code_p = sub.add_parser("send-code", help="Send raw Python code to Fusion 360")
    code_p.add_argument("code", help="Python code to execute (use quotes)")
    code_p.add_argument("--task-id", "-t", default=None, help="Task ID")
    code_p.add_argument("--wait", "-w", action="store_true", help="Wait for execution to complete")
    code_p.add_argument("--timeout", type=float, default=120.0, help="Wait timeout in seconds")

    # --- result ---
    res_p = sub.add_parser("result", help="Read a task result")
    res_p.add_argument("task_id", help="Task ID to look up")

    # --- wait ---
    wait_p = sub.add_parser("wait", help="Wait for a task to complete")
    wait_p.add_argument("task_id", help="Task ID to wait for")
    wait_p.add_argument("--timeout", "-t", type=float, default=120.0, help="Timeout in seconds")

    # --- list ---
    sub.add_parser("list", help="List pending, completed, and done tasks")

    # --- listen ---
    sub.add_parser("listen", help="Continuous monitor mode (Ctrl+C to stop)")

    # --- clean ---
    clean_p = sub.add_parser("clean", help="Clean up old scripts and results")
    clean_p.add_argument("--keep", "-k", type=int, default=0, help="Number of recent results to keep")

    args = parser.parse_args()
    client = BridgeClient()

    if args.command == "send":
        task_id = client.send_script(args.script, task_id=args.task_id)
        if args.wait:
            client.wait_for(task_id, timeout=args.timeout)

    elif args.command == "send-code":
        task_id = client.send_code(args.code, task_id=args.task_id)
        if args.wait:
            client.wait_for(task_id, timeout=args.timeout)

    elif args.command == "result":
        result = client.get_result(args.task_id)
        if result is None:
            print(f"[bridge] No result yet for task: {args.task_id}")
            sys.exit(1)
        client._print_result(result)

    elif args.command == "wait":
        result = client.wait_for(args.task_id, timeout=args.timeout)
        if result is None:
            sys.exit(1)

    elif args.command == "list":
        client.print_list()

    elif args.command == "listen":
        client.listen()

    elif args.command == "clean":
        client.clean(keep_results=args.keep)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
