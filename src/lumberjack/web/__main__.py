from __future__ import annotations

import argparse


def main() -> None:
    """Launch the Lumberjack web server via uvicorn."""
    parser = argparse.ArgumentParser(description="Launch the Lumberjack web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
