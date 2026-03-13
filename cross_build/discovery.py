import asyncio
import ipaddress
import json
import logging
import platform
import socket
import time

logger = logging.getLogger(__name__)

DISCOVERY_PORT = 5199
ANNOUNCE_INTERVAL = 3
PEER_TIMEOUT = 15


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_broadcast_addresses():
    """Compute subnet-directed broadcast addresses.

    On Windows, sending to 255.255.255.255 (limited broadcast) is unreliable
    when multiple network adapters are present (Hyper-V, Docker, VPN, etc.).
    Subnet-directed broadcasts (e.g. 192.168.1.255) are routed correctly.
    """
    addrs = set()
    try:
        local_ip = get_local_ip()
        if local_ip != "127.0.0.1":
            network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
            addrs.add(str(network.broadcast_address))
    except Exception:
        pass
    # Always include limited broadcast as fallback (works on Linux/macOS)
    addrs.add("255.255.255.255")
    return list(addrs)


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, local_id, peers):
        self.local_id = local_id
        self.peers = peers
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        try:
            msg = json.loads(data.decode())
            if msg.get("service") != "cross_build":
                return
            if msg.get("id") == self.local_id:
                return
            key = f"{msg['hostname']}_{msg['platform']}"
            self.peers[key] = {**msg, "last_seen": time.time(), "addr": addr[0]}
        except (json.JSONDecodeError, KeyError):
            pass


class Discovery:
    def __init__(self, hostname, http_port, repo_path):
        self.peers = {}
        self._id = f"{hostname}_{id(self)}_{time.time()}"
        self.service_info = {
            "service": "cross_build",
            "version": 1,
            "id": self._id,
            "hostname": hostname,
            "platform": platform.system().lower(),
            "port": http_port,
            "repo_path": repo_path,
        }
        self._transport = None
        self._announce_task = None

    async def start(self):
        loop = asyncio.get_running_loop()

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

        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(self._id, self.peers), sock=sock
        )
        self._announce_task = asyncio.create_task(self._announce_loop())
        logger.info("Discovery started on port %d", DISCOVERY_PORT)

    async def _announce_loop(self):
        while True:
            try:
                msg = json.dumps(
                    {**self.service_info, "ip": get_local_ip()}
                ).encode()
                for addr in _get_broadcast_addresses():
                    try:
                        self._transport.sendto(msg, (addr, DISCOVERY_PORT))
                    except OSError:
                        pass
            except Exception as e:
                logger.warning("Discovery announce failed: %s", e)

            now = time.time()
            stale = [
                k for k, v in self.peers.items()
                if now - v["last_seen"] > PEER_TIMEOUT
            ]
            for k in stale:
                del self.peers[k]

            await asyncio.sleep(ANNOUNCE_INTERVAL)

    async def stop(self):
        if self._announce_task:
            self._announce_task.cancel()
            try:
                await self._announce_task
            except asyncio.CancelledError:
                pass
        if self._transport:
            self._transport.close()

    def get_peers(self):
        return list(self.peers.values())
