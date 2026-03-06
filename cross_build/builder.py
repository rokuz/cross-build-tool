import asyncio
import base64
import logging
import os
import shutil
import tempfile
import uuid

logger = logging.getLogger(__name__)


class Builder:
    def __init__(self, repo_path, build_commands):
        self.repo_path = repo_path
        self.build_commands = build_commands
        self.builds = {}

    async def start_build(self, patch_data):
        build_id = uuid.uuid4().hex[:8]
        self.builds[build_id] = {
            "id": build_id,
            "status": "running",
            "logs": "",
            "exit_code": None,
        }
        asyncio.create_task(self._run_build(build_id, patch_data))
        return build_id

    async def _run_build(self, build_id, patch_data):
        worktree_path = None
        try:
            base_commit = patch_data["base_commit"]
            diff = patch_data.get("diff", "")
            new_files = patch_data.get("new_files", {})
            build_commands = patch_data.get("build_commands") or self.build_commands

            if not build_commands:
                self.builds[build_id]["status"] = "error"
                self.builds[build_id]["logs"] = (
                    "No build commands configured. "
                    "Set them in cross_build.json or pass via --cmd."
                )
                self.builds[build_id]["exit_code"] = -1
                return

            # Verify base commit exists
            proc = await asyncio.create_subprocess_exec(
                "git", "cat-file", "-t", base_commit,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                self.builds[build_id]["status"] = "error"
                self.builds[build_id]["logs"] = (
                    f"Base commit {base_commit} not found. "
                    f"Please fetch/pull the repository.\n{stderr.decode()}"
                )
                self.builds[build_id]["exit_code"] = -1
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
                self.builds[build_id]["status"] = "error"
                self.builds[build_id]["logs"] = (
                    f"Failed to create worktree:\n{stderr.decode()}"
                )
                self.builds[build_id]["exit_code"] = -1
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
                    self.builds[build_id]["status"] = "error"
                    self.builds[build_id]["logs"] = (
                        f"Failed to apply patch:\n{stderr.decode()}"
                    )
                    self.builds[build_id]["exit_code"] = -1
                    return

            # Write new files
            for fpath, content_b64 in new_files.items():
                full_path = os.path.join(worktree_path, fpath)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "wb") as f:
                    f.write(base64.b64decode(content_b64))

            # Run build commands
            logs = []
            final_exit_code = 0
            for cmd in build_commands:
                logs.append(f"$ {cmd}")
                logger.info("Build %s: running %r", build_id, cmd)
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=worktree_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env={**os.environ, "CROSS_BUILD": "1"},
                )
                stdout, _ = await proc.communicate()
                output = stdout.decode(errors="replace")
                logs.append(output)
                if proc.returncode != 0:
                    logs.append(
                        f"Command failed with exit code {proc.returncode}"
                    )
                    final_exit_code = proc.returncode
                    break

            self.builds[build_id]["status"] = (
                "success" if final_exit_code == 0 else "failed"
            )
            self.builds[build_id]["logs"] = "\n".join(logs)
            self.builds[build_id]["exit_code"] = final_exit_code

        except Exception as e:
            logger.exception("Build %s error", build_id)
            self.builds[build_id]["status"] = "error"
            self.builds[build_id]["logs"] = f"Build error: {e}"
            self.builds[build_id]["exit_code"] = -1
        finally:
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
