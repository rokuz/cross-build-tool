import argparse
import asyncio
import json
import logging
import os
import platform
import socket
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="cross_build",
        description="Cross-platform build service",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    subparsers = parser.add_subparsers(dest="command")

    # serve
    serve_p = subparsers.add_parser("serve", help="Run the build service")
    serve_p.add_argument("--port", type=int, default=None)
    serve_p.add_argument("--repo", default=os.getcwd())
    serve_p.add_argument("--config", default=None)

    # discover
    disc_p = subparsers.add_parser("discover", help="Discover peers on the network")
    disc_p.add_argument("--timeout", type=int, default=5)

    # build
    build_p = subparsers.add_parser("build", help="Send changes to peers for building")
    build_p.add_argument("--repo", default=os.getcwd())
    build_p.add_argument(
        "--to", dest="targets", default=None,
        help="Comma-separated platforms: linux,windows,darwin",
    )
    build_p.add_argument("--timeout", type=int, default=300)
    build_p.add_argument(
        "--cmd", action="append", dest="commands",
        help="Build command (repeatable)",
    )

    # result
    res_p = subparsers.add_parser("result", help="Get build result from a peer")
    res_p.add_argument("build_id")
    res_p.add_argument("--host", required=True)
    res_p.add_argument("--port", type=int, default=5200)

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.command == "serve":
        try:
            asyncio.run(_run_service(args))
        except KeyboardInterrupt:
            pass
    elif args.command == "discover":
        asyncio.run(_run_discover(args))
    elif args.command == "build":
        asyncio.run(_run_build(args))
    elif args.command == "result":
        asyncio.run(_run_result(args))
    else:
        parser.print_help()
        sys.exit(1)


async def _run_service(args):
    from .config import load_config
    from .discovery import Discovery
    from .server import Server
    from .builder import Builder

    config = load_config(args.config, args.repo)
    port = args.port or config.get("port", 5200)
    build_commands_cfg = config.get("build_commands", {})

    plat = platform.system().lower()
    if isinstance(build_commands_cfg, dict):
        cmds = build_commands_cfg.get(plat, build_commands_cfg.get("default", []))
    else:
        cmds = build_commands_cfg

    hostname = socket.gethostname()

    discovery = Discovery(hostname, port, args.repo)
    builder = Builder(args.repo, cmds)
    server = Server(discovery, builder, port=port)

    await discovery.start()
    await server.start()

    print(f"Cross-build service running on {hostname} ({plat})")
    print(f"  HTTP port : {port}")
    print(f"  Repo      : {args.repo}")
    print(f"  Commands  : {cmds}")
    print("Press Ctrl+C to stop.")

    try:
        # Wait forever; on Unix we use signal handlers, on Windows
        # asyncio.run() cancels the task on Ctrl+C.
        stop = asyncio.Event()
        try:
            loop = asyncio.get_running_loop()
            import signal
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, AttributeError):
            pass  # Windows
        await stop.wait()
    except asyncio.CancelledError:
        pass
    finally:
        await server.stop()
        await discovery.stop()
        print("\nService stopped.")


async def _run_discover(args):
    from .client import discover_peers

    print(f"Listening for peers ({args.timeout}s)...", file=sys.stderr)
    peers = await discover_peers(timeout=args.timeout)
    if not peers:
        print("No peers found.", file=sys.stderr)
        sys.exit(1)

    # Clean output for JSON consumers
    clean = []
    for p in peers:
        clean.append({
            "hostname": p.get("hostname"),
            "platform": p.get("platform"),
            "ip": p.get("ip") or p.get("addr"),
            "port": p.get("port"),
        })
    print(json.dumps(clean, indent=2))


async def _run_build(args):
    from .client import build_on_peers

    def on_output(plat, hostname, line):
        print(f"[{plat}/{hostname}] {line}", file=sys.stderr, flush=True)

    results = await build_on_peers(
        repo_path=args.repo,
        targets=args.targets,
        build_commands=args.commands,
        timeout=args.timeout,
        on_output=on_output,
    )
    print(json.dumps(results, indent=2))

    # Print coverage summary to stderr for human readers
    coverage = results.get("coverage")
    if coverage:
        current = coverage["current_platform"]
        covered = ", ".join(coverage["covered"])
        print(f"\nCurrent platform: {current}", file=sys.stderr)
        print(f"Covered platforms: {covered}", file=sys.stderr)
        if coverage["missing"]:
            missing = ", ".join(coverage["missing"])
            print(
                f"WARNING: Missing platforms: {missing} "
                "(no service discovered for these)",
                file=sys.stderr,
            )
        else:
            print("All platforms covered (linux, windows, darwin)", file=sys.stderr)

    # Exit with non-zero if any build failed or if there's an error
    if results.get("error"):
        sys.exit(1)
    for r in results.get("results", []):
        if r.get("status") not in ("success",):
            sys.exit(1)


async def _run_result(args):
    import aiohttp

    url = f"http://{args.host}:{args.port}/api/build/{args.build_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            result = await resp.json()
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
