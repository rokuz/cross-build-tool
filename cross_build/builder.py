import asyncio
import base64
import logging
import os
import shutil
import tempfile
import uuid

logger = logging.getLogger(__name__)


class BuildLog:
    """Async log buffer supporting real-time followers."""

    def __init__(self):
        self.lines = []
        self.finished = False
        self._condition = asyncio.Condition()

    async def append(self, line):
        async with self._condition:
            self.lines.append(line)
            self._condition.notify_all()

    async def finish(self):
        async with self._condition:
            self.finished = True
            self._condition.notify_all()

    async def follow(self, start=0):
        """Async generator yielding log lines as they arrive."""
        pos = start
        while True:
            async with self._condition:
                while pos >= len(self.lines) and not self.finished:
                    await self._condition.wait()
                new_lines = self.lines[pos:]
                pos = len(self.lines)
                finished = self.finished
            for line in new_lines:
                yield line
            if finished:
                break


class Builder:
    def __init__(self, repo_path, build_commands):
        self.repo_path = repo_path
        self.build_commands = build_commands
        self.builds = {}
        self.build_logs = {}

    async def start_build(self, patch_data):
        build_id = uuid.uuid4().hex[:8]
        self.builds[build_id] = {
            "id": build_id,
            "status": "running",
            "logs": "",
            "exit_code": None,
        }
        self.build_logs[build_id] = BuildLog()
        asyncio.create_task(self._run_build(build_id, patch_data))
        return build_id

    def get_build_log(self, build_id):
        return self.build_logs.get(build_id)

    async def _run_build(self, build_id, patch_data):
        worktree_path = None
        build_log = self.build_logs[build_id]
        try:
            base_commit = patch_data["base_commit"]
            diff = patch_data.get("diff", "")
            new_files = patch_data.get("new_files", {})
            build_commands = patch_data.get("build_commands") or self.build_commands

            if not build_commands:
                msg = (
                    "No build commands configured. "
                    "Set them in cross_build.json or pass via --cmd."
                )
                self.builds[build_id]["status"] = "error"
                self.builds[build_id]["logs"] = msg
                self.builds[build_id]["exit_code"] = -1
                await build_log.append(msg)
                return

            # Fetch latest commits to ensure base_commit is available
            logger.info("Build %s: fetching latest commits", build_id)
            proc = await asyncio.create_subprocess_exec(
                "git", "fetch", "--all",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            # Verify base commit exists
            proc = await asyncio.create_subprocess_exec(
                "git", "cat-file", "-t", base_commit,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                msg = (
                    f"Base commit {base_commit} not found even after fetch. "
                    f"Please push your commits and try again.\n{stderr.decode()}"
                )
                self.builds[build_id]["status"] = "error"
                self.builds[build_id]["logs"] = msg
                self.builds[build_id]["exit_code"] = -1
                await build_log.append(msg)
                return

            # Create worktree
            worktree_path = os.path.join(
                tempfile.gettempdir(), f"cross_build_{build_id}"
            )
            proc = await asyncio.create_subprocess_exec(
                "git", "worktree", "add", "--detach", worktree_path, base_commit,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                msg = f"Failed to create worktree:\n{stderr.decode()}"
                self.builds[build_id]["status"] = "error"
                self.builds[build_id]["logs"] = msg
                self.builds[build_id]["exit_code"] = -1
                await build_log.append(msg)
                return

            # Apply diff
            if diff:
                proc = await asyncio.create_subprocess_exec(
                    "git", "apply", "--allow-empty", "-",
                    cwd=worktree_path,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate(
                    input=diff.encode(errors="surrogateescape")
                )
                if proc.returncode != 0:
                    msg = f"Failed to apply patch:\n{stderr.decode()}"
                    self.builds[build_id]["status"] = "error"
                    self.builds[build_id]["logs"] = msg
                    self.builds[build_id]["exit_code"] = -1
                    await build_log.append(msg)
                    return

            # Write new files
            for fpath, content_b64 in new_files.items():
                full_path = os.path.join(worktree_path, fpath)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "wb") as f:
                    f.write(base64.b64decode(content_b64))

            # If python3 is not usable, fall back to python
            if any("python3" in cmd for cmd in build_commands):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "python3", "--version",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()
                    python3_works = proc.returncode == 0
                except FileNotFoundError:
                    python3_works = False
                if not python3_works:
                    logger.info("Build %s: python3 not usable, falling back to python", build_id)
                    build_commands = [cmd.replace("python3", "python") for cmd in build_commands]

            # Run build commands
            logs = []
            final_exit_code = 0
            for cmd in build_commands:
                header = f"$ {cmd}"
                logs.append(header)
                await build_log.append(header)
                logger.info("Build %s: running %r", build_id, cmd)
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=worktree_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env={**os.environ, "CROSS_BUILD": "1"},
                )
                output_lines = []
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    text = line.decode(errors="replace").rstrip("\n\r")
                    output_lines.append(text)
                    await build_log.append(text)
                await proc.wait()
                logs.append("\n".join(output_lines))
                if proc.returncode != 0:
                    msg = f"Command failed with exit code {proc.returncode}"
                    logs.append(msg)
                    await build_log.append(msg)
                    final_exit_code = proc.returncode
                    break

            self.builds[build_id]["status"] = (
                "success" if final_exit_code == 0 else "failed"
            )
            self.builds[build_id]["logs"] = "\n".join(logs)
            self.builds[build_id]["exit_code"] = final_exit_code

        except Exception as e:
            logger.exception("Build %s error", build_id)
            msg = f"Build error: {e}"
            self.builds[build_id]["status"] = "error"
            self.builds[build_id]["logs"] = msg
            self.builds[build_id]["exit_code"] = -1
            await build_log.append(msg)
        finally:
            await build_log.finish()
            if worktree_path and os.path.exists(worktree_path):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "git", "worktree", "remove", "--force", worktree_path,
                        cwd=self.repo_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()
                except Exception:
                    shutil.rmtree(worktree_path, ignore_errors=True)

    def get_build(self, build_id):
        return self.builds.get(build_id)

    def list_builds(self):
        return list(self.builds.values())
