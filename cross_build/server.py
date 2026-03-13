import json
import logging
from aiohttp import web

logger = logging.getLogger(__name__)


class Server:
    def __init__(self, discovery, builder, host="0.0.0.0", port=5200):
        self.discovery = discovery
        self.builder = builder
        self.host = host
        self.port = port
        self.app = web.Application(client_max_size=50 * 1024 * 1024)  # 50MB
        self._setup_routes()
        self._runner = None

    def _setup_routes(self):
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/peers", self.handle_peers)
        self.app.router.add_post("/api/build", self.handle_build)
        self.app.router.add_get("/api/build/{build_id}", self.handle_build_status)
        self.app.router.add_get("/api/build/{build_id}/stream", self.handle_build_stream)
        self.app.router.add_get("/api/builds", self.handle_builds)

    async def handle_status(self, request):
        return web.json_response(self.discovery.service_info)

    async def handle_peers(self, request):
        peers = self.discovery.get_peers()
        clean = []
        for p in peers:
            clean.append({k: v for k, v in p.items() if k not in ("last_seen",)})
        return web.json_response(clean)

    async def handle_build(self, request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        if "base_commit" not in data:
            return web.json_response(
                {"error": "Missing base_commit"}, status=400
            )

        build_id = await self.builder.start_build(data)
        logger.info("Build %s started", build_id)
        return web.json_response({"build_id": build_id, "status": "running"})

    async def handle_build_status(self, request):
        build_id = request.match_info["build_id"]
        build = self.builder.get_build(build_id)
        if not build:
            return web.json_response({"error": "Build not found"}, status=404)
        return web.json_response(build)

    async def handle_build_stream(self, request):
        build_id = request.match_info["build_id"]
        build_log = self.builder.get_build_log(build_id)
        if not build_log:
            return web.json_response({"error": "Build not found"}, status=404)

        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request)

        try:
            async for line in build_log.follow():
                data = json.dumps({"line": line})
                await response.write(f"data: {data}\n\n".encode())

            # Send final build result
            build = self.builder.get_build(build_id)
            data = json.dumps(build)
            await response.write(f"event: done\ndata: {data}\n\n".encode())
        except ConnectionResetError:
            logger.debug("Stream client disconnected for build %s", build_id)

        await response.write_eof()
        return response

    async def handle_builds(self, request):
        return web.json_response(self.builder.list_builds())

    async def start(self):
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info("HTTP server started on %s:%d", self.host, self.port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
