import asyncio
import json
import logging
import platform
import socket

import aiohttp

from .patcher import create_patch

logger = logging.getLogger(__name__)

DISCOVERY_PORT = 5199
ALL_PLATFORMS = {"linux", "windows", "darwin"}


class _ListenerProtocol(asyncio.DatagramProtocol):
    def __init__(self, local_hostname, peers):
        self.local_hostname = local_hostname
        self.peers = peers

    def connection_made(self, transport):
        pass

    def datagram_received(self, data, addr):
        try:
            msg = json.loads(data.decode())
            if msg.get("service") != "cross_build":
                return
            if msg.get("hostname") == self.local_hostname:
                return
            key = f"{msg['hostname']}_{msg['platform']}"
            msg["addr"] = addr[0]
            self.peers[key] = msg
        except (json.JSONDecodeError, KeyError):
            pass


async def discover_peers(timeout=5):
    """Listen for discovery broadcasts and return found peers."""
    peers = {}
    local_hostname = socket.gethostname()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    sock.bind(("", DISCOVERY_PORT))
    sock.setblocking(False)

    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _ListenerProtocol(local_hostname, peers), sock=sock
    )

    await asyncio.sleep(timeout)
    transport.close()

    return list(peers.values())


async def send_build(peer, patch_data, timeout=300, on_output=None):
    """Send a build request to a peer and stream/poll until completion.

    If on_output callback is provided, streams build output in real-time
    via SSE. Falls back to polling if streaming is unavailable.
    """
    ip = peer.get("ip") or peer.get("addr")
    port = peer["port"]
    base_url = f"http://{ip}:{port}"

    hostname = peer.get("hostname", ip)
    logger.info("Sending build request to %s (%s:%s)", hostname, ip, port)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{base_url}/api/build", json=patch_data, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            result = await resp.json()
            if "error" in result:
                logger.error("Build request to %s failed: %s", hostname, result["error"])
                return {
                    "status": "error",
                    "logs": result["error"],
                    "exit_code": -1,
                }
            build_id = result["build_id"]
            logger.info("Build accepted by %s, build_id=%s", hostname, build_id)

        # Try SSE streaming if callback provided
        if on_output:
            result = await _stream_build(
                session, base_url, build_id, hostname, timeout, on_output
            )
            if result is not None:
                return result
            # Fall through to polling if streaming failed

        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(2)
            elapsed += 2
            try:
                async with session.get(
                    f"{base_url}/api/build/{build_id}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    result = await resp.json()
                    if result.get("status") in ("success", "failed", "error"):
                        logger.info(
                            "Build result from %s: status=%s exit_code=%s",
                            hostname, result.get("status"), result.get("exit_code"),
                        )
                        return result
            except Exception as e:
                logger.warning("Polling %s failed: %s", hostname, e)

    logger.warning("Build on %s timed out after %ss", hostname, timeout)
    return {"status": "timeout", "logs": "Build timed out", "exit_code": -1}


async def _stream_build(session, base_url, build_id, hostname, timeout, on_output):
    """Connect to SSE stream endpoint and relay output lines. Returns build
    result dict on success, or None if streaming is unavailable."""
    try:
        async with session.get(
            f"{base_url}/api/build/{build_id}/stream",
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                logger.debug("Stream endpoint returned %s, falling back to polling", resp.status)
                return None

            current_event = None
            async for raw_line in resp.content:
                line_str = raw_line.decode(errors="replace").rstrip("\n\r")
                if not line_str:
                    current_event = None
                    continue
                if line_str.startswith("event: "):
                    current_event = line_str[7:]
                elif line_str.startswith("data: "):
                    data = json.loads(line_str[6:])
                    if current_event == "done":
                        logger.info(
                            "Build result from %s: status=%s exit_code=%s",
                            hostname, data.get("status"), data.get("exit_code"),
                        )
                        return data
                    elif "line" in data:
                        on_output(data["line"])
    except Exception as e:
        logger.warning("Streaming from %s failed: %s, falling back to polling", hostname, e)
        return None

    return None


def get_current_platform():
    return platform.system().lower()


async def build_on_peers(repo_path, targets=None, build_commands=None, timeout=300, on_output=None):
    """Create patch, discover peers, send builds, collect results.

    Automatically detects the current platform and targets only OTHER platforms.
    Reports platform coverage (which of linux/windows/darwin are covered).

    If on_output(platform, hostname, line) is provided, build output is
    streamed in real-time.
    """
    current_platform = get_current_platform()
    peers = await discover_peers()

    # Exclude peers running on the same platform as us
    peers = [p for p in peers if p["platform"] != current_platform]

    if not peers:
        return {
            "error": (
                f"No peers on other platforms discovered (current: {current_platform}). "
                "Is the service running on other machines?"
            ),
            "current_platform": current_platform,
            "coverage": _coverage_report(current_platform, []),
            "results": [],
        }

    if targets:
        target_list = [t.strip().lower() for t in targets.split(",")]
        # Remove current platform from explicit targets -- we're already on it
        target_list = [t for t in target_list if t != current_platform]
        peers = [p for p in peers if p["platform"] in target_list]

    if not peers:
        return {
            "error": f"No peers matching platforms: {targets}",
            "current_platform": current_platform,
            "coverage": _coverage_report(current_platform, []),
            "results": [],
        }

    patch_data = await create_patch(repo_path)
    if build_commands:
        patch_data["build_commands"] = build_commands

    def _peer_callback(peer):
        def cb(line):
            on_output(peer["platform"], peer["hostname"], line)
        return cb

    tasks = [
        send_build(peer, patch_data, timeout,
                   on_output=_peer_callback(peer) if on_output else None)
        for peer in peers
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    combined = []
    for peer, result in zip(peers, results):
        if isinstance(result, Exception):
            combined.append({
                "platform": peer["platform"],
                "hostname": peer["hostname"],
                "status": "error",
                "logs": str(result),
                "exit_code": -1,
            })
        else:
            combined.append({
                "platform": peer["platform"],
                "hostname": peer["hostname"],
                **result,
            })

    return {
        "current_platform": current_platform,
        "coverage": _coverage_report(current_platform, combined),
        "results": combined,
    }


def _coverage_report(current_platform, results):
    """Report which platforms are covered and which are missing."""
    remote_platforms = {r["platform"] for r in results}
    covered = remote_platforms | {current_platform}
    missing = ALL_PLATFORMS - covered
    return {
        "current_platform": current_platform,
        "remote_platforms": sorted(remote_platforms),
        "covered": sorted(covered),
        "missing": sorted(missing),
        "all_covered": len(missing) == 0,
    }
