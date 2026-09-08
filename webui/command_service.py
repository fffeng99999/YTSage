"""
Custom yt-dlp command runner for YTSage Web UI.

Mirrors official CommandWorker (ytsage_dialogs_custom.py L45-110):
  args = command.split(); [yt-dlp] + args + [-P path] + [url]
Output streams to the WebSocket event bus as command_output events.
"""

import asyncio
import logging
import shlex
import sys
import uuid
from typing import Any, Dict, Optional

from .download_manager import decode_output
from .event_bus import bus
from .official_bridge import SUBPROCESS_CREATIONFLAGS
from .yt_dlp_finder import get_yt_dlp_path

logger = logging.getLogger("ytsage.webui")


class CommandService:
    def __init__(self) -> None:
        self._procs: Dict[str, asyncio.subprocess.Process] = {}

    async def run(self, command: str, url: Optional[str] = None, path: Optional[str] = None) -> str:
        exec_id = uuid.uuid4().hex[:12]
        # Official uses .split(); prefer shlex when it parses cleanly so
        # quoted templates keep working, fall back to naive split otherwise.
        try:
            args = shlex.split(command)
        except ValueError:
            args = command.split()

        cmd = [get_yt_dlp_path()] + args
        if path:
            cmd.extend(["-P", path])
        if url:
            cmd.append(url)

        kwargs: Dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                SUBPROCESS_CREATIONFLAGS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True  # own process group for killpg

        bus.publish({"type": "command_output", "exec_id": exec_id, "line": " ".join(cmd)})
        bus.publish({"type": "command_output", "exec_id": exec_id, "line": "=" * 50})

        try:
            proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
        except Exception as e:
            bus.publish({"type": "command_output", "exec_id": exec_id, "line": f"ERROR: {e}"})
            bus.publish({"type": "command_finished", "exec_id": exec_id, "success": False, "exit_code": -1})
            return exec_id

        self._procs[exec_id] = proc

        async def _pump() -> None:
            try:
                assert proc.stdout is not None
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    text = decode_output(line).rstrip()
                    if text:
                        bus.publish({"type": "command_output", "exec_id": exec_id, "line": text})
                rc = await proc.wait()
            except Exception as e:
                logger.error(f"[WebUI] command pump error: {e}")
                rc = -1
            finally:
                self._procs.pop(exec_id, None)
                bus.publish({"type": "command_output", "exec_id": exec_id, "line": "=" * 50})
                bus.publish({
                    "type": "command_finished",
                    "exec_id": exec_id,
                    "success": rc == 0,
                    "exit_code": rc,
                })

        asyncio.create_task(_pump())
        return exec_id

    async def cancel(self, exec_id: str) -> bool:
        proc = self._procs.get(exec_id)
        if not proc or proc.returncode is not None:
            return False
        await _kill_tree_async(proc)
        return True

    def active_count(self) -> int:
        return len(self._procs)


async def _kill_tree_async(proc: asyncio.subprocess.Process) -> None:
    """Kill yt-dlp and any ffmpeg children. POSIX: SIGTERM the group, then
    escalate to SIGKILL after a grace period (was SIGTERM-only before)."""
    pid = proc.pid
    try:
        if sys.platform == "win32":
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=SUBPROCESS_CREATIONFLAGS,
            )
            try:
                await asyncio.wait_for(killer.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
        else:
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pgid = None
            if pgid is not None:
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except (asyncio.TimeoutError, Exception):
                    pass
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
    except Exception as e:
        logger.warning(f"[WebUI] kill tree failed: {e}")
        try:
            proc.kill()
        except Exception:
            pass


command_service = CommandService()
