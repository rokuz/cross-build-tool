import asyncio
import base64
import os


async def create_patch(repo_path):
    """Create a patch bundle from the current git working state.

    Returns a dict with:
      - base_commit: HEAD commit hash
      - diff: output of `git diff --binary HEAD`
      - new_files: {relative_path: base64_content} for untracked files
    """
    # Base commit
    proc = await asyncio.create_subprocess_exec(
        "git", "rev-parse", "HEAD",
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git rev-parse HEAD failed: {stderr.decode().strip()}")
    base_commit = stdout.decode().strip()

    # Diff (staged + unstaged, including binary)
    proc = await asyncio.create_subprocess_exec(
        "git", "diff", "--binary", "HEAD",
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    diff = stdout.decode(errors="surrogateescape")

    # New untracked files
    proc = await asyncio.create_subprocess_exec(
        "git", "ls-files", "--others", "--exclude-standard",
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    new_file_paths = [f for f in stdout.decode().strip().split("\n") if f]

    new_files = {}
    for fpath in new_file_paths:
        full_path = os.path.join(repo_path, fpath)
        if os.path.isfile(full_path):
            with open(full_path, "rb") as f:
                new_files[fpath] = base64.b64encode(f.read()).decode()

    return {
        "base_commit": base_commit,
        "diff": diff,
        "new_files": new_files,
    }
